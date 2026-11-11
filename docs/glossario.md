# Glossário

| Termo | Significado |
|---|---|
| **FRTT** | *Frame round-trip time*: tempo entre a emissão de um quadro pelo dispositivo e a chegada do resultado; soma da subida pela rede, do processamento e da descida. É a latência reportada para o YOLO. |
| **K** | Número de servidores de borda com GPU, entre 14, no experimento de densidade de GPU. |
| **N** | Número de clientes YOLO servidos por uma GPU, no experimento de escala de clientes. |
| **Ponto** | Uma configuração de um experimento (um valor de K ou de N), identificada por um código como K02 ou N08. |
| **Execução** | Uma simulação de um ponto com uma semente. A amostra de cada ponto tem 30. |
| **Semente** | Número que inicializa o gerador pseudoaleatório de uma execução; é embaralhado (SplitMix64) antes do uso. |
| **Aquecimento** | Período inicial de 5 min descartado das métricas, até o sistema atingir o regime. |
| **MI, MI/s** | Milhões de instruções e milhões de instruções por segundo: unidades de tamanho de tarefa e de capacidade de processamento. O campo `gflops` da GPU está em MI/s. |
| **Memória livre da GPU** | Memória de vídeo disponível para os quadros em processamento: 6144 − N × 416 MB na RTX 3050. |
| **Buffer do servidor** | Número máximo de quadros em processamento simultâneo: memória livre / 20 MB. |
| **Falha por capacidade** (`vm_capacity`) | Tarefa rejeitada por não haver VM com GPU e memória de vídeo livre. |
| **Falha por banda** | Tarefa recusada porque o buffer do enlace sem fio está cheio; não ocorre com buffer infinito, o padrão. |
| **Contenção de WLAN** | Divisão da banda do ponto de acesso entre as transmissões simultâneas nele. |
| **MAN** | Rede metropolitana entre servidores de borda, atravessada pela tarefa executada num servidor distinto do que atende o ponto de acesso do dispositivo; fila M/M/1 por sentido (`man_enabled`). |
| **Carga mista** | 30% de clientes YOLO e 70% de dispositivos com aplicações só de CPU, no experimento de densidade. |
| **Registro por tarefa** (*deep log*) | Saída opcional com uma linha por tarefa, necessária para percentis e distribuições. |
| **SIMRESULT** | Arquivos de saída do simulador com as métricas agregadas de uma execução. |
| **Manifesto** | `run_manifest.csv` de um ponto: as execuções que formam a sua amostra, com status de validação e SHA-256. |
| **IC95** | Intervalo de confiança de 95% da média entre as execuções de um ponto: média ± t · s / √n, em que t é o quantil 0,975 da t de Student de n − 1 graus de liberdade (2,045 para 30 execuções, 2,262 para 10). Cálculo em `analise/estatistica.py`. |
| **p50, p95, p99** | Percentis da latência por tarefa: valores abaixo dos quais estão 50%, 95% e 99% das tarefas concluídas. |
| **Intervalo entre quadros** | 33 ms, o período de emissão a 30 fps. |
| **Orçamento de latência** | 100 ms, limite de ponta a ponta para realidade aumentada; não é imposto pelo simulador. |
