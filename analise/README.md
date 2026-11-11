# Análise

Scripts em Python que transformam as saídas brutas das simulações em métricas, relatórios
de validação e figuras. Todos importam `config.py`, que centraliza os caminhos, os pontos
(K01…K14, N01…N14), os rótulos e as cores. O uso detalhado está em
[`docs/como-rodar.md`](../docs/como-rodar.md).

| Script | Função | Precisa de saídas brutas |
|---|---|---|
| `config.py` | caminhos, pontos, rótulos e cores | — |
| `estatistica.py` | IC95 da média com o quantil t de Student (n − 1 graus de liberdade) | — |
| `validar_run.py` | integridade de uma execução | sim |
| `publicar_manifest.py` | define a amostra de um ponto (`run_manifest.csv`) | sim |
| `agregar_metricas.py` | métricas por execução, por aplicação e do ponto | sim |
| `validar_saidas.py` | validação contra o modelo, escala de clientes | sim |
| `validar_saidas_misto.py` | validação contra o modelo, densidade de GPU | sim |
| `plotar_metricas.py` | latência, vazão e falha por execução de um ponto | não |
| `plotar_breakdown.py` | FRTT decomposto em processamento e rede | não |
| `plotar_falhas_por_app.py` | dispositivos e falhas por aplicação, uma execução | sim |
| `plotar_mobilidade.py` | concentração de dispositivos por ponto de acesso | sim |
| `plotar_curva_densidade_gpu.py` | latência, rede e falha contra K | não¹ |
| `plotar_curva_escala_clientes.py` | latência, rede e falha contra N | não¹ |
| `plotar_densidade_percentis.py` | média e percentis contra K | não |
| `plotar_sintese_densidade.py` | variação a cada GPU acrescentada | não |
| `plotar_retorno_decrescente.py` | vazão e ganho marginal por GPU | sim |
| `plotar_isolamento_apps.py` | efeito da saturação da GPU nas aplicações de CPU | não |
| `plotar_falhas_por_app_agregado.py` | falha por aplicação e por causa, com IC95 | não |
| `plotar_multi_latencia.py` | latência e falha do YOLO por semente, vários pontos | parcial² |
| `plotar_distribuicao_latencia.py` | CDF e percentis por tarefa | registro por tarefa |
| `plotar_conservacao_fluxo.py` | taxa ofertada, servida e perdida | não¹ |
| `plotar_dispersao_falha_latencia.py` | regimes de saturação pela correlação entre falha e latência | não |
| `plotar_ocupacao_temporal.py` | série temporal do `VM_LOAD` | sim |

¹ Onde faltam as saídas brutas, usam-se os valores já publicados (a tabela da série ou o
`metrics_runs.csv` do ponto), sem perdê-los. ² Nos pontos de carga mista, a latência do YOLO por execução exige as saídas
brutas.
