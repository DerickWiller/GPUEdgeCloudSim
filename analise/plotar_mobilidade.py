#!/usr/bin/env python3
"""Mobilidade e concentração por ponto de acesso — o SIMRESULT_*_LOCATION.log.

O registro traz, a cada 6 s, o número de dispositivos sob cada ponto de acesso. Com
contenção de WLAN, a banda de cada ponto de acesso é dividida entre suas transmissões
simultâneas; o número de dispositivos sob um ponto de acesso é, portanto, o limite
superior dessa divisão (nem todos transmitem ao mesmo tempo).

  (a) mapa de calor tempo × datacenter, de uma execução;
  (b) dispositivos no ponto de acesso mais carregado a cada instante.

Usa-se uma execução, e não a média das execuções, porque a média entre execuções
atenua os picos de concentração; os picos são calculados por execução e só depois
agregados. A mobilidade afeta apenas a rede: a escolha do servidor não considera
proximidade.

Uso:
    python3 analise/plotar_mobilidade.py --ponto K01
    python3 analise/plotar_mobilidade.py --ponto K01 --run 3
"""

import argparse
import glob
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import config

COR_SERIE = "#2a78d6"
INK = "#0b0b0b"
INK_MUTED = "#52514e"
WARM_UP_S = 300.0


def datacenters_com_gpu(num: str) -> list:
    """Índices dos datacenters que declaram ao menos uma <gpu>."""
    xml = config.ponto(num)["pasta"] / "edge_devices.xml"
    dcs = ET.parse(xml).getroot().findall("datacenter")
    return [i for i, dc in enumerate(dcs) if dc.findall(".//gpu")]


def carregar(num: str, indice_run: int = 0) -> tuple:
    """Ocupação por datacenter de uma execução e o pico por ponto de acesso de todas.

    Devolve (df_da_execução, série_de_picos_de_todas_as_execuções).
    """
    # Execuções da amostra do ponto, em ordem de nome da pasta.
    logs = sorted(glob.glob(str(d / "*LOCATION.log"))[0]
                  for d in config.runs_da_amostra(num)
                  if glob.glob(str(d / "*LOCATION.log")))
    if not logs:
        return pd.DataFrame(), pd.Series(dtype=float)

    quadros = []
    for log in logs:
        tempos, linhas = [], []
        for linha in open(log):
            if linha.startswith("#"):
                continue
            p = linha.strip().split(";")
            if len(p) < 2:
                continue
            tempos.append(float(p[0]))
            linhas.append([float(v) for v in p[1:]])
        if tempos:
            quadros.append(pd.DataFrame(linhas, index=tempos))

    if not quadros:
        return pd.DataFrame(), pd.Series(dtype=float)

    escolhida = quadros[min(indice_run, len(quadros) - 1)]
    # Picos de todas as execuções: distribuição da ocupação do ponto de acesso mais carregado.
    picos = pd.concat([q.max(axis=1) for q in quadros], ignore_index=True)
    return escolhida, picos


def painel_mapa(ax, d: pd.DataFrame, com_gpu: list):
    # Escala sequencial de uma única matiz.
    im = ax.imshow(d.T.values, aspect="auto", origin="lower", cmap="Blues",
                   extent=[d.index.min() / 60, d.index.max() / 60,
                           -0.5, d.shape[1] - 0.5])

    ax.set_yticks(range(d.shape[1]))
    ax.set_yticklabels([f"DC {i}" + ("  ⬤ GPU" if i in com_gpu else "")
                        for i in range(d.shape[1])], fontsize=8.5)
    for i in com_gpu:
        ax.get_yticklabels()[i].set_fontweight("bold")

    ax.axvline(WARM_UP_S / 60.0, color="white", linestyle=":", linewidth=1.5)
    ax.set_xlabel("Tempo de simulação (min)", fontweight="bold", color=INK)
    ax.set_title("(a) Dispositivos por ponto de acesso ao longo do tempo",
                 fontweight="bold", color=INK, pad=10)
    barra = plt.colorbar(im, ax=ax, pad=0.02)
    barra.set_label("Dispositivos sob o AP (contagem, uma run)", fontsize=9)


