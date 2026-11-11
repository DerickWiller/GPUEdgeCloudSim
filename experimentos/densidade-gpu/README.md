# Densidade de GPU na borda

**Pergunta.** Quantos dos 14 servidores de borda precisam ter GPU para sustentar
detecção de objetos em tempo real?

**Variável.** K, o número de servidores com uma RTX 3050: 1, 2, 3, 7 e 14.

**Fixo.** 14 servidores com 8 VMs de 2 núcleos a 10 000 MIPS (Toczé et al., 2020,
Tabela 5); 30 dispositivos com carga mista, dos quais 9 executam YOLO a 30 fps e 21
executam três aplicações só de CPU (Sonmez et al., 2019, Tabela II); WLAN de 480 Mbps
com contenção; 60 min simulados, 5 min de aquecimento; 30 execuções por ponto.

## Resultados

| Ponto | GPUs | FRTT médio do YOLO | p50 | p99 | Falha do YOLO |
|---|---|---|---|---|---|
| K01 | 1 de 14 | 447,57 ms | 456,51 ms | 517,20 ms | 9,16% |
| K02 | 2 de 14 | 13,11 ms | 8,44 ms | 33,29 ms | 0% |
| K03 | 3 de 14 | 10,43 ms | 8,44 ms | 33,32 ms | 0% |
| K07 | 7 de 14 | 8,62 ms | 8,44 ms | 11,76 ms | 0% |
| K14 | 14 de 14 | 8,62 ms | 8,44 ms | 11,76 ms | 0% |

FRTT médio e falha do YOLO: 30 execuções (`resultados/curva_densidade_gpu.csv` e
`<ponto>/resultados/metrics_by_app.csv`). O `metrics_summary.csv` de cada ponto traz a
média de todas as aplicações, ligeiramente diferente (445,49 ms em K01, 13,73 ms em K02),
pois inclui as aplicações de CPU. Percentis: registro por tarefa de 10 execuções
(`resultados/percentis_latencia.csv`).

1. **A média indica K = 2; a cauda, K entre 3 e 7.** De K = 1 para K = 2 a latência média
   do YOLO cai 97% (447,57 → 13,11 ms), mas K02 e K03 têm p99 de 33,29 e 33,32 ms, acima do
   intervalo entre quadros de 33 ms: 1,05% e 1,29% dos quadros o excedem.
2. **A mediana é constante de K = 2 a K = 14**, em 8,44 ms, o piso físico de 4,00 ms de
   GPU e 4,44 ms de rede. GPUs adicionais não aceleram o quadro típico; reduzem quantos
   quadros esperam em fila. A razão p99/p50 cai de 3,9 (K = 2 e 3) para 1,4 (K = 7 e 14).
3. **Isolamento entre classes.** A saturação da GPU em K01 não altera a latência das
   aplicações de CPU (variação de até 0,1%), enquanto a do YOLO cai 98,1% de K = 1 para
   K = 14. O isolamento decorre do modelo (`docs/modelo.md`, seção 8).

## Figuras e tabelas da série

Em `resultados/`: `curva_densidade_gpu.csv` e as curvas de latência, rede e falha;
`densidade_percentis` (média, p50, p95 e p99 contra K); `sintese_densidade` (variação a
cada GPU acrescentada); `retorno_decrescente` (vazão e ganho marginal por GPU);
`isolamento_apps`; `falhas_por_app_densidade`; `latencia_multi_densidade`.

## Situação dos resultados

30 execuções por ponto. A mobilidade usa a semente de cada execução, e repetir uma
semente repete o resultado. Com 7 ou mais GPUs nenhum quadro espera em fila, e K07 e K14
dão resultados idênticos.
