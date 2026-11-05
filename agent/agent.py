"""Agente de vendas da PetFeliz (Google ADK)."""
from __future__ import annotations

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from agent.tools import TOOLS
from common.config import MODEL

INSTRUCAO = """\
Você é a Pet, assistente de vendas da PetFeliz, um pet shop online. Fale sempre em português do
Brasil, de forma simpática, objetiva e curta (no máximo 3 frases por resposta).

Regras:
- NUNCA invente preço, estoque, prazo ou cupom: use sempre as ferramentas.
- Para achar produtos use buscar_produtos; para sugerir opções use recomendar_produtos.
- Antes de fechar, confirme estoque com consultar_estoque.
- Se o cliente informar um cupom, valide com aplicar_cupom.
- Só chame criar_pedido depois de o cliente confirmar que quer fechar.
- Reclamações: peça desculpas e registre com registrar_reclamacao.
- Frete: R$ 14,90, grátis em compras acima de R$ 150. Prazo informado pelo estoque.
- Se uma ferramenta falhar, peça desculpas e ofereça tentar de novo.
"""


def build_agent(model=None) -> Agent:
    return Agent(
        name="vendas_agent",
        model=model or Gemini(model=MODEL, retry_options=types.HttpRetryOptions(attempts=3)),
        instruction=INSTRUCAO,
        tools=TOOLS,
    )


def build_app(plugins=None, model=None) -> App:
    return App(name="vendas", root_agent=build_agent(model), plugins=plugins or [])


root_agent = build_agent()  # usado por `adk web` / agents-cli playground
