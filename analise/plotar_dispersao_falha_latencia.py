#!/usr/bin/env python3
"""Dispersão entre execuções: taxa de falha × latência, um painel por ponto.

Cada ponto é uma execução. A forma da nuvem classifica o regime de saturação:

  rígido          FRTT praticamente constante e perda nula;
  fila sem perda  FRTT variável entre execuções e perda nula;
  perda-válvula   correlação negativa: execuções que perdem mais têm menor latência;
  afogado         correlação positiva próxima de 1 entre falha e latência.

O sinal da correlação de Pearson distingue os dois últimos regimes e só é observável
por execução, não na média. Cada painel tem escala própria, pois os valores variam em
ordens de grandeza; os intervalos são anotados em cada painel.

A figura é gravada em experimentos/comparativos/figuras/dispersao_falha_latencia.png.

Uso:
    python3 analise/plotar_dispersao_falha_latencia.py
    python3 analise/plotar_dispersao_falha_latencia.py --pontos K01,N14
"""

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import config

COR_PONTO = "#2a78d6"
COR_TENDENCIA = "#e34948"  # reta de tendência
INK = "#0b0b0b"
INK_MUTED = "#52514e"

# Os cinco pontos da densidade de GPU e as duas pontas da escala de clientes.
PADRAO = ["K01", "K02", "K03", "K07", "K14", "N01", "N14"]

# Correlação mínima, em módulo, para desenhar a reta de tendência (n = 30).
R_MINIMO = 0.30
# Amplitude relativa do FRTT abaixo da qual o regime é classificado como rígido.
RIGIDO_MAX = 0.05


def classificar_regime(d: pd.DataFrame, r: float) -> str:
    """Nomeia o regime a partir da forma da nuvem de 30 runs."""
    falha_max = d["failure_rate"].max()
    frtt = d["latency_mean_ms"]
    amplitude = (frtt.max() - frtt.min()) / frtt.mean() if frtt.mean() else 0.0

    if falha_max == 0:
        return "rígido" if amplitude < RIGIDO_MAX else "fila sem perda"
    if r <= -R_MINIMO:
        return "perda como válvula"
    if r >= R_MINIMO:
        return "afogado"
    return "saturado"


def painel(ax, num: str, d: pd.DataFrame):
    cfg = config.ponto(num)
    x = d["latency_mean_ms"]
    y = d["failure_rate"]
    r = x.corr(y) if y.std() > 0 else float("nan")
    regime = classificar_regime(d, r if pd.notna(r) else 0.0)

    ax.scatter(x, y, s=55, color=COR_PONTO, edgecolor="white", linewidth=1.5,
               zorder=3, alpha=0.85)

    # Reta de tendência só quando há correlação que a sustente.
    if pd.notna(r) and abs(r) >= R_MINIMO:
        m, b = _polyfit(x, y)
        xs = [x.min(), x.max()]
        ax.plot(xs, [m * v + b for v in xs], "--", color=COR_TENDENCIA,
                linewidth=2, zorder=2)

    rotulo_r = "—" if pd.isna(r) else f"{r:+.2f}"
    ax.set_title(f"{cfg['rotulo']}\n"
                 f"regime: {regime}  ·  r = {rotulo_r}",
                 fontsize=10, fontweight="bold", color=INK, pad=8)

    # Intervalos anotados, pois cada painel tem escala própria.
    ax.text(0.02, 0.97,
            f"FRTT {x.min():.1f}–{x.max():.1f} ms\n"
            f"falha {y.min():.2f}–{y.max():.2f} %",
            transform=ax.transAxes, va="top", ha="left",
            fontsize=8.5, color=INK_MUTED)

    ax.grid(True, alpha=0.25, linestyle="--")
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.margins(0.18)
    ax.tick_params(labelsize=9)

    # Com perda nula, a faixa do eixo é fixada explicitamente.
    if y.max() == 0:
        ax.set_ylim(-0.5, 1.0)
        ax.set_yticks([0])


def _polyfit(x, y):
    """Ajuste linear por mínimos quadrados."""
    n = len(x)
    mx, my = x.mean(), y.mean()
    sxx = ((x - mx) ** 2).sum()
    sxy = ((x - mx) * (y - my)).sum()
    m = sxy / sxx if sxx else 0.0
    return m, my - m * mx


def carregar(num: str) -> pd.DataFrame:
    csv = config.ponto(num)["experimento"] / "metrics_runs.csv"
    if not csv.exists():
        print(f"  AVISO: {num} sem metrics_runs.csv; ponto ignorado.")
        return pd.DataFrame()
    return pd.read_csv(csv)


def plotar(dados: dict, output_file: Path):
    n = len(dados)
    ncols = min(4, n)
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.1 * ncols, 4.0 * nrows),
                             squeeze=False)

    for i, (num, d) in enumerate(dados.items()):
        painel(axes[i // ncols][i % ncols], num, d)
    for j in range(n, nrows * ncols):          # apaga sobras do grid
        axes[j // ncols][j % ncols].axis("off")

    # Posição vertical explícita, para não sobrepor o rodapé.
    fig.supxlabel("Latência média da run — FRTT (ms)", fontweight="bold",
                  color=INK, fontsize=11, y=0.085)
    fig.supylabel("Taxa de falha da run (%)", fontweight="bold",
                  color=INK, fontsize=11)
    fig.suptitle("Dispersão entre runs: cada ponto é uma das 30 execuções",
                 fontweight="bold", fontsize=14, color=INK, y=0.995)
    fig.text(0.5, 0.012,
             "Escala própria por painel (os regimes diferem em ordem de grandeza) — "
             "compare o FORMATO da nuvem, não a posição.\n"
             "r = Pearson(FRTT, falha); a reta só aparece com |r| ≥ 0,30. "
             "Num painel de perda zero, os 30 pontos se espalham só na horizontal.",
             ha="center", va="bottom", fontsize=9, color=INK_MUTED)

    plt.tight_layout(rect=[0.02, 0.13, 1, 0.94])
    plt.savefig(output_file, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"\n✓ Gerado: {output_file}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dispersão falha × latência entre execuções, um painel por ponto.")
    parser.add_argument("--pontos", default=",".join(PADRAO),
                        help=f"lista separada por vírgula (padrão: {','.join(PADRAO)})")
    args = parser.parse_args()

    nums = [v.strip().upper() for v in args.pontos.split(",") if v.strip()]
    for num in nums:
        if num not in config.PONTOS:
            print(f"ERRO: ponto {num} desconhecido. Use um de: {', '.join(config.PONTOS)}.")
            return 1

    print("=" * 74)
    print("Dispersão falha × latência entre runs")
    print("=" * 74)

    dados = {}
    for num in nums:
        d = carregar(num)
        if not d.empty:
            dados[num] = d
            r = d["latency_mean_ms"].corr(d["failure_rate"]) if d["failure_rate"].std() > 0 else float("nan")
            regime = classificar_regime(d, r if pd.notna(r) else 0.0)
            rotulo_r = "—" if pd.isna(r) else f"{r:+.3f}"
            print(f"  {num}: n={len(d):<3} r={rotulo_r:<8} regime: {regime}")

    if not dados:
        print("ERRO: nenhum ponto com métricas agregadas.")
        return 1

    saida = config.COMPARATIVOS_DIR / "figuras"
    saida.mkdir(parents=True, exist_ok=True)
    plotar(dados, saida / "dispersao_falha_latencia.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
