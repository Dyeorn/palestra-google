"""Plugin ADK de telemetria (técnica + negócio) — grava tudo em SQLite local.

Regras de ouro:
  * nunca derruba o agente (todo callback passa por @safe);
  * nunca bloqueia (escrita vai para uma fila consumida por outra thread);
  * é passivo: observa e devolve None, não altera o fluxo do agente.
"""
from __future__ import annotations

import functools
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from google.adk.plugins.base_plugin import BasePlugin

from common.config import DB_PATH, PRICE_IN_USD_1M, PRICE_OUT_USD_1M, USD_BRL
from plugin import simctx
from plugin.classifiers import (STAGES, abandon_reason, classify_intent, is_resolved,
                                sentiment_score)
from plugin.db import Writer

log = logging.getLogger("telemetria")
FMT = "%Y-%m-%d %H:%M:%S"
SLOW_TURN_MS = 3000     # turno (modelo + ferramentas) acima disso = cliente percebe "demora"


def safe(fn):
    """Erro no plugin NUNCA pode derrubar o agente."""
    @functools.wraps(fn)
    async def wrapper(self, *a, **kw):
        try:
            return await fn(self, *a, **kw)
        except Exception:
            log.exception("erro no plugin de telemetria (%s) — ignorado", fn.__name__)
            return None
    return wrapper


def _ts(d: datetime) -> str:
    return d.strftime(FMT)


@dataclass
class Conv:
    id: str
    user_id: str
    persona: str
    started_at: datetime
    last_at: datetime
    turns: int = 0
    user_msgs: list[str] = field(default_factory=list)
    stage: int = 0
    in_tokens: int = 0
    out_tokens: int = 0
    converted: bool = False
    complaint: bool = False
    out_of_stock: bool = False
    mentions: set[str] = field(default_factory=set)
    # por turno: [erros_tool, erros_modelo, ms_totais_do_turno]
    turn_flags: list[list] = field(default_factory=list)  # ver acima


