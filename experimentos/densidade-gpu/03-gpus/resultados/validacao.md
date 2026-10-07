# Validação de saídas — 3 de 14 servidores com GPU (K03)

Gerado em 2026-08-10 13:04 · 30 runs · 0 falha(s)

## Topologia

- 14 hosts, 3 GPUs, 112 VMs (3 com GPU)
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
| A3 — toda falha tem causa atribuída | PASS | falhas médias 0.0; bw + vm_capacity + mobility + wlan_range fecha em todos os runs |
| A4 — edge + cloud + mobile = completed | PASS | edge 905,225 | cloud 0 | mobile 0 |
| A2[YOLO_DETECTION] — tarefas geradas (stream contínuo) | PASS | 9 clientes × 3300s ÷ 0.033s = 900,000 | observado 900,000.0 |
| A2[HEALTH_APP] — tarefas geradas | INFO | observado 661.0 (teto contínuo seria 660; a app tem active/idle period, então gerar menos é esperado) |
| A2[HEAVY_COMP_APP] — tarefas geradas | INFO | observado 327.7 (teto contínuo seria 330; a app tem active/idle period, então gerar menos é esperado) |
| A2[INFOTAINMENT_APP] — tarefas geradas | INFO | observado 4,237.9 (teto contínuo seria 4,243; a app tem active/idle period, então gerar menos é esperado) |
| B1[YOLO_DETECTION] — processamento ≥ mínimo físico | PASS | mínimo 4.0000 ms (gpu_length 91 MI ÷ gflops 22750 MI/s) | medido 5.7275 ms | déficit -1.727507 ms de uma folga de 0.0000 ms (exigência estrita (caminho da GPU não trunca MI)) |
| B1[HEALTH_APP] — processamento ≥ mínimo físico | PASS | mínimo 40.0000 ms (task_length 400 MI ÷ (10000 MIPS × 1 core)) | medido 39.9973 ms | déficit +0.002667 ms de uma folga de 0.1000 ms (1 MI ÷ 10000 MIPS = granularidade do CloudSim) |
| B1[HEAVY_COMP_APP] — processamento ≥ mínimo físico | PASS | mínimo 300.0000 ms (task_length 3000 MI ÷ (10000 MIPS × 1 core)) | medido 299.9834 ms | déficit +0.016567 ms de uma folga de 0.1000 ms (1 MI ÷ 10000 MIPS = granularidade do CloudSim) |
| B1[INFOTAINMENT_APP] — processamento ≥ mínimo físico | PASS | mínimo 75.0000 ms (task_length 750 MI ÷ (10000 MIPS × 1 core)) | medido 74.9950 ms | déficit +0.004985 ms de uma folga de 0.1000 ms (1 MI ÷ 10000 MIPS = granularidade do CloudSim) |
| B2 — throughput agregado | INFO | 274.31 tarefas/s = 905,225 completadas ÷ 3300s úteis |
| B3 — ocupação da GPU (YOLO_DETECTION) | PASS | servido 272.73 fps de capacidade 750.00 fps (3 GPUs) = 36.4% de ocupação |
| B4 — demanda vs capacidade (app GPU) | INFO | λ = 272.73 fps (9 clientes ÷ 0.033s) | capacidade 750.00 fps | folga 2.75× |
| B5 — conservação de fluxo (YOLO_DETECTION) | PASS | 1 − throughput/λ = 0.000% | falha medida 0.000% | Δ 0.000 p.p. |
| B8[YOLO_DETECTION] — atraso de rede ≥ piso analítico (contenção ON) | PASS | piso WLAN 3.316667 + PCIe 1.124008 = 4.440675 ms | medido 4.677064 ms | disputa implícita = 1.071 fluxos simultâneos no AP |
| B8[HEALTH_APP] — atraso de rede ≥ piso analítico (contenção ON) | PASS | piso WLAN 21.166667 + PCIe 0.000000 = 21.166667 ms | medido 22.830893 ms | disputa implícita = 1.079 fluxos simultâneos no AP |
| B8[HEAVY_COMP_APP] — atraso de rede ≥ piso analítico (contenção ON) | PASS | piso WLAN 45.833333 + PCIe 0.000000 = 45.833333 ms | medido 49.548901 ms | disputa implícita = 1.081 fluxos simultâneos no AP |
| B8[INFOTAINMENT_APP] — atraso de rede ≥ piso analítico (contenção ON) | PASS | piso WLAN 33.750000 + PCIe 0.000000 = 33.750000 ms | medido 36.592381 ms | disputa implícita = 1.084 fluxos simultâneos no AP |
| C1 — amostra | PASS | n = 30 runs, seeds 1..30, contíguas e sem repetição |
| C2 — latência agregada | INFO | 11.0393 ± 2.9621 ms | IC95% [9.9794, 12.0993] | CV 26.83% |
| C2 — throughput | INFO | 274.3106 ± 0.0198 tarefas/s | IC95% [274.3035, 274.3177] | CV 0.01% |
| C2 — latência [YOLO_DETECTION] | INFO | 10.4046 ± 2.9806 ms | IC95% [9.3380, 11.4712] | CV 28.65% |
| C2 — latência [HEALTH_APP] | INFO | 62.8282 ± 0.3573 ms | IC95% [62.7004, 62.9561] | CV 0.57% |
| C2 — latência [HEAVY_COMP_APP] | INFO | 349.5323 ± 0.8585 ms | IC95% [349.2251, 349.8395] | CV 0.25% |
| C2 — latência [INFOTAINMENT_APP] | INFO | 111.5874 ± 0.3323 ms | IC95% [111.4685, 111.7063] | CV 0.30% |
| C3 — independência (seed × latência) | PASS | Pearson r = +0.1125 (|r| < 0,5 ⇒ sem deriva sistemática) |
| D1 — deadline não é lido pelo motor | INFO | max_delay_requirement NUNCA entra na simulação: nenhuma tarefa falha por estourar prazo. 'Atende o deadline' é comparação pós-hoc sobre a MÉDIA. |
| D2 — percentis exigem deep log | INFO | o SIMRESULT agregado só traz a média por aplicação. Percentis exigem o registro por tarefa (execucao/rodar_deeplog.sh e analise/plotar_distribuicao_latencia.py). |
| D3 — contenção de WLAN (ligada nesta bateria) | INFO | Com wlan_contention_enabled=true, a banda do ponto de acesso é repartida entre as transmissões simultâneas nele; o atraso de rede passa a depender do número de dispositivos que transmitem ao mesmo tempo. |
| D4 — heterogeneidade é intra-host | INFO | 14 hosts, 3 GPUs, 112 VMs (3 com GPU). A app GPU só pode usar as VMs com GPU; as apps CPU usam qualquer VM. |
