-- Rastreabilidade do ensaio: identidade da fonte (*IDN?) e versão do software
-- usadas no momento do teste, gravadas na própria sessão (congeladas no
-- histórico). A calibração/patrimônio do instrumento entram no
-- config_snapshot_json (também congelado), vindos de config/app_config.yaml.
ALTER TABLE test_sessions ADD COLUMN instrument_identity TEXT;
ALTER TABLE test_sessions ADD COLUMN app_version TEXT;
