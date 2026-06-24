"""Gerência de conexão SQLite: modo WAL, migrações versionadas, batch insert.

A conexão é a fonte de verdade para dados de longa duração (seção 10): o
estado em memória (buffer circular) é só para exibição, nunca para
persistência. `executemany_batch` existe especificamente para que o
monitoramento contínuo nunca faça um INSERT por amostra.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


class Database:
    """Wrapper fino sobre `sqlite3.Connection` com migrações e modo WAL."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._connection: sqlite3.Connection | None = None

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("Database.connect() ainda não foi chamado.")
        return self._connection

    def connect(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL;")
        self._connection.execute("PRAGMA foreign_keys=ON;")
        self._connection.execute("PRAGMA synchronous=NORMAL;")
        self._apply_migrations()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _apply_migrations(self) -> None:
        """Aplica os arquivos .sql de `migrations/` ainda não aplicados.

        Cada arquivo `NNN_*.sql` corresponde à versão de schema NNN.
        `PRAGMA user_version` registra a última versão aplicada, evitando
        reaplicar migrações em bancos já existentes em campo.
        """
        current_version = self.connection.execute("PRAGMA user_version;").fetchone()[0]
        migration_files = sorted(_MIGRATIONS_DIR.glob("*.sql"))

        for migration_file in migration_files:
            version = int(migration_file.name.split("_", 1)[0])
            if version <= current_version:
                continue
            script = migration_file.read_text(encoding="utf-8")
            self.connection.executescript(script)
            self.connection.execute(f"PRAGMA user_version = {version};")
            self.connection.commit()

    def executemany_batch(self, sql: str, rows: list[tuple]) -> None:
        """Insere/atualiza em lote (ex. amostras de monitoramento)."""
        if not rows:
            return
        self.connection.executemany(sql, rows)
        self.connection.commit()
