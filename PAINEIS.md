# Painéis → endpoints

Cada painel é `GET /api/paineis/{id}` e devolve `{id, titulo, pergunta, origem, dados}`.
`titulo`, `pergunta` e `origem` vêm do `coverage.json`; `dados` vem da função de mesmo id em
[`api/paineis.py`](api/paineis.py), onde estão as queries SQL (percentis p50/p95 são calculados em Python).
Renderização: [`dashboard/dash.js`](dashboard/dash.js) (os 10 endpoints alimentam os cards do dashboard).

| # | id | Origem | Tabelas | Gráfico |
|---|---|---|---|---|
| 1 | conversas-por-dia | bq | conversations | linha + mapa de calor (dia da semana × hora) |
| 2 | tempo-primeira-resposta | bq | model_calls | cards p50/p95 + linha por hora, meta `TTFT_META_MS` |
| 3 | falhas-ferramentas | bq | tool_calls, model_calls, agent_errors | barras de taxa de erro + cards de erros do modelo/agente |
| 4 | tokens-por-conversa | bq | model_calls, conversations | área empilhada (entrada/saída) + linha por conversa |
| 5 | funil-vendas | exclusivo | conversations | funil de 5 etapas; maior queda em vermelho |
| 6 | motivos-abandono | exclusivo | conversations | barras horizontais |
| 7 | custo-por-venda | exclusivo | conversations, orders | 4 cards + receita e custo por dia |
| 8 | produtos-cupons-perfil | exclusivo | product_mentions, order_items, orders | citados vs vendidos, cupom por perfil, cupons |
| 9 | intencao-resolucao-sentimento | exclusivo | conversations | barras por intenção + selo de sentimento + linha por dia |
| 10 | venda-perdida | exclusivo (destaque) | conversations, model_calls, tool_calls | conversão por faixa de latência e com/sem erro + linha ao vivo |

Decisão de gráfico: receita e custo (escalas muito diferentes) e tokens por dia vs. por conversa ficam em
gráficos separados, nunca em eixo duplo.

Outros endpoints: `GET /api/coverage`, `GET/POST /api/caos` (`{"ativo": true}`), `GET /api/resumo`.

Smoke test: `for id in $(jq -r '.paineis[].id' coverage.json); do curl -s localhost:8000/api/paineis/$id | head -c 200; echo; done`
