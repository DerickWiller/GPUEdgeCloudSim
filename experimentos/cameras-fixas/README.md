# Câmeras fixas: ponto de acesso sobrecarregado e vizinhos pela MAN

**Pergunta.** Quando um ponto de acesso recebe mais câmeras do que a sua GPU atende, a MAN
permite usar as GPUs dos vizinhos sem penalizar as câmeras dos demais pontos?

**Variável.** h, o número de câmeras no ponto quente (ponto de acesso 0): 2, 4, 6, 8 e 9.
Três políticas por ponto, cada uma com os seus pontos em `local/`, `rodizio/` e
`local-primeiro/`:

| Política | Chave | Escolha da GPU |
|---|---|---|
| Só local | `edge_vm_selection=LOCAL` | a do servidor do ponto de acesso da câmera |
| Rodízio | `edge_vm_selection=AUTO` | as quatro, em rodízio, sem considerar a localização |
| Menor tempo estimado | `edge_vm_selection=LOCAL_FIRST` | a de menor (n + 1) · S, somada a ida e volta pela MAN nas remotas |

**Fixo.** Quatro servidores de borda iguais aos da densidade de GPU, um por ponto de acesso,
cada um com uma RTX 3050; 2, 1 e 1 câmeras nos pontos de acesso 1 a 3
(`mobility_static_devices_per_wlan=h,2,1,1`); MAN habilitada, com 1 000 Mbps e 10 ms de
propagação; quadros a 30 fps com chegada periódica; WLAN de 480 Mbps com contenção; 60 min
simulados, 5 min de aquecimento.

O desenho fica limitado a 9 câmeras por ponto de acesso, abaixo da saturação da WLAN
(9,95 clientes); até 13 no total, para que a memória livre de cada GPU seja positiva
(6144 − 13 × 416 = 736 MB). A memória livre desconta o modelo residente de todas as câmeras
nas três políticas (`docs/modelo.md`, seção 6).

**Expectativa analítica.** Só local, a GPU do ponto quente satura com h = 8,25 câmeras,
como na escala de clientes, e os demais pontos ficam ociosos. O rodízio divide a carga
entre as quatro GPUs, mas cerca de 3/4 dos quadros de todas as câmeras pagam cerca de 22 ms
de MAN. O menor tempo estimado deve coincidir com o só local enquanto a fila local não
exceder a remota em cerca de 5 quadros (d_MAN / S) e desviar para os vizinhos só os quadros
excedentes do ponto quente.

Com h = 4 e h = 8 (8 e 12 câmeras), o total é múltiplo de 4, e o rodízio prende cada câmera
à mesma GPU (`docs/modelo.md`, seção 5): a fração de quadros pela MAN passa a
depender de qual GPU coube a cada câmera, e não da carga.

## Resultados

Latência do YOLO, em ms: média de 10 execuções de 60 min por ponto e política, com IC95 da
média no total; separada entre as câmeras do ponto quente e as dos demais pontos pelo registro
por tarefa. MAN com 1 000 Mbps e 10 ms de propagação.

| h | Só local | quente | demais | Rodízio | quente | demais | Menor tempo | quente | demais |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 10,5 ± 2,4 | 11,5 | 10,0 | 27,7 ± 1,9 | 28,8 | 27,1 | 10,5 ± 2,4 | 11,5 | 10,0 |
| 4 | 12,5 ± 2,1 | 15,7 | 9,2 | 30,2 ± 4,0 | 29,3 | 31,1 | 12,5 ± 2,1 | 15,7 | 9,2 |
| 6 | 17,4 ± 2,4 | 20,9 | 12,1 | 31,1 ± 2,0 | 32,2 | 29,4 | 17,4 ± 2,4 | 20,9 | 12,1 |
| 8 | 37,0 ± 2,8 | 50,9 | 9,2 | 32,8 ± 1,5 | 32,7 | 32,8 | 23,4 ± 1,0 | 30,1 | 10,0 |
| 9 | 98,8 ± 1,5 | 143,8 | 11,4 | 40,1 ± 1,1 | 43,7 | 32,0 | 31,7 ± 2,0 | 39,5 | 13,9 |

Perto da saturação: p99 do registro por tarefa, falha e fração dos quadros do ponto quente que
atravessam a MAN.

| h | Só local: p99 | falha | MAN | Rodízio: p99 | falha | MAN | Menor tempo: p99 | falha | MAN |
|---|---|---|---|---|---|---|---|---|---|
| 8 | 66,4 | 0,0% | 0% | 50,4 | 0,0% | 74% | 50,1 | 0,0% | 9% |
| 9 | 216,4 | 9,5% | 0% | 69,1 | 0,0% | 75% | 76,4 | 0,0% | 21% |

1. Até h = 6, o menor tempo estimado coincide com o só local, execução a execução: nenhum
   quadro atravessa a MAN. O rodízio paga a MAN sem necessidade e fica 14 a 18 ms acima.
2. **Com h = 8 e h = 9, o menor tempo estimado é a melhor das três políticas.** Em h = 9, só
   local tem 143,8 ms e 9,5% de falha no ponto quente; o menor tempo estimado desvia
   21% dos quadros do ponto quente aos vizinhos (9% em h = 8) e mantém as câmeras dos demais pontos em
   13,9 ms, contra 32,0 ms no rodízio.
3. A cauda do ponto quente fica próxima da do rodízio: em h = 9, p99 de 76,4 ms contra
   69,1 ms. As câmeras do ponto quente pagam também a contenção da WLAN com 9 clientes
   (cerca de 21 ms de subida e descida, nas três políticas).
4. Só local reproduz a escala de clientes: com 8 câmeras na mesma GPU, o ponto quente tem
   50,9 ms, e a escala, 51,6 ms em N = 8.
5. Com carga baixa, a latência varia entre sementes. Com chegada periódica, a fase inicial sorteada
   decide se os quadros das câmeras de um ponto coincidem: em h = 6, só local varia de 12,0 a
   23,6 ms entre execuções. Nesses pontos (h = 4 e h = 6, só local e menor tempo estimado), a
   correlação entre o número da semente e a latência passa de 0,5 (0,57 e 0,78), o que, com 10
   execuções, ainda pode ser acaso; reconferir com 30 sementes.
