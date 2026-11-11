"""Intervalo de confiança de 95% da média entre execuções independentes (sementes).

A semiamplitude é t(0,975; n - 1) * s / sqrt(n), com s o desvio padrão amostral e t o
quantil da distribuição t de Student com n - 1 graus de liberdade. Com 30 execuções,
t = 2,045; com 10, t = 2,262. Fonte única para os scripts de analise/ e para a interface,
que usa só a biblioteca padrão.
"""

import math
import statistics

# Quantil bilateral de 95% da t de Student por graus de liberdade, com quatro casas.
_T95 = {1: 12.7062, 2: 4.3027, 3: 3.1824, 4: 2.7764, 5: 2.5706, 6: 2.4469, 7: 2.3646,
        8: 2.3060, 9: 2.2622, 10: 2.2281, 11: 2.2010, 12: 2.1788, 13: 2.1604, 14: 2.1448,
        15: 2.1314, 16: 2.1199, 17: 2.1098, 18: 2.1009, 19: 2.0930, 20: 2.0860, 21: 2.0796,
        22: 2.0739, 23: 2.0687, 24: 2.0639, 25: 2.0595, 26: 2.0555, 27: 2.0518, 28: 2.0484,
        29: 2.0452, 30: 2.0423, 40: 2.0211, 60: 2.0003, 120: 1.9799}
_T_INFINITO = 1.9600


def t95(graus_de_liberdade: int) -> float:
    """Quantil t(0,975). Entre os valores tabelados acima de 30 graus de liberdade,
    interpola-se linearmente em 1/gl, aproximação usual das tabelas da t."""
    gl = int(graus_de_liberdade)
    if gl < 1:
        raise ValueError("o intervalo de confiança exige ao menos 2 execuções")
    if gl in _T95:
        return _T95[gl]
    pontos = sorted(_T95.items()) + [(math.inf, _T_INFINITO)]
    for (g0, t0), (g1, t1) in zip(pontos, pontos[1:]):
        if g0 < gl < g1:
            inv0, inv1 = 1 / g0, (0.0 if g1 == math.inf else 1 / g1)
            return t1 + (t0 - t1) * (1 / gl - inv1) / (inv0 - inv1)
    return _T_INFINITO


def semiamplitude(desvio: float, n: int) -> float:
    """Semiamplitude do IC95 da média a partir do desvio padrão amostral e de n."""
    return t95(n - 1) * desvio / math.sqrt(n) if n > 1 else 0.0


def ic95(valores) -> float:
    """Semiamplitude do IC95 da média dos valores (zero com menos de 2 valores)."""
    valores = list(valores)
    return semiamplitude(statistics.stdev(valores), len(valores)) if len(valores) > 1 else 0.0
