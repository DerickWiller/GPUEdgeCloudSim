#!/usr/bin/env python3
"""Gera gráficos da dispersão das métricas entre as execuções de um ponto.

Lê metrics_runs.csv e gera três gráficos de linha (latency.png, throughput.png,
failure_rate.png) com o valor de cada execução, a média, a faixa de IC95 da média e
um resumo estatístico, em resultados/figuras/ do ponto.

Uso:
    python3 analise/plotar_metricas.py --ponto K02
"""

import argparse
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from math import sqrt
import pandas as pd
import seaborn as sns

import config

sns.set_style("whitegrid")
plt.rcParams["figure.figsize"] = (12, 6)
plt.rcParams["font.size"] = 11
plt.rcParams["axes.labelsize"] = 12
plt.rcParams["axes.titlesize"] = 14


def load_metrics(metrics_csv, ponto: str) -> pd.DataFrame:
    """Carrega metrics_runs.csv e mantém apenas runs com dados válidos."""
    if not metrics_csv.exists():
        print(f"ERRO: Arquivo {metrics_csv} não encontrado!")
        print(f"Execute primeiro: python3 analise/agregar_metricas.py --ponto {ponto}")
        sys.exit(1)

    df = pd.read_csv(metrics_csv)
    df_valid = df[(df["latency_mean_ms"] > 0) | (df["completed_tasks"] > 0)].copy()
    if len(df_valid) == 0:
        print("AVISO: Nenhum run com dados válidos — usando todos mesmo assim.")
        df_valid = df.copy()

    if "run_id" in df_valid.columns:
        df_valid = df_valid.sort_values("run_id")
    else:
        df_valid = df_valid.sort_values("seed")
        df_valid["run_id"] = range(1, len(df_valid) + 1)
    return df_valid


def cantos_mais_vazios(ax, xs, ys):
    """Ordena os quatro cantos do eixo pelo número de pontos, do menor para o maior.

    Usado para posicionar a caixa de estatísticas sem cobrir dados. Opera em
    coordenadas normalizadas do eixo (0 a 1), independentes da unidade da métrica.
    """
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    larg, alt = (x1 - x0) or 1.0, (y1 - y0) or 1.0
    faixa = 0.32                      # tamanho da quina, em fração do eixo

    cantos = {
        "upper left": (0.0, faixa, 1 - faixa, 1.0),
        "upper right": (1 - faixa, 1.0, 1 - faixa, 1.0),
        "lower left": (0.0, faixa, 0.0, faixa),
        "lower right": (1 - faixa, 1.0, 0.0, faixa),
    }
    contagem = {}
    for nome, (xa, xb, ya, yb) in cantos.items():
        n = 0
        for x, y in zip(xs, ys):
            xn, yn = (x - x0) / larg, (y - y0) / alt
            if xa <= xn <= xb and ya <= yn <= yb:
                n += 1
        contagem[nome] = n
    # desempate por ordem fixa, para que o layout seja reprodutível
    ordem = ["lower right", "upper right", "lower left", "upper left"]
    return sorted(contagem, key=lambda c: (contagem[c], ordem.index(c)))


ANCORA_DO_CANTO = {
    "upper left": (0.02, 0.98, "top", "left"),
    "upper right": (0.98, 0.98, "top", "right"),
    "lower left": (0.02, 0.02, "bottom", "left"),
    "lower right": (0.98, 0.02, "bottom", "right"),
}


