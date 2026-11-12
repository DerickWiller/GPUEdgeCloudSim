# Experimentos

Cada experimento responde a uma pergunta e varia uma única grandeza. Cada ponto é uma
pasta com a configuração lida pelo simulador e os resultados agregados da sua amostra.

| Experimento | Pergunta | Variável | Pontos |
|---|---|---|---|
| [`densidade-gpu/`](densidade-gpu/) | Quantos servidores de borda precisam ter GPU? | K servidores com GPU entre 14, com 9 clientes YOLO | K01, K02, K03, K07, K14 |
| [`escala-clientes/`](escala-clientes/) | Quantos clientes uma GPU atende? | N clientes YOLO sobre uma RTX 3050 | N01, N04, N06, N08, N09, N10, N12, N14 |
| [`dois-servidores/`](dois-servidores/) | A partir de quantos clientes compensa a GPU remota, pela MAN? | N clientes YOLO num ponto de acesso, duas políticas | `local/`, `rodizio/` × N01…N14 |
| [`cameras-fixas/`](cameras-fixas/) | A MAN alivia um ponto de acesso sobrecarregado sem penalizar os demais? | h câmeras YOLO no ponto quente, três políticas | `local/`, `rodizio/`, `local-primeiro/` × h = 2, 4, 6, 8, 9 |
| [`comparativos/`](comparativos/) | Figuras que reúnem a escala de clientes e a densidade de GPU | — | — |

## Estrutura de um ponto

```
<experimento>/<ponto>/
├── config.properties      parâmetros da simulação
├── edge_devices.xml       infraestrutura de borda
├── applications.xml       carga
└── resultados/
    ├── run_manifest.csv   execuções que formam a amostra, com status e SHA-256
    ├── metrics_runs.csv   uma linha por execução
    ├── metrics_summary.csv  média, desvio e IC95 do ponto
    ├── metrics_by_app.csv   média, desvio e IC95 por aplicação
    ├── validacao.md       relatório da validação contra o modelo
    └── figuras/
```

Os três arquivos de configuração são gerados por [`gerar_configs.py`](gerar_configs.py);
alterações devem ser feitas nele. Cada experimento é descrito também por `cenario.json`,
formato lido por [`gerar_cenario.py`](gerar_cenario.py), que gera os experimentos novos
(inclusive os criados pela interface, `docs/interface.md`) e confere que a descrição dos
publicados reproduz os valores versionados (`--conferir-todos`). As saídas brutas de cada execução ficam em
`saidas/<experimento>/<ponto>/`, fora do controle de versão.
