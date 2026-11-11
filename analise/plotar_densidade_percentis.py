#!/usr/bin/env python3
"""Densidade de GPU: latência em quatro estatísticas e taxa de falha, contra K.

Média, mediana, p95 e p99 no mesmo eixo, para comparar a tendência central com a
cauda da distribuição.

A figura combina duas amostras: média e falha vêm de 30 execuções por ponto
(SIMRESULT); os percentis, do registro por tarefa de 10 execuções por ponto, pois o
SIMRESULT não guarda a distribuição. Para a mesma semente, o SIMRESULT é idêntico com
e sem o registro por tarefa.

Fontes: curva_densidade_gpu.csv e percentis_latencia.csv, em
experimentos/densidade-gpu/resultados/.

Uso:
    python3 analise/plotar_densidade_percentis.py [--com-falha]
"""

import argparse
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config
from estatistica import semiamplitude

INK = "#0b0b0b"
INK_MUTED = "#52514e"

# Estatística -> (rótulo, cor, marcador, estilo de linha). Cores categóricas, pois as
# curvas distinguem estatísticas, não níveis de uma variável ordenada; p50, p95 e p99
# têm as mesmas cores de plotar_distribuicao_latencia.py.
ESTATISTICAS = [
    ("media", "Média",   "#4a3aa7", "o", "-"),
    ("p50",   "Mediana", "#2a78d6", "s", "-"),
    ("p95",   "p95",     "#eb6834", "^", "--"),
    ("p99",   "p99",     "#1baf7a", "D", "--"),
]
ORCAMENTO_QUADRO_MS = 33.0


def num(valor: float, casas: int = 2) -> str:
    """Número formatado com vírgula decimal."""
    return f"{valor:.{casas}f}".replace(".", ",")


def carregar() -> pd.DataFrame:
    """Uma linha por K, com média e falha de 30 runs e percentis do deep log."""
    resultados = config.SERIES["densidade"]["pasta"] / "resultados"
    curva = resultados / "curva_densidade_gpu.csv"
    perc = resultados / "percentis_latencia.csv"
    for arq in (curva, perc):
        if not arq.exists():
            raise SystemExit(f"ERRO: falta {arq}")

    d = pd.read_csv(curva).set_index("ponto")
    p = pd.read_csv(perc).set_index("ponto")

    linhas = []
    for num, k in sorted(config.SERIE_DENSIDADE_GPU.items(),
                         key=lambda kv: kv[1]):
        if num not in d.index:
            print(f"  AVISO: {num} ausente em curva_densidade_gpu.csv; ponto omitido.")
            continue
        if num not in p.index:
            print(f"  AVISO: {num} sem percentis (registro por tarefa); ponto omitido.")
            continue
        linhas.append({
            "ponto": num,
            "k": k,
            "media": d.loc[num, "frtt_ms"],
            "media_ic95": d.loc[num, "frtt_ic95"],
            "p50": p.loc[num, "p50_ms"],
            "p95": p.loc[num, "p95_ms"],
            "p99": p.loc[num, "p99_ms"],
            "falha": d.loc[num, "falha_pct"],
            # A barra representa o IC95 da média (t · desvio / √n), e não a dispersão
            # entre execuções.
            "n": int(d.loc[num, "num_runs"]),
            "falha_ic95": semiamplitude(d.loc[num, "falha_std"], int(d.loc[num, "num_runs"])),
            "cor": config.ponto(num)["cor"],
        })
    if not linhas:
        raise SystemExit("ERRO: nenhum ponto da série de densidade disponível.")
    return pd.DataFrame(linhas)


