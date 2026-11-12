# GPUEdgeCloudSim

Simulador de computação de borda com GPU. Estende o EdgeCloudSim (Sonmez et al., 2018),
que simula servidores de borda mas não modela GPU, para responder perguntas de
dimensionamento como "quantos clientes uma GPU atende?" ou "quantos servidores precisam
de GPU?" sem montar o hardware.

A carga dos experimentos é a detecção de objetos com YOLO em realidade aumentada móvel,
com parâmetros medidos em hardware real por Rodrigues et al. (2026): cada cliente envia um
quadro de 640 × 480 a cada 33 ms, e uma RTX 3050 processa cada quadro em 4 ms.

## O que foi acrescentado ao EdgeCloudSim

- GPU nos servidores de borda: tempo de processamento, memória de vídeo (o modelo de cada
  cliente fica residente) e divisão da GPU no tempo entre as tarefas de vários usuários.
- Rede: WLAN com contenção entre os clientes do mesmo ponto de acesso, PCIe e uma rede
  metropolitana (MAN) entre os servidores de borda. A MAN é uma fila M/M/1 por sentido,
  como no EdgeCloudSim, e vem desligada por padrão.
- Escolha da GPU para cada quadro: rodízio entre todas, só a do ponto de acesso do
  cliente, ou a de menor tempo estimado, que soma a ida e volta pela MAN quando a GPU é
  de outro servidor.
- Câmeras fixas em pontos de acesso escolhidos, além da mobilidade original.
- Validação dos resultados contra cálculos feitos antes das execuções
  ([`docs/validacao.md`](docs/validacao.md)).

O código do EdgeCloudSim está em `GPUEdgeCloudSim/src/edu/boun/edgecloudsim`, sem as
aplicações de exemplo; a extensão está em `GPUEdgeCloudSim/src/gpuedgecloudsim`, nos mesmos
subpacotes. Seis arquivos do EdgeCloudSim foram alterados (`SimSettings`, `SimManager`,
`SimLogger`, `SimUtils`, `NomadicMobility` e `EdgeVmAllocationPolicy_Custom`); os demais
são iguais aos do repositório original.

## Resultados

Cada experimento tem uma pergunta. Os números são médias de 30 execuções de 60 min por
ponto, ou 10 nos experimentos com MAN. O intervalo de confiança de 95% está no README de
cada experimento.

| Experimento | Pergunta | Resposta |
|---|---|---|
| [Escala de clientes](experimentos/escala-clientes/) | Quantos clientes uma GPU atende? | 8. A saturação ocorre entre 8 e 9 clientes, como previa o cálculo (250 quadros/s ÷ 30,3 quadros/s por cliente = 8,25). Com 8, a média é 51,6 ms sem perda; com 9, passa de 450 ms e 9,3% dos quadros são perdidos. |
| [Densidade de GPU](experimentos/densidade-gpu/) | Quantos dos 14 servidores de borda precisam de GPU para 9 clientes? | Pela média, 2 (13,1 ms). Pela cauda, mais de 3: com 2 e 3 GPUs o percentil 99 (33,3 ms) passa do intervalo entre quadros; com 7, cai para 11,8 ms. |
| [Dois servidores](experimentos/dois-servidores/) | A partir de quantos clientes compensa mandar quadros à GPU de outro servidor, pela MAN? | Entre 6 e 8. Com até 6 clientes a GPU local ganha. Com 8, a fila local já custa mais que os cerca de 22 ms da MAN. |
| [Câmeras fixas](experimentos/cameras-fixas/) | Um ponto de acesso com câmeras demais pode usar as GPUs vizinhas sem prejudicar os outros pontos? | Sim, com a escolha por menor tempo estimado. Com 9 câmeras no ponto sobrecarregado: 31,7 ms, contra 98,8 ms e 9,5% de perda usando só a GPU local e 40,1 ms no rodízio. As câmeras dos outros pontos ficam em 13,9 ms. |

## Como usar

Requisitos: Java 21 e Python 3.12 com as bibliotecas de `requirements.txt`
(`pip install -r requirements.txt`), e cerca de 2 GB de memória por simulação. Roda no
Linux e no Windows; no Windows, os comandos são os mesmos, no Git Bash.

```bash
bash execucao/compilar.sh
bash execucao/rodar_teste_rapido.sh       # 1 cliente; latência esperada: 8,44 ms
bash execucao/rodar_experimento.sh K02    # 30 execuções do ponto K02 (2 servidores com GPU)
```

Os pontos são identificados por código: `N08` é a escala de clientes com 8 clientes, `K02`
a densidade com 2 servidores com GPU. A lista completa, a análise e as figuras estão em
[`docs/como-rodar.md`](docs/como-rodar.md).

### Interface no navegador

```bash
bash execucao/interface.sh
```

Abre uma página local (`http://127.0.0.1:8765`). Por ela dá para rodar execuções, ver o
andamento e os gráficos e criar cenários novos. Ela chama os mesmos scripts do terminal e
mostra o comando de cada ação. Detalhes em [`docs/interface.md`](docs/interface.md).

## Organização

```
GPUEdgeCloudSim/   código Java do simulador e bibliotecas (CloudSim, Commons Math, Colt)
experimentos/      configuração e resultados de cada experimento, um ponto por pasta
analise/           agregação, validação e figuras (Python)
execucao/          compilação e execução (shell)
interface/         interface no navegador (Python e HTML)
docs/              modelo, validação, guia de uso, glossário e referências
saidas/            saídas brutas das simulações, fora do controle de versão
```

## Documentação

- [`docs/modelo.md`](docs/modelo.md): o que é modelado, hipóteses, origem dos parâmetros e
  limitações.
- [`docs/validacao.md`](docs/validacao.md): comparação dos resultados com os cálculos
  analíticos.
- [`docs/como-rodar.md`](docs/como-rodar.md): compilação, execução, análise e cuidados.
- [`docs/interface.md`](docs/interface.md): a interface no navegador.
- [`docs/glossario.md`](docs/glossario.md): termos e unidades.
- [`docs/referencias.bib`](docs/referencias.bib): referências.

## Autoria

Desenvolvido por Dérick Willer Borges Monteiro no Instituto de Informática da Universidade
Federal de Goiás, com orientação de Sand Luz Corrêa e coorientação de Bruno Oliveira
Silvestre.
