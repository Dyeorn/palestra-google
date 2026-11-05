-- Schema do SQLite local (ver SCHEMA.md). Datas: texto 'YYYY-MM-DD HH:MM:SS', horário da loja.
CREATE TABLE IF NOT EXISTS conversations (
  conversation_id TEXT PRIMARY KEY,
  user_id TEXT, persona TEXT,
  started_at TEXT, ended_at TEXT, turns INTEGER DEFAULT 0,
  intent TEXT,
  max_stage TEXT DEFAULT 'iniciou',      -- iniciou|buscou|recomendado|carrinho|pedido
  converted INTEGER DEFAULT 0,
  abandon_reason TEXT,
  sentiment REAL, resolved INTEGER DEFAULT 0,
  cost_brl REAL DEFAULT 0,
  finalizada INTEGER DEFAULT 0           -- 1 quando o host encerrou a conversa
);
CREATE TABLE IF NOT EXISTS model_calls (
  conversation_id TEXT, called_at TEXT,
  input_tokens INTEGER, output_tokens INTEGER,
  latency_ms REAL, ttft_ms REAL,
  status TEXT,                           -- ok|error
  error_message TEXT
);
CREATE TABLE IF NOT EXISTS tool_calls (
  conversation_id TEXT, called_at TEXT, tool_name TEXT,
  success INTEGER, latency_ms REAL, error_message TEXT, args_json TEXT
);
CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY, conversation_id TEXT, created_at TEXT,
  total_brl REAL, coupon_code TEXT
);
CREATE TABLE IF NOT EXISTS order_items (
  order_id TEXT, product_name TEXT, quantity INTEGER
);
CREATE TABLE IF NOT EXISTS product_mentions (
  conversation_id TEXT, product_name TEXT,
  PRIMARY KEY (conversation_id, product_name)
);
CREATE TABLE IF NOT EXISTS agent_errors (  -- falhas da execução do agente (não do modelo/tool)
  conversation_id TEXT, occurred_at TEXT, origem TEXT, error_message TEXT
);
CREATE TABLE IF NOT EXISTS controle (      -- chave/valor: botão "ativar caos" do dashboard
  chave TEXT PRIMARY KEY, valor TEXT
);
CREATE INDEX IF NOT EXISTS ix_conv_started ON conversations(started_at);
CREATE INDEX IF NOT EXISTS ix_model_conv ON model_calls(conversation_id);
CREATE INDEX IF NOT EXISTS ix_tool_conv ON tool_calls(conversation_id);
