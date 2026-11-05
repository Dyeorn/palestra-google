"""LLM scriptado para o modo --offline (sem chave de API).

É um `BaseLlm` de verdade: passa pelo Runner e pelos callbacks do plugin como o Gemini
passaria. Decide chamadas de ferramenta por regras simples e monta respostas em pt-BR.
Latências/tokens são simulados e reportados ao plugin via `simctx`.
"""
from __future__ import annotations

import re
from typing import AsyncGenerator

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from agent import catalog as cat
from plugin import simctx
from plugin.classifiers import norm

ORDINAIS = {"primeiro": 0, "primeira": 0, "1": 0, "segundo": 1, "segunda": 1, "2": 1,
            "terceiro": 2, "terceira": 2, "3": 2, "quarto": 3, "quarta": 3, "4": 3}
RE_FECHAR = r"fecha|finaliz|vou levar|quero levar|confirm|pode fazer o pedido|fechamos"
RE_ESTOQUE = r"estoque|dispon|tem pronta"
RE_RECOM = r"recomend|indica|sugest|qual (e )?(o )?melhor|diferenca|compar|outro parecido|outra opcao"
RE_RECL = r"reclam|absurdo|chegou errado|defeito|estragou|nao chegou|atrasou"
RE_ADEUS = r"obrigad|vou pensar|tchau|deixa pra la|desist|vou embora|ate mais|depois eu volto|vou ver em outro"


def _tok(text: str) -> int:
    return max(1, int(len(text) / 3.6))


def _text_of(content: types.Content) -> str:
    return " ".join(p.text for p in (content.parts or []) if p.text)


