"""Configuração central: lê .env (sem dependências extras) e expõe constantes."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if v:  # valor vazio não sobrescreve nada
            os.environ.setdefault(k.strip(), v)


_load_dotenv()


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


MODEL = os.environ.get("MODEL", "gemini-3.8-flash")
DB_PATH = Path(os.environ.get("DB_PATH", "data/telemetria.db"))
if not DB_PATH.is_absolute():
    DB_PATH = ROOT / DB_PATH
PRICE_IN_USD_1M = _f("PRICE_INPUT_PER_1M_USD", 0.30)
PRICE_OUT_USD_1M = _f("PRICE_OUTPUT_PER_1M_USD", 2.50)
USD_BRL = _f("USD_BRL", 5.50)
TTFT_META_MS = _f("TTFT_META_MS", 2000)
TZ_NAME = os.environ.get("TZ_NAME", "America/Sao_Paulo")
COVERAGE_PATH = ROOT / "coverage.json"


def now_local() -> datetime:
    """Agora, no fuso da loja, sem tzinfo (é assim que gravamos no SQLite)."""
    return datetime.now(ZoneInfo(TZ_NAME)).replace(tzinfo=None)


def has_api_key() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
