"""API FastAPI: /api/coverage, /api/paineis/{id}, /api/caos, /api/resumo + serve o dashboard."""
from __future__ import annotations

import json
import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from api.paineis import PANELS, one
from common.config import COVERAGE_PATH, DB_PATH, ROOT
from plugin.db import connect

app = FastAPI(title="Demo PetFeliz — painéis de telemetria")


def load_coverage() -> dict:
    """coverage.json é a fonte única de rótulos, títulos e ordem (relido a cada chamada)."""
    return json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))


def db() -> sqlite3.Connection:
    return connect(DB_PATH)


@app.get("/api/coverage")
def coverage():
    cov = load_coverage()
    cov["contagem"] = {k: sum(1 for p in cov["paineis"] if p["origem"] == k) for k in cov["rotulos"]}
    return cov


@app.get("/api/paineis/{pid}")
def get_painel(pid: str):
    meta = next((p for p in load_coverage()["paineis"] if p["id"] == pid), None)
    if meta is None or pid not in PANELS:
        raise HTTPException(404, f"painel '{pid}' não existe")
    con = db()
    try:
        dados = PANELS[pid](con)
    finally:
        con.close()
    return {"id": pid, "titulo": meta["titulo"], "pergunta": meta["pergunta"],
            "origem": meta["origem"], "dados": dados}


class Caos(BaseModel):
    ativo: bool


@app.get("/api/caos")
def get_caos():
    con = db()
    try:
        r = one(con, "SELECT valor FROM controle WHERE chave='caos'")
    finally:
        con.close()
    return {"ativo": r.get("valor") == "1"}


@app.post("/api/caos")
def set_caos(body: Caos):
    """O simulador (--live) lê esta chave a cada nova conversa."""
    con = db()
    try:
        with con:
            con.execute("INSERT INTO controle(chave, valor) VALUES('caos', ?) "
                        "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", ("1" if body.ativo else "0",))
    finally:
        con.close()
    return {"ativo": body.ativo}


@app.get("/api/resumo")
def resumo():
    con = db()
    try:
        r = one(con, "SELECT COUNT(*) AS conversas, MAX(ended_at) AS ultima_atividade FROM conversations")
        c = one(con, "SELECT valor FROM controle WHERE chave='caos'")
    finally:
        con.close()
    return {**r, "caos_ativo": c.get("valor") == "1"}


@app.get("/")
def index():
    return FileResponse(ROOT / "dashboard" / "index.html")


app.mount("/", StaticFiles(directory=ROOT / "dashboard"), name="dashboard")
