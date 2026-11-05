# Demo: agente de vendas + plugin de telemetria + dashboard

Projeto de palestra, 100% local. O foco é o **dashboard**: cada painel traz o rótulo
**"Também no plugin do BQ"** (contorno azul) ou **"Exclusivo do nosso plugin"** (contorno laranja).

```
/agent       agente PetFeliz (pet shop fictício) em Google ADK: 6 tools, catálogo de 40 produtos
/plugin      TelemetryPlugin (herda de BasePlugin): grava técnica + negócio em SQLite
/simulator   clientes sintéticos que conversam com o agente de verdade (Runner do ADK) + modo --chaos
/api         FastAPI: /api/paineis/{id}, /api/coverage, /api/caos
/dashboard   HTML/JS puro (SVG próprio, sem dependências, funciona offline)
coverage.json  fonte única de rótulos, ordem e origem de cada painel
```

## Rodar (3 comandos)

```bash
uv sync
uv run python -m simulator.run --reset      # 400 conversas em 30 dias (~30 s)
uv run uvicorn api.main:app --port 8000     # abrir http://localhost:8000
```

Na hora da palestra, em outro terminal:

```bash
uv run python -m simulator.run --live       # tráfego contínuo; o dashboard atualiza a cada 4 s
```

No dashboard, o botão **Ativar caos** (painel 10) liga erro de ferramenta + lentidão no simulador
(`--live` lê a chave `caos` na tabela `controle` a cada conversa); a linha de conversão por minuto cai ao vivo.
Também dá para já começar com caos: `--live --chaos`.

### Com o Gemini de verdade

Coloque `GEMINI_API_KEY` no `.env` (copie de `.env.example`) e use `--modelo real` (é o padrão quando há chave).
Sem chave, o simulador usa **`--modelo offline`**: um `BaseLlm` scriptado (`agent/fake_llm.py`) que passa pelo mesmo
Runner, pelas mesmas tools e pelo mesmo plugin; só as latências e os tokens são simulados.
Teste em modo real (chave) **não foi executado** neste ambiente — ver "Pendências".

## Suposições (o que foi assumido para manter simples)

| Tema | Decisão |
|---|---|
| Segmento | Pet shop "PetFeliz" (ração, petisco, brinquedo, higiene, cama, acessório) |
| Dashboard | HTML/JS puro servido pela própria API (nada para compilar; fácil de explicar no palco) |
| Escopo do agents-cli | O scaffold (`agents-cli create vendas-agent --adk -s -y`) foi gerado e usado como referência (string do modelo, estrutura do `Agent`/`App`). O projeto roda com um único `pyproject.toml` na raiz; deploy/Terraform do scaffold não foram trazidos. Os flags do documento de handoff (`scaffold create ... --agent adk --prototype`) **não** correspondem ao CLI v1.13.0: o comando real é `create`. |
| "Carrinho" | O agente não tem tool de carrinho. A etapa "carrinho" = cliente pediu estoque de um item ou validou cupom |
| Fim da conversa | O host chama `plugin.finalize_conversation(id)`. Em produção seria um timeout de inatividade |
| Perfil do cliente | Vem de `session.state["perfil"]` (em produção, CRM). O plugin não adivinha perfil |
| Intenção / sentimento / resolvida / motivo de abandono | Regras e léxico em `plugin/classifiers.py` (transparentes). Podem virar chamada a LLM |
| Motivo de abandono | Telemetria primeiro (erro de tool/modelo → "Erro do sistema"; turno > 3 s → "Demora"; sem estoque), depois texto do cliente (frete, preço), senão "Indeciso" |
| Fuso | Datas gravadas em horário da loja (`TZ_NAME`), texto `YYYY-MM-DD HH:MM:SS` |
| Falhas | Tools devolvem `{"status": "error"}` para falha técnica (conta como erro de ferramenta). "Sem estoque" é regra de negócio, não erro. Erro do modelo propaga e vira "erro do agente" |
| Custo | tokens × preço por 1 M tokens (`.env`). **Preços do `.env.example` são exemplos, não preço oficial** |

### O que o histórico simulado contém de propósito

Para o dashboard ter o que mostrar: picos às 12–13 h e 19–21 h (modelo mais lento nos picos), volume crescendo ao longo
do mês, prompt "crescendo" (+20 tokens/dia), um incidente de estoque + lentidão (há 12 dias) e outro de checkout
(há 5 dias). Os números **não são dados reais**. A relação "lento/erro → menos conversão" não é escrita no banco:
vem do comportamento dos clientes sintéticos (que perdem a paciência), medido pelo plugin.

## Testes

```bash
uv run pytest -q
```

## Pendências (do documento de handoff)

- [ ] Rodar contra o Gemini real (sem chave neste ambiente) e conferir `ttft` com streaming SSE.
- [ ] Confirmar a string do modelo (`MODEL`; o scaffold usa `gemini-3.8-flash`) e os preços por token.
- [ ] Revisar a lista de payloads do plugin do BQ para confirmar o rótulo "exclusivo" de cada conceito.
