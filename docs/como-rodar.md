# Como compilar, executar e analisar

Todos os comandos partem da raiz do repositório. Os scripts localizam a raiz sozinhos e
podem ser chamados de qualquer diretório.

## Requisitos

- Java 21 (`javac` e `java` no PATH).
- Python 3.12 com `pandas`, `numpy`, `matplotlib` e `seaborn`
  (`pip install -r requirements.txt`).
- Cerca de 2 GB de memória por simulação em execução.

### Windows

Os scripts de `execucao/` rodam no Git Bash (Git for Windows), com o Java e o Python do
Windows; os comandos deste guia são os mesmos, com `python` no lugar de `python3` quando
este for só o atalho da Microsoft Store. Diferenças já tratadas no repositório:

- o classpath usa `;` e caminhos no formato `C:/...` (`execucao/_comum.sh`);
- nos scripts, o interpretador é `python` quando `python3` não executa;
- o simulador grava o console em UTF-8 e com ponto decimal, independentemente do idioma do
  sistema, e a análise lê e grava os arquivos em UTF-8;
- as saídas do simulador terminam as linhas com LF (`-Dline.separator`), e os caminhos
  gravados em manifestos e métricas usam `/`, de modo que os arquivos são iguais aos do
  Linux;
- os `.sh` são mantidos com fim de linha LF (`.gitattributes`), mesmo com
  `core.autocrlf=true`. Se um clone tiver os `.sh` com CRLF, `git add --renormalize .` e um
  novo checkout desses arquivos corrigem o fim de linha.

Uma bateria de N01 (sementes 1 a 30) no Windows reproduz o `metrics_runs.csv` publicado.

## Identificação dos pontos

Cada ponto experimental tem um código curto, usado por todos os scripts:

| Código | Experimento | Pasta |
|---|---|---|
| K01, K02, K03, K07, K14 | densidade de GPU: K servidores com GPU entre 14 | `experimentos/densidade-gpu/<KK>-gpus/` |
| N01, N04, N06, N08, N09, N10, N12, N14 | escala de clientes: N clientes YOLO numa GPU | `experimentos/escala-clientes/<NN>-clientes/` |

## 1. Compilar

```bash
bash execucao/compilar.sh
```

Compila `GPUEdgeCloudSim/src` com os JARs de `GPUEdgeCloudSim/lib` e grava as classes em
`GPUEdgeCloudSim/bin` (não versionada).

## 2. Executar

```bash
bash execucao/rodar_teste_rapido.sh            # compila e roda N01 com a semente 1
bash execucao/rodar_simulacao.sh K02 7         # uma execução de K02, semente 7
bash execucao/rodar_experimento.sh K02         # bateria: 30 execuções, sementes 1 a 30
bash execucao/rodar_experimento.sh N08 10 100  # 10 execuções, sementes 100 a 109
bash execucao/rodar_serie.sh escala            # bateria de todos os pontos de um experimento
bash execucao/rodar_deeplog.sh N14 10 1        # registro por tarefa, para percentis
```

Cada execução grava em `saidas/<experimento>/<ponto>/run_<data>_<hora>_seed<N>/`:

| Arquivo | Conteúdo |
|---|---|
| `SIMRESULT_*_ALL_APPS_GENERIC.log` | métricas agregadas de todas as aplicações |
| `SIMRESULT_*_<APLICAÇÃO>_GENERIC.log` | métricas por aplicação |
| `SIMRESULT_*_LOCATION.log` | dispositivos por ponto de acesso, a cada 6 s |
| `SIMRESULT_*_VM_LOAD.log` | utilização dos servidores de borda, a cada 6 s |
| `console.log.gz` | registro do simulador, comprimido |
| `config.properties`, `*.xml` | cópia da configuração utilizada |

`saidas/` não é versionada: uma bateria de 30 execuções ocupa de 0,2 a 1,3 GB. O registro
por tarefa vai para `saidas/deeplog/`, fora da amostra oficial, e ocupa cerca de 90 MB
por execução.

O simulador termina com código 0 mesmo quando captura uma exceção; por isso
`rodar_simulacao.sh` só considera a execução bem-sucedida se os SIMRESULT existirem.

## 3. Publicar a amostra, agregar e validar

