#!/usr/bin/env python3
"""Síntese da série de densidade: o que cada GPU a mais muda, na média E na cauda.

  (a) média, p95 e p99 em função de K, com o intervalo entre quadros (33 ms) marcado;
  (b) tabela com a variação da média e do p99 a cada valor de K.

Fontes, geradas antes por outros scripts, em experimentos/densidade-gpu/:
  resultados/retorno_decrescente.csv     média e vazão
  resultados/percentis_latencia.csv      p50, p95 e p99
  <ponto>/resultados/metrics_by_app.csv  taxa de falha

Os percentis vêm do registro por tarefa de 10 sementes; média e falha, de 30
execuções. Para a mesma semente o SIMRESULT é idêntico com e sem registro por tarefa,
mas o tamanho da amostra difere entre as colunas.

Uso:
    python3 analise/plotar_sintese_densidade.py
"""

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import config

COR_MEDIA = "#2a78d6"
COR_P95 = "#eb6834"
COR_P99 = "#1baf7a"
COR_ALERTA = "#e34948"
INK = "#0b0b0b"
INK_MUTED = "#52514e"

ORCAMENTO_MS = 33.0   # intervalo entre quadros a 30 fps
APP_GPU = "YOLO_DETECTION"


def carregar() -> pd.DataFrame:
    base = config.SERIES["densidade"]["pasta"] / "resultados"
    csv_retorno = base / "retorno_decrescente.csv"
    csv_percentis = base / "percentis_latencia.csv"

    for csv, script in ((csv_retorno, "plotar_retorno_decrescente.py"),
                        (csv_percentis, "plotar_distribuicao_latencia.py")):
        if not csv.exists():
            print(f"ERRO: {csv} não encontrado.")
            print(f"Execute antes: python3 analise/{script}")
            sys.exit(1)

    d = pd.read_csv(csv_retorno)
    p = pd.read_csv(csv_percentis).set_index("ponto")

    linhas = []
    for _, r in d.iterrows():
        num = r["ponto"]
        by_app = pd.read_csv(config.ponto(num)["experimento"] / "metrics_by_app.csv")
        yolo = by_app[by_app["app"] == APP_GPU]
        linhas.append({
            "ponto": num,
            "k": int(r["k"]),
            "gpus": int(r["gpus"]),
            "media": r["latencia"],
            "p95": p.loc[num, "p95_ms"] if num in p.index else float("nan"),
            "p99": p.loc[num, "p99_ms"] if num in p.index else float("nan"),
            "falha": yolo["failure_rate"].iloc[0] if not yolo.empty else float("nan"),
            "servido": r["servido"],
        })

    df = pd.DataFrame(linhas).sort_values("k").reset_index(drop=True)

    # Diferença entre valores consecutivos de K.
    df["d_media"] = df["media"].diff()
    df["d_p99"] = df["p99"].diff()
    df["d_gpus"] = df["gpus"].diff()
    return df


def painel_curvas(ax, df: pd.DataFrame):
    x = range(len(df))
    series = [("media", "Média", COR_MEDIA), ("p95", "p95", COR_P95),
              ("p99", "p99", COR_P99)]

    for coluna, rotulo, cor in series:
        ax.plot(x, df[coluna], "-o", color=cor, linewidth=2.5, markersize=9,
                markeredgecolor="white", markeredgewidth=2, label=rotulo, zorder=3)

    ax.axhline(ORCAMENTO_MS, color=INK_MUTED, linestyle="--", linewidth=1.8)
    ax.text(len(df) - 0.5, ORCAMENTO_MS,
            f"orçamento de 1 quadro ({ORCAMENTO_MS:.0f} ms) ",
            va="bottom", ha="right", fontsize=9, color=INK_MUTED, fontweight="bold")

    # Rótulos apenas no p99, para evitar sobreposição.
    for i, r in df.iterrows():
        estoura = r["p99"] > ORCAMENTO_MS
        ax.annotate(f"{r['p99']:.1f}", xy=(i, r["p99"]), xytext=(0, 13),
                    textcoords="offset points", ha="center", fontsize=9.5,
                    fontweight="bold", color=COR_ALERTA if estoura else INK)

    ax.set_xticks(list(x))
    # Marcas com o valor de K; o rótulo do eixo informa o total de 14.
    ax.set_xticklabels([str(int(r["k"])) for _, r in df.iterrows()], fontsize=11)
    ax.set_yscale("log")
    ax.set_xlabel("Servidores com GPU (de 14)", fontweight="bold", color=INK)
    ax.set_ylabel("Latência do YOLO (ms, escala log)", fontweight="bold", color=INK)
    # Título descritivo, sem conclusão; a interpretação fica no texto.
    ax.set_title("(a) Latência do YOLO em função da densidade de GPU",
                 fontweight="bold", color=INK, pad=10)

    ax.grid(True, alpha=0.25, linestyle="--")
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.legend(loc="upper right", frameon=False, fontsize=10)
    ax.margins(y=0.22)


