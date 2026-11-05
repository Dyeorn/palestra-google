"""Um painel = uma função que devolve o campo `dados`. As queries seguem o PAINEIS.md."""
from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timedelta

from common.config import TTFT_META_MS, now_local

PANELS: dict = {}


def painel(pid: str):
    def deco(fn):
        PANELS[pid] = fn
        return fn
    return deco


def pct(values: list[float], p: float) -> float | None:
    """Percentil por posto mais próximo (SQLite não tem percentil)."""
    if not values:
        return None
    v = sorted(values)
    return round(v[max(0, math.ceil(p / 100 * len(v)) - 1)], 1)


def q(db: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in db.execute(sql, params).fetchall()]


def one(db, sql, params=()) -> dict:
    r = q(db, sql, params)
    return r[0] if r else {}


def _fill_days(rows: list[dict], key: str = "dia", **defaults) -> list[dict]:
    if not rows:
        return rows
    by = {r[key]: r for r in rows}
    d = datetime.strptime(rows[0][key], "%Y-%m-%d")
    end = datetime.strptime(rows[-1][key], "%Y-%m-%d")
    out = []
    while d <= end:
        k = d.strftime("%Y-%m-%d")
        out.append(by.get(k, {key: k, **defaults}))
        d += timedelta(days=1)
    return out


# 1 ---------------------------------------------------------------------------
@painel("conversas-por-dia")
def conversas_por_dia(db):
    por_dia = _fill_days(q(db, "SELECT date(started_at) AS dia, COUNT(*) AS conversas "
                               "FROM conversations GROUP BY dia ORDER BY dia"), conversas=0)
    calor = q(db, "SELECT CAST(strftime('%w', started_at) AS INT) AS dia_semana, "
                  "CAST(strftime('%H', started_at) AS INT) AS hora, COUNT(*) AS conversas "
                  "FROM conversations GROUP BY 1, 2")
    por_hora = {}
    for c in calor:
        por_hora[c["hora"]] = por_hora.get(c["hora"], 0) + c["conversas"]
    pico = max(por_hora.items(), key=lambda kv: kv[1]) if por_hora else None
    total = sum(d["conversas"] for d in por_dia)
    return {"por_dia": por_dia, "mapa_calor": calor, "total": total,
            "media_por_dia": round(total / len(por_dia), 1) if por_dia else 0,
            "hora_de_pico": pico[0] if pico else None}


# 2 ---------------------------------------------------------------------------
@painel("tempo-primeira-resposta")
def tempo_primeira_resposta(db):
    rows = q(db, "SELECT CAST(strftime('%H', called_at) AS INT) AS hora, ttft_ms "
                 "FROM model_calls WHERE status = 'ok' AND ttft_ms IS NOT NULL")
    horas: dict[int, list[float]] = {}
    for r in rows:
        horas.setdefault(r["hora"], []).append(r["ttft_ms"])
    por_hora = [{"hora": h, "p50_ms": pct(v, 50), "p95_ms": pct(v, 95), "chamadas": len(v)}
                for h, v in sorted(horas.items())]
    todos = [r["ttft_ms"] for r in rows]
    lat = [r["latency_ms"] for r in q(db, "SELECT latency_ms FROM model_calls WHERE status='ok'")]
    pior = max(por_hora, key=lambda h: h["p95_ms"] or 0) if por_hora else None
    return {"p50_ms": pct(todos, 50), "p95_ms": pct(todos, 95), "meta_ms": TTFT_META_MS,
            "latencia_total_p50_ms": pct(lat, 50), "latencia_total_p95_ms": pct(lat, 95),
            "por_hora": por_hora, "pior_hora": pior["hora"] if pior else None,
            "chamadas": len(todos)}


