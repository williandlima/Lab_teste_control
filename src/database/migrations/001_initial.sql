-- Schema inicial do FCT Avibras Aeroco.
-- Versionado via PRAGMA user_version (ver database.py); este arquivo
-- corresponde à versão 1. Migrações futuras devem ser arquivos
-- 002_*.sql, 003_*.sql, etc., nunca editar este arquivo após o release.

CREATE TABLE operators (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE boards (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL,
    part_number TEXT NOT NULL,
    revision    TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (code, part_number, revision)
);

CREATE TABLE test_parameter_configs (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    board_id             INTEGER REFERENCES boards(id) ON DELETE SET NULL,
    name                 TEXT NOT NULL,
    nominal_voltage      REAL NOT NULL,
    voltage_min          REAL NOT NULL,
    voltage_max          REAL NOT NULL,
    current_max          REAL NOT NULL,
    test_duration_s      REAL NOT NULL,
    -- Lista de passos [{voltage, current, duration_s}, ...] para sequência
    -- de alimentação com múltiplos passos (seção 3.2). Guardado como JSON
    -- porque o número de passos é variável e não justifica uma tabela própria.
    power_sequence_json  TEXT NOT NULL DEFAULT '[]',
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE test_sessions (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    board_id                  INTEGER NOT NULL REFERENCES boards(id),
    serial_number             TEXT NOT NULL,
    operator_id               INTEGER NOT NULL REFERENCES operators(id),
    test_parameter_config_id  INTEGER REFERENCES test_parameter_configs(id),
    -- Cópia congelada dos parâmetros realmente usados nesta sessão: se o
    -- preset for editado depois, o histórico desta sessão não pode mudar.
    config_snapshot_json      TEXT NOT NULL,
    production_order          TEXT,
    observations              TEXT,
    status                    TEXT NOT NULL DEFAULT 'PENDING',
    started_at                TEXT,
    finished_at               TEXT,
    created_at                TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_test_sessions_board ON test_sessions(board_id);
CREATE INDEX idx_test_sessions_serial ON test_sessions(serial_number);

CREATE TABLE monitored_samples (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    test_session_id   INTEGER NOT NULL REFERENCES test_sessions(id) ON DELETE CASCADE,
    timestamp         TEXT NOT NULL,
    step_index        INTEGER NOT NULL DEFAULT 0,
    voltage_measured  REAL NOT NULL,
    current_measured  REAL NOT NULL
);
CREATE INDEX idx_monitored_samples_session ON monitored_samples(test_session_id);

CREATE TABLE evaluations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    test_session_id   INTEGER NOT NULL UNIQUE REFERENCES test_sessions(id) ON DELETE CASCADE,
    operator_id       INTEGER NOT NULL REFERENCES operators(id),
    -- Preenchido SEMPRE manualmente pelo operador; nunca calculado pelo sistema.
    result            TEXT NOT NULL,
    comment           TEXT,
    evaluated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE event_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    test_session_id   INTEGER REFERENCES test_sessions(id) ON DELETE CASCADE,
    timestamp         TEXT NOT NULL DEFAULT (datetime('now')),
    level             TEXT NOT NULL,
    source            TEXT NOT NULL,
    message           TEXT NOT NULL
);
CREATE INDEX idx_event_log_session ON event_log(test_session_id);
