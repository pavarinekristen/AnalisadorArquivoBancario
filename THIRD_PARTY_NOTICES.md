# Componentes de terceiros

| Componente | Versão | Licença |
|---|---|---|
| Python | 3.11+ (instalador: 3.12) | PSF License |
| Streamlit | 1.65.0 | Apache-2.0 |
| pandas | 3.0.6 | BSD-3-Clause |
| openpyxl | 3.1.5 | MIT |
| PyYAML | 6.0.3 | MIT |
| keyring | 25.7.0 | MIT |

As dependências indiretas (numpy, pyarrow, tornado, altair, pillow etc.) vêm com o Streamlit e o pandas e usam
licenças permissivas (BSD, MIT, Apache-2.0, HPND). A lista completa sai de `pip-licenses` no ambiente de build.

A tabela de códigos de ocorrência (`regras/ocorrencias.yaml`) segue o layout FEBRABAN CNAB 240 e os manuais
dos bancos.
