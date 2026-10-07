# Characterization of Mobile Augmented Reality Tasks Supported by Edge Computing Resources

## Identificação

- **Título:** Characterization of Mobile Augmented Reality Tasks Supported by Edge Computing Resources
- **Autores:** Karlla Chaves Rodrigues, Kleber Vieira Cardoso, Sand Luz Correa
- **Instituição:** Instituto de Informática, Universidade Federal de Goiás (UFG)
- **Contexto:** SBRC 2026
- **Tema:** Caracterização de workloads de Mobile Augmented Reality (MAR) com suporte de edge computing e infraestrutura CPU/GPU.

## Resumo

O artigo caracteriza empiricamente tarefas de realidade aumentada móvel executadas com apoio de servidores de borda. O foco está em duas tarefas centrais de aplicações MAR:

- **SLAM**, usando ORB-SLAM2.
- **Detecção de objetos**, usando YOLO.

Os autores estendem o protótipo MR-Leo, criando o **eMR-Leo**, com suporte a execução acelerada por GPU e um novo pipeline de detecção de objetos. A avaliação mede latência, demanda computacional, uso de memória e tráfego IP gerado pelas aplicações.

O principal resultado é que **SLAM permanece majoritariamente CPU-bound**, enquanto **YOLO se beneficia fortemente de GPU**, reduzindo o tempo de processamento por frame de aproximadamente **148 ms para 4 ms**, uma redução próxima de **98%**.

## Problema Investigado

Aplicações MAR são sensíveis a latência e exigem processamento intenso. Dispositivos móveis têm limitações de CPU, GPU, memória, bateria e dissipação térmica. Offloading para servidores edge pode mitigar esses limites, mas ainda faltam modelos realistas de workload que representem:

- demanda computacional;
- uso de RAM e VRAM;
- padrões de tráfego IP;
- diferença entre tarefas CPU-bound e GPU-friendly;
- heterogeneidade entre infraestrutura CPU-only e CPU/GPU.

## Contribuições do Artigo

1. Extensão do MR-Leo para criar o **eMR-Leo**, com suporte a SLAM acelerado por GPU e detecção de objetos com YOLO.
2. Caracterização empírica de duas tarefas MAR em infraestrutura edge heterogênea.
3. Modelagem estatística de workload computacional, memória e tráfego IP para SLAM e YOLO.
4. Disponibilização de dados e modelos para apoiar simulações e pesquisas reprodutíveis em edge-assisted MAR.

## Arquitetura e Protótipo

O eMR-Leo segue arquitetura cliente-servidor:

- O **cliente móvel** captura, codifica e transmite vídeo.
- O **servidor edge** recebe frames, executa SLAM ou YOLO, renderiza/enriquece o conteúdo e envia o vídeo processado de volta ao cliente.
- O tráfego usa **H.264**, **RTP** e **UDP**.
- O cliente não executa análise de imagem; apenas captura, codifica, transmite e exibe.

### Tarefas Implementadas

#### SLAM

- Baseado em ORB-SLAM2.
- Versão avançada usa implementação CUDA-acelerada.
- A aceleração por GPU atua principalmente em rastreamento e renderização.
- O ganho geral é limitado, pois a geração de mapa e pose continua fortemente dependente da CPU.

#### Detecção de Objetos

- Baseada em YOLO.
- Implementada em C++ por meio da classe `YoloProcesser`.
- Usa OpenCV para aquisição, pré-processamento e pós-processamento.
- Usa DarkHelp para integração com modelos YOLO/Darknet em C++.
- Beneficia-se fortemente de paralelismo em GPU.

## Ambiente Experimental

- **Servidor edge:** Lenovo Legion laptop.
- **CPU:** Intel Core i5-13420H.
- **RAM:** 16 GB DDR5.
- **GPU:** NVIDIA GeForce RTX 3050 com 6 GB de memória.
- **Sistema operacional:** Ubuntu 24.04 LTS.
- **Dispositivo móvel:** Samsung Galaxy A21s com Android 12.
- **Conexão:** USB tethering, para isolar variabilidade de rede sem fio.
- **Vídeo:** 60 segundos, 640 x 480 pixels, 30 FPS.
- **Execuções:** 30 repetições por experimento.

## Resultados Principais

### SLAM

- 90% das amostras de FRTT ficam abaixo de **69 ms**.
- Mantém aproximadamente **30 FPS**.
- A GPU tem impacto limitado na latência total.
- A tarefa é dominada por geração de nuvem de pontos e operações CPU-bound.
- A GPU reduz parte do tempo de renderização, mas esse componente representa pequena fração do processamento total.
- Pico de CPU na configuração básica: aproximadamente **164%**.
- Pico de GPU na configuração avançada: aproximadamente **32%**.

Conclusão: para SLAM, o uso de GPU não muda substancialmente o desempenho fim a fim.

### YOLO / Detecção de Objetos

- A execução CPU-only é insuficiente para tempo real.
- O percentil 90 de FRTT cai de **232 ms** para **67 ms** com GPU.
- O tempo de processamento de detecção cai de aproximadamente **148 ms/frame** para **4 ms/frame**.
- Redução aproximada de **98%** no tempo de processamento.
- A configuração com GPU alcança **30 FPS** e atende ao requisito típico de MAR de até **100 ms**.
- CPU na configuração básica chega a aproximadamente **730%**, indicando saturação multicore.
- Na configuração avançada:
  - CPU cai para aproximadamente **47%**.
  - GPU estabiliza em aproximadamente **34%**.

