#!/usr/bin/env python3
"""Isolamento entre aplicações: o que a saturação da GPU faz com os vizinhos de CPU.

Os cinco pontos da densidade de GPU têm a mesma carga e diferem apenas em K, o número de
servidores de borda com GPU entre 14.

  (a) latência por aplicação em função de K, em escala logarítmica;
  (b) variação percentual da latência entre K = 1 e K = 14.

Ressalva: o isolamento observado decorre do modelo. O orquestrador aloca tarefas de
GPU apenas a VMs com GPU, e o simulador não representa disputa de barramento, cache
ou memória do host entre as duas classes de aplicação.

Lê os metrics_by_app.csv dos pontos e grava, em experimentos/densidade-gpu/resultados/,
a tabela isolamento_apps.csv e a figura figuras/isolamento_apps.png.

Uso:
    python3 analise/plotar_isolamento_apps.py
"""

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import config

INK = "#0b0b0b"
INK_MUTED = "#52514e"


def carregar() -> pd.DataFrame:
    """Junta os metrics_by_app.csv dos pontos da densidade de GPU."""
    linhas = []
    for num, k in sorted(config.SERIE_DENSIDADE_GPU.items(), key=lambda kv: kv[1]):
        csv = config.ponto(num)["experimento"] / "metrics_by_app.csv"
        if not csv.exists():
            print(f"  AVISO: {num} sem metrics_by_app.csv; ponto ignorado.")
            continue
        d = pd.read_csv(csv)
        d["k"] = k
        d["ponto"] = num
        linhas.append(d)
    if not linhas:
        print("ERRO: nenhum ponto da série tem métricas por aplicação.")
        sys.exit(1)
    return pd.concat(linhas, ignore_index=True)


def limpar_eixo(ax):
    ax.grid(True, alpha=0.25, linestyle="--")
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def painel_latencia(ax, df: pd.DataFrame):
    ks = sorted(df["k"].unique())
    for app in sorted(df["app"].unique()):
        d = df[df["app"] == app].sort_values("k")
        usa_gpu = bool(d["uses_gpu"].iloc[0])
        ax.plot(d["k"], d["latency_ms"], "-o", color=config.cor_da_app(app),
                linewidth=2.5 if usa_gpu else 2, markersize=8,
                markeredgecolor="white", markeredgewidth=1.5,
                label=f"{app} ({'GPU' if usa_gpu else 'CPU'})",
                zorder=3 if usa_gpu else 2)

        # Rótulo direto em K = 1, necessário para as duas cores de baixo contraste.
        p = d.iloc[0]
        ax.annotate(f"{p['latency_ms']:.0f} ms",
                    xy=(p["k"], p["latency_ms"]), xytext=(-8, 0),
                    textcoords="offset points", ha="right", va="center",
                    fontsize=9, fontweight="bold", color=INK)

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xticks(ks)
    ax.set_xticklabels([str(k) for k in ks])
    ax.set_xlabel("Servidores com GPU (K de 14)", fontweight="bold", color=INK)
    ax.set_ylabel("Latência média — FRTT (ms), escala log",
                  fontweight="bold", color=INK)
    ax.set_title("(a) Latência por aplicação conforme a densidade de GPU",
                 fontweight="bold", color=INK, pad=10)
    ax.legend(loc="center right", frameon=False, fontsize=9)
    limpar_eixo(ax)


def painel_variacao(ax, df: pd.DataFrame):
    """Variação percentual da latência entre o K mais escasso e o mais folgado."""
    k_min, k_max = df["k"].min(), df["k"].max()
    apps, variacoes, cores = [], [], []

    for app in sorted(df["app"].unique()):
        d = df[df["app"] == app]
        a = d[d["k"] == k_min]["latency_ms"]
        b = d[d["k"] == k_max]["latency_ms"]
        if a.empty or b.empty or a.iloc[0] == 0:
            continue
        apps.append(app)
        variacoes.append(100.0 * (b.iloc[0] - a.iloc[0]) / a.iloc[0])
        cores.append(config.cor_da_app(app))

    y = range(len(apps))
    ax.barh(list(y), variacoes, 0.6, color=cores, edgecolor="white", linewidth=2)
    ax.axvline(0, color=INK_MUTED, linewidth=1)

    for i, v in enumerate(variacoes):
        # Rótulo do lado de fora da ponta da barra, seja ela negativa ou positiva.
        ax.text(v + (-1.5 if v < 0 else 1.5), i, f"{v:+.1f}%",
                va="center", ha="right" if v < 0 else "left",
                fontsize=10, fontweight="bold", color=INK)

    ax.set_yticks(list(y))
    ax.set_yticklabels([a.replace("_", " ") for a in apps], fontsize=9)
    ax.set_xlabel(f"Variação da latência de K={k_min} para K={k_max} (%)",
                  fontweight="bold", color=INK)
    ax.set_title("(b) Quem realmente sente a densidade de GPU",
                 fontweight="bold", color=INK, pad=10)
    ax.margins(x=0.22)
    limpar_eixo(ax)


def plotar(df: pd.DataFrame, output_file: Path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6.4))
    painel_latencia(ax1, df)
    painel_variacao(ax2, df)

    fig.suptitle("Isolamento entre aplicações — a saturação da GPU não contamina "
                 "os vizinhos de CPU",
                 fontweight="bold", fontsize=13, color=INK, y=0.99)
    fig.text(0.5, 0.005,
             "Mesmo workload (30 dispositivos, 4 apps) sobre 14 servidores de borda; "
             "só muda quantos têm GPU. 30 runs por ponto.\n"
             "Isolamento é consequência do modelo (roteamento por gpu_length, "
             "sem disputa de barramento/cache entre classes), não medição de hardware.",
             ha="center", va="bottom", fontsize=9, color=INK_MUTED)

    plt.tight_layout(rect=[0, 0.07, 1, 0.94])
    plt.savefig(output_file, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"\n✓ Gerado: {output_file}")


def main() -> int:
    argparse.ArgumentParser(
        description="Isolamento entre apps ao longo da série de densidade de GPU."
    ).parse_args()

    print("=" * 74)
    print("Isolamento entre aplicações — série de densidade de GPU")
    print("=" * 74)

    df = carregar()
    tabela = df.pivot_table(index="app", columns="k", values="latency_ms")
    print(tabela.round(2).to_string())
    print()

    saida = config.SERIES["densidade"]["pasta"] / "resultados"
    (saida / "figuras").mkdir(parents=True, exist_ok=True)
    plotar(df, saida / "figuras" / "isolamento_apps.png")
    tabela.to_csv(saida / "isolamento_apps.csv")
    print(f"✓ Tabela:  {saida / 'isolamento_apps.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
