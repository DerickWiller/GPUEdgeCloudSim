#!/usr/bin/env python3
"""Ocupação dos servidores de borda ao longo do tempo, a partir do SIMRESULT_*_VM_LOAD.log.

O registro amostra, a cada 6 s de simulação, a utilização média dos hosts de borda: nos
hosts com GPU, a média entre a reserva de CPU e a utilização da GPU, que é binária (100%
com qualquer tarefa em execução). Cada painel é um ponto; a linha é a média das
execuções e a faixa, o intervalo entre o mínimo e o máximo.

Esta série não mede a ocupação da GPU, por duas razões: a utilização registrada é binária
e misturada à de CPU, e a amostragem instantânea a cada 6 s de eventos de 4 ms subestima
a ocupação em proporção variável (de 0,11 a 0,55 da ocupação calculada analiticamente). A série serve apenas para observar a estrutura temporal,
como a estacionariedade após o aquecimento; valores de ocupação devem ser obtidos pelo
cálculo analítico (vazão servida × 4 ms).

Em alguns pontos a faixa entre execuções desaparece entre cerca de 5 e 20 min, o que
sugere sincronia entre o passo de amostragem (6 s) e o período de chegada (33 ms);
o efeito não foi investigado.

A figura é gravada em experimentos/comparativos/figuras/ocupacao_temporal.png.

Uso:
    python3 analise/plotar_ocupacao_temporal.py
    python3 analise/plotar_ocupacao_temporal.py --pontos K01,N14
"""

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import config

COR_LINHA = "#2a78d6"
COR_FAIXA = "#2a78d6"
INK = "#0b0b0b"
INK_MUTED = "#52514e"

# Os cinco pontos da densidade de GPU e as duas pontas da escala de clientes.
PADRAO = ["K01", "K02", "K03", "K07", "K14", "N01", "N14"]
WARM_UP_S = 300.0   # aquecimento de 5 min, comum a todos os pontos


def series_do_ponto(num: str) -> pd.DataFrame:
    """Média, mínimo e máximo da ocupação de borda por instante, entre as execuções."""
    logs = [log for pasta in config.runs_da_amostra(num)
            for log in sorted(pasta.glob("*VM_LOAD.log"))]
    colunas = {}
    for i, log in enumerate(logs):
        tempos, cargas = [], []
        for linha in open(log, encoding="utf-8"):
            if linha.startswith("#"):
                continue
            p = linha.strip().split(";")
            if len(p) < 2:
                continue
            tempos.append(float(p[0]))
            cargas.append(float(p[1]))
        if tempos:
            colunas[f"run{i}"] = pd.Series(cargas, index=tempos)

    if not colunas:
        return pd.DataFrame()

    m = pd.DataFrame(colunas)
    return pd.DataFrame({"media": m.mean(axis=1),
                         "minimo": m.min(axis=1),
                         "maximo": m.max(axis=1)}).sort_index()


def painel(ax, num: str, d: pd.DataFrame):
    cfg = config.ponto(num)
    t = d.index / 60.0   # segundos → minutos

    ax.fill_between(t, d["minimo"], d["maximo"], color=COR_FAIXA, alpha=0.20,
                    linewidth=0)
    ax.plot(t, d["media"], "-", color=COR_LINHA, linewidth=1.8, zorder=3)

    ax.axvline(WARM_UP_S / 60.0, color=INK_MUTED, linestyle=":", linewidth=1.5)
    ax.text(WARM_UP_S / 60.0, 98, " warm-up", fontsize=8, color=INK_MUTED,
            va="top", ha="left")

    ax.set_title(f"{cfg['rotulo']}  ·  "
                 f"média {d['media'].mean():.1f}%",
                 fontsize=10, fontweight="bold", color=INK, pad=6)
    ax.set_ylim(0, 100)
    ax.grid(True, alpha=0.25, linestyle="--")
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(labelsize=9)


def plotar(dados: dict, output_file: Path):
    n = len(dados)
    ncols = min(4, n)
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.2 * ncols, 3.6 * nrows),
                             squeeze=False, sharey=True)

    for i, (num, d) in enumerate(dados.items()):
        painel(axes[i // ncols][i % ncols], num, d)
    for j in range(n, nrows * ncols):
        axes[j // ncols][j % ncols].axis("off")

    fig.supxlabel("Tempo de simulação (min)", fontweight="bold", color=INK,
                  fontsize=11, y=0.125)
    fig.supylabel("VM_LOAD amostrado (%) — NÃO é a utilização real",
                  fontweight="bold", color=INK, fontsize=11)
    fig.suptitle("Estrutura temporal do VM_LOAD — linha = média de 30 runs, "
                 "faixa = min–max",
                 fontweight="bold", fontsize=13, color=INK, y=0.995)
    fig.text(0.5, 0.012,
             "A altura destas curvas não é a ocupação da GPU: o registro amostra a cada 6 s "
             "eventos de 4 ms e mistura a reserva de CPU com a utilização binária da GPU.\n"
             "Ocupação calculada vs amostrada: 1 cliente 12,1%→4,5% · 14 clientes "
             "78,8%→43,6% · 1 GPU de 14 99,1%→10,6%. O ponto mais saturado parece o mais ocioso.\n"
             "Use este gráfico só para a forma da série (estacionariedade, dispersão "
             "entre runs); para o número, use o cálculo analítico da validação.",
             ha="center", va="bottom", fontsize=9, color=INK_MUTED)

    plt.tight_layout(rect=[0.02, 0.17, 1, 0.94])
    plt.savefig(output_file, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"\n✓ Gerado: {output_file}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Série temporal de ocupação dos servidores de borda.")
    parser.add_argument("--pontos", default=",".join(PADRAO),
                        help=f"lista separada por vírgula (padrão: {','.join(PADRAO)})")
    parser.add_argument("--permitir-parcial", action="store_true",
                        help="grava a figura mesmo que falte algum ponto")
    args = parser.parse_args()

    nums = [v.strip().upper() for v in args.pontos.split(",") if v.strip()]

    print("=" * 74)
    print("Ocupação das VMs de borda no tempo")
    print("=" * 74)

    dados = {}
    for num in nums:
        if num not in config.PONTOS:
            print(f"ERRO: ponto {num} desconhecido. Use um de: {', '.join(config.PONTOS)}.")
            return 1
        d = series_do_ponto(num)
        if d.empty:
            print(f"  AVISO: {num} sem VM_LOAD legível na amostra; ponto ignorado.")
            continue
        dados[num] = d
        print(f"  {num}: {len(d)} amostras  "
              f"média {d['media'].mean():.2f}%  pico {d['maximo'].max():.2f}%")

    if not dados:
        print("ERRO: nenhum ponto com VM_LOAD.")
        return 1
    faltando = [n for n in nums if n not in dados]
    if faltando and not args.permitir_parcial:
        print(f"Figura não gravada, para não substituir a completa: faltam "
              f"{', '.join(faltando)}. Use --permitir-parcial para gravá-la assim mesmo.")
        return 0

    saida = config.COMPARATIVOS_DIR / "figuras"
    saida.mkdir(parents=True, exist_ok=True)
    plotar(dados, saida / "ocupacao_temporal.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
