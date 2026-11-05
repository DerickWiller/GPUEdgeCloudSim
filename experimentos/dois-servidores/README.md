# Dois servidores: GPU local ou GPU remota pela MAN

**Pergunta.** A partir de quantos clientes compensa enviar quadros à GPU de outro servidor,
pagando a MAN, em vez de usar só a GPU local?

**Variável.** N, o número de clientes YOLO: 1, 4, 6, 8, 9, 10, 12 e 14, os mesmos pontos
da escala de clientes. Duas políticas por ponto: rodízio entre as duas GPUs (padrão) e
seleção só local (`edge_vm_selection=LOCAL`). Cada política tem os seus pontos em
`rodizio/` e `local/`.

**Fixo.** Dois servidores de borda iguais aos da densidade de GPU, cada um com uma
RTX 3050; todos os clientes fixos no ponto de acesso do primeiro
(`mobility_static_wlan_id=0`); MAN habilitada, com 1 000 Mbps e 10 ms de propagação;
quadros a 30 fps com chegada periódica; WLAN de 480 Mbps com contenção; 60 min simulados,
5 min de aquecimento.

**Expectativa analítica.** Só local, a GPU satura com N = 8,25 clientes, como na escala de
clientes. No rodízio, cada GPU recebe metade dos quadros e satura com N = 16,5, mas metade
dos quadros paga cerca de 22 ms de MAN. O rodízio deve perder com poucos clientes e ganhar
perto da saturação da GPU local.

**Rodízio com N par.** Com chegada periódica e N par, cada cliente recebe sempre a mesma
GPU (`docs/modelo.md`, seção 5): metade dos clientes paga a MAN em todos os quadros, e a
outra metade em nenhum.

**Rodízio com N ≥ 10.** Todos os clientes compartilham um ponto de acesso, e a WLAN de
480 Mbps comporta 480 / 48,24 = 9,95 clientes. No rodízio, as duas GPUs aceitam todos os
quadros, de modo que o tráfego inteiro chega ao enlace; com buffer infinito
(`wlan_buffer_size_kb=0`), a fila cresce sem limite e o atraso de subida chega a centenas de
segundos. Esses pontos não são executados no rodízio. Na seleção só local, a GPU satura antes
(8,25 clientes) e rejeita os quadros excedentes antes do envio, e a WLAN não satura.


## Resultados

Latência do YOLO: média de 10 execuções de 60 min por ponto e p99 do registro por tarefa
das mesmas execuções; MAN com 1 000 Mbps e 10 ms de propagação.

| Clientes | Só local: média | p99 | falha | Rodízio: média | p99 | falha |
|---|---|---|---|---|---|---|
| 1 | 8,4 ms | 8,4 ms | 0,0% | 19,2 ms | 30,1 ms | 0,0% |
| 4 | 15,7 ms | 35,3 ms | 0,0% | 20,3 ms | 36,6 ms | 0,0% |
| 6 | 20,9 ms | 34,9 ms | 0,0% | 23,3 ms | 58,4 ms | 0,0% |
| 8 | 50,9 ms | 66,7 ms | 0,0% | 26,3 ms | 56,4 ms | 0,0% |
| 9 | 451,5 ms | 536,1 ms | 9,3% | 37,1 ms | 65,2 ms | 0,0% |
| 10 | 398,2 ms | 431,5 ms | 18,4% | WLAN saturada | |  |
| 12 | 255,0 ms | 317,6 ms | 35,1% | WLAN saturada | |  |
| 14 | 96,1 ms | 175,3 ms | 54,1% | WLAN saturada | |  |

1. **O cruzamento fica entre 6 e 8 clientes.** Até 6, só local é melhor: o rodízio paga
   cerca de 22 ms de MAN em metade dos quadros sem precisar. A partir de 8, a fila da GPU
   local custa mais que a MAN.
2. **Só local reproduz a escala de clientes**, como esperado para a mesma GPU com a mesma
   carga (N = 8: 50,9 ms aqui e 51,6 ms na escala).
3. **A memória residente não limitou o rodízio.** Cada GPU desconta N × 416 MB, embora com N
   par cada cliente use só uma delas; nenhuma tarefa foi rejeitada até 9 clientes.
4. **Nenhuma política fixa é a melhor em toda a faixa**: usar a GPU local até ela encher e só
   então a remota combinaria as duas curvas.
