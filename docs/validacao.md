# Validação dos resultados

Este documento reúne as evidências de que os números produzidos pelo simulador têm
sentido físico, e não apenas aparência plausível. Cada resultado é confrontado com uma
referência independente: o cálculo analítico, a capacidade do hardware modelado ou uma
identidade de conservação.

## 1. Protocolo

Cada ponto experimental tem 30 execuções independentes (sementes 1 a 30). A amostra
passa por duas camadas de verificação:

1. **Integridade de cada execução** (`analise/validar_run.py`): arquivos presentes e não
   vazios, configuração da execução com os mesmos valores da configuração versionada do
   ponto, métricas legíveis e coerentes. O manifesto do ponto registra o resultado e o
   SHA-256 dos arquivos principais.
2. **Validação da amostra contra o modelo** (`analise/validar_saidas.py`, para a escala
   de clientes; `analise/validar_saidas_misto.py`, para a densidade de GPU, que valida
   cada aplicação com o seu próprio modelo). O relatório fica em
   `experimentos/<experimento>/<ponto>/resultados/validacao.md`; uma checagem reprovada
   encerra o script com código de erro.

| Grupo | O que verifica |
|---|---|
| A | Conservação: total de tarefas, FRTT = processamento + rede, soma das causas de falha |
| B | Física: piso de tempo por carga e capacidade, vazão, ocupação ≤ 100%, razão demanda/capacidade, perda = 1 − vazão/λ, lei de Little, buffer de memória de vídeo, atraso de rede analítico |
| C | Estatística: tamanho da amostra, IC95 e coeficiente de variação, independência entre semente e latência |
| D | Limitações registradas no relatório, sem valor de aprovação |

Nenhum dos 13 pontos tem checagem reprovada: são 31 itens por ponto na densidade de GPU
e 21 na escala de clientes, entre aprovações e medidas informativas.

## 2. Evidências

### 2.1 Conservação de fluxo

Toda tarefa gerada é concluída ou falha. Em quadros por segundo:

    λ_ofertada = vazão servida + vazão perdida

com λ calculada da configuração (N clientes × 1 quadro a cada 33 ms), e não medida.
O maior desvio entre λ e a soma medida, nos 13 pontos, é de **0,012%**
(`experimentos/comparativos/conservacao_fluxo.csv`).

### 2.2 Tempo de serviço

Com um cliente (N01), não há disputa, e o FRTT medido deve igualar o piso físico:

    GPU:  91 MI / 22 750 MI/s                                   = 4,0000000 ms
    rede: (94 + 105) KB / 480 Mbps + 2 × (0,5 ms + 1 MB / 15,75 GB/s) = 4,4406746 ms
    total                                                       = 8,4406746 ms

O FRTT medido é 8,4406746 ms em todas as 30 execuções.

### 2.3 Vazão sob saturação

Com 14 clientes (N14), a demanda é de 424,24 quadros/s para uma GPU de 250 quadros/s.
A perda prevista por conservação, 1 − 197,09 / 424,24 = 53,53%, difere da medida, 53,54%,
em 0,01 ponto percentual. Nos três pontos saturados intermediários (N09, N10, N12) a
diferença também é de no máximo 0,01 ponto percentual.

### 2.4 Predição antes da execução

Os pontos da escala de clientes foram escolhidos a partir de dois limites analíticos,
calculados antes de rodar:

    GPU:  N = 250 quadros/s / 30,3 quadros/s por cliente = 8,25
    WLAN: N = 480 Mbps / 48,24 Mbps por cliente          = 9,95

A transição medida ocorreu entre N = 8 (51,58 ms, perda nula) e N = 9 (450,99 ms, 9,29%
de perda), como previsto. O limite da WLAN não se manifesta porque a GPU satura antes e
rejeita os quadros na admissão: todas as falhas da série são por capacidade.

### 2.5 Estatística

- 30 execuções por ponto e intervalos de confiança de 95% em todas as métricas.
- Coeficiente de variação abaixo de 0,5% nas aplicações de CPU.
- Correlação de Pearson entre semente e latência com |r| < 0,5 em todos os pontos
  (|r| < 0,27 na escala de clientes): não há deriva associada à semente.
- A semente da linha de comando é embaralhada (SplitMix64) antes de semear o gerador
  linear congruencial, para que sementes consecutivas não produzam sequências
  correlacionadas (Steele; Lea; Flood, 2014).

## 3. Reprodutibilidade

Todos os sorteios de uma execução derivam da semente (`docs/modelo.md`, seção 4), e a
mesma semente reproduz a execução byte a byte, exceto o tempo de relógio registrado no
SIMRESULT. Os resultados da densidade de GPU são provisórios e serão regerados com 30
execuções por ponto.

## 4. Limitações

- **Prazo não imposto.** Nenhuma tarefa falha por exceder os 100 ms; dizer que um ponto
  atende ao requisito é uma comparação feita sobre a latência medida.
- **Parâmetros sem fonte externa.** A memória de trabalho por quadro (20 MB), a latência
  do PCIe e o buffer infinito do enlace foram adotados neste trabalho (`docs/modelo.md`,
  seção 7). A memória por quadro define o buffer do servidor e, sob saturação, a perda.
- **Aplicações de CPU como carga de fundo.** Vêm do EdgeCloudSim; a tarefa de CPU
  caracterizada por Rodrigues et al. (2026), o ORB-SLAM2, não é modelada.
- **Isolamento entre aplicações.** O simulador não representa disputa de barramento,
  cache ou memória do host; o isolamento observado é consequência do modelo.
- **Percentis com amostra menor.** Médias e taxas de falha usam 30 execuções; percentis
  usam 10, pois exigem o registro por tarefa.

## Referências

- Rodrigues, K. C.; Cardoso, K. V.; Correa, S. L. *Characterization of Mobile Augmented
  Reality Tasks Supported by Edge Computing Resources*. SBRC, 2026.
- Steele, G. L.; Lea, D.; Flood, C. H. *Fast splittable pseudorandom number generators*.
  OOPSLA, 2014.
