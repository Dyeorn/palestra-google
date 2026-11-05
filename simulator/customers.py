"""Clientes sintéticos. Cada um reage ao que o agente de fato fez (latência, erro, estoque, preço).

O cliente NÃO fala "meu motivo de abandono é X": ele só reage e escreve como uma pessoa.
Quem deduz o motivo é o plugin, a partir da telemetria + texto.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from agent.catalog import CUPONS


@dataclass
class Obs:
    """O que o cliente percebeu da última resposta do agente."""
    text: str = ""
    latency_ms: float = 0.0
    system_error: bool = False        # a execução falhou (ex.: 503 do modelo)
    tool_error: bool = False          # agente pediu desculpas por falha técnica
    produtos: list = field(default_factory=list)
    em_estoque: bool | None = None
    prazo_dias: int | None = None
    preco: float | None = None
    cupom_valido: bool | None = None
    desconto_pct: int = 0
    pedido: bool = False
    reclamacao: bool = False
    sem_estoque_pedido: bool = False


@dataclass
class Step:
    message: str | None       # None = vai embora em silêncio
    end: bool = False         # True = manda a mensagem e encerra


PERSONAS = {
    # peso, p_compra, p_cupom_conhece, paciência (ms), p_sai_lento, p_sai_erro, sensível_preço, sensível_prazo
    "Indeciso":            dict(w=30, p_buy=0.42, patience=6000, p_slow=0.30, p_err=0.30, price=0.5, prazo=0.4, extra_q=(1, 2), p_knows=0.18),
    "Apressado":           dict(w=25, p_buy=0.88, patience=3500, p_slow=0.65, p_err=0.50, price=0.2, prazo=0.7, extra_q=(0, 0), p_knows=0.06),
    "Caçador de desconto": dict(w=28, p_buy=0.80, patience=5000, p_slow=0.25, p_err=0.30, price=1.0, prazo=0.3, extra_q=(0, 1), p_knows=1.0),
    "Irritado":            dict(w=17, p_buy=0.55, patience=4000, p_slow=0.60, p_err=0.75, price=0.6, prazo=0.6, extra_q=(0, 1), p_knows=0.1),
}

# (consulta, peso)
NEEDS = [
    ("ração para cachorro adulto", 18), ("ração para gato castrado", 14), ("ração para filhote", 8),
    ("petisco para cachorro", 10), ("brinquedo para gato", 7), ("brinquedo para cachorro", 8),
    ("areia higiênica para gato", 9), ("shampoo para cachorro", 5), ("cama para cachorro", 5),
    ("coleira para cachorro", 5), ("arranhador para gato", 4), ("antipulgas para cachorro", 6),
    ("tapete higiênico", 6), ("comedouro", 3),
]

OPEN = {
    "Indeciso": ["Oi, estou procurando {n}, mas não sei bem qual escolher", "Bom dia! Preciso de {n}",
                 "Oi! Queria ver opções de {n}", "Pode me recomendar {n}? Não sei qual é o melhor",
                 "Quanto custa {n}?"],
    "Apressado": ["{n}. Rápido por favor", "Preciso de {n} hoje", "Oi, quero {n}", "Quanto custa {n}?",
                  "Qual o prazo de entrega para {n}?"],
    "Caçador de desconto": ["Oi, procuro {n}. Tem cupom ou desconto?", "Quero {n}, tem alguma promoção?",
                            "Bom dia! {n} com desconto, tem?", "Quanto custa {n}? Procuro o mais barato"],
    "Irritado": ["Já perdi tempo demais, preciso de {n}", "Oi. Quero {n} e espero que funcione dessa vez",
                 "Preciso de {n}, vê se não demora", "Qual o prazo de entrega de {n}? Da última vez atrasou"],
}
COMPLAINT_OPEN = ["Meu último pedido chegou errado, isso é um absurdo!",
                  "Comprei aí e o produto veio com defeito, quero reclamar!",
                  "Meu pedido atrasou de novo, que absurdo!"]


class Customer:
    def __init__(self, persona: str, rng: random.Random):
        self.persona, self.rng = persona, rng
        self.cfg = PERSONAS[persona]
        self.need = rng.choices([n for n, _ in NEEDS], [w for _, w in NEEDS])[0]
        self.budget = rng.choice([40, 60, 90, 120, 160, 220])
        self.extra = rng.randint(*self.cfg["extra_q"])
        self.phase = "start"
        self.last_msg = ""
        self.retries = 0
        self.picked_price: float | None = None
        self.coupon_tried = False
        self.complaint_first = persona == "Irritado" and rng.random() < 0.35
        self.pct = 0

    # ---- helpers
    def _say(self, msg: str) -> Step:
        self.last_msg = msg
        return Step(msg)

    def _leave(self, msg: str | None, silent_p: float = 0.35) -> Step:
        if msg is None or self.rng.random() < silent_p:
            return Step(None)
        return Step(msg, end=True)

    def opening(self) -> str:
        if self.complaint_first:
            self.phase = "complaint"
            return self.rng.choice(COMPLAINT_OPEN)
        self.phase = "search"
        return self.last_msg_set(self.rng.choice(OPEN[self.persona]).format(n=self.need))

    def last_msg_set(self, m):  # noqa: D401
        self.last_msg = m
        return m

    # ---- reação principal
    def react(self, o: Obs) -> Step:
        r, cfg = self.rng, self.cfg
        irritado = self.persona == "Irritado"

        if o.system_error:
            if self.retries < 1 and r.random() > cfg["p_err"]:
                self.retries += 1
                return self._say("Deu erro aqui, pode tentar de novo?")
            return self._leave("Não está funcionando, vou embora." if irritado else "Deu erro, deixa pra lá.")
        if o.latency_ms > cfg["patience"] and r.random() < cfg["p_slow"]:
            return self._leave("Demorou demais, desisti." if irritado else "Tá muito lento, vou deixar pra depois.")
        if o.tool_error:
            if self.retries < 2 and r.random() > cfg["p_err"]:
                self.retries += 1
                return self._say("Tenta de novo, por favor.")
            return self._leave("Esse sistema não funciona direito, vou embora." if irritado else "Deu problema, deixa pra lá.")

        if self.phase == "complaint":
            if r.random() < 0.3:
                self.phase = "search"
                return self._say(f"Tá. Aproveitando, preciso de {self.need}")
            return Step("Ok, obrigado.", end=True)

        if o.pedido:
            ok = ["Obrigado! Perfeito!", "Valeu, adorei o atendimento!", "Show, obrigada!"]
            return Step("Muito mal-humorado, mas obrigado." if irritado and r.random() < 0.3 else r.choice(ok), end=True)

        if o.sem_estoque_pedido:
            return self._leave("Que pena, esgotou. Vou ver em outro lugar.", 0.2)

        if self.phase == "search":
            if not o.produtos:
                if self.retries < 1:
                    self.retries += 1
                    return self._say(f"Pode me indicar algo parecido com {self.need}?")
                return self._leave("Não achei nada, tchau.")
            cheapest = min(o.produtos, key=lambda p: p["preco"])
            price_ok = cheapest["preco"] <= self.budget * 1.25
            if not price_ok and r.random() < cfg["price"]:
                self.phase = "price_objection"
                return self._say("Hmm, está caro. Tem algo mais barato?")
            pick_cheap = r.random() < cfg["price"] * 0.8
            if pick_cheap:
                idx, who = o.produtos.index(cheapest), "o mais barato"
            else:
                idx = r.choices(range(len(o.produtos)), [4, 3, 2, 2][:len(o.produtos)])[0]
                who = ["o primeiro", "o segundo", "o terceiro", "o quarto"][idx]
            self.picked_price = o.produtos[idx]["preco"]
            self.phase = "pick"
            if self.persona == "Apressado":
                self.phase = "decide"
                return self._say(f"Quero {who}, pode fechar")
            return self._say(f"Tem estoque d{who}?")

        if self.phase == "price_objection":
            if not o.produtos:
                return self._leave("Está acima do que eu queria. Vou ver em outro lugar.", 0.2)
            self.picked_price = min(p["preco"] for p in o.produtos)
            if self.picked_price > self.budget * 1.25:
                return self._leave("Ficou caro pra mim, vou ver em outro lugar.", 0.1)
            self.phase = "pick"
            return self._say("Tem estoque do mais barato?")

        if self.phase == "pick":
            if o.em_estoque is False:
                if r.random() < 0.4:
                    self.phase = "search"
                    return self._say("Pode me recomendar outro parecido?")
                return self._leave("Que pena, sem estoque. Vou ver em outro lugar.", 0.2)
            if o.prazo_dias and o.prazo_dias >= 5 and r.random() < cfg["prazo"]:
                return self._leave(f"{o.prazo_dias} dias de entrega é muito, o prazo não serve pra mim.", 0.1)
            if self.extra > 0:
                self.extra -= 1
                return self._say("Qual a diferença desse pro segundo? Pode comparar?")
            return self._after_stock(o)

        if self.phase == "coupon":
            self.coupon_tried = True
            if o.cupom_valido:
                self.pct = o.desconto_pct
                self.phase = "decide"
                return self._decide(coupon=True)
            if self.persona != "Caçador de desconto":
                self.phase = "decide"
                return self._decide(coupon=False)
            return self._leave("Sem desconto não compro, tá caro.", 0.15)

        if self.phase == "decide":
            return self._decide(coupon=bool(self.pct))

        return self._leave("Obrigado.", 0.5)

    def _after_stock(self, o: Obs) -> Step:
        r = self.rng
        if not self.coupon_tried and r.random() < self.cfg["p_knows"]:
            self.phase = "coupon"
            code = r.choice(list(CUPONS)) if r.random() > 0.2 else "BLACK50"
            return self._say(f"Tenho o cupom {code}, aplica pra mim?")
        self.phase = "decide"
        return self._decide(coupon=False)

    def _decide(self, coupon: bool) -> Step:
        r, cfg = self.rng, self.cfg
        p = cfg["p_buy"]
        if self.picked_price:
            eff = self.picked_price * (1 - self.pct / 100)
            if eff > self.budget * 1.25:
                p *= 0.35
            elif eff <= self.budget:
                p = min(0.97, p * 1.1)
        if self.persona == "Caçador de desconto":
            p = cfg["p_buy"] if coupon else 0.15
        if r.random() < p:
            self.phase = "decide"
            return self._say("Pode fechar, quero levar" + (" com o cupom" if coupon else ""))
        return self._leave(r.choice(["Vou pensar e depois eu volto.", "Hmm, preciso ver com a família, depois falo.",
                                     "Ainda estou em dúvida, obrigado."]), 0.3)