def _brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class FakeSalesLlm(BaseLlm):
    model: str = "fake-vendas-offline"

    # ------------------------------------------------------------ decisões
    def _history(self, contents):
        cands, chosen, coupon = [], None, ""
        for c in contents:
            for p in c.parts or []:
                if p.function_response and p.function_response.response:
                    r = p.function_response.response
                    if r.get("produtos"):
                        cands = r["produtos"]
                    if p.function_response.name == "aplicar_cupom" and r.get("valido"):
                        coupon = r["codigo"]
                if p.function_call and p.function_call.name == "consultar_estoque":
                    chosen = (p.function_call.args or {}).get("produto_id")
        return cands, chosen, coupon

    def _pick(self, text: str, cands, chosen):
        t = norm(text)
        for w, i in ORDINAIS.items():
            if re.search(rf"\b{w}\b", t) and i < len(cands):
                return cands[i]["id"]
        if cands and re.search(r"barato|menor preco", t):
            return min(cands, key=lambda p: p["preco"])["id"]
        if chosen:
            return chosen
        return cands[0]["id"] if cands else None

    def _decide(self, contents, user_text: str):
        t = norm(user_text)
        cands, chosen, coupon = self._history(contents)
        code = next((c for c in re.findall(r"[A-Z0-9]{4,}", user_text.upper())
                     if c in cat.CUPONS or re.fullmatch(r"[A-Z]{3,}\d{1,3}", c)), None)
        pid = self._pick(user_text, cands, chosen)
        especie = "gato" if re.search(r"gat", t) else "cachorro"
        if code and code not in (coupon,):
            return ("call", "aplicar_cupom", {"codigo": code})
        if re.search(RE_RECL, t):
            return ("call", "registrar_reclamacao", {"descricao": user_text[:200], "categoria": "geral"})
        if re.search(RE_FECHAR, t) and pid:
            args = {"produto_ids": [pid], "quantidades": [1]}
            if coupon:
                args["cupom"] = coupon
            return ("call", "criar_pedido", args)
        if re.search(RE_ESTOQUE, t) and pid:
            return ("call", "consultar_estoque", {"produto_id": pid})
        if re.search(RE_RECOM, t):
            return ("call", "recomendar_produtos", {"especie": especie, "necessidade": user_text[:120]})
        if re.search(r"prazo|entrega|frete", t):
            if pid:
                return ("call", "consultar_estoque", {"produto_id": pid})
            return ("text", "O frete é R$ 14,90 e fica grátis acima de R$ 150. O prazo depende do produto: "
                            "me diga qual você quer que eu consulto.")
        if re.search(RE_ADEUS, t):
            return ("text", "Obrigada pelo contato! Se precisar, é só chamar a PetFeliz. 🐾")
        if re.search(r"cupom|desconto|promoc", t) and not cands:
            return ("text", "Temos cupons ativos! Se você tiver um código, me passe que eu valido. "
                            "Mas antes, o que você procura para o seu pet?")
        if re.search(r"cupom|desconto|promoc", t):
            return ("text", "Se você tiver um código de cupom, me passe que eu valido na hora.")
        if re.search(r"^(oi|ola|bom dia|boa tarde|boa noite)[!. ]*$", t):
            return ("text", "Oi! Sou a Pet, da PetFeliz. O que você procura para o seu pet hoje?")
        return ("call", "buscar_produtos", {"consulta": user_text[:120]})

    def _after_tool(self, name: str, r: dict) -> str:
        if r.get("status") == "error":
            return ("Desculpe, tive um problema técnico ao consultar o sistema agora. "
                    "Quer que eu tente de novo?")
        if name in ("buscar_produtos", "recomendar_produtos"):
            ps = r.get("produtos") or []
            if not ps:
                return "Não encontrei isso no catálogo. Pode me dar mais detalhes do que procura?"
            linhas = "; ".join(f"{i}. {p['nome']} ({_brl(p['preco'])})" for i, p in enumerate(ps, 1))
            return f"Encontrei estas opções: {linhas}. Qual delas te interessa?"
        if name == "consultar_estoque":
            if not r.get("em_estoque"):
                return "Esse produto está sem estoque no momento. Posso recomendar outro parecido?"
            return (f"Temos {r['nome']} em estoque por {_brl(r['preco'])}, com entrega em até "
                    f"{r['prazo_dias']} dias. Quer fechar o pedido?")
        if name == "aplicar_cupom":
            if r.get("valido"):
                return f"Cupom {r['codigo']} aplicado: {r['desconto_pct']}% de desconto! Posso fechar o pedido?"
            return "Esse cupom não é válido. Quer tentar outro código ou seguir sem desconto?"
        if name == "criar_pedido":
            if r.get("motivo") == "sem_estoque":
                return "Poxa, esse item acabou de esgotar. Posso sugerir outro?"
            if not r.get("pedido_id"):
                return "Não consegui criar o pedido. Pode confirmar o produto?"
            return (f"Pedido {r['pedido_id']} confirmado! Total {_brl(r['total'])} "
                    f"(frete {_brl(r['frete'])}), chega em até {r['prazo_dias']} dias. Obrigada! 🐶")
        if name == "registrar_reclamacao":
            return f"Sinto muito pelo transtorno. Registrei sua reclamação, protocolo {r['protocolo']}."
        return "Pronto! Posso ajudar em mais alguma coisa?"

    # ------------------------------------------------------------ interface
    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False
                                     ) -> AsyncGenerator[LlmResponse, None]:
        ctx = simctx.current()
        contents = llm_request.contents
        if ctx is not None and ctx.model_fails():
            simctx.report_latency("model", ctx.model_latency(10)[0])
            raise simctx.ModelUnavailable("503 UNAVAILABLE: o modelo está sobrecarregado, tente novamente")

        last = contents[-1]
        fr = [p.function_response for p in last.parts or [] if p.function_response]
        if fr:
            text = self._after_tool(fr[0].name, fr[0].response or {})
            parts = [types.Part(text=text)]
        else:
            kind, *rest = self._decide(contents, _text_of(last))
            if kind == "call":
                parts = [types.Part(function_call=types.FunctionCall(name=rest[0], args=rest[1]))]
                text = rest[0] + str(rest[1])
            else:
                text = rest[0]
                parts = [types.Part(text=text)]

        # tokens (estimados): entrada = prompt do sistema + ferramentas + histórico inteiro
        sys_txt = str(getattr(llm_request.config, "system_instruction", "") or "")
        tin = _tok(sys_txt) + 700 + sum(_tok(str(c.parts)) for c in contents)
        tin += ctx.prompt_extra_tokens if ctx else 0
        tout = _tok(text)
        if ctx is not None:
            total, ttft = ctx.model_latency(tout)
            simctx.report_latency("model", total, ttft)
        usage = types.GenerateContentResponseUsageMetadata(
            prompt_token_count=tin, candidates_token_count=tout, total_token_count=tin + tout)
        if stream and parts[0].text:
            half = text[: len(text) // 2]
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=half)]), partial=True)
        yield LlmResponse(content=types.Content(role="model", parts=parts), usage_metadata=usage,
                          finish_reason=types.FinishReason.STOP, partial=False)