Conclusão: YOLO é altamente paralelizável e deve ser tratado como workload adequado para GPU.

## Análise de Tráfego IP

O artigo analisa três métricas:

- intervalo entre pacotes;
- intervalo entre frames;
- tamanho dos frames.

Foram analisados três fluxos:

- **Stream 1:** uplink do vídeo da câmera do smartphone para o edge.
- **Stream 2:** downlink dos frames enriquecidos por SLAM.
- **Stream 3:** downlink dos frames enriquecidos por YOLO.

O tráfego mantém temporização estável alinhada a 30 FPS. A principal diferença está no tamanho e variabilidade dos frames no downlink, especialmente quando YOLO adiciona bounding boxes e metadados visuais.

## Modelo Estatístico de Workload

### Camera Stream

- **Chegada de tarefas:** periódica, a cada **33 ms**.
- **Uplink - tamanho do frame:** JohnsonSU:
  - gamma = -3.71
  - delta = 1.54
  - xi = 94.20
  - lambda = 3.57
- **Uplink - intervalo entre frames:** JohnsonSU:
  - gamma = -0.17
  - delta = 1.04
  - xi = 33.04
  - lambda = 1.64
- **Uplink - intervalo entre pacotes:** JohnsonSU:
  - gamma = -0.466
  - delta = 0.416
  - xi = 0.04090
  - lambda = 0.00351

### ORB-SLAM2

- **Hardware predominante:** CPU.
- **Chegada de tarefas:** periódica, a cada **33 ms**.
- **Computação:**
  - 43%: Normal, media = **494 MI**, desvio = **147.97 MI**.
  - 53%: Normal, media = **404 MI**, desvio = **110.99 MI**.
- **Downlink - tamanho do frame:** JohnsonSU:
  - gamma = 0.46
  - delta = 1.04
  - xi = 144.17
  - lambda = 20.98
- **Downlink - intervalo entre frames:** JohnsonSU:
  - gamma = -0.37
  - delta = 1.58
  - xi = 30.48
  - lambda = 10.84
- **Downlink - intervalo entre pacotes:** Lognormal:
  - s = 1.91
  - loc = 9.54e-4
  - scale = 0.0103
- **Memória edge:** 408 MB base.
- **Memória adicional por cliente:** 288 MB.

### YOLO

- **Hardware predominante:** GPU.
- **Chegada de tarefas:** periódica, a cada **33 ms**.
- **Resolução de referência:** 640 x 480 pixels, 30 FPS.
- **Computação:**
  - 82%: Generalized Normal, media = **91 MI**, alpha = **0.40 MI**, beta = **0.80**.
  - 18%: Generalized Normal, media = **89 MI**, alpha = **2.05 MI**, beta = **1.25**.
- **Downlink - tamanho do frame:** JohnsonSU:
  - gamma = 2.74
  - delta = 3.56e4
  - xi = 104.56
  - lambda = 4.06e5
- **Downlink - intervalo entre frames:** JohnsonSU:
  - gamma = -0.10
  - delta = 1.24
  - xi = 32.88
  - lambda = 4.44
- **Downlink - intervalo entre pacotes:** Lognormal:
  - s = 1.97
  - loc = 9.53e-4
  - scale = 0.00909
- **Memória edge:** 208 MB base.
- **Memória adicional por cliente:** 416 MB RAM + 416 MB VRAM.

#### Procedimento de Amostragem YOLO

Para cada frame processado por YOLO:

1. Sortear o componente da mistura:
   - 82% de probabilidade para o componente com media de 91 MI.
   - 18% de probabilidade para o componente com media de 89 MI.
2. Amostrar o valor de MI usando a distribuição Generalized Normal correspondente.
3. Aplicar um piso positivo caso a amostra seja inválida ou negativa.
4. Converter a demanda computacional em tempo usando a capacidade da GPU modelada no simulador.

A parametrização esperada é equivalente a `scipy.stats.gennorm(beta, loc=media, scale=alpha)`, em que `beta` é o parâmetro de forma, `loc` é a media e `scale` é `alpha`.

---

Sobre o tempo de inferência, o texto do artigo é: *"GPU acceleration reduces this cost to
approximately 4 ms per frame (a reduction of about 98%), enabling real-time performance."*
Trata-se de uma medição na RTX 3050 do ambiente experimental.

---

## Conclusões do Artigo

O trabalho mostra que diferentes tarefas MAR têm perfis muito distintos:

- **SLAM:** permanece CPU-bound; GPU ajuda pouco no desempenho total.
- **YOLO:** é altamente paralelizável; GPU transforma uma execução inviável em tempo real em uma execução compatível com MAR.

Os modelos estatísticos derivados ajudam a criar simulações mais realistas de edge computing, especialmente para comparar políticas de offloading, alocação de recursos, escalabilidade multiusuário e uso de infraestrutura heterogênea CPU/GPU.

## Referência Principal

Rodrigues, K. C.; Cardoso, K. V.; Correa, S. L. **Characterization of Mobile Augmented Reality Tasks Supported by Edge Computing Resources**. SBRC 2026.
