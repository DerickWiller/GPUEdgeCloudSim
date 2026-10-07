# GPUEdgeCloudSim

Simulador de eventos discretos para computação de borda com GPU, construído sobre o
EdgeCloudSim (Sonmez et al., 2018) e o CloudSim, e os experimentos que o utilizam para
avaliar detecção de objetos (YOLO) em tempo real a partir de dispositivos de realidade
aumentada. A carga e o hardware seguem a caracterização de Rodrigues et al. (2026): uma
RTX 3050 processa um quadro de 640 × 480 em 4 ms, e cada cliente envia 30 quadros por
segundo.

## Perguntas

| Experimento | Pergunta | Resposta |
|---|---|---|
| [Densidade de GPU](experimentos/densidade-gpu/) | Quantos dos 14 servidores de borda precisam ter GPU, com 9 clientes? | A média indica 2; a cauda, entre 3 e 7: com 2 e 3 GPUs o p99 (33,32 ms) excede o intervalo entre quadros |
| [Escala de clientes](experimentos/escala-clientes/) | Quantos clientes uma GPU atende? | 8: a saturação ocorre entre 8 e 9 clientes, como previsto analiticamente (8,25) |

## Organização

```
GPUEdgeCloudSim/      o simulador
  src/edu/boun/edgecloudsim/   código-base do EdgeCloudSim
  src/gpuedgecloudsim/         extensão com GPU, nos mesmos subpacotes
  lib/                         CloudSim, Commons Math e Colt
experimentos/         configurações e resultados agregados, por pergunta e por ponto
analise/              agregação, validação e figuras (Python)
execucao/             compilação e execução das simulações (shell)
docs/                 modelo, validação, guia de uso, glossário e referências
saidas/               saídas brutas das simulações (não versionada)
```

O código-base do EdgeCloudSim está no pacote `edu.boun.edgecloudsim`, sem as aplicações de
exemplo. Seis de seus arquivos foram alterados por este trabalho:
`SimSettings`, `SimManager`, `SimLogger`, `SimUtils`, `NomadicMobility` e
`EdgeVmAllocationPolicy_Custom`. Os demais são idênticos aos do repositório original.

## Uso rápido

```bash
bash execucao/compilar.sh
bash execucao/rodar_teste_rapido.sh       # uma execução de 1 cliente; FRTT esperado: 8,44 ms
bash execucao/rodar_experimento.sh K02    # 30 execuções de 2 servidores com GPU
```

Requisitos: Java 21 e Python 3.12 (`pip install -r requirements.txt`). O guia completo
está em [`docs/como-rodar.md`](docs/como-rodar.md).

## Documentação

- [`docs/modelo.md`](docs/modelo.md): o que o simulador modela, hipóteses, origem dos
  parâmetros e limitações.
- [`docs/validacao.md`](docs/validacao.md): evidências de que os resultados têm sentido
  físico.
- [`docs/como-rodar.md`](docs/como-rodar.md): compilação, execução, análise e cuidados.
- [`docs/glossario.md`](docs/glossario.md): termos e unidades.
- [`docs/referencias.bib`](docs/referencias.bib) e [`docs/referencias/`](docs/referencias/):
  referências e resumos dos trabalhos de origem dos parâmetros.

## Situação dos resultados

Os resultados da escala de clientes são definitivos. Os da densidade de GPU são
provisórios: a série será executada novamente com 30 execuções por ponto, e os números
desta página e de [`experimentos/densidade-gpu/`](experimentos/densidade-gpu/) serão
atualizados.
