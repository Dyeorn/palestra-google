"""Classificadores simples (léxico/regras) para os dados de negócio.

São deliberadamente transparentes: dá para explicar cada um no palco.
Em produção, qualquer um deles pode ser trocado por uma chamada a LLM.
"""
from __future__ import annotations

import re
import unicodedata

STAGES = ["iniciou", "buscou", "recomendado", "carrinho", "pedido"]

INTENTS = {
    "reclamacao": "Reclamação",
    "cupom": "Usar cupom/desconto",
    "entrega": "Dúvida de entrega",
    "recomendacao": "Pedir recomendação",
    "preco": "Consultar preço",
    "compra": "Comprar produto",
}
ABANDON = {
    "preco": "Preço alto", "estoque": "Sem estoque", "indeciso": "Indeciso",
    "demora": "Demora na resposta", "erro": "Erro do sistema", "frete": "Frete/prazo",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


_INTENT_RULES = [
    ("reclamacao", r"reclam|absurdo|errado|defeito|estragou|nao chegou|atrasou|pessimo|devolv"),
    ("cupom", r"cupom|desconto|promoc|codigo"),
    ("entrega", r"entrega|frete|prazo|chega"),
    ("recomendacao", r"recomend|indica|sugest|qual (e )?(o )?melhor|nao sei qual"),
    ("preco", r"quanto (custa|sai|e)|preco|valor"),
]


def classify_intent(user_msgs: list[str], complaint_filed: bool) -> str:
    """A intenção é o que o cliente pediu na PRIMEIRA mensagem (ou reclamação registrada)."""
    if complaint_filed:
        return INTENTS["reclamacao"]
    t = norm(user_msgs[0]) if user_msgs else ""
    for key, pat in _INTENT_RULES:
        if re.search(pat, t):
            return INTENTS[key]
    return INTENTS["compra"]


_POS = r"otimo|perfeito|maravilh|adorei|gostei|show|legal|excelente|amei|beleza|fechado|valeu|top|ajudou|rapido"
_NEG = (r"perdi tempo|atras|errado|defeito|reclam|caro|absurdo|pessimo|horrivel|demor|lent[oa]|erro|nao funciona|ridicul|cansei|desist|pior|"
        r"droga|lixo|decepc|irritad|raiva|nunca mais|inaceit|deixa pra la|vou embora|nao compro|demais")


def sentiment_score(user_msgs: list[str]) -> float:
    """-1..+1. Média das mensagens do cliente, as últimas pesam mais."""
    if not user_msgs:
        return 0.0
    num = den = 0.0
    for i, text in enumerate(user_msgs):
        t = norm(text)
        pos, neg = len(re.findall(_POS, t)), len(re.findall(_NEG, t))
        if pos + neg == 0:
            s = 0.0
        else:
            s = (pos - neg) / (pos + neg)
            if "!!" in text or text.isupper():
                s *= 1.25
        w = 1 + i * 0.5 + (1.5 if i == len(user_msgs) - 1 else 0)
        num += s * w
        den += w
    return round(max(-1.0, min(1.0, num / den)), 2)


def abandon_reason(*, recent_tool_errors: int, recent_model_errors: int, recent_slow: bool,
                   out_of_stock: bool, last_msgs: list[str]) -> str:
    """Evidências de telemetria primeiro; depois o que o cliente disse por último."""
    if recent_tool_errors or recent_model_errors:
        return ABANDON["erro"]
    if recent_slow:
        return ABANDON["demora"]
    if out_of_stock:
        return ABANDON["estoque"]
    t = norm(" ".join(last_msgs))
    if re.search(r"frete|prazo|entrega|demora pra chegar", t):
        return ABANDON["frete"]
    if re.search(r"caro|preco|valor|desconto|cupom|orcamento|barato", t):
        return ABANDON["preco"]
    return ABANDON["indeciso"]


def is_resolved(*, converted: bool, intent: str, complaint_filed: bool,
                last_turn_failed: bool, last_sentiment_ok: bool) -> bool:
    if converted or complaint_filed:
        return True
    if intent in (INTENTS["entrega"], INTENTS["preco"], INTENTS["recomendacao"]):
        return (not last_turn_failed) and last_sentiment_ok
    return False