def plot_line(df: pd.DataFrame, metric_col: str, ylabel: str, title: str,
              unit: str, marker: str, color: str, output_file):
    """Gráfico da métrica por execução, com média e faixa do IC95 da média.

    Não se ajusta reta de tendência sobre o identificador da execução: as execuções
    são amostras independentes, sem ordem temporal, e a inclinação dependeria apenas
    da ordem arbitrária. A linha que liga os pontos serve só à leitura visual.
    """
    fig, ax = plt.subplots(figsize=(12, 6))
    df_sorted = df.sort_values("run_id")
    df_v = df_sorted[df_sorted[metric_col] > 0].copy() if metric_col != "failure_rate" else df_sorted.copy()

    if len(df_v) == 0:
        print(f"AVISO: nenhum run válido para {metric_col} — gráfico não gerado.")
        plt.close()
        return

    # Linha entre os pontos, para leitura da dispersão; o rótulo do eixo x indica que
    # ele não representa tempo.
    ax.plot(df_v["run_id"], df_v[metric_col], marker=marker, markersize=6,
            linewidth=2, color=color, label=ylabel, alpha=0.8, zorder=3)

    if len(df_v) > 1:
        media = df_v[metric_col].mean()
        desvio = df_v[metric_col].std()
        margem = 1.96 * desvio / sqrt(len(df_v))
        ax.axhline(media, color="#52514e", linestyle="--", linewidth=1.8,
                   label=f"Média = {media:.2f} {unit}")
        ax.axhspan(media - margem, media + margem, color="#52514e", alpha=0.12,
                   label=f"IC 95% da MÉDIA (±{margem:.2f} {unit}) — não é faixa de predição")

    ax.set_xlabel("Run ID (seed — amostras independentes, sem ordem temporal)",
                  fontweight="bold")
    ax.set_ylabel(ylabel, fontweight="bold")
    ax.set_title(title, fontweight="bold", pad=34)   # folga para a legenda acima do eixo
    ax.set_xticks(range(1, len(df_sorted) + 1))
    ax.set_xlim(0.5, len(df_sorted) + 0.5)
    ax.grid(True, alpha=0.3, linestyle="--")

    # Legenda acima do eixo, na horizontal: seus itens são longos demais para um
    # canto da área de plotagem sem cobrir dados.
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.005), ncol=3, fontsize=9,
              frameon=False, borderaxespad=0)

    # Caixa de estatísticas no canto com menos pontos.
    canto_caixa = cantos_mais_vazios(ax, df_v["run_id"], df_v[metric_col])[0]

    mean_val, std_val = df_v[metric_col].mean(), df_v[metric_col].std()
    stats_text = (f"Média: {mean_val:.2f} {unit}\nDesvio: {std_val:.2f} {unit}\n"
                  f"Min: {df_v[metric_col].min():.2f} {unit}\nMax: {df_v[metric_col].max():.2f} {unit}\n"
                  f"Runs válidos: {len(df_v)}/{len(df_sorted)}")
    x_cx, y_cx, va, ha = ANCORA_DO_CANTO[canto_caixa]
    ax.text(x_cx, y_cx, stats_text, transform=ax.transAxes, verticalalignment=va,
            horizontalalignment=ha,
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.7), fontsize=9)

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"✓ Gerado: {output_file}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera gráficos da dispersão das métricas de um ponto.")
    parser.add_argument("--ponto", required=True, choices=list(config.PONTOS),
                        help="Código do ponto (K01…K14 ou N01…N14)")
    args = parser.parse_args()

    cfg = config.ponto(args.ponto)
    experimento_dir = cfg["experimento"]
    plots_dir = experimento_dir / "figuras"
    metrics_csv = experimento_dir / "metrics_runs.csv"
    plots_dir.mkdir(parents=True, exist_ok=True)
    rotulo = cfg["rotulo"]
    cor = cfg["cor"]

    print("=" * 70)
    print(f"Gerando gráficos de evolução das métricas — {rotulo}")
    print("=" * 70)
    print()

    df = load_metrics(metrics_csv, args.ponto)
    print(f"  {len(df)} runs carregados\n")

    plot_line(df, "latency_mean_ms", "Latência Média (ms)",
              f"Latência por run — dispersão entre as seeds\n{rotulo}", "ms", "o", cor,
              plots_dir / "latency.png")
    plot_line(df, "throughput", "Throughput (tasks/s)",
              f"Throughput por run — dispersão entre as seeds\n{rotulo}", "tps", "s", cor,
              plots_dir / "throughput.png")
    plot_line(df, "failure_rate", "Taxa de Falhas (%)",
              f"Taxa de falhas por run — dispersão entre as seeds\n{rotulo}", "%", "^", cor,
              plots_dir / "failure_rate.png")

    print(f"\nGráficos salvos em: {plots_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
