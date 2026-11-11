# Interface no navegador

A interface é uma aplicação local: um servidor em Python, só com a biblioteca padrão, serve
uma página em `http://127.0.0.1:8765` e dispara os mesmos scripts de `execucao/` e
`analise/` usados no terminal. Ela não tem lógica própria de simulação nem de análise e atende
só a 127.0.0.1. O uso pelo terminal continua valendo, e cada tela mostra o comando
equivalente.

```bash
bash execucao/interface.sh          # porta 8765; abre o navegador
bash execucao/interface.sh 8800     # outra porta
```

O servidor fica ativo enquanto o comando roda; Ctrl+C o encerra e interrompe as baterias em
andamento. Roda no Linux e, pelo Git Bash, no Windows.

## Telas

- Experimento: tabela dos pontos com latência média do YOLO (± IC95) e taxa de falha,
  gráfico da latência contra a variável do experimento e figuras do ponto. Para os pontos
  com amostra oficial (`resultados/`), os números são os publicados; para os demais, os das
  execuções encontradas em `saidas/`, uma por semente.
- Nova bateria: um ponto ou todos os pontos do experimento, intervalo de sementes,
  execuções em paralelo e registro por tarefa. O limite sugerido de execuções em paralelo
  supõe 2 GB por execução (`-Xms2g` de `rodar_simulacao.sh`) e 2 GB para o sistema.
- Baterias: andamento por semente, com o resultado de `validar_run.py`. Nos cenários
  criados pela interface, `Tornar amostra oficial` roda, para cada ponto, o
  `publicar_manifest.py`, o `agregar_metricas.py` e o `plotar_metricas.py`. Nos
  experimentos publicados a interface só mostra o comando: a amostra oficial deles só é trocada
  no terminal, para não alterar sem querer os resultados versionados.
- Novo cenário: construtor numa página. À esquerda, as escolhas (servidores e GPUs, quem usa
  e onde, MAN, forma de escolher a GPU e o que comparar); à direita, o desenho da topologia,
  atualizado a cada mudança, com os limites físicos em vermelho (WLAN saturada, memória da
  GPU insuficiente). A conferência com `experimentos/gerar_cenario.py` roda a cada mudança, e
  `Criar experimento` grava `experimentos/<nome>/cenario.json` e os pontos. O mesmo desenho
  aparece na página de cada experimento. A nuvem aparece apagada: o modelo de rede com GPU não
  tem WAN, e as tarefas de GPU não vão à nuvem (`docs/modelo.md`, seção 5).

## Formato do cenário

Um experimento criado pela interface, ou à mão, é descrito por `cenario.json`. Os campos
ausentes assumem os valores de `PADRAO` em `experimentos/gerar_cenario.py`.

| Campo | Valores | Efeito |
|---|---|---|
| `servidores` | `quantidade`, `com_gpu`, `modelo` (`tocze` ou `rodrigues`) | um servidor por ponto de acesso; os `com_gpu` primeiros têm uma RTX 3050 |
| `carga` | `yolo` ou `mista` | só YOLO, ou 30% YOLO e 70% aplicações de CPU (Sonmez et al., 2019) |
| `dispositivos` | inteiro | total de dispositivos, com `mobilidade` `nomade` ou `fixa` (`ponto_fixo`) |
| `dispositivos_por_ponto` | lista de inteiros | dispositivos fixos em cada ponto de acesso; tem precedência sobre `dispositivos` |
| `man` | `ligada`, `banda_mbps`, `propagacao_ms` | rede metropolitana (`docs/modelo.md`, seção 3) |
| `politica` | `AUTO`, `LOCAL`, `LOCAL_FIRST` | escolha da GPU (`docs/modelo.md`, seção 5) |
| `duracao_min`, `aquecimento_min` | minutos | tempo simulado e aquecimento descartado |
| `variar` | lista de `{campo, valores, pasta}` | cada combinação de valores é um ponto; `campo` em notação de pontos (`servidores.com_gpu`, `dispositivos_por_ponto.0`) |
| `excluir` | lista de combinações | combinações que não viram ponto |

O gerador recusa cenários sem memória livre na GPU (6144 − N × 416 MB) e avisa quando um
ponto de acesso recebe mais de 9,95 clientes YOLO, limite da WLAN de 480 Mbps.

```bash
python3 experimentos/gerar_cenario.py experimentos/<nome>/cenario.json --previa
python3 experimentos/gerar_cenario.py experimentos/<nome>/cenario.json
python3 experimentos/gerar_cenario.py --conferir-todos
```

Os quatro experimentos publicados também têm `cenario.json`, com `gerado_por`
`gerar_configs.py`: as suas configurações continuam vindo de `gerar_configs.py`, e
`--conferir-todos` verifica que a descrição reproduz os valores versionados dos 41 pontos.

## Pontos sem código curto

Os scripts de `execucao/` e `analise/` aceitam, além dos códigos K01…N14, a pasta de um
ponto relativa a `experimentos/`:

```bash
bash execucao/rodar_experimento.sh cameras-fixas/local-primeiro/09-no-ponto-quente 10 1
python3 analise/publicar_manifest.py --ponto cameras-fixas/local-primeiro/09-no-ponto-quente --lista <lista>
```

As saídas desses pontos ficam em `saidas/<pasta do ponto>/`, e o registro por tarefa, em
`saidas/deeplog/<pasta do ponto>/`.
