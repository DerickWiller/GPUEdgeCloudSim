# Validação de saídas — 6 clientes YOLO sobre 1 GPU (N06)

Gerado em 2026-11-11 14:51 por `analise/validar_saidas.py`.

## Configuração validada

- Clientes: **6** · GPUs: **1** · gflops: **22750 MI/s** · VRAM: **3648 MB**
- Janela: 3600 s totais − 300 s de warm-up = **3300 s úteis**
- Workload: 91 MI/frame · 20 MB/frame · chegada a cada 0.033 s
- Runs analisados: **30**

## Resultado

| | Checagem | Detalhe |
|---|---|---|
| ✓ | A1. Conservação de tarefas | completed+failed+uncompleted = 600,000 (= 6 clientes × 3300 s ÷ 0.033 s) em 30/30 runs |
| ✓ | A2. Decomposição do FRTT (tautológica) | serviceTime = processingTime + networkDelay em 30/30 runs. Sem poder de validação: o SimLogger define processingTime := serviceTime − networkDelay, então a identidade vale por construção. Só detecta corrupção do arquivo, não erro de modelagem. |
| ✓ | A3. Causas de falha somam o total | vm_capacity + bw + mobility + wlan_range = failed em 30/30 runs |
| ✓ | A4. Camadas somam o total | edge+cloud+mobile = completed em 30/30 runs |
| ✓ | B1. Tempo de processamento ≥ mínimo físico | medido 12.5398 ms vs. mínimo 4.0000 ms (= gpu_length 91 MI ÷ gflops 22750 MI/s). Excesso de 8.5398 ms = fila/time-share. |
| ✓ | B2. Throughput = completed ÷ tempo útil | 181.82 fps sobre 3300 s (warm-up de 300 s descontado) |
| ✓ | B3. Ocupação da GPU ≤ 100% | 72.7% (throughput 181.82 fps × 4.00 ms ÷ 1 GPU) |
| · | B4. Capacidade vs. demanda | capacidade 250.00 fps · chegada λ 181.82 fps · razão λ/capacidade = 0.73× (com folga) |
| ✓ | B5. Perda condiz com vazão vs. chegada | falha medida 0.00% vs. 1 − throughput/λ = 0.00% (diferença 0.00 p.p.) |
| ✓ | B6. Little's Law dentro do buffer de VRAM | frames em voo = 2.28 (throughput × tempo no servidor) ≤ buffer 182 frames (VRAM 3648 MB ÷ 20 MB/frame) |
| · | B7. Inflação do tempo no servidor | tempo no servidor ÷ mínimo físico da GPU = 3.13× (12.54 ms vs. 4.00 ms). Mede fila + escalonamento + time-share juntos — o motor não expõe o tempo de GPU isolado, então esses componentes não são separáveis. A ocupação real do buffer é a de B6: 1.2%. |
| ✓ | B8. Atraso de rede ≥ piso analítico (contenção ON) | medido 8.0089384 ms vs. piso 4.4406746 ms = WLAN (94+105 KB ÷ 480 Mbps) + 2× PCIe (0.5 ms + 1 MB ÷ 15.75 GB/s). Disputa implícita = 2.076 fluxos simultâneos no AP. |
| · | C1. Amostra | 30 runs, seeds 1–30, contíguas e sem repetição |
| · | C2. Latência | 20.5488 ± 3.5995 ms · IC95 [19.2047, 21.8928] · CV 17.52% |
| · | C2. Throughput | 181.8175 ± 0.0003 fps · IC95 [181.8174, 181.8176] · CV 0.00% |
| · | C2. Falha | 0.0000 ± 0.0000 % · IC95 [0.0000, 0.0000] · CV 0.00% |
| ✓ | C3. Independência entre seed e latência | correlação de Pearson r = +0.1863 (sem relação sistemática) |
| · | D1. Deadline | requisito 100 ms · latência média 20.55 ms. max_delay_requirement não é lido pelo motor — nenhuma tarefa falha por estourar o prazo. A comparação é pós-hoc e sobre a média, não é taxa de violação. |
| · | D2. Percentis | o simulador não emite latência por tarefa, apenas a média agregada → p50/p90/p99 exigem o registro por tarefa (execucao/rodar_deeplog.sh); a partir do SIMRESULT agregado são impossíveis. Comparar a média com o p90 de um artigo é comparar grandezas diferentes. |
| · | D3. Rede: contenção ligada | a banda do AP é repartida entre as transmissões simultâneas, então o atraso de rede depende de quantos transmitem (ver B8). Tráfego ofertado 289 Mbps · servido 289 Mbps · WLAN 480 Mbps. Buffer infinito (wlan_buffer_size_kb=0): a contenção só atrasa, não descarta — nenhuma falha é por banda. |
| · | D4. Warm-up | 300 s (8% da janela) descartados das métricas, inclusive as tarefas rejeitadas nesse intervalo, que são marcadas no instante da chegada. |

**Falhas: 0**
