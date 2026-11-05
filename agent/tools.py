"""Ferramentas do agente. Todas devolvem dict com `status`.

`status == "error"` = falha técnica (o plugin conta como erro de ferramenta).
Regras de negócio (ex.: sem estoque) NÃO são erros técnicos.
"""
from __future__ import annotations

import functools
import itertools
import random

from agent import catalog as cat
from plugin import simctx

_pedido_seq = itertools.count(1)


def _instrumented(fn):
    """No simulador: latência e falhas simuladas. Fora dele: não faz nada."""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        ctx = simctx.current()
        if ctx is not None:
            simctx.report_latency(f"tool:{fn.__name__}", ctx.tool_latency(fn.__name__))
            if ctx.tool_fails(fn.__name__):
                return {"status": "error",
                        "error_message": f"Serviço de {fn.__name__.split('_')[0]} indisponível (timeout)"}
        return fn(*a, **kw)
    return wrapper


@_instrumented
def buscar_produtos(consulta: str) -> dict:
    """Busca produtos no catálogo da PetFeliz por texto livre.

    Args:
        consulta: o que o cliente procura, ex.: "ração para gato castrado".

    Returns:
        Até 4 produtos com id, nome, categoria, espécie e preço em reais.
    """
    return {"status": "ok", "produtos": [cat.public(p) for p in cat.search(consulta)]}


@_instrumented
def consultar_estoque(produto_id: str) -> dict:
    """Consulta estoque e prazo de entrega de um produto.

    Args:
        produto_id: id do produto, ex.: "P003".

    Returns:
        Se há estoque, quantidade disponível e prazo de entrega em dias.
    """
    p = cat.BY_ID.get(produto_id)
    if not p:
        return {"status": "ok", "nome": None, "em_estoque": False, "motivo": "produto_inexistente"}
    q = cat.stock_of(produto_id)
    return {"status": "ok", "produto_id": produto_id, "nome": p["nome"], "preco": p["preco"],
            "em_estoque": q > 0, "quantidade": q, "prazo_dias": cat.prazo_dias(produto_id)}


@_instrumented
def recomendar_produtos(especie: str, necessidade: str) -> dict:
    """Recomenda até 3 produtos conforme a espécie do pet e a necessidade.

    Args:
        especie: "cachorro" ou "gato".
        necessidade: o que o cliente precisa, ex.: "ração para filhote".

    Returns:
        Lista de produtos recomendados com preço.
    """
    found = cat.search(f"{especie} {necessidade}", limit=6)
    found = [p for p in found if p["especie"] in (especie, "ambos")] or found
    return {"status": "ok", "produtos": [cat.public(p) for p in found[:3]]}


@_instrumented
def aplicar_cupom(codigo: str) -> dict:
    """Valida um cupom de desconto.

    Args:
        codigo: código do cupom informado pelo cliente.

    Returns:
        Se o cupom é válido e o percentual de desconto.
    """
    pct = cat.CUPONS.get(codigo.strip().upper())
    return {"status": "ok", "codigo": codigo.strip().upper(), "valido": pct is not None,
            "desconto_pct": pct or 0}


@_instrumented
def criar_pedido(produto_ids: list[str], quantidades: list[int], cupom: str = "") -> dict:
    """Cria o pedido do cliente. Só chame depois de o cliente confirmar a compra.

    Args:
        produto_ids: ids dos produtos.
        quantidades: quantidade de cada produto (mesma ordem de produto_ids).
        cupom: cupom já validado (opcional).

    Returns:
        Número do pedido, itens, total com desconto e frete, e prazo.
    """
    itens, subtotal, prazo = [], 0.0, 1
    for pid, qtd in zip(produto_ids, quantidades or [1] * len(produto_ids)):
        p = cat.BY_ID.get(pid)
        if not p:
            return {"status": "ok", "motivo": "produto_inexistente"}
        if cat.stock_of(pid) < qtd:
            return {"status": "ok", "motivo": "sem_estoque", "produto": p["nome"]}
        itens.append({"nome": p["nome"], "quantidade": qtd, "preco": p["preco"]})
        subtotal += p["preco"] * qtd
        prazo = max(prazo, cat.prazo_dias(pid))
    pct = cat.CUPONS.get((cupom or "").strip().upper(), 0)
    desconto = round(subtotal * pct / 100, 2)
    frete = 0.0 if subtotal - desconto >= cat.FRETE_GRATIS_ACIMA else cat.FRETE_FIXO
    total = round(subtotal - desconto + frete, 2)
    return {"status": "ok", "pedido_id": f"PF{random.randint(10**6, 10**7 - 1)}-{next(_pedido_seq)}",
            "itens": itens, "subtotal": round(subtotal, 2), "desconto": desconto, "frete": frete,
            "total": total, "cupom": (cupom or "").strip().upper() if pct else "", "prazo_dias": prazo}


@_instrumented
def registrar_reclamacao(descricao: str, categoria: str = "geral") -> dict:
    """Registra uma reclamação do cliente para o time de atendimento.

    Args:
        descricao: resumo do problema relatado.
        categoria: "entrega", "produto", "atendimento" ou "geral".

    Returns:
        Número de protocolo da reclamação.
    """
    return {"status": "ok", "protocolo": f"REC{random.randint(10**5, 10**6 - 1)}", "categoria": categoria}


TOOLS = [buscar_produtos, consultar_estoque, recomendar_produtos, aplicar_cupom,
         criar_pedido, registrar_reclamacao]