def painel_latencia(ax, df: pd.DataFrame):
    x = np.arange(len(df))
    for chave, rotulo, cor, marca, traco in ESTATISTICAS:
        erro = df["media_ic95"] if chave == "media" else None
        ax.errorbar(x, df[chave], yerr=erro, color=cor, marker=marca,
                    linestyle=traco, linewidth=2.2, markersize=8,
                    markeredgecolor="white", markeredgewidth=1.2,
                    capsize=4, label=rotulo, zorder=3)

    ax.axhline(ORCAMENTO_QUADRO_MS, color=INK_MUTED, linestyle=":", linewidth=1.8)
    ax.text(len(df) - 0.5, ORCAMENTO_QUADRO_MS * 1.08,
            "orçamento de 1 quadro a 30 fps (33 ms)", ha="right", va="bottom",
            fontsize=9.5, color=INK_MUTED)

    # Uma única anotação para os dois pontos com p99 acima do orçamento, que têm o
    # mesmo valor.
    estourados = df[(df["p99"] > ORCAMENTO_QUADRO_MS) & (df["k"] > 1)]
    if len(estourados):
        centro = float(estourados.index.to_series().mean())
        alvo = float(estourados["p99"].iloc[0])
        quais = " e ".join(str(int(k)) for k in estourados["k"])
        ax.annotate(f"p99 idêntico com {quais} GPUs ({num(alvo)} ms):\n"
                    "a GPU a mais não encurta a cauda aqui",
                    xy=(centro, alvo), xytext=(0, 34), textcoords="offset points",
                    ha="center", fontsize=9.5, fontweight="bold", color="#c0392b",
                    arrowprops=dict(arrowstyle="-", color="#c0392b", lw=1.1,
                                    shrinkB=3))

    # Abaixo da linha da mediana, onde o painel está vazio.
    meio = (len(df) - 1) / 2
    ax.annotate(f"mediana constante em {num(df['p50'].iloc[-1])} ms — o piso físico "
                "(4,00 ms de GPU + 4,44 ms de rede):\nacrescentar GPU não acelera "
                "o quadro típico, só reduz quantos esperam em fila",
                xy=(meio, df["p50"].iloc[-1]), xytext=(0, -42),
                textcoords="offset points", ha="center", fontsize=9.5,
                color="#2a78d6", fontweight="bold",
                arrowprops=dict(arrowstyle="-", color="#2a78d6", lw=1.1,
                                shrinkB=3))

    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{k}" for k in df["k"]], fontsize=11)
    ax.set_xlabel("Servidores de borda com GPU, de 14", fontweight="bold",
                  color=INK, fontsize=11)
    ax.set_ylabel("FRTT do YOLO (ms, escala log)", fontweight="bold",
                  color=INK, fontsize=11)
    ax.set_title("A média diz que bastam 2 GPUs; a cauda diz que só 7 resolvem",
                 fontweight="bold", color=INK, pad=10, fontsize=12)
    ax.set_ylim(df["p50"].min() / 3.4, df["p99"].max() * 2.6)
    ax.tick_params(labelsize=10)
    ax.grid(True, alpha=0.25, linestyle="--")
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.legend(loc="upper right", frameon=False, fontsize=10, ncol=4)


def painel_falha(ax, df: pd.DataFrame):
    x = np.arange(len(df))
    ax.bar(x, df["falha"], 0.55, yerr=df["falha_ic95"], color=df["cor"],
           edgecolor="white", linewidth=1.5, capsize=4, zorder=3)
    for i, linha in df.iterrows():
        texto = "0%" if linha["falha"] == 0 else f"{num(linha['falha'])}%"
        ax.text(i, linha["falha"] + df["falha"].max() * 0.035, texto,
                ha="center", va="bottom", fontsize=10, fontweight="bold",
                color=INK)

    ax.set_xticks(x)
    ax.set_xticklabels([f"{k}" for k in df["k"]], fontsize=11)
    ax.set_xlabel("Servidores de borda com GPU, de 14", fontweight="bold",
                  color=INK, fontsize=11)
    ax.set_ylabel("Quadros perdidos (%)", fontweight="bold", color=INK,
                  fontsize=11)
    ax.set_title("(b) A perda desaparece no primeiro passo e não volta",
                 fontweight="bold", color=INK, pad=10, fontsize=12)
    ax.set_ylim(0, df["falha"].max() * 1.28)
    ax.tick_params(labelsize=10)
    ax.grid(True, axis="y", alpha=0.25, linestyle="--")
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Latência em quatro estatísticas contra a densidade de GPU.")
    # O painel de falha é opcional: a mesma informação está em
    # falhas_por_app_densidade.png, acompanhada da causa de cada perda.
    parser.add_argument("--com-falha", action="store_true",
                        help="acrescenta o painel de taxa de falha (redundante "
                             "com falhas_por_app_densidade.png)")
    args = parser.parse_args()

    df = carregar()
    print(df[["k", "media", "p50", "p95", "p99", "falha"]].to_string(index=False))

    if args.com_falha:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.6, 9.4),
                                       gridspec_kw={"height_ratios": [1.5, 1]})
        painel_falha(ax2, df)
    else:
        fig, ax1 = plt.subplots(figsize=(8.6, 5.9))
    painel_latencia(ax1, df)
    fig.text(0.5, 0.004,
             f"Carga fixa de 9 clientes de detecção de objetos nos cinco pontos; só "
             f"muda quantos dos 14 servidores têm GPU. Média: {'/'.join(str(v) for v in sorted(set(df['n'])))} execuções "
             "por ponto, barras de IC95 da média.\nPercentis: registro por tarefa, "
             "10 execuções por ponto — percentil exige a distribuição, que a "
             "métrica agregada não guarda. A taxa de falha por K está na figura de "
             "falha por aplicação.",
             ha="center", va="bottom", fontsize=9, color=INK_MUTED)

    plt.tight_layout(rect=[0, 0.085 if not args.com_falha else 0.055, 1, 1],
                     h_pad=3.0)
    saida = config.SERIES["densidade"]["pasta"] / "resultados" / "figuras"
    saida.mkdir(parents=True, exist_ok=True)
    arq = saida / ("densidade_percentis_falha.png" if args.com_falha
                   else "densidade_percentis.png")
    plt.savefig(arq, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"\n✓ Gerado: {arq}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
