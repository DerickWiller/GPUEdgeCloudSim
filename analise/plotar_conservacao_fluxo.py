#!/usr/bin/env python3
"""Conservação de fluxo do YOLO: taxa ofertada, servida e perdida, em quadros/s.

Como toda tarefa é concluída ou falha, deve valer, em cada ponto:

    λ_ofertada = vazão servida + vazão perdida

em que λ é calculada da configuração (clientes YOLO × 1/0,033 s). O desvio entre λ e a
soma das barras é o erro de conservação do simulador; a parcela perdida indica onde a
infraestrutura satura.

Considera-se apenas o YOLO: é a aplicação comum a todos os pontos e, por ter chegada
periódica, tem λ exata. A figura tem um painel por experimento, cada um com a sua
variável no eixo x (N clientes ou K GPUs).

As vazões são calculadas das saídas brutas da amostra de cada ponto. O ponto sem saídas
brutas nesta máquina mantém a linha já registrada em
experimentos/comparativos/conservacao_fluxo.csv, de modo que a tabela não perca pontos.

Saída: experimentos/comparativos/conservacao_fluxo.csv e
figuras/conservacao_fluxo.png.

Uso:
    python3 analise/plotar_conservacao_fluxo.py
"""

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import config
from plotar_falhas_por_app import ler_usuarios_por_app

COR_SERVIDO = "#1baf7a"    # verde-água
COR_PERDIDO = "#e34948"    # vermelho
COR_OFERTA = "#0b0b0b"
INK = "#0b0b0b"
INK_MUTED = "#52514e"

APP_GPU = "YOLO_DETECTION"
INTERVALO_FRAME_S = 0.033   # intervalo entre quadros do YOLO (30 fps), em s
# Todos os pontos: simulation_time = 60 min e warm_up_period = 5 min.
TEMPO_EFETIVO_S = 3300.0
SAIDA = config.COMPARATIVOS_DIR
# Cada painel é ordenado pela variável do experimento.
SERIES = (
    ("escala", "(a) Uma GPU, variando o número de clientes",
     "Clientes YOLO", config.SERIE_ESCALA_CLIENTES),
    ("densidade", "(b) Nove clientes, variando o número de GPUs",
     "Servidores com GPU (de 14)", config.SERIE_DENSIDADE_GPU),
)
PONTOS = [p for _, _, _, serie in SERIES
          for p in sorted(serie, key=serie.get)]


def metricas_do_ponto(ponto: str) -> dict:
    """Vazão servida e perdida do YOLO (média das execuções) e λ oferecido do ponto."""
    runs = [r for r in config.runs_da_amostra(ponto) if r.is_dir()]
    if not runs:
        return {}

    servidas, perdidas = [], []
    for run in runs:
        logs = list(run.glob(f"*_{APP_GPU}_GENERIC.log"))
        if not logs:
            continue
        linhas = [l for l in open(logs[0]) if not l.startswith("#")]
        if not linhas:
            continue
        p = linhas[0].split(";")
        servidas.append(float(p[0]) / TEMPO_EFETIVO_S)
        perdidas.append(float(p[1]) / TEMPO_EFETIVO_S)

    if not servidas:
        return {}

    # Número de clientes YOLO efetivamente gerados, lido do console da primeira execução.
    usuarios = ler_usuarios_por_app(runs[0])
    n_clientes = usuarios.get(APP_GPU, 0)
    if not n_clientes:
        # Sem a contagem não há λ; o ponto é omitido, pois λ = 0 produziria um erro de
        # conservação nulo sem significado.
        print(f"  AVISO: {ponto} sem contagem de clientes no console; λ não pode ser "
              f"calculado e o ponto é omitido.")
        return {}

    servido = sum(servidas) / len(servidas)
    perdido = sum(perdidas) / len(perdidas)
    oferta = n_clientes / INTERVALO_FRAME_S
    return {
        "ponto": ponto, "n_runs": len(servidas), "clientes": n_clientes,
        "rotulo": config.ponto(ponto)["rotulo_curto"],
        "servido": servido, "perdido": perdido, "total": servido + perdido,
        "oferta": oferta,
        "erro_pct": (100.0 * (servido + perdido - oferta) / oferta) if oferta else 0.0,
    }


def registrados() -> dict:
    """Linhas da tabela já publicada, por ponto, para os pontos sem saídas brutas."""
    arq = SAIDA / "conservacao_fluxo.csv"
    if not arq.exists():
        return {}
    df = pd.read_csv(arq)
    return {r["ponto"]: r.to_dict() for _, r in df.iterrows()}


def carregar() -> pd.DataFrame:
    anteriores = registrados()
    linhas = []
    for ponto in PONTOS:
        m = metricas_do_ponto(ponto)
        if m:
            linhas.append(m)
        elif ponto in anteriores:
            linha = anteriores[ponto]
            linha.setdefault("rotulo", config.ponto(ponto)["rotulo_curto"])
            if pd.isna(linha.get("rotulo")):
                linha["rotulo"] = config.ponto(ponto)["rotulo_curto"]
            linhas.append(linha)
            print(f"  NOTA: {ponto} sem saídas brutas; mantida a linha registrada.")
        else:
            print(f"  AVISO: {ponto} sem execuções legíveis do {APP_GPU}; ponto omitido.")
    if not linhas:
        print("ERRO: nenhum ponto com dados do YOLO.")
        sys.exit(1)
    return pd.DataFrame(linhas)


