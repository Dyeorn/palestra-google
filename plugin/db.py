"""SQLite + escritor assíncrono em thread própria (escrita não-bloqueante)."""
from __future__ import annotations

import logging
import queue
import sqlite3
import threading
from pathlib import Path

log = logging.getLogger("telemetria.db")
SCHEMA = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")


def connect(path: str | Path, readonly: bool = False) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript(SCHEMA)
    return con


class Writer:
    """Fila + thread. `submit` nunca bloqueia nem lança: se a fila encher, descarta."""

    def __init__(self, path: str | Path, max_queue: int = 50_000):
        self.path = Path(path)
        self._q: queue.Queue = queue.Queue(maxsize=max_queue)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.dropped = 0

    def _ensure(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._loop, name="telemetria-writer", daemon=True)
            self._thread.start()

    def submit(self, sql: str, params: tuple = ()) -> None:
        try:
            self._ensure()
            self._q.put_nowait((sql, params))
        except Exception:  # fila cheia ou qualquer outra coisa: nunca derruba o agente
            self.dropped += 1

    def flush(self) -> None:
        if self._thread and self._thread.is_alive():
            self._q.join()

    def _loop(self) -> None:
        try:
            con = connect(self.path)
        except Exception:
            log.exception("não consegui abrir o SQLite; telemetria desativada")
            while True:  # esvazia a fila para não travar flush()
                self._q.get()
                self._q.task_done()
        while True:
            batch = [self._q.get()]
            try:
                while len(batch) < 300:
                    batch.append(self._q.get_nowait())
            except queue.Empty:
                pass
            try:
                with con:
                    for sql, params in batch:
                        try:
                            con.execute(sql, params)
                        except Exception:
                            log.exception("falha ao gravar: %s", sql[:60])
            except Exception:
                log.exception("falha no commit")
            finally:
                for _ in batch:
                    self._q.task_done()