```bash
# Manifesto: as execuções da bateria passam a ser a amostra oficial do ponto
python3 analise/publicar_manifest.py --ponto K02 \
    --lista saidas/densidade-gpu/02-gpus/bateria_20261007_101500.txt

# Métricas agregadas (metrics_runs.csv, metrics_by_app.csv, metrics_summary.csv)
python3 analise/agregar_metricas.py --ponto K02

# Validação contra o modelo; sai com código 1 se alguma checagem reprovar
python3 analise/validar_saidas_misto.py --ponto K02   # densidade de GPU
python3 analise/validar_saidas.py --ponto N08         # escala de clientes
```

`rodar_experimento.sh` não altera a amostra oficial: ao final, grava a lista das suas
execuções e imprime o comando de publicação. Assim, uma bateria de teste não substitui o
manifesto sem que isso seja pedido. A publicação recusa sementes repetidas, e a agregação
e a validação recusam gravar resultados se faltar alguma execução do manifesto nesta
máquina (`--permitir-parcial` força). Nenhum número deve ser usado sem passar pelo
validador.

## 4. Figuras

Por ponto, em `experimentos/<experimento>/<ponto>/resultados/figuras/`:

```bash
python3 analise/plotar_metricas.py --ponto K02         # latência, vazão e falha por execução
python3 analise/plotar_breakdown.py --ponto K02        # FRTT decomposto em processamento e rede
python3 analise/plotar_falhas_por_app.py --ponto K02   # falhas por aplicação (exige saídas brutas)
python3 analise/plotar_mobilidade.py --ponto K02       # concentração por ponto de acesso (exige saídas brutas)
```

Por experimento, em `experimentos/<experimento>/resultados/`:

```bash
python3 analise/plotar_curva_densidade_gpu.py
python3 analise/plotar_curva_escala_clientes.py
python3 analise/plotar_densidade_percentis.py
python3 analise/plotar_sintese_densidade.py
python3 analise/plotar_retorno_decrescente.py
python3 analise/plotar_isolamento_apps.py
python3 analise/plotar_falhas_por_app_agregado.py --serie densidade
python3 analise/plotar_multi_latencia.py --serie escala
python3 analise/plotar_distribuicao_latencia.py --serie escala   # exige registro por tarefa
```

Comparações entre os dois experimentos, em `experimentos/comparativos/`:

```bash
python3 analise/plotar_conservacao_fluxo.py
python3 analise/plotar_dispersao_falha_latencia.py
python3 analise/plotar_ocupacao_temporal.py
python3 analise/plotar_multi_latencia.py --serie todos
python3 analise/plotar_distribuicao_latencia.py
```

Os scripts que dependem de saídas brutas avisam quando elas não estão disponíveis e não
sobrescrevem tabelas ou figuras existentes com versões parciais.

## 5. Configurações

As configurações dos pontos são geradas por `experimentos/gerar_configs.py`, a partir de
um modelo por experimento; alterações devem ser feitas no gerador:

```bash
python3 experimentos/gerar_configs.py
```

O campo `simulation_time` do `config.properties` está em minutos.

A rede metropolitana entre servidores de borda é ligada com `man_enabled=true` no
`config.properties` (`docs/modelo.md`, seção 3). Sem a chave, ela fica desligada, como nas
configurações dos experimentos publicados. Os validadores conferem o atraso de rede como
piso (WLAN + PCIe); o termo da MAN ainda não tem checagem analítica.

Duas chaves servem ao experimento de dois servidores (`docs/modelo.md`, seções 4 e 5):
`mobility_static_wlan_id=<id>` fixa todos os dispositivos num ponto de acesso, e
`edge_vm_selection=LOCAL` restringe a escolha às VMs do servidor desse ponto de acesso.
Ausentes, valem a mobilidade nômade e o critério da topologia.

## Cuidados na análise

- **Média não é distribuição.** O SIMRESULT traz médias; percentis e CDF por tarefa
  exigem o registro por tarefa (`rodar_deeplog.sh`).
- **Execuções são amostras independentes.** O eixo de semente não tem ordem temporal; não
  se ajusta tendência sobre ele. Usa-se média e IC95 da média.
- **Picos se calculam por execução.** A média elemento a elemento entre execuções apaga
  concentrações transitórias, como o ponto de acesso mais cheio.
- **`VM_LOAD` não é a ocupação da GPU** (`docs/modelo.md`, seção 8).
- **Tráfego contra a capacidade da WLAN:** compara-se o tráfego servido, e não o
  ofertado, pois a GPU rejeita quadros antes de eles chegarem à rede.
- **Cor e rótulo.** A cor de um ponto vem de `analise/config.py` (rampa ordenada por
  experimento) e a de uma aplicação, de `config.cor_da_app`; o rótulo descreve a condição
  física ("2 de 14 servidores com GPU").
