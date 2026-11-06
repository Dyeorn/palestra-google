"""Simulador de tráfego: roda o agente DE VERDADE (ADK Runner) contra clientes sintéticos.

  uv run python -m simulator.run --reset                 # 30 dias de histórico
  uv run python -m simulator.run --live                  # tráfego contínuo (usar com o dashboard)
  uv run python -m simulator.run --live --chaos          # já começa com caos ligado
  uv run python -m simulator.run --modelo real           # Gemini de verdade (precisa de chave)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import random
import sqlite3
import time
import uuid
from datetime import datetime, timedelta

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent.agent import build_app
from agent.fake_llm import FakeSalesLlm
from common.config import DB_PATH, has_api_key, now_local
from plugin import simctx
from plugin.telemetry_plugin import TelemetryPlugin
from simulator.chaos import ChaosPlugin
from simulator.customers import PERSONAS, Customer, Obs

# peso de conversas por hora do dia (picos ~12-13h e ~19-21h)
HOUR_W = [0.2, 0.1, 0.05, 0.05, 0.05, 0.1, 0.3, 0.6, 1.0, 1.6, 1.8, 1.5,
          2.2, 2.0, 1.4, 1.2, 1.3, 1.5, 1.9, 2.6, 2.8, 2.2, 1.2, 0.5]
MAX_TURNS = 10
for _n in ("google_adk", "google.adk", "google_genai"):  # erros simulados poluem o terminal
    logging.getLogger(_n).setLevel(logging.CRITICAL)


def conditions(start: datetime, today: datetime, days: int) -> dict:
    """Roteiro do histórico: picos de horário, 2 incidentes e prompt crescendo."""
    load = HOUR_W[start.hour] / max(HOUR_W)
    d = (today.date() - start.date()).days  # 0 = hoje
    out = dict(load=load, latency_mult=1.0, tool_fail_extra={},
               prompt_extra_tokens=int(max(0, days - d) * 20))
    if d == 12 and 11 <= start.hour < 19:   # incidente A: estoque instável + modelo muito lento
        out["tool_fail_extra"] = {"consultar_estoque": 0.45}
        out["latency_mult"] = 4.0
    if d == 3:                              # incidente C: dia de provedor lento
        out["latency_mult"] = 2.6
    if d == 5 and 18 <= start.hour < 22:    # incidente B: checkout/cupom falhando
        out["tool_fail_extra"] = {"criar_pedido": 0.35, "aplicar_cupom": 0.25}
    return out


def build_timeline(n: int, days: int, rng: random.Random, now: datetime) -> list[datetime]:
    day_w = []
    for d in range(days, 0, -1):  # d dias atrás (mais antigo primeiro)
        day = (now - timedelta(days=d)).date()
        w = 0.75 if day.weekday() >= 5 else 1.0
        w *= 1 + 0.5 * (1 - d / days)       # volume cresce ao longo do mês
        day_w.append((day, w))
    out = []
    while len(out) < n:
        day = rng.choices([d for d, _ in day_w], [w for _, w in day_w])[0]
        hour = rng.choices(range(24), HOUR_W)[0]
        t = datetime(day.year, day.month, day.day, hour, rng.randint(0, 59), rng.randint(0, 59))
        if t < now - timedelta(minutes=2):
            out.append(t)
    return sorted(out)


def read_chaos_flag() -> bool:
    try:
        con = sqlite3.connect(str(DB_PATH), timeout=5)
        row = con.execute("SELECT valor FROM controle WHERE chave='caos'").fetchone()
        con.close()
        return bool(row and row[0] == "1")
    except Exception:
        return False


async def run_turn(runner, app_name, uid, sid, text, ctx: simctx.SimContext) -> Obs:
    ctx.turn_ms = 0.0
    obs = Obs()
    try:
        async for ev in runner.run_async(
                user_id=uid, session_id=sid,
                new_message=types.Content(role="user", parts=[types.Part(text=text)]),
                run_config=RunConfig(streaming_mode=StreamingMode.SSE)):
            if ev.partial:
                continue
            for fr in ev.get_function_responses():
                _fold(obs, fr.name, fr.response or {})
            if ev.is_final_response() and ev.content and ev.content.parts:
                obs.text = " ".join(p.text for p in ev.content.parts if p.text)
    except Exception:
        obs.system_error = True
    obs.latency_ms = ctx.turn_ms
    return obs


def _fold(o: Obs, name: str, r: dict) -> None:
    if r.get("status") == "error":
        o.tool_error = True
        return
    if r.get("produtos") is not None:
        o.produtos = r["produtos"]
    if name == "consultar_estoque":
        o.em_estoque, o.prazo_dias, o.preco = r.get("em_estoque"), r.get("prazo_dias"), r.get("preco")
    elif name == "aplicar_cupom":
        o.cupom_valido, o.desconto_pct = r.get("valido"), r.get("desconto_pct", 0)
    elif name == "criar_pedido":
        o.pedido = bool(r.get("pedido_id"))
        o.sem_estoque_pedido = r.get("motivo") == "sem_estoque"
    elif name == "registrar_reclamacao":
        o.reclamacao = True


async def run_conversation(runner, app, plugin, ctx: simctx.SimContext, persona: str, seed: int) -> None:
    simctx.set_current(ctx)  # cada task tem seu próprio contexto
    rng = random.Random(seed)
    customer = Customer(persona, rng)
    uid, sid = f"cliente-{rng.randint(1000, 9999)}", f"conv-{uuid.UUID(int=rng.getrandbits(128)).hex[:12]}"
    await runner.session_service.create_session(app_name=app.name, user_id=uid, session_id=sid,
                                                state={"perfil": persona})
    msg = customer.opening()
    for _ in range(MAX_TURNS):
        obs = await run_turn(runner, app.name, uid, sid, msg, ctx)
        ctx.offset_ms += rng.uniform(8, 45) * 1000 * ctx.think_scale
        step = customer.react(obs)
        if step.message is None:
            break
        msg = step.message
        if step.end:
            await run_turn(runner, app.name, uid, sid, msg, ctx)
            break
    plugin.finalize_conversation(sid)


def make_runner(offline: bool, db_path):
    plugin = TelemetryPlugin(db_path=db_path)
    plugins = [plugin] + ([] if offline else [ChaosPlugin()])
    app = build_app(plugins, FakeSalesLlm() if offline else None)
    return Runner(app=app, session_service=InMemorySessionService()), app, plugin


async def main_async(a) -> None:
    offline = a.modelo == "offline" or (a.modelo == "auto" and not has_api_key())
    if not offline and not has_api_key():
        raise SystemExit("--modelo real exige GEMINI_API_KEY (ou GOOGLE_API_KEY) no .env")
    if a.reset:
        for suf in ("", "-wal", "-shm"):
            DB_PATH.with_name(DB_PATH.name + suf).unlink(missing_ok=True)
    runner, app, plugin = make_runner(offline, DB_PATH)
    rng = random.Random(a.seed)
    names = list(PERSONAS)
    weights = [PERSONAS[n]["w"] for n in names]
    print(f"modo: {'OFFLINE (LLM scriptado)' if offline else 'REAL (Gemini)'} | banco: {DB_PATH}")
    sem = asyncio.Semaphore(a.concorrencia or (24 if offline else 4))

    async def guarded(coro):
        async with sem:
            await coro

    if not a.live:
        now = now_local()
        times = build_timeline(a.conversas, a.dias, rng, now)
        tasks = []
        for i, start in enumerate(times):
            cond = conditions(start, now, a.dias)
            ctx = simctx.SimContext(start=start, rng=random.Random(a.seed * 100003 + i),
                                    simulate_latency=offline, chaos=a.chaos, **cond)
            persona = rng.choices(names, weights)[0]
            tasks.append(asyncio.create_task(
                guarded(run_conversation(runner, app, plugin, ctx, persona, a.seed * 7919 + i))))
        t0 = time.time()
        for n, t in enumerate(asyncio.as_completed(tasks), 1):
            await t
            if n % 25 == 0 or n == len(tasks):
                print(f"  {n}/{len(tasks)} conversas ({time.time() - t0:.0f}s)")
    else:
        print(f"ao vivo: 1 conversa a cada ~{a.intervalo}s. Ctrl+C para parar. "
              f"Caos: {'LIGADO (--chaos)' if a.chaos else 'controlado pelo dashboard'}")
        minutos = a.aquecer if offline else 0   # no modo real não gasta chamadas de API só para aquecer
        if minutos > 0:
            # "Aquece": gera os últimos N minutos na mesma cadência do ao vivo, para a linha e os KPIs
            # já abrirem preenchidos (sem precisar ligar o --live uns 6 minutos antes).
            n = int(minutos * 60 / a.intervalo)
            print(f"aquecendo: {n} conversas dos últimos {minutos} min (a linha ao vivo já abre preenchida)...")
            agora, aquece = now_local(), []
            for k in range(n):
                inicio = agora - timedelta(minutes=minutos) + timedelta(seconds=k * minutos * 60 / n)
                c = simctx.SimContext(start=inicio, rng=random.Random(random.random()), simulate_latency=offline,
                                      chaos=a.chaos, think_scale=0.08, load=0.5, prompt_extra_tokens=420)
                aquece.append(asyncio.create_task(guarded(run_conversation(
                    runner, app, plugin, c, rng.choices(names, weights)[0], random.getrandbits(32)))))
            await asyncio.gather(*aquece)
            print("aquecimento pronto; seguindo em tempo real.")
        i, running = 0, set()
        try:
            while True:
                chaos = a.chaos or read_chaos_flag()
                ctx = simctx.SimContext(start=now_local(), rng=random.Random(random.random()),
                                        simulate_latency=offline, chaos=chaos, think_scale=0.08,
                                        load=0.5, prompt_extra_tokens=420)
                persona = rng.choices(names, weights)[0]
                t = asyncio.create_task(guarded(run_conversation(runner, app, plugin, ctx, persona,
                                                                 random.getrandbits(32))))
                running.add(t)
                t.add_done_callback(running.discard)
                i += 1
                if i % 20 == 0:
                    print(f"  {i} conversas | caos={'ON' if chaos else 'off'}")
                await asyncio.sleep(rng.uniform(0.5, 1.5) * a.intervalo)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await asyncio.gather(*running, return_exceptions=True)
    plugin.flush()
    await runner.close()
    print("pronto.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--conversas", type=int, default=400)
    ap.add_argument("--dias", type=int, default=30)
    ap.add_argument("--live", action="store_true", help="tráfego contínuo em tempo real")
    ap.add_argument("--chaos", action="store_true", help="injeta erro de ferramenta e lentidão")
    ap.add_argument("--modelo", choices=["auto", "offline", "real"], default="auto")
    ap.add_argument("--offline", dest="modelo", action="store_const", const="offline")
    ap.add_argument("--reset", action="store_true", help="apaga o banco antes")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--concorrencia", type=int, default=0)
    ap.add_argument("--intervalo", type=float, default=1.5, help="segundos entre conversas (--live)")
    ap.add_argument("--aquecer", type=float, default=8, help="minutos recentes gerados ao iniciar o --live (0 desliga)")
    a = ap.parse_args()
    try:
        asyncio.run(main_async(a))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
