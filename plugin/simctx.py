"""Contexto de simulação (opcional).

Fora do simulador não existe SimContext: o plugin usa relógio e medições reais.
No simulador ele permite (1) timestamps retroativos, (2) latências simuladas no
modo offline e (3) injeção de falhas (caos / incidentes).
"""
from __future__ import annotations

import contextlib
import contextvars
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from common.config import now_local

# Falhas "de base" por ferramenta (probabilidade por chamada, antes de carga/incidente)
BASE_TOOL_FAIL = {
    "buscar_produtos": 0.015, "consultar_estoque": 0.05, "recomendar_produtos": 0.02,
    "aplicar_cupom": 0.03, "criar_pedido": 0.035, "registrar_reclamacao": 0.01,
}
BASE_TOOL_LATENCY_MS = {
    "buscar_produtos": 140, "consultar_estoque": 110, "recomendar_produtos": 220,
    "aplicar_cupom": 70, "criar_pedido": 320, "registrar_reclamacao": 160,
}
CHAOS_TOOL_FAIL = 0.45
CHAOS_LATENCY_MULT = 3.4


class ModelUnavailable(RuntimeError):
    """Erro de modelo simulado (equivalente a um 503 do endpoint)."""


@dataclass
class SimContext:
    start: datetime
    rng: random.Random
    simulate_latency: bool = True      # True = offline (não dorme, só reporta)
    load: float = 0.0                  # 0..1: quão perto do pico de horário
    chaos: bool = False
    latency_mult: float = 1.0          # incidentes (ex.: degradação do provedor)
    tool_fail_extra: dict = field(default_factory=dict)  # incidentes por ferramenta
    prompt_extra_tokens: int = 0       # "crescimento do prompt" ao longo dos dias
    think_scale: float = 1.0           # tempo de reflexão do cliente entre turnos
    offset_ms: float = 0.0
    turn_ms: float = 0.0
    pending: dict = field(default_factory=dict)

    # --- amostragem --------------------------------------------------------
    def _ln(self, sigma: float) -> float:
        return math.exp(self.rng.gauss(0, sigma))

    def model_latency(self, out_tokens: int) -> tuple[float, float]:
        mult = (1 + 1.4 * self.load) * self.latency_mult * self._ln(0.4)
        if self.rng.random() < 0.02:   # picos ocasionais do provedor
            mult *= 3.5
        if self.chaos:
            mult *= CHAOS_LATENCY_MULT * (2.0 if self.rng.random() < 0.25 else 1.0)
        total = (330 + 4 * out_tokens) * mult
        ttft = (220 * mult) * self._ln(0.2)
        return total, min(ttft, total)

    def tool_latency(self, name: str) -> float:
        mult = (1 + 0.5 * self.load) * self._ln(0.4) * (CHAOS_LATENCY_MULT if self.chaos else 1)
        return BASE_TOOL_LATENCY_MS.get(name, 150) * mult * (self.latency_mult ** 0.5)

    def tool_fails(self, name: str) -> bool:
        p = BASE_TOOL_FAIL.get(name, 0.02) * (1 + 0.8 * self.load)
        p += self.tool_fail_extra.get(name, 0.0)
        if self.chaos:
            p = max(p, CHAOS_TOOL_FAIL)
        return self.rng.random() < min(p, 0.95)

    def model_fails(self) -> bool:
        p = 0.012 * (1 + self.load) + (0.12 if self.chaos else 0)
        return self.rng.random() < p


_current: contextvars.ContextVar[SimContext | None] = contextvars.ContextVar("simctx", default=None)


def current() -> SimContext | None:
    return _current.get()


def set_current(ctx: SimContext | None) -> None:
    _current.set(ctx)


@contextlib.contextmanager
def use(ctx: SimContext):
    tok = _current.set(ctx)
    try:
        yield ctx
    finally:
        _current.reset(tok)


def clock() -> datetime:
    ctx = _current.get()
    if ctx is None:
        return now_local()
    return ctx.start + timedelta(milliseconds=ctx.offset_ms)


def report_latency(kind: str, ms: float, ttft: float | None = None) -> None:
    """Quem simula (LLM fake / ferramentas) informa a latência que o plugin deve registrar."""
    ctx = _current.get()
    if ctx is not None and ctx.simulate_latency:
        ctx.pending.setdefault(kind, []).append((ms, ttft))


def pop_latency(kind: str) -> tuple[float, float | None] | None:
    ctx = _current.get()
    if ctx is None:
        return None
    q = ctx.pending.get(kind)
    return q.pop(0) if q else None


def advance(ms: float) -> None:
    ctx = _current.get()
    if ctx is not None:
        ctx.offset_ms += ms
        ctx.turn_ms += ms