class TelemetryPlugin(BasePlugin):
    def __init__(self, db_path=None, name: str = "telemetria_vendas"):
        super().__init__(name=name)
        self.db = Writer(db_path or DB_PATH)
        self._convs: dict[str, Conv] = {}
        self._model_inflight: dict[str, dict] = {}
        self._tool_inflight: dict[str, dict] = {}

    # ------------------------------------------------------------------ util
    def flush(self) -> None:
        self.db.flush()

    async def close(self) -> None:
        self.db.flush()

    def _conv(self, ctx) -> Conv:
        """Obtém (ou cria) o estado da conversa a partir da sessão do ADK."""
        session = getattr(ctx, "session", None) or ctx._invocation_context.session
        sid = session.id
        c = self._convs.get(sid)
        if c is None:
            now = simctx.clock()
            persona = (session.state.get("perfil") if session.state else None) or "Desconhecido"
            c = Conv(id=sid, user_id=session.user_id, persona=persona, started_at=now, last_at=now)
            self._convs[sid] = c
        return c

    def _cid(self, callback_context) -> str:
        return callback_context._invocation_context.session.id

    def _cost(self, c: Conv) -> float:
        usd = (c.in_tokens * PRICE_IN_USD_1M + c.out_tokens * PRICE_OUT_USD_1M) / 1e6
        return round(usd * USD_BRL, 6)

    def _recent(self, c: Conv, n: int = 2):
        flags = c.turn_flags[-n:]
        return (sum(f[0] for f in flags), sum(f[1] for f in flags), any(f[2] > SLOW_TURN_MS for f in flags))

    def _upsert(self, c: Conv, finalizada: bool = False) -> None:
        tool_err, model_err, slow = self._recent(c)
        intent = classify_intent(c.user_msgs, c.complaint)
        reason = None
        if not c.converted:
            reason = abandon_reason(
                recent_tool_errors=tool_err, recent_model_errors=model_err, recent_slow=slow,
                out_of_stock=c.out_of_stock, last_msgs=c.user_msgs[-2:])
        last_sent = sentiment_score(c.user_msgs[-1:])
        resolved = is_resolved(
            converted=c.converted, intent=intent, complaint_filed=c.complaint,
            last_turn_failed=bool(tool_err or model_err), last_sentiment_ok=last_sent >= 0)
        self.db.submit(
            """INSERT INTO conversations(conversation_id,user_id,persona,started_at,ended_at,turns,
                 intent,max_stage,converted,abandon_reason,sentiment,resolved,cost_brl,finalizada)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(conversation_id) DO UPDATE SET ended_at=excluded.ended_at,
                 turns=excluded.turns,intent=excluded.intent,max_stage=excluded.max_stage,
                 converted=excluded.converted,abandon_reason=excluded.abandon_reason,
                 sentiment=excluded.sentiment,resolved=excluded.resolved,
                 cost_brl=excluded.cost_brl,finalizada=excluded.finalizada""",
            (c.id, c.user_id, c.persona, _ts(c.started_at), _ts(simctx.clock()), c.turns, intent,
             STAGES[c.stage], int(c.converted), reason, sentiment_score(c.user_msgs),
             int(resolved), self._cost(c), int(finalizada)))

    # --------------------------------------------------- ciclo de vida do run
    @safe
    async def on_user_message_callback(self, *, invocation_context, user_message):
        c = self._conv(invocation_context)
        text = " ".join(p.text for p in (user_message.parts or []) if getattr(p, "text", None))
        c.turns += 1
        c.user_msgs.append(text)
        c.turn_flags.append([0, 0, 0.0])
        return None

    @safe
    async def after_run_callback(self, *, invocation_context):
        c = self._conv(invocation_context)
        c.last_at = simctx.clock()
        self._upsert(c)

    @safe
    async def on_run_error_callback(self, *, invocation_context, error):
        c = self._conv(invocation_context)
        self.db.submit("INSERT INTO agent_errors VALUES(?,?,?,?)",
                       (c.id, _ts(simctx.clock()), "agente", f"{type(error).__name__}: {error}"[:500]))
        if c.turn_flags:
            c.turn_flags[-1][1] += 1
        self._upsert(c)

    def finalize_conversation(self, conversation_id: str) -> None:
        """O host (simulador / app de chat) chama quando a conversa termina."""
        try:
            c = self._convs.pop(conversation_id, None)
            if c:
                self._upsert(c, finalizada=True)
        except Exception:
            log.exception("erro ao finalizar conversa")

    # -------------------------------------------------------------- modelo
    @safe
    async def before_model_callback(self, *, callback_context, llm_request):
        self._conv(callback_context)
        self._model_inflight[callback_context.invocation_id] = {
            "t0": simctx.clock(), "p0": time.perf_counter(), "ttft": None}
        return None

    @safe
    async def after_model_callback(self, *, callback_context, llm_response):
        rec = self._model_inflight.get(callback_context.invocation_id)
        if rec is None:
            return None
        has_content = bool(llm_response.content and llm_response.content.parts)
        if llm_response.partial:  # streaming: o primeiro pedaço dá o "tempo até a primeira resposta"
            if rec["ttft"] is None and has_content:
                rec["ttft"] = (time.perf_counter() - rec["p0"]) * 1000
            return None
        self._model_inflight.pop(callback_context.invocation_id, None)
        c = self._conv(callback_context)
        sim = simctx.pop_latency("model")
        if sim:
            latency, ttft = sim
        else:
            latency = (time.perf_counter() - rec["p0"]) * 1000
            ttft = rec["ttft"]
        u = llm_response.usage_metadata
        tin = int(getattr(u, "prompt_token_count", 0) or 0)
        tout = int((getattr(u, "candidates_token_count", 0) or 0)
                   + (getattr(u, "thoughts_token_count", 0) or 0))
        status = "error" if llm_response.error_code else "ok"
        c.in_tokens += tin
        c.out_tokens += tout
        if c.turn_flags:
            c.turn_flags[-1][2] += latency
        if status == "error" and c.turn_flags:
            c.turn_flags[-1][1] += 1
        self.db.submit(
            "INSERT INTO model_calls VALUES(?,?,?,?,?,?,?,?)",
            (c.id, _ts(rec["t0"]), tin, tout, round(latency, 1),
             None if ttft is None else round(ttft, 1), status, llm_response.error_message))
        simctx.advance(latency)
        return None

    @safe
    async def on_model_error_callback(self, *, callback_context, llm_request, error):
        rec = self._model_inflight.pop(callback_context.invocation_id, None) or {
            "t0": simctx.clock(), "p0": time.perf_counter()}
        c = self._conv(callback_context)
        sim = simctx.pop_latency("model")
        latency = sim[0] if sim else (time.perf_counter() - rec["p0"]) * 1000
        if c.turn_flags:
            c.turn_flags[-1][1] += 1
            c.turn_flags[-1][2] += latency
        self.db.submit("INSERT INTO model_calls VALUES(?,?,?,?,?,?,?,?)",
                       (c.id, _ts(rec["t0"]), 0, 0, round(latency, 1), None, "error",
                        f"{type(error).__name__}: {error}"[:500]))
        simctx.advance(latency)
        return None

    # ---------------------------------------------------------- ferramentas
    @safe
    async def before_tool_callback(self, *, tool, tool_args, tool_context):
        self._tool_inflight[tool_context.function_call_id] = {
            "t0": simctx.clock(), "p0": time.perf_counter()}
        return None

    def _finish_tool(self, tool, tool_args, tool_context, ok: bool, err: str | None) -> tuple[Conv, datetime]:
        rec = self._tool_inflight.pop(tool_context.function_call_id, None) or {
            "t0": simctx.clock(), "p0": time.perf_counter()}
        c = self._conv(tool_context)
        sim = simctx.pop_latency(f"tool:{tool.name}")
        latency = sim[0] if sim else (time.perf_counter() - rec["p0"]) * 1000
        if c.turn_flags:
            c.turn_flags[-1][0] += 0 if ok else 1
            c.turn_flags[-1][2] += latency
        self.db.submit(
            "INSERT INTO tool_calls VALUES(?,?,?,?,?,?,?)",
            (c.id, _ts(rec["t0"]), tool.name, int(ok), round(latency, 1), err,
             json.dumps(tool_args, ensure_ascii=False, default=str)[:1000]))
        simctx.advance(latency)
        return c, rec["t0"]

    @safe
    async def after_tool_callback(self, *, tool, tool_args, tool_context, result):
        result = result if isinstance(result, dict) else {"result": result}
        ok = result.get("status") != "error"
        c, t0 = self._finish_tool(tool, tool_args, tool_context, ok,
                                  None if ok else str(result.get("error_message"))[:500])
        if ok:
            self._business(c, tool.name, tool_args, result, t0)
        return None

    @safe
    async def on_tool_error_callback(self, *, tool, tool_args, tool_context, error):
        self._finish_tool(tool, tool_args, tool_context, False, f"{type(error).__name__}: {error}"[:500])
        return None

    # ------------------------------------------------- dados de negócio
    def _mention(self, c: Conv, names) -> None:
        for n in names:
            if n and n not in c.mentions:
                c.mentions.add(n)
                self.db.submit("INSERT OR IGNORE INTO product_mentions VALUES(?,?)", (c.id, n))

    def _advance(self, c: Conv, stage: str) -> None:
        c.stage = max(c.stage, STAGES.index(stage))

    def _business(self, c: Conv, tool: str, args: dict, r: dict, t0: datetime) -> None:
        if tool in ("buscar_produtos", "recomendar_produtos"):
            prods = r.get("produtos") or []
            if prods:
                self._advance(c, "buscou" if tool == "buscar_produtos" else "recomendado")
                self._mention(c, [p.get("nome") for p in prods])
        elif tool == "consultar_estoque":
            self._advance(c, "carrinho")  # pediu estoque de um item = intenção de compra
            self._mention(c, [r.get("nome")])
            c.out_of_stock = not r.get("em_estoque", True)
        elif tool == "aplicar_cupom":
            if r.get("valido"):
                self._advance(c, "carrinho")
        elif tool == "criar_pedido":
            if r.get("motivo") == "sem_estoque":
                c.out_of_stock = True
            elif r.get("pedido_id"):
                self._advance(c, "pedido")
                c.converted = True
                c.out_of_stock = False
                self.db.submit("INSERT OR REPLACE INTO orders VALUES(?,?,?,?,?)",
                               (r["pedido_id"], c.id, _ts(t0), r.get("total"), r.get("cupom") or None))
                for it in r.get("itens", []):
                    self.db.submit("INSERT INTO order_items VALUES(?,?,?)",
                                   (r["pedido_id"], it["nome"], it["quantidade"]))
                    self._mention(c, [it["nome"]])
        elif tool == "registrar_reclamacao":
            c.complaint = True