# 3 ---------------------------------------------------------------------------
@painel("falhas-ferramentas")
def falhas_ferramentas(db):
    ferramentas = q(db, "SELECT tool_name AS ferramenta, COUNT(*) AS chamadas, "
                        "SUM(1 - success) AS falhas, "
                        "ROUND(100.0 * SUM(1 - success) / COUNT(*), 1) AS taxa_erro_pct, "
                        "ROUND(AVG(latency_ms)) AS latencia_media_ms "
                        "FROM tool_calls GROUP BY tool_name ORDER BY taxa_erro_pct DESC")
    m = one(db, "SELECT COUNT(*) AS chamadas, COALESCE(SUM(status != 'ok'),0) AS erros FROM model_calls")
    ag = one(db, "SELECT COUNT(*) AS erros FROM agent_errors")
    tot = sum(f["chamadas"] for f in ferramentas) or 1
    return {"ferramentas": ferramentas,
            "total_chamadas": tot, "total_falhas": sum(f["falhas"] for f in ferramentas),
            "erros_modelo": {"erros": m["erros"], "chamadas": m["chamadas"]},
            "erros_agente": {"erros": ag["erros"]}}


# 4 ---------------------------------------------------------------------------
@painel("tokens-por-conversa")
def tokens_por_conversa(db):
    por_dia = _fill_days(q(db, "SELECT date(called_at) AS dia, SUM(input_tokens) AS tokens_entrada, "
                               "SUM(output_tokens) AS tokens_saida, "
                               "ROUND(1.0 * (SUM(input_tokens) + SUM(output_tokens)) / "
                               "COUNT(DISTINCT conversation_id)) AS tokens_por_conversa "
                               "FROM model_calls GROUP BY dia ORDER BY dia"),
                         tokens_entrada=0, tokens_saida=0, tokens_por_conversa=None)
    turnos = {r["dia"]: r["turnos"] for r in q(db, "SELECT date(started_at) AS dia, "
                                                  "ROUND(AVG(turns),2) AS turnos FROM conversations GROUP BY dia")}
    for d in por_dia:
        d["turnos_medios"] = turnos.get(d["dia"])
    vals = [d["tokens_por_conversa"] for d in por_dia if d["tokens_por_conversa"]]
    k = max(1, len(vals) // 4)
    ini, fim = (sum(vals[:k]) / k, sum(vals[-k:]) / k) if vals else (0, 0)
    g = one(db, "SELECT ROUND(AVG(turns),1) AS turnos FROM conversations")
    return {"por_dia": por_dia, "media_tokens_por_conversa": round(sum(vals) / len(vals)) if vals else 0,
            "variacao_pct": round(100 * (fim - ini) / ini, 1) if ini else None,
            "turnos_medios": g.get("turnos")}


# 5 ---------------------------------------------------------------------------
ETAPAS = [("iniciou", "Iniciou conversa"), ("buscou", "Buscou produto"), ("recomendado", "Recebeu recomendação"),
          ("carrinho", "Foi ao carrinho"), ("pedido", "Fez o pedido")]


@painel("funil-vendas")
def funil_vendas(db):
    r = one(db, """WITH e AS (SELECT CASE max_stage WHEN 'iniciou' THEN 1 WHEN 'buscou' THEN 2
             WHEN 'recomendado' THEN 3 WHEN 'carrinho' THEN 4 WHEN 'pedido' THEN 5 END AS n FROM conversations)
             SELECT COALESCE(SUM(n >= 1),0) AS iniciou, COALESCE(SUM(n >= 2),0) AS buscou,
             COALESCE(SUM(n >= 3),0) AS recomendado, COALESCE(SUM(n >= 4),0) AS carrinho,
             COALESCE(SUM(n >= 5),0) AS pedido FROM e""")
    base = r.get("iniciou") or 0
    etapas, prev = [], None
    for key, nome in ETAPAS:
        v = r.get(key, 0)
        etapas.append({"id": key, "nome": nome, "valor": v,
                       "pct_do_total": round(100 * v / base, 1) if base else 0,
                       "perda_vs_anterior": (prev - v) if prev is not None else 0})
        prev = v
    vaz = max(range(1, len(etapas)), key=lambda i: etapas[i]["perda_vs_anterior"]) if base else None
    return {"etapas": etapas, "maior_vazamento": vaz,
            "de_cada_100": round(100 * r.get("pedido", 0) / base, 1) if base else 0}


# 6 ---------------------------------------------------------------------------
@painel("motivos-abandono")
def motivos_abandono(db):
    rows = q(db, "SELECT abandon_reason AS motivo, COUNT(*) AS conversas FROM conversations "
                 "WHERE converted = 0 AND abandon_reason IS NOT NULL GROUP BY abandon_reason "
                 "ORDER BY conversas DESC")
    tot = sum(r["conversas"] for r in rows)
    for r in rows:
        r["pct"] = round(100 * r["conversas"] / tot, 1) if tot else 0
    return {"motivos": rows, "total_abandonos": tot}


# 7 ---------------------------------------------------------------------------
@painel("custo-por-venda")
def custo_por_venda(db):
    c = one(db, "SELECT ROUND(AVG(cost_brl), 4) AS custo_por_conversa, "
                "ROUND(SUM(cost_brl) / NULLIF(SUM(converted), 0), 4) AS custo_por_venda, "
                "ROUND(SUM(cost_brl), 2) AS custo_total, COUNT(*) AS conversas, SUM(converted) AS vendas "
                "FROM conversations")
    o = one(db, "SELECT ROUND(SUM(total_brl), 2) AS receita, COUNT(*) AS pedidos, "
                "ROUND(AVG(total_brl), 2) AS ticket_medio FROM orders")
    custo = {r["dia"]: r["custo"] for r in q(db, "SELECT date(started_at) AS dia, ROUND(SUM(cost_brl),4) AS custo "
                                                 "FROM conversations GROUP BY dia")}
    rec = {r["dia"]: r["receita"] for r in q(db, "SELECT date(created_at) AS dia, ROUND(SUM(total_brl),2) AS receita "
                                                 "FROM orders GROUP BY dia")}
    dias = sorted(set(custo) | set(rec))
    por_dia = _fill_days([{"dia": d, "custo": custo.get(d, 0), "receita": rec.get(d, 0)} for d in dias],
                         custo=0, receita=0)
    receita = o.get("receita") or 0
    return {**c, **o, "receita": receita, "por_dia": por_dia,
            "retorno_por_real": round(receita / c["custo_total"]) if c.get("custo_total") else None}


# 8 ---------------------------------------------------------------------------
@painel("produtos-cupons-perfil")
def produtos_cupons_perfil(db):
    produtos = q(db, "SELECT p.product_name AS produto, COUNT(*) AS citacoes, COALESCE(v.vendidos, 0) AS vendidos "
                     "FROM product_mentions p LEFT JOIN (SELECT product_name, SUM(quantity) AS vendidos "
                     "FROM order_items GROUP BY product_name) v USING (product_name) "
                     "GROUP BY p.product_name ORDER BY citacoes DESC LIMIT 10")
    tc, tv = sum(p["citacoes"] for p in produtos), sum(p["vendidos"] for p in produtos)
    media = tv / tc if tc else 0
    for p in produtos:  # muito citado e pouco vendido
        p["interesse_sem_conversao"] = bool(media and p["vendidos"] / p["citacoes"] < 0.5 * media)
    perfis = q(db, "SELECT c.persona AS perfil, COUNT(*) AS pedidos, "
                   "ROUND(100.0 * SUM(o.coupon_code IS NOT NULL) / COUNT(*), 1) AS pct_com_cupom, "
                   "ROUND(AVG(o.total_brl), 2) AS ticket_medio FROM orders o "
                   "JOIN conversations c USING (conversation_id) GROUP BY c.persona ORDER BY pct_com_cupom DESC")
    cupons = q(db, "SELECT coupon_code AS cupom, COUNT(*) AS pedidos, ROUND(SUM(total_brl),2) AS receita "
                   "FROM orders WHERE coupon_code IS NOT NULL GROUP BY coupon_code ORDER BY pedidos DESC")
    g = one(db, "SELECT COUNT(*) AS pedidos, ROUND(AVG(total_brl),2) AS ticket_medio, "
                "ROUND(100.0*SUM(coupon_code IS NOT NULL)/COUNT(*),1) AS pct_com_cupom FROM orders")
    return {"produtos": produtos, "perfis": perfis, "cupons": cupons, "geral": g}


# 9 ---------------------------------------------------------------------------
@painel("intencao-resolucao-sentimento")
def intencao(db):
    intencoes = q(db, "SELECT intent AS intencao, COUNT(*) AS conversas, "
                      "ROUND(100.0 * AVG(resolved), 1) AS pct_resolvido, "
                      "ROUND(AVG(sentiment), 2) AS sentimento_medio FROM conversations "
                      "GROUP BY intent ORDER BY conversas DESC")
    por_dia = _fill_days(q(db, "SELECT date(started_at) AS dia, ROUND(AVG(sentiment),2) AS sentimento, "
                               "ROUND(100.0*AVG(resolved),1) AS pct_resolvido FROM conversations "
                               "GROUP BY dia ORDER BY dia"), sentimento=None, pct_resolvido=None)
    g = one(db, "SELECT ROUND(100.0*AVG(resolved),1) AS pct_resolvido, ROUND(AVG(sentiment),2) AS sentimento_medio "
                "FROM conversations")
    return {"intencoes": intencoes, "sentimento_por_dia": por_dia, "geral": g}


# 10 --------------------------------------------------------------------------
FAIXAS = ["< 2 s", "2 a 5 s", "> 5 s"]


@painel("venda-perdida")
def venda_perdida(db):
    base = """WITH base AS (SELECT c.converted,
        (SELECT MAX(latency_ms) FROM model_calls m WHERE m.conversation_id = c.conversation_id) AS lat_max,
        (SELECT COUNT(*) FROM tool_calls t WHERE t.conversation_id = c.conversation_id AND t.success = 0) AS erros
        FROM conversations c) """
    lat = q(db, base + """SELECT CASE WHEN lat_max < 2000 THEN '< 2 s' WHEN lat_max < 5000 THEN '2 a 5 s'
        ELSE '> 5 s' END AS faixa, COUNT(*) AS conversas, ROUND(100.0 * AVG(converted), 1) AS conversao_pct
        FROM base WHERE lat_max IS NOT NULL GROUP BY faixa""")
    lat.sort(key=lambda r: FAIXAS.index(r["faixa"]))
    err = q(db, base + """SELECT CASE WHEN erros = 0 THEN 'sem erro' ELSE 'com erro' END AS grupo,
        COUNT(*) AS conversas, ROUND(100.0 * AVG(converted), 1) AS conversao_pct FROM base GROUP BY grupo""")
    err.sort(key=lambda r: r["grupo"] != "sem erro")
    desde = (now_local() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    vivo = q(db, "SELECT strftime('%H:%M', started_at) AS minuto, COUNT(*) AS conversas, "
                 "ROUND(100.0 * AVG(converted), 1) AS conversao_pct FROM conversations "
                 "WHERE finalizada = 1 AND started_at >= ? GROUP BY strftime('%Y-%m-%d %H:%M', started_at) "
                 "ORDER BY strftime('%Y-%m-%d %H:%M', started_at)", (desde,))
    caos = one(db, "SELECT valor FROM controle WHERE chave='caos'")
    sem = next((e for e in err if e["grupo"] == "sem erro"), None)
    com = next((e for e in err if e["grupo"] == "com erro"), None)
    return {"por_latencia": lat, "por_erro": err, "ao_vivo": vivo,
            "caos_ativo": caos.get("valor") == "1",
            "queda_com_erro_pp": round(sem["conversao_pct"] - com["conversao_pct"], 1) if sem and com else None}
