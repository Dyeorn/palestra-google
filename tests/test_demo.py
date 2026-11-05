"""Smoke tests: plugin nunca derruba o agente; simulação enche as tabelas; todos os painéis respondem."""
import asyncio
import json
import random
import sqlite3
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent.agent import build_app
from agent.fake_llm import FakeSalesLlm
from common.config import COVERAGE_PATH
from plugin import simctx
from plugin.telemetry_plugin import TelemetryPlugin
from simulator import run as sim


def _args(**kw):
    import argparse
    base = dict(conversas=25, dias=5, live=False, chaos=False, modelo="offline", reset=False,
                seed=3, concorrencia=8, intervalo=1.0)
    base.update(kw)
    return argparse.Namespace(**base)


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "t.db"
    monkeypatch.setattr(sim, "DB_PATH", path)
    monkeypatch.setattr("api.main.DB_PATH", path)
    return path


def test_simulacao_enche_tabelas(db):
    asyncio.run(sim.main_async(_args()))
    con = sqlite3.connect(db)
    for t in ("conversations", "model_calls", "tool_calls", "product_mentions"):
        assert con.execute(f"select count(*) from {t}").fetchone()[0] > 0, t
    assert con.execute("select count(*) from conversations where finalizada=0").fetchone()[0] == 0


def test_todos_os_paineis_respondem(db):
    asyncio.run(sim.main_async(_args(conversas=40)))
    from api.main import app
    c = TestClient(app)
    cov = c.get("/api/coverage").json()
    assert cov["contagem"] == {"bq": 4, "exclusivo": 6}
    for p in json.loads(COVERAGE_PATH.read_text())["paineis"]:
        r = c.get(f"/api/paineis/{p['id']}")
        assert r.status_code == 200, p["id"]
        assert r.json()["origem"] == p["origem"] and r.json()["dados"]
    assert c.get("/api/paineis/inexistente").status_code == 404


def test_caos_via_api(db):
    from api.main import app
    c = TestClient(app)
    assert c.post("/api/caos", json={"ativo": True}).json() == {"ativo": True}
    assert c.get("/api/caos").json() == {"ativo": True}
    assert sim.read_chaos_flag() is True


def test_erro_no_plugin_nao_derruba_o_agente(tmp_path, monkeypatch):
    plugin = TelemetryPlugin(db_path=tmp_path / "x.db")

    def boom(*a, **k):
        raise RuntimeError("plugin quebrado")
    monkeypatch.setattr(plugin.db, "submit", boom)  # toda escrita falha

    async def go():
        app = build_app([plugin], FakeSalesLlm())
        ss = InMemorySessionService()
        runner = Runner(app=app, session_service=ss)
        await ss.create_session(app_name="vendas", user_id="u", session_id="s")
        out = []
        async for ev in runner.run_async(user_id="u", session_id="s", new_message=types.Content(
                role="user", parts=[types.Part(text="Oi! Procuro ração para gato castrado")])):
            if ev.is_final_response() and ev.content:
                out.append(ev.content.parts[0].text)
        return out
    assert "Encontrei" in asyncio.run(go())[0]


def test_falha_de_ferramenta_vira_erro_registrado(tmp_path):
    plugin = TelemetryPlugin(db_path=tmp_path / "y.db")

    async def go():
        ctx = simctx.SimContext(start=datetime.now() - timedelta(days=1), rng=random.Random(1), chaos=True)
        ctx.tool_fail_extra = {"buscar_produtos": 1.0}
        simctx.set_current(ctx)
        app = build_app([plugin], FakeSalesLlm())
        ss = InMemorySessionService()
        runner = Runner(app=app, session_service=ss)
        await ss.create_session(app_name="vendas", user_id="u", session_id="s")
        for _ in range(3):  # o modelo simulado também falha no caos; tenta até uma tool rodar
            try:
                async for _ in runner.run_async(user_id="u", session_id="s", new_message=types.Content(
                        role="user", parts=[types.Part(text="quero ração para cachorro")])):
                    pass
            except Exception:
                pass
        plugin.finalize_conversation("s")
        plugin.flush()
    asyncio.run(go())
    con = sqlite3.connect(tmp_path / "y.db")
    assert con.execute("select count(*) from tool_calls where success=0").fetchone()[0] > 0