def painel_pico(ax, d: pd.DataFrame, picos_todas: pd.Series):
    """Dispositivos no ponto de acesso mais carregado a cada instante."""
    serie = d.max(axis=1)
    t = d.index / 60.0

    ax.plot(t, serie, "-", color=COR_SERIE, linewidth=1.4, zorder=3)
    ax.axhline(serie.mean(), color=INK_MUTED, linestyle="--", linewidth=1.5)
    ax.text(t.max(), serie.mean(), f" média desta run {serie.mean():.2f} ",
            va="bottom", ha="right", fontsize=9, color=INK_MUTED,
            fontweight="bold")

    ax.axvline(WARM_UP_S / 60.0, color=INK_MUTED, linestyle=":", linewidth=1.5)
    ax.set_xlabel("Tempo de simulação (min)", fontweight="bold", color=INK)
    ax.set_ylabel("Dispositivos no AP mais cheio", fontweight="bold", color=INK)

    # Eixo secundário com a fração de banda: N transmissões simultâneas recebem 1/N cada.
    pior = int(picos_todas.max())
    ax.set_title(f"(b) Teto de disputa da WLAN — o AP mais carregado tem de "
                 f"{int(serie.min())} a {int(serie.max())} dispositivos nesta run "
                 f"(até {pior} nas 30)\n"
                 f"com N transmitindo no mesmo AP, cada um fica com 1/N da banda",
                 fontweight="bold", color=INK, pad=10)
    ax.set_ylim(0, max(serie.max(), pior) * 1.30)
    ax.grid(True, alpha=0.25, linestyle="--")
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def plotar(num: str, d: pd.DataFrame, picos_todas: pd.Series, com_gpu: list,
           output_file: Path):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9.5),
                                   gridspec_kw={"height_ratios": [1.5, 1]})
    painel_mapa(ax1, d, com_gpu)
    painel_pico(ax2, d, picos_todas)

    cfg = config.ponto(num)
    fig.suptitle(f"Mobilidade e disputa por ponto de acesso — {cfg['rotulo']}",
                 fontweight="bold", fontsize=13, color=INK, y=0.995)
    fig.text(0.5, 0.008,
             "Uma run (não a média das 30): a média entre runs achata a concentração, "
             "que é justamente o que a contenção de WLAN consome.\n"
             "A banda do enlace é repartida POR AP entre as transmissões simultâneas "
             "dali — por isso a lotação do AP importa. A escolha do servidor, essa, "
             "continua sem usar proximidade.",
             ha="center", va="bottom", fontsize=9, color=INK_MUTED)

    plt.tight_layout(rect=[0, 0.055, 1, 0.97])
    plt.savefig(output_file, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"\n✓ Gerado: {output_file}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mobilidade dos dispositivos no tempo.")
    parser.add_argument("--ponto", default="K01", choices=list(config.PONTOS),
                        help="Código do ponto (padrão: K01)")
    parser.add_argument("--run", type=int, default=1,
                        help="Qual run usar no mapa e na série (1 = a primeira)")
    args = parser.parse_args()

    cfg = config.ponto(args.ponto)
    print("=" * 74)
    print(f"Mobilidade — {cfg['rotulo']}")
    print("=" * 74)

    d, picos = carregar(args.ponto, max(0, args.run - 1))
    if d.empty:
        print(f"ERRO: {args.ponto} sem LOCATION.log legível.")
        return 1

    com_gpu = datacenters_com_gpu(args.ponto)
    total = d.sum(axis=1)
    pico = d.max(axis=1)
    print(f"  {d.shape[0]} instantes × {d.shape[1]} datacenters (run {args.run})")
    print(f"  datacenters com GPU: {com_gpu}")
    print(f"  conservação: total por instante varia de {total.min():.2f} a "
          f"{total.max():.2f}")
    print(f"  AP mais cheio nesta run: média {pico.mean():.2f}, "
          f"faixa {pico.min():.0f}–{pico.max():.0f}")
    print(f"  AP mais cheio nas 30 runs: máximo {picos.max():.0f}")
    print()

    saida = cfg["experimento"] / "figuras"
    saida.mkdir(parents=True, exist_ok=True)
    plotar(args.ponto, d, picos, com_gpu, saida / "mobilidade.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