def _barras(ax, df, titulo, xlabel, variavel):
    """Desenha um painel: barras empilhadas + a marca de λ sobre cada uma."""
    x = range(len(df))
    ax.bar(x, df["servido"], 0.55, label="Servido (completou)", color=COR_SERVIDO,
           edgecolor="white", linewidth=2)
    ax.bar(x, df["perdido"], 0.55, bottom=df["servido"], label="Perdido (falhou)",
           color=COR_PERDIDO, edgecolor="white", linewidth=2)

    # λ como traço horizontal sobre cada barra; há conservação quando a barra o atinge.
    for i, (_, r) in enumerate(df.iterrows()):
        ax.plot([i - 0.36, i + 0.36], [r["oferta"], r["oferta"]], "-",
                color=COR_OFERTA, linewidth=2.5, zorder=4,
                label="λ oferecido (calculado da config)" if i == 0 else None)
        ax.text(i, r["oferta"], f"λ = {r['oferta']:.1f}", ha="center", va="bottom",
                fontsize=9, fontweight="bold", color=INK)
        if r["servido"] >= 0.10 * r["total"]:
            ax.text(i, r["servido"] / 2, f"{r['servido']:.0f}", ha="center",
                    va="center", color="white", fontsize=10, fontweight="bold")
        if r["perdido"] >= 0.10 * r["total"]:
            ax.text(i, r["servido"] + r["perdido"] / 2, f"{r['perdido']:.0f}",
                    ha="center", va="center", color="white", fontsize=10,
                    fontweight="bold")

    # O rótulo de cada marca é o valor da variável da série; o eixo indica qual é ela.
    ax.set_xticks(list(x))
    ax.set_xticklabels([str(variavel[r["ponto"]]) for _, r in df.iterrows()],
                       fontsize=11)
    ax.set_xlabel(xlabel, fontweight="bold", color=INK)
    ax.set_title(titulo, fontweight="bold", color=INK, pad=10, fontsize=11)
    ax.grid(True, axis="y", alpha=0.25, linestyle="--")
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.margins(y=0.16)


def plotar(df: pd.DataFrame, output_file: Path):
    paineis = [(nome, titulo, xlabel, serie,
                df[df["ponto"].isin(serie)].sort_values(
                    "ponto", key=lambda c: c.map(serie)))
               for nome, titulo, xlabel, serie in SERIES]
    paineis = [p for p in paineis if not p[4].empty]
    if not paineis:
        print("ERRO: nenhuma série com dados.")
        sys.exit(1)

    larguras = [max(3.2, 1.15 * len(p[4]) + 1.6) for p in paineis]
    fig, axes = plt.subplots(
        1, len(paineis), figsize=(sum(larguras) + 1.2, 6.4), sharey=True,
        gridspec_kw={"width_ratios": larguras})
    axes = [axes] if len(paineis) == 1 else list(axes)

    for ax, (_, titulo, xlabel, serie, sub) in zip(axes, paineis):
        _barras(ax, sub, titulo, xlabel, serie)
    axes[0].set_ylabel("Vazão do YOLO (quadros por segundo)",
                       fontweight="bold", color=INK)
    axes[0].legend(loc="upper left", frameon=False, fontsize=10)

    fig.suptitle("Conservação de fluxo — oferta = servido + perdido",
                 fontweight="bold", color=INK, fontsize=13)

    pior = df["erro_pct"].abs().max()
    faltando = len(PONTOS) - len(df)
    aviso = (f" {faltando} dos {len(PONTOS)} pontos não têm dados nesta "
             f"máquina e ficaram fora." if faltando else "")
    fig.text(0.5, 0.005,
             f"λ = clientes YOLO × 1/33 ms, calculado da configuração — não medido. "
             f"Maior desvio de conservação entre os {len(df)} pontos mostrados: "
             f"{pior:.3f}%.{aviso}\n"
             "Onde a barra vermelha aparece, a infraestrutura não deu conta; "
             "a altura da faixa verde é o teto real de vazão da GPU naquele ponto.",
             ha="center", va="bottom", fontsize=9, color=INK_MUTED)

    plt.tight_layout(rect=[0, 0.06, 1, 0.96])
    plt.savefig(output_file, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"\n✓ Gerado: {output_file}")


def main() -> int:
    argparse.ArgumentParser(
        description="Conservação de fluxo do YOLO por ponto.").parse_args()

    print("=" * 74)
    print("Conservação de fluxo — YOLO_DETECTION")
    print("=" * 74)

    df = carregar()
    print(df[["ponto", "rotulo", "clientes", "n_runs", "oferta", "servido",
              "perdido", "total", "erro_pct"]].round(3).to_string(index=False))
    print()

    (SAIDA / "figuras").mkdir(parents=True, exist_ok=True)
    plotar(df, SAIDA / "figuras" / "conservacao_fluxo.png")
    df.to_csv(SAIDA / "conservacao_fluxo.csv", index=False)
    print(f"✓ Tabela:  {SAIDA / 'conservacao_fluxo.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
