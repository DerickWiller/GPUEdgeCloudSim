#!/usr/bin/env python3
"""Retorno decrescente: quantas GPUs a borda precisa, e a partir de quantas sobra.

  (a) vazão servida em função de K, comparada à taxa ofertada pelos clientes;
  (b) ganho marginal: redução da latência média por GPU acrescentada, em ms/GPU,
      entre valores consecutivos de K.

Ressalva: a carga é fixa (30 dispositivos, 9 com YOLO). GPUs sem efeito sobre a
latência média podem ainda oferecer margem para picos de carga e falhas de nó, que
estes pontos não exercitam.

Lê as saídas brutas da amostra de cada ponto e grava, em
experimentos/densidade-gpu/resultados/, a tabela retorno_decrescente.csv e a figura
figuras/retorno_decrescente.png.

Uso:
    python3 analise/plotar_retorno_decrescente.py
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import config
from plotar_falhas_por_app import ler_usuarios_por_app

COR_VAZAO = "#2a78d6"
COR_OFERTA = "#52514e"
COR_GANHO = "#eb6834"
INK = "#0b0b0b"
INK_MUTED = "#52514e"

APP_GPU = "YOLO_DETECTION"
INTERVALO_FRAME_S = 0.033
TEMPO_EFETIVO_S = 3300.0


def num_gpus(num: str) -> int:
    """K, contado a partir das GPUs declaradas no edge_devices.xml."""
    xml = config.ponto(num)["pasta"] / "edge_devices.xml"
    return len(ET.parse(xml).getroot().findall(".//gpu"))


def metricas_do_ponto(num: str) -> dict:
    runs = config.runs_da_amostra(num)
    if not runs:
        return {}

    servidas, latencias = [], []
    for run in runs:
        logs = sorted(run.glob(f"*_{APP_GPU}_GENERIC.log"))
        if not logs:
            continue
        linhas = [l for l in open(logs[0]) if not l.startswith("#")]
        if not linhas:
            continue
        p = linhas[0].split(";")
        servidas.append(float(p[0]) / TEMPO_EFETIVO_S)
        latencias.append(float(p[4]) * 1000.0)

    if not servidas:
        return {}

    clientes = ler_usuarios_por_app(runs[0]).get(APP_GPU, 0)
    return {
        "ponto": num,
        "k": config.SERIE_DENSIDADE_GPU[num],
        "gpus": num_gpus(num),
        "clientes": clientes,
        "servido": sum(servidas) / len(servidas),
        "latencia": sum(latencias) / len(latencias),
        "oferta": clientes / INTERVALO_FRAME_S,
    }


def carregar() -> pd.DataFrame:
    """Métricas dos pontos com saídas brutas; encerra se faltar algum, para não
    substituir a tabela e a figura completas por versões parciais."""
    linhas = []
    for num in sorted(config.SERIE_DENSIDADE_GPU, key=config.SERIE_DENSIDADE_GPU.get):
        m = metricas_do_ponto(num)
        if m:
            linhas.append(m)
        else:
            print(f"  AVISO: {num} sem execuções legíveis na amostra; ponto ignorado.")
    if not linhas:
        print("ERRO: nenhum ponto da densidade de GPU tem saídas brutas nesta máquina.")
        sys.exit(1)
    if len(linhas) < len(config.SERIE_DENSIDADE_GPU):
        print("ERRO: faltam saídas brutas de algum ponto; nada foi gravado.")
        sys.exit(1)
    df = pd.DataFrame(linhas).sort_values("k").reset_index(drop=True)

    # Ganho marginal: latência devolvida por GPU acrescentada desde o K anterior.
    ganhos = [float("nan")]
    for i in range(1, len(df)):
        d_lat = df.loc[i - 1, "latencia"] - df.loc[i, "latencia"]
        d_gpu = df.loc[i, "gpus"] - df.loc[i - 1, "gpus"]
        ganhos.append(d_lat / d_gpu if d_gpu else float("nan"))
    df["ganho_ms_por_gpu"] = ganhos
    return df


def limpar_eixo(ax):
    ax.grid(True, axis="y", alpha=0.25, linestyle="--")
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def painel_vazao(ax, df: pd.DataFrame):
    ks = df["k"].tolist()
    x = range(len(df))

    oferta = df["oferta"].iloc[0]
    ax.axhline(oferta, color=COR_OFERTA, linestyle=":", linewidth=2)
    # Anotação à esquerda e acima da linha, longe da curva.
    ax.text(-0.35, oferta, f"oferecido pelos clientes = {oferta:.0f} fps",
            va="bottom", ha="left", fontsize=9, color=COR_OFERTA)

    ax.plot(x, df["servido"], "-o", color=COR_VAZAO, linewidth=2.5, markersize=10,
            markeredgecolor="white", markeredgewidth=2, zorder=3)
    for i, r in df.iterrows():
        deficit = r["oferta"] - r["servido"]
        texto = f"{r['servido']:.1f} fps"
        if deficit > 0.5:
            texto += f"\n(−{deficit:.0f} não servidos)"
        ax.annotate(texto, xy=(i, r["servido"]), xytext=(0, -30 if i == 0 else 14),
                    textcoords="offset points", ha="center", fontsize=9.5,
                    fontweight="bold", color=INK)

    ax.set_xticks(list(x))
    ax.set_xticklabels([str(k) for k in ks], fontsize=11)
    ax.set_xlabel("Servidores com GPU (de 14)", fontweight="bold", color=INK)
    ax.set_ylabel("Vazão servida do YOLO (fps)", fontweight="bold", color=INK)
    ax.set_title("(a) A partir de K=2 já se serve tudo que chega",
                 fontweight="bold", color=INK, pad=10)
    ax.set_ylim(0, oferta * 1.22)
    limpar_eixo(ax)


def painel_ganho(ax, df: pd.DataFrame):
    d = df.dropna(subset=["ganho_ms_por_gpu"])
    x = range(len(d))
    ax.bar(x, d["ganho_ms_por_gpu"], 0.55, color=COR_GANHO,
           edgecolor="white", linewidth=2)

    for i, (_, r) in enumerate(d.iterrows()):
        v = r["ganho_ms_por_gpu"]
        # Ganho negativo está dentro da variabilidade entre execuções e é rotulado ≈0.
        texto = f"{v:.2f}" if abs(v) >= 0.01 else f"≈0 ({v:+.3f})"
        ax.text(i, max(v, 0), texto, ha="center", va="bottom", fontsize=10,
                fontweight="bold", color=INK)

    rotulos = []
    anterior = df.iloc[0]
    for _, r in d.iterrows():
        rotulos.append(f"K={int(anterior['k'])}→{int(r['k'])}\n"
                       f"(+{int(r['gpus'] - anterior['gpus'])} GPU"
                       f"{'s' if r['gpus'] - anterior['gpus'] > 1 else ''})")
        anterior = r

    ax.set_xticks(list(x))
    ax.set_xticklabels(rotulos, fontsize=9.5)
    ax.set_xlabel("Passo na densidade de GPU", fontweight="bold", color=INK)
    ax.set_ylabel("Latência devolvida por GPU acrescentada (ms/GPU)",
                  fontweight="bold", color=INK)
    ax.set_title("(b) O ganho marginal morre no terceiro passo",
                 fontweight="bold", color=INK, pad=10)
    # Escala symlog: comprime ordens de grandeza (o primeiro passo vale ~434 ms/GPU) e
    # admite zero e valores negativos.
    ax.set_yscale("symlog", linthresh=0.01)
    limpar_eixo(ax)
    ax.margins(y=0.30)


def plotar(df: pd.DataFrame, output_file: Path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6.4))
    painel_vazao(ax1, df)
    painel_ganho(ax2, df)

    fig.suptitle("Retorno decrescente da GPU na borda — o que cada placa a mais entrega",
                 fontweight="bold", fontsize=13, color=INK, y=0.99)
    fig.text(0.5, 0.005,
             "Mesmo workload nos cinco cenários; só muda quantos dos 14 servidores têm GPU. "
             "30 runs por ponto.\n"
             "GPUs ociosas em K alto ainda são margem para pico e falha de nó — que "
             "estes cenários não exercitam.",
             ha="center", va="bottom", fontsize=9, color=INK_MUTED)

    plt.tight_layout(rect=[0, 0.06, 1, 0.94])
    plt.savefig(output_file, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"\n✓ Gerado: {output_file}")


def main() -> int:
    argparse.ArgumentParser(
        description="Retorno decrescente da densidade de GPU.").parse_args()

    print("=" * 74)
    print("Retorno decrescente — série de densidade de GPU")
    print("=" * 74)

    df = carregar()
    print(df[["ponto", "k", "gpus", "clientes", "oferta", "servido",
              "latencia", "ganho_ms_por_gpu"]].round(3).to_string(index=False))
    print()

    saida = config.SERIES["densidade"]["pasta"] / "resultados"
    (saida / "figuras").mkdir(parents=True, exist_ok=True)
    plotar(df, saida / "figuras" / "retorno_decrescente.png")
    df.to_csv(saida / "retorno_decrescente.csv", index=False)
    print(f"✓ Tabela:  {saida / 'retorno_decrescente.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
