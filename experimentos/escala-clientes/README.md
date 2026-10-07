# Escala de clientes numa GPU

**Pergunta.** Quantos clientes de detecção de objetos uma única GPU atende?

**Variável.** N, o número de clientes YOLO: 1, 4, 6, 8, 9, 10, 12 e 14.

**Fixo.** Um servidor de borda com uma RTX 3050 e uma VM, como no ambiente de Rodrigues
et al. (2026); quadros a 30 fps com chegada periódica; WLAN de 480 Mbps com contenção;
60 min simulados, 5 min de aquecimento; 30 execuções por ponto.

**Escolha dos pontos.** Dois limites analíticos, calculados antes das execuções:

    GPU:  N = 250 quadros/s / 30,3 quadros/s por cliente = 8,25
    WLAN: N = 480 Mbps / 48,24 Mbps por cliente          = 9,95

Por isso há um ponto por cliente entre 8 e 10 e pontos esparsos fora dessa faixa.

**Carga e buffer variam juntos.** A memória livre da GPU é 6144 − N × 416 MB
(`docs/modelo.md`, seção 2), então o número máximo de quadros em processamento cai de
286 (N = 1) para 16 (N = 14). Parte do comportamento após a saturação se deve ao buffer,
e não à carga.

## Resultados

| Ponto | Clientes | FRTT médio | p99 | Falha | Buffer (quadros) | Ocupação da GPU |
|---|---|---|---|---|---|---|
| N01 | 1 | 8,44 ms | 8,44 ms | 0% | 286 | 12% |
| N04 | 4 | 16,62 ms | 35,30 ms | 0% | 224 | 48,5% |
| N06 | 6 | 20,55 ms | 34,88 ms | 0% | 182 | 72,7% |
| N08 | 8 | 51,58 ms | 66,68 ms | 0% | 140 | 97,0% |
| N09 | 9 | 450,99 ms | 536,13 ms | 9,29% | 120 | 98,9% |
| N10 | 10 | 398,62 ms | 431,54 ms | 18,36% | 99 | 99,0% |
| N12 | 12 | 255,09 ms | 317,61 ms | 35,06% | 57 | 94,5% |
| N14 | 14 | 95,32 ms | 175,32 ms | 53,54% | 16 | 78,8% |

Médias e falhas: 30 execuções. Percentis: registro por tarefa de 10 execuções
(`resultados/percentis_latencia.csv`). Ocupação da GPU: cálculo analítico do validador.

1. **A transição ocorre entre N = 8 e N = 9, onde a análise previu.** N = 8 é o último
   ponto sem perda (51,58 ms, dentro do orçamento de 100 ms); em N = 9 a latência média
   é 8,7 vezes maior e surge perda.
2. **Após a saturação, a latência cai e a perda sobe** (451 → 95 ms contra 9% → 54%),
   porque o buffer encolhe com N. A latência sozinha inverteria a conclusão.
3. **A rede não se torna o gargalo.** A GPU satura antes da WLAN e rejeita quadros na
   admissão; o tráfego servido não passa de 82% da banda. Todas as falhas são por
   capacidade, nenhuma por banda; a contenção acrescenta atraso de rede (6,2 → 82,8 ms),
   mas não causa perda, pois o buffer do enlace é infinito.
4. **A cauda confirma N = 8 por um critério e o rejeita por outro.** O p99 de N = 8,
   66,68 ms, cabe no orçamento de 100 ms; mas todos os quadros de N = 8 excedem o
   intervalo entre quadros de 33 ms, e a taxa se mantém por fila e paralelismo. Em N = 4
   e N = 6, 6,5% e 3,2% dos quadros excedem 33 ms.

## Figuras e tabelas da série

Em `resultados/`: `curva_escala_clientes.csv` e as curvas de latência, rede e falha;
`distribuicao_latencia_escala` (CDF e percentis por tarefa); `falhas_por_app_escala`;
`latencia_multi_escala`.
