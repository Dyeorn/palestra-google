# Schema (SQLite) — `plugin/schema.sql`

Datas em texto `YYYY-MM-DD HH:MM:SS`, horário da loja. `converted`, `resolved`, `success`, `finalizada` = 0/1.

| Tabela | Colunas |
|---|---|
| `conversations` | conversation_id (PK), user_id, persona, started_at, ended_at, turns, intent, max_stage, converted, abandon_reason, sentiment (−1..1), resolved, cost_brl, **finalizada** |
| `model_calls` | conversation_id, called_at, input_tokens, output_tokens, latency_ms, ttft_ms, status (`ok`/`error`), **error_message** |
| `tool_calls` | conversation_id, called_at, tool_name, success, latency_ms, error_message, **args_json** |
| `orders` | order_id (PK), conversation_id, created_at, total_brl, coupon_code |
| `order_items` | order_id, product_name, quantity |
| `product_mentions` | conversation_id, product_name (PK composta) |
| **`agent_errors`** | conversation_id, occurred_at, origem, error_message — execução do agente interrompida |
| **`controle`** | chave, valor — hoje só `caos` (`1`/`0`), escrita pelo botão do dashboard |

Em **negrito**: acrescentado ao schema do documento de handoff.

`max_stage`: `iniciou` < `buscou` < `recomendado` < `carrinho` < `pedido`.
Motivos de abandono: Preço alto, Sem estoque, Indeciso, Demora na resposta, Erro do sistema, Frete/prazo.
Intenções: Comprar produto, Consultar preço, Pedir recomendação, Usar cupom/desconto, Dúvida de entrega, Reclamação.

A conversa é gravada (upsert) ao fim de cada turno e marcada `finalizada = 1` quando o host a encerra.
