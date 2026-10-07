#!/usr/bin/env python3
"""Gráfico de decomposição do FRTT (latência) por aplicação: compute + rede.

Lê metrics_by_app.csv (gerado por agregar_metricas.py) e gera uma barra empilhada
por aplicação, decompondo a latência média em:
  - processamento: tempo no servidor (inferência na GPU nas aplicações de GPU;
                   tempo de CPU nas aplicações só de CPU);
  - rede:          subida + descida + PCIe.

Cada aplicação é uma barra, rotulada como GPU ou CPU. Com um único cliente YOLO, a
barra reproduz a decomposição analítica: 4,00 ms de GPU + 4,44 ms de rede = 8,44 ms.

Uso:
    python3 analise/plotar_breakdown.py --ponto N01
"""

import argparse
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import config

# Cores categóricas seguras para daltonismo (ΔE 73,6 sob deuteranopia). O baixo
# contraste do verde-água com o fundo é compensado por rótulos diretos.
COR_COMPUTE = "#2a78d6"   # azul
COR_REDE = "#1baf7a"      # aqua
INK = "#0b0b0b"           # text-primary
INK_MUTED = "#52514e"     # text-secondary


def carregar(metrics_by_app_csv, ponto: str) -> pd.DataFrame:
    if not metrics_by_app_csv.exists():
        print(f"ERRO: {metrics_by_app_csv} não encontrado!")
        print(f"Execute antes: python3 analise/agregar_metricas.py --ponto {ponto}")
        sys.exit(1)
    df = pd.read_csv(metrics_by_app_csv)
    # Ordena por FRTT desc para leitura (maior latência à esquerda).
    return df.sort_values("latency_ms", ascending=False).reset_index(drop=True)


def rotulo_app(row) -> str:
    """Nome da app + tag GPU/CPU (para o caso misto)."""
    tag = "GPU" if bool(row["uses_gpu"]) else "CPU"
    nome = str(row["app"]).replace("_", "\n")
    return f"{nome}\n({tag})"


def anotar_fora(ax, x_borda, y_centro, texto):
    """Rótulo fora da barra, ligado ao segmento por uma linha-guia.

    Usado quando o segmento é estreito demais para conter o texto. A escala permanece
    linear, sem ocultar o valor.
    """
    ax.annotate(
        texto,
        xy=(x_borda, y_centro),
        xytext=(26, 22), textcoords="offset points",
        ha="left", va="center", fontsize=10, fontweight="bold", color=INK,
        arrowprops=dict(arrowstyle="-", color=INK_MUTED, linewidth=1.0,
                        shrinkA=0, shrinkB=1,
                        connectionstyle="angle,angleA=0,angleB=90,rad=3"),
    )


def plotar(df: pd.DataFrame, rotulo_ponto: str, output_file):
    n = len(df)
    fig, ax = plt.subplots(figsize=(max(6, 2.2 * n + 2), 6))

    x = range(n)
    compute = df["processing_ms"].values
    rede = df["network_ms"].values
    width = 0.55 if n > 1 else 0.4

    # Barra empilhada; a borda branca separa visualmente os segmentos.
    b1 = ax.bar(x, compute, width, label="Compute (GPU/CPU)", color=COR_COMPUTE,
                edgecolor="white", linewidth=2)
    b2 = ax.bar(x, rede, width, bottom=compute, label="Rede (up+down+PCIe)",
                color=COR_REDE, edgecolor="white", linewidth=2)

    # Rótulo dentro do segmento quando ele ocupa ao menos 6% do total; caso contrário,
    # fora da barra, com linha-guia.
    for i in range(n):
        total = compute[i] + rede[i]
        min_h = 0.06 * total if total > 0 else 0
        x_borda = i + width / 2

        if compute[i] >= min_h:
            ax.text(i, compute[i] / 2, f"{compute[i]:.2f} ms", ha="center",
                    va="center", color="white", fontsize=10, fontweight="bold")
        else:
            anotar_fora(ax, x_borda, compute[i] / 2, f"Compute {compute[i]:.2f} ms")

        if rede[i] >= min_h:
            ax.text(i, compute[i] + rede[i] / 2, f"{rede[i]:.2f} ms", ha="center",
                    va="center", color=INK, fontsize=10, fontweight="bold")
        else:
            anotar_fora(ax, x_borda, compute[i] + rede[i] / 2,
                        f"Rede {rede[i]:.2f} ms")

        # Total (FRTT) acima da barra.
        ax.text(i, total, f"FRTT {total:.2f} ms", ha="center", va="bottom",
                color=INK, fontsize=11, fontweight="bold")

    ax.set_xticks(list(x))
    ax.set_xticklabels([rotulo_app(df.iloc[i]) for i in range(n)], fontsize=10)
    ax.set_ylabel("Latência média (ms)", fontweight="bold", color=INK)
    ax.set_title(f"Decomposição do FRTT por aplicação — {rotulo_ponto}",
                 fontweight="bold", pad=16, color=INK)

    # Apenas grade horizontal, sem bordas superior e direita.
    ax.grid(True, axis="y", alpha=0.25, linestyle="--")
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.margins(y=0.15)
    # Legenda à esquerda: o lado direito é reservado às anotações externas.
    ax.legend(loc="upper left", frameon=False, fontsize=10)

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"✓ Gerado: {output_file}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gráfico de decomposição do FRTT (compute + rede) por aplicação.")
    parser.add_argument("--ponto", required=True, choices=list(config.PONTOS),
                        help="Código do ponto (K01…K14 ou N01…N14)")
    args = parser.parse_args()

    cfg = config.ponto(args.ponto)
    experimento_dir = cfg["experimento"]
    plots_dir = experimento_dir / "figuras"
    plots_dir.mkdir(parents=True, exist_ok=True)
    metrics_by_app_csv = experimento_dir / "metrics_by_app.csv"

    print("=" * 70)
    print(f"Gerando breakdown do FRTT — {cfg['rotulo']}")
    print("=" * 70)

    df = carregar(metrics_by_app_csv, args.ponto)
    print(f"  {len(df)} aplicação(ões): {', '.join(df['app'])}\n")

    plotar(df, cfg["rotulo"], plots_dir / "breakdown_frtt.png")
    print(f"\nGráfico salvo em: {plots_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
