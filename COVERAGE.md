# Cobertura: o que é "também no BQ" e o que é "exclusivo"

Fonte única: [`coverage.json`](coverage.json) (a API e o dashboard leem dele; o contador do topo é calculado dali).
O plugin oficial `BigQueryAgentAnalyticsPlugin` **não é usado**; é só referência. A classificação é uma leitura da
documentação (tokens, latência, tempo até o 1º token, eventos e erros de tool/modelo existem lá; intenção, sentimento,
conversão, pedido, receita, produto, cupom e custo em reais não). **A validar** com a lista completa de payloads.

| # | Painel | Rótulo | Cobre |
|---|---|---|---|
| 1 | Conversas por dia e horários de pico | Também no plugin do BQ | Volume de conversas |
| 2 | Tempo até a primeira resposta | Também no plugin do BQ | Latência do modelo, Tempo até a primeira resposta |
| 3 | Ferramentas que mais falham | Também no plugin do BQ | Uso de ferramentas, Latência das ferramentas, Erros de ferramentas, Erros do modelo e do agente |
| 4 | Tokens por conversa | Também no plugin do BQ | Tokens consumidos, Turnos por conversa |
| 5 | Funil de vendas | Exclusivo do nosso plugin | Conversão e funil de vendas |
| 6 | Motivos de abandono | Exclusivo do nosso plugin | Motivo de abandono |
| 7 | Custo por conversa e por venda | Exclusivo do nosso plugin | Custo estimado, Pedidos e receita |
| 8 | Produtos, cupons e perfil do cliente | Exclusivo do nosso plugin | Produtos mais citados, Cupons usados, Ticket médio, Perfil do cliente |
| 9 | Intenção, resolução e sentimento | Exclusivo do nosso plugin | Intenção do cliente, Conversa resolvida, Sentimento |
| 10 | Venda perdida por lentidão ou erro | Exclusivo do nosso plugin | Conversão por faixa de latência, Conversão com e sem erro |

Contagem: 4 também no BQ · 6 exclusivos.

Para mudar um rótulo, edite só o `coverage.json`.