def veredito(r) -> str:
    """Resumo, em poucas palavras, do efeito do passo de K."""
    if pd.isna(r["d_media"]):
        return "ponto de partida"
    ganho_p99 = -r["d_p99"] if pd.notna(r["d_p99"]) else 0.0
    if abs(r["d_media"]) < 0.05 and abs(ganho_p99) < 0.05:
        return "nada"
    if abs(ganho_p99) < 0.05:
        return "só a média"
    if -r["d_media"] > 100:
        return "tira da saturação"
    return "encurta a cauda"


def painel_tabela(ax, df: pd.DataFrame):
    ax.axis("off")

    cabecalho = ["Passo", "GPUs", "Média (ms)", "p99 (ms)", "Δ média", "Δ p99",
                 "O que o passo entrega"]
    linhas, cores = [], []

    anterior = None
    for _, r in df.iterrows():
        if anterior is None:
            passo = f"K={int(r['k'])}"
            d_gpus = f"{int(r['gpus'])}"
            d_media = d_p99 = "—"
        else:
            passo = f"K={int(anterior['k'])}→{int(r['k'])}"
            d_gpus = f"+{int(r['d_gpus'])}"
            d_media = f"{r['d_media']:+.2f}"
            d_p99 = f"{r['d_p99']:+.2f}" if pd.notna(r["d_p99"]) else "—"

        linhas.append([passo, d_gpus, f"{r['media']:.2f}", f"{r['p99']:.2f}",
                       d_media, d_p99, veredito(r)])
        # Destaque em vermelho claro onde o p99 excede 33 ms.
        cores.append("#fdeaea" if r["p99"] > ORCAMENTO_MS else "#ffffff")
        anterior = r

    # Posição por bbox, para controlar a altura da tabela e a largura de cada coluna.
    larguras = [0.13, 0.08, 0.13, 0.11, 0.12, 0.11, 0.32]
    tabela = ax.table(cellText=linhas, colLabels=cabecalho, cellLoc="center",
                      colWidths=larguras, bbox=[0.0, 0.0, 1.0, 0.94])
    tabela.auto_set_font_size(False)
    tabela.set_fontsize(9.5)

    for (i, j), celula in tabela.get_celld().items():
        celula.set_edgecolor("#d8d7d2")
        if i == 0:
            celula.set_facecolor("#f2f1ee")
            celula.set_text_props(fontweight="bold", color=INK)
        else:
            celula.set_facecolor(cores[i - 1])
            if j in (4, 5) and linhas[i - 1][j].startswith("-"):
                celula.set_text_props(fontweight="bold")

    ax.set_title("(b) O que cada passo na densidade de GPU devolve\n"
                 "fundo vermelho = p99 acima do orçamento de 33 ms",
                 fontweight="bold", color=INK, pad=18)


def plotar(df: pd.DataFrame, output_file: Path):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9.5),
                                   gridspec_kw={"height_ratios": [1.5, 0.85]})
    painel_curvas(ax1, df)
    painel_tabela(ax2, df)

    fig.suptitle("Densidade de GPU na borda: latência, cauda e ganho marginal por passo",
                 fontweight="bold", fontsize=14, color=INK, y=0.985)
    fig.text(0.5, 0.008,
             "Mesmo workload nos cinco cenários (30 dispositivos, 4 aplicações); "
             "só muda quantos dos 14 servidores têm GPU.\n"
             "Média e falha: 30 runs por ponto. Percentis: deep log de 10 seeds. "
             "As duas famílias são consistentes — a mesma seed dá SIMRESULT idêntico "
             "com e sem deep log.",
             ha="center", va="bottom", fontsize=9, color=INK_MUTED)

    plt.tight_layout(rect=[0, 0.045, 1, 0.965])
    plt.savefig(output_file, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"\n✓ Gerado: {output_file}")


def main() -> int:
    argparse.ArgumentParser(
        description="Síntese da série de densidade: média, cauda e diferença por K."
    ).parse_args()

    print("=" * 78)
    print("Síntese da densidade de GPU — ponto × K × diferença")
    print("=" * 78)

    df = carregar()
    print(df[["ponto", "k", "gpus", "media", "p95", "p99", "falha",
              "d_media", "d_p99"]].round(2).to_string(index=False))
    print()

    resultados = config.SERIES["densidade"]["pasta"] / "resultados"
    (resultados / "figuras").mkdir(parents=True, exist_ok=True)
    plotar(df, resultados / "figuras" / "sintese_densidade.png")
    df.to_csv(resultados / "sintese_densidade.csv", index=False)
    print(f"✓ Tabela:  {resultados / 'sintese_densidade.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
