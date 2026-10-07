# Validação de saídas — 14 clientes YOLO sobre 1 GPU (N14)

Gerado em 2026-08-19 17:26 por `analise/validar_saidas.py`.

## Configuração validada

- Clientes: **14** · GPUs: **1** · gflops: **22750 MI/s** · VRAM: **320 MB**
- Janela: 3600 s totais − 300 s de warm-up = **3300 s úteis**
- Workload: 91 MI/frame · 20 MB/frame · chegada a cada 0.033 s
- Runs analisados: **30**

## Resultado

| | Checagem | Detalhe |
|---|---|---|
| ✓ | A1. Conservação de tarefas | completed+failed+uncompleted = 1,400,000 (= 14 clientes × 3300 s ÷ 0.033 s) em 30/30 runs |
| ✓ | A2. Decomposição do FRTT (TAUTOLÓGICA) | serviceTime = processingTime + networkDelay em 30/30 runs. ⚠️ SEM PODER DE VALIDAÇÃO: `SimLogger.java:1172` define processingTime := serviceTime − networkDelay, então a identidade vale por construção. Só detecta corrupção do arquivo, não erro de modelagem. |
| ✓ | A3. Causas de falha somam o total | vm_capacity + bw + mobility + wlan_range = failed em 30/30 runs |
| ✓ | A4. Camadas somam o total | edge+cloud+mobile = completed em 30/30 runs |
| ✓ | B1. Tempo de processamento ≥ mínimo físico | medido 62.2055 ms vs. mínimo 4.0000 ms (= gpu_length 91 MI ÷ gflops 22750 MI/s). Excesso de 58.2055 ms = fila/time-share. |
| ✓ | B2. Throughput = completed ÷ tempo útil | 197.09 fps sobre 3300 s (warm-up de 300 s descontado) |
| ✓ | B3. Ocupação da GPU ≤ 100% | 78.8% (throughput 197.09 fps × 4.00 ms ÷ 1 GPU) |
| · | B4. Capacidade vs. demanda | capacidade 250.00 fps · chegada λ 424.24 fps · razão λ/capacidade = 1.70× (saturado) |
| ✓ | B5. Perda condiz com vazão vs. chegada | falha medida 53.54% vs. 1 − throughput/λ = 53.54% (diferença 0.00 p.p.) |
| ✓ | B6. Little's Law dentro do buffer de VRAM | frames em voo = 12.26 (throughput × tempo no servidor) ≤ buffer 16 frames (VRAM 320 MB ÷ 20 MB/frame) |
| · | B7. Inflação do tempo no servidor | tempo no servidor ÷ mínimo físico da GPU = 15.55× (62.21 ms vs. 4.00 ms). Mede fila + escalonamento + time-share juntos — o motor não expõe o tempo de GPU isolado, então esses componentes NÃO são separáveis. A ocupação real do buffer é a de B6: 76.6%. |
| ✓ | B8. Atraso de rede ≥ piso analítico (contenção ON) | medido 33.1177099 ms vs. piso 4.4406746 ms = WLAN (94+105 KB ÷ 480 Mbps) + 2× PCIe (0.5 ms + 1 MB ÷ 15.75 GB/s). Disputa implícita = 9.646 fluxos simultâneos no AP. |
| · | C1. Amostra | 30 runs, seeds 1–30, contíguas e sem repetição |
| · | C2. Latência | 95.3232 ± 3.5608 ms · IC95 [94.0490, 96.5974] · CV 3.74% |
| · | C2. Throughput | 197.0862 ± 10.5733 fps · IC95 [193.3025, 200.8698] · CV 5.36% |
| · | C2. Falha | 53.5433 ± 2.4925 % · IC95 [52.6514, 54.4352] · CV 4.66% |
| ✓ | C3. Independência entre seed e latência | correlação de Pearson r = -0.0762 (sem relação sistemática) |
| · | D1. Deadline | requisito 100 ms · latência média 95.32 ms. ATENÇÃO: max_delay_requirement NUNCA é lido pelo motor — nenhuma tarefa falha por estourar o prazo. A comparação é pós-hoc e sobre a MÉDIA, não é taxa de violação. |
| · | D2. Percentis | o simulador não emite latência por tarefa, apenas a média agregada → p50/p90/p99 exigem o registro por tarefa (execucao/rodar_deeplog.sh); a partir do SIMRESULT agregado são impossíveis. Comparar a média com o p90 de um artigo é comparar grandezas diferentes. |
| · | D3. Rede: contenção ligada | a banda do AP é repartida entre as transmissões simultâneas, então o atraso de rede DEPENDE de quantos transmitem (ver B8). Tráfego ofertado 675 Mbps · servido 314 Mbps · WLAN 480 Mbps. Buffer infinito (wlan_buffer_size_kb=0): a contenção só ATRASA, nunca descarta — nenhuma falha é por banda. ⚠️ O ofertado excede a WLAN em 1.41×, mas só o servido cursa a rede: o gargalo a montante (GPU) rejeita na admissão antes de o tráfego chegar ao ar. Compare o SERVIDO com a WLAN, não o ofertado. |
| · | D4. Warm-up | 300 s (8% da janela) descartados das métricas, inclusive as tarefas rejeitadas nesse intervalo, que são marcadas no instante da chegada. |

**Falhas: 0**
