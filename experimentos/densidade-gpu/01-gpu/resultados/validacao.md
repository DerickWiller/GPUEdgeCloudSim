# Validação de saídas — 1 de 14 servidores com GPU (K01)

Gerado em 2026-08-10 13:04 · 30 runs · 0 falha(s)

## Topologia

- 14 hosts, 1 GPUs, 112 VMs (1 com GPU)
- 30 dispositivos, 3300s úteis (de 3600s, warm-up 300s)

| App | usa GPU | clientes | interarrival |
|---|---|---|---|
| YOLO_DETECTION | sim | 9 | 0.033s |
| HEALTH_APP | não | 6 | 30.0s |
| HEAVY_COMP_APP | não | 6 | 60.0s |
| INFOTAINMENT_APP | não | 9 | 7.0s |

## Checagens

| | Status | Detalhe |
|---|---|---|
| A1 — conservação de tarefas (todas as apps) | PASS | esperado ≈ 905,233 | observado 905,226.6 (completed+failed+uncompleted) | erro 0.001% |
| A3 — toda falha tem causa atribuída | PASS | falhas médias 82,404.6; bw + vm_capacity + mobility + wlan_range fecha em todos os runs |
| A4 — edge + cloud + mobile = completed | PASS | edge 822,715 | cloud 0 | mobile 0 |
| A2[YOLO_DETECTION] — tarefas geradas (stream contínuo) | PASS | 9 clientes × 3300s ÷ 0.033s = 900,000 | observado 900,000.0 |
| A2[HEALTH_APP] — tarefas geradas | INFO | observado 661.0 (teto contínuo seria 660; a app tem active/idle period, então gerar menos é esperado) |
| A2[HEAVY_COMP_APP] — tarefas geradas | INFO | observado 327.7 (teto contínuo seria 330; a app tem active/idle period, então gerar menos é esperado) |
| A2[INFOTAINMENT_APP] — tarefas geradas | INFO | observado 4,237.9 (teto contínuo seria 4,243; a app tem active/idle period, então gerar menos é esperado) |
| B1[YOLO_DETECTION] — processamento ≥ mínimo físico | PASS | mínimo 4.0000 ms (gpu_length 91 MI ÷ gflops 22750 MI/s) | medido 442.4313 ms | déficit -438.431298 ms de uma folga de 0.0000 ms (exigência estrita (caminho da GPU não trunca MI)) |
| B1[HEALTH_APP] — processamento ≥ mínimo físico | PASS | mínimo 40.0000 ms (task_length 400 MI ÷ (10000 MIPS × 1 core)) | medido 39.9973 ms | déficit +0.002687 ms de uma folga de 0.1000 ms (1 MI ÷ 10000 MIPS = granularidade do CloudSim) |
| B1[HEAVY_COMP_APP] — processamento ≥ mínimo físico | PASS | mínimo 300.0000 ms (task_length 3000 MI ÷ (10000 MIPS × 1 core)) | medido 299.9833 ms | déficit +0.016661 ms de uma folga de 0.1000 ms (1 MI ÷ 10000 MIPS = granularidade do CloudSim) |
| B1[INFOTAINMENT_APP] — processamento ≥ mínimo físico | PASS | mínimo 75.0000 ms (task_length 750 MI ÷ (10000 MIPS × 1 core)) | medido 74.9950 ms | déficit +0.005004 ms de uma folga de 0.1000 ms (1 MI ÷ 10000 MIPS = granularidade do CloudSim) |
| B2 — throughput agregado | INFO | 249.31 tarefas/s = 822,715 completadas ÷ 3300s úteis |
| B3 — ocupação da GPU (YOLO_DETECTION) | PASS | servido 247.72 fps de capacidade 250.00 fps (1 GPUs) = 99.1% de ocupação |
| B4 — demanda vs capacidade (app GPU) | INFO | λ = 272.73 fps (9 clientes ÷ 0.033s) | capacidade 250.00 fps | folga 0.92× |
| B5 — conservação de fluxo (YOLO_DETECTION) | PASS | 1 − throughput/λ = 9.168% | falha medida 9.157% | Δ 0.011 p.p. |
| B8[YOLO_DETECTION] — atraso de rede ≥ piso analítico (contenção ON) | PASS | piso WLAN 3.316667 + PCIe 1.124008 = 4.440675 ms | medido 5.011265 ms | disputa implícita = 1.172 fluxos simultâneos no AP |
| B8[HEALTH_APP] — atraso de rede ≥ piso analítico (contenção ON) | PASS | piso WLAN 21.166667 + PCIe 0.000000 = 21.166667 ms | medido 22.891397 ms | disputa implícita = 1.081 fluxos simultâneos no AP |
| B8[HEAVY_COMP_APP] — atraso de rede ≥ piso analítico (contenção ON) | PASS | piso WLAN 45.833333 + PCIe 0.000000 = 45.833333 ms | medido 49.499732 ms | disputa implícita = 1.080 fluxos simultâneos no AP |
| B8[INFOTAINMENT_APP] — atraso de rede ≥ piso analítico (contenção ON) | PASS | piso WLAN 33.750000 + PCIe 0.000000 = 33.750000 ms | medido 36.592021 ms | disputa implícita = 1.084 fluxos simultâneos no AP |
| C1 — amostra | PASS | n = 30 runs, seeds 1..30, contíguas e sem repetição |
| C2 — latência agregada | INFO | 445.3645 ± 5.9476 ms | IC95% [443.2362, 447.4929] | CV 1.34% |
| C2 — throughput | INFO | 249.3075 ± 0.6035 tarefas/s | IC95% [249.0915, 249.5234] | CV 0.24% |
| C2 — latência [YOLO_DETECTION] | INFO | 447.4426 ± 5.9897 ms | IC95% [445.2992, 449.5860] | CV 1.34% |
| C2 — latência [HEALTH_APP] | INFO | 62.8887 ± 0.2634 ms | IC95% [62.7944, 62.9830] | CV 0.42% |
| C2 — latência [HEAVY_COMP_APP] | INFO | 349.4831 ± 0.7663 ms | IC95% [349.2089, 349.7573] | CV 0.22% |
| C2 — latência [INFOTAINMENT_APP] | INFO | 111.5870 ± 0.3139 ms | IC95% [111.4747, 111.6993] | CV 0.28% |
| C3 — independência (seed × latência) | PASS | Pearson r = -0.2367 (|r| < 0,5 ⇒ sem deriva sistemática) |
| D1 — deadline não é lido pelo motor | INFO | max_delay_requirement NUNCA entra na simulação: nenhuma tarefa falha por estourar prazo. 'Atende o deadline' é comparação pós-hoc sobre a MÉDIA. |
| D2 — percentis exigem deep log | INFO | o SIMRESULT agregado só traz a média por aplicação. Percentis exigem o registro por tarefa (execucao/rodar_deeplog.sh e analise/plotar_distribuicao_latencia.py). |
| D3 — contenção de WLAN (ligada nesta bateria) | INFO | Com wlan_contention_enabled=true, a banda do ponto de acesso é repartida entre as transmissões simultâneas nele; o atraso de rede passa a depender do número de dispositivos que transmitem ao mesmo tempo. |
| D4 — heterogeneidade é intra-host | INFO | 14 hosts, 1 GPUs, 112 VMs (1 com GPU). A app GPU só pode usar as VMs com GPU; as apps CPU usam qualquer VM. |
