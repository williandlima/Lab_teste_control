-- Torna (board_id, name) único em test_parameter_configs, para que "Salvar"
-- uma configuração com o mesmo nome sobrescreva o registro existente em vez
-- de duplicá-lo (mesma lógica do "Ctrl+S" sobre o mesmo arquivo do Word).
--
-- Bancos já em campo podem ter duplicatas herdadas do comportamento antigo
-- (cada Salvar fazia um INSERT novo). Antes de criar o índice único:
--   1. Reapontamos test_sessions.test_parameter_config_id que referenciava
--      uma duplicata para a versão mais recente (maior id) do mesmo
--      (board_id, name), preservando o vínculo do histórico.
--   2. Removemos as duplicatas mais antigas, mantendo só a mais recente.

UPDATE test_sessions
SET test_parameter_config_id = (
    SELECT MAX(tpc.id)
    FROM test_parameter_configs AS tpc
    JOIN test_parameter_configs AS cur ON cur.id = test_sessions.test_parameter_config_id
    WHERE tpc.board_id IS cur.board_id AND tpc.name = cur.name
)
WHERE test_parameter_config_id IS NOT NULL;

DELETE FROM test_parameter_configs
WHERE id NOT IN (
    SELECT MAX(id) FROM test_parameter_configs GROUP BY board_id, name
);

CREATE UNIQUE INDEX idx_test_parameter_configs_board_name
    ON test_parameter_configs (board_id, name);
