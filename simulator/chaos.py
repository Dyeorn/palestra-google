"""Plugin de caos: só faz sentido no modo real (Gemini de verdade).

No modo offline a lentidão é simulada pelo próprio SimContext; aqui, com o modelo
real, precisamos de lentidão REAL (sleep) para o plugin de telemetria medir.
Deve vir DEPOIS do TelemetryPlugin na lista, para a espera entrar na latência medida.
"""
from __future__ import annotations

import asyncio

from google.adk.plugins.base_plugin import BasePlugin

from plugin import simctx


class ChaosPlugin(BasePlugin):
    def __init__(self):
        super().__init__(name="caos")

    async def before_model_callback(self, *, callback_context, llm_request):
        ctx = simctx.current()
        if ctx and ctx.chaos and not ctx.simulate_latency:
            await asyncio.sleep(ctx.rng.uniform(2.5, 7.0))
        return None

    async def before_tool_callback(self, *, tool, tool_args, tool_context):
        ctx = simctx.current()
        if ctx and ctx.chaos and not ctx.simulate_latency:
            await asyncio.sleep(ctx.rng.uniform(1.0, 4.0))
        return None
