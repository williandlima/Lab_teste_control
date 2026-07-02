-- Faixa V/A da fonte escolhida pelo operador para este preset de parâmetros
-- (seção 3.2): NULL = seleção automática (recomendado, deixa
-- PowerSupplyE363x._ensure_range escolher a faixa mais "justa" a cada
-- passo); um nome de faixa (ex.: "LOW"/"HIGH", ver instrument.ranges em
-- app_config.yaml) trava o ensaio inteiro nessa faixa.
ALTER TABLE test_parameter_configs ADD COLUMN range_mode TEXT;
