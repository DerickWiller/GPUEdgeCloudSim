# Characterization and modeling of an edge computing mixed reality workload (2020)

## Referência

- **Título:** Characterization and modeling of an edge computing mixed reality workload  
- **Autores:** Klervie Toczé, Johan Lindqvist, Simin Nadjm-Tehrani  
- **Periódico:** Journal of Cloud Computing: Advances, Systems and Applications  
- **Ano:** 2020  
- **DOI:** https://doi.org/10.1186/s13677-020-00190-x  

## Resumo executivo

O artigo apresenta uma caracterização empírica de carga de trabalho para uma aplicação de Mixed Reality (MR) com offloading para edge, usando o protótipo open-source **MR-Leo** como base experimental.  

A principal motivação é que muitos estudos de edge usam modelos sintéticos ou suposições genéricas (por exemplo, chegadas Poisson sem validação), o que pode distorcer resultados de orquestração e alocação de recursos.

Os autores:

1. analisam o consumo real de CPU, memória, rede e latência de uma aplicação MR;
2. constroem um **modelo de aplicação**;
3. constroem um **modelo estatístico de workload** baseado em medições reais;
4. mostram diferenças relevantes entre esse modelo real e modelos teóricos comumente usados.

## Problema que o artigo ataca

Aplicações MR móveis são:

- sensíveis a latência;
- intensivas em computação e comunicação;
- candidatas naturais para offloading ao edge.

Apesar disso, há escassez de modelos de carga específicos para MR em edge baseados em software real e instrumentação experimental. O artigo busca preencher essa lacuna com um modelo reproduzível e orientado por dados.

## Perguntas de pesquisa destacadas

O trabalho busca responder, em essência:

1. É viável offloading completo de MR para edge com tecnologia atual?
2. Quais são os gargalos principais (compute, rede, codificação, renderização etc.)?
3. É possível derivar um modelo estatístico útil para simulação/estudo analítico de algoritmos de alocação?

## Protótipo MR-Leo (visão geral)

O MR-Leo é usado como veículo experimental para estudar:

- envio de fluxo de vídeo do usuário para edge;
- processamento no edge;
- retorno de vídeo enriquecido ao usuário.

O artigo discute também variações de protocolo e codificação de vídeo na comunicação, e como isso afeta latência e footprint de recursos.

## Metodologia do estudo

O paper segue uma linha empírica:

1. instrumentação da aplicação e coleta de medições;
2. execução de experimentos controlados;
3. análise de comportamento temporal da carga;
4. ajuste/modelagem estatística;
5. comparação com modelos teóricos usados na literatura.

Métricas observadas incluem, entre outras:

- latência fim a fim;
- utilização de CPU;
- demanda computacional;
- padrão de chegada de tarefas;
- características de tráfego de rede;
- consumo de memória.

## Principais achados

### 1) Workload real de MR difere de abstrações comuns

Um resultado central é que o perfil da aplicação real não segue, de forma confiável, simplificações amplamente adotadas em estudos de edge.

### 2) Padrão de chegada de tarefas importa

O artigo reforça que assumir um padrão de chegada genérico sem validação empírica pode levar a conclusões erradas de dimensionamento e orquestração.

### 3) Gargalo computacional depende fortemente do pipeline de ponto de nuvem

A demanda de CPU no edge é fortemente influenciada pelo algoritmo de point cloud/processamento visual.

### 4) Modelos empíricos mudam decisões de alocação

Ao comparar com modelos teóricos, os autores mostram que resultados de estudos de edge podem mudar de forma relevante quando o workload é modelado com base em aplicação real.

## Contribuições do artigo (em linguagem prática)

1. **Um caso real open-source** para estudos de edge + MR (MR-Leo).
2. **Uma metodologia de caracterização** reprodutível.
3. **Modelo de aplicação** (application model) para representar o comportamento funcional.
4. **Modelo estatístico de workload** para estudos em simulação e análise.
5. **Evidência empírica** de que modelos teóricos simplificados podem ser insuficientes.

## Limitações destacadas pelo artigo (interpretação)

Como todo estudo empírico:

- resultados dependem do protótipo e ambiente de medição;
- há risco de variação ao trocar hardware, codec, rede e configuração;
- o modelo é mais robusto para classes de aplicações semelhantes ao MR-Leo do que para qualquer app MR arbitrário.

Ainda assim, a contribuição é valiosa porque sai do abstrato e entrega uma base mensurável para pesquisa.
