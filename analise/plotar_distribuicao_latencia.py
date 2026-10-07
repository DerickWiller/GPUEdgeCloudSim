#!/usr/bin/env python3
"""Distribuição da latência por tarefa: CDF e percentis (p50/p95/p99).

Para aplicações de tempo real a média é insuficiente; os percentis exigem a latência
de cada tarefa, disponível no registro por tarefa (SUCCESS.log) gerado por
execucao/rodar_deeplog.sh em saidas/deeplog/<experimento>/<ponto>/.

  (a) CDF do FRTT por ponto, com tempo em escala logarítmica e linhas verticais nos
      requisitos de tempo real;
  (b) p50, p95 e p99 por ponto; a distância entre p50 e p99 mede a cauda.

Consideram-se apenas tarefas concluídas, pois as que falham não têm latência. Nos
pontos saturados os percentis descrevem apenas as tarefas atendidas e devem ser lidos
com a taxa de falha.

Saídas: com --serie, as figuras vão para experimentos/<experimento>/resultados/figuras/;
sem ela, a figura que mistura os experimentos vai para experimentos/comparativos/figuras/.
Os percentis de cada ponto calculado são atualizados no percentis_latencia.csv do seu
experimento, preservadas as linhas dos demais pontos. Se algum ponto pedido não tiver
registro por tarefa nesta máquina, a figura não é gravada, para não substituir uma
figura completa por uma parcial (use --permitir-parcial para forçar).

Uso:
    python3 analise/plotar_distribuicao_latencia.py --serie escala
    python3 analise/plotar_distribuicao_latencia.py --serie escala --layout ambos
    python3 analise/plotar_distribuicao_latencia.py --pontos N01,N14 --sufixo _pontas
"""

import argparse
import csv
import sys
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config

INK = "#0b0b0b"
INK_MUTED = "#52514e"
# Cores categóricas distinguíveis entre si em todos os pares, pois as curvas se cruzam.
PALETA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7"]
COR_P = {"p50": "#2a78d6", "p95": "#eb6834", "p99": "#1baf7a"}

# A cor do ponto segue uma rampa sequencial, com tons vizinhos próximos; cada curva
# recebe também marcador distinto e rótulo direto, o que dispensa a legenda.
MARCADORES = ["o", "s", "^", "D", "v", "P", "X", "*"]
# Alturas dos marcadores, escalonadas para que não se sobreponham nos cruzamentos.
NIVEIS_MARCA = np.array([0.10, 0.30, 0.50, 0.70, 0.90])
PASSO_MARCA = 0.032
# Alturas dos rótulos diretos, alternadas na ordem das medianas para evitar colisão.
NIVEIS_ROTULO = (0.96, 0.87, 0.78)

# Os cinco pontos da densidade de GPU e as duas pontas da escala de clientes.
PADRAO = ["N01", "K01", "K02", "K03", "K07", "K14", "N14"]

# Pontos e sufixo de arquivo por experimento; o sufixo distingue as figuras dos dois.
SERIES = {
    "densidade": (config.pontos_da_serie("densidade"), "_densidade"),
    "escala": (config.pontos_da_serie("escala"), "_escala"),
}
# Intervalo entre quadros a 30 fps, em ms.
REQUISITOS_MS = [(33.0, "orçamento de 1 quadro (33 ms)")]
# Índices no SUCCESS.log (SimLogger.java:1622): taskType, início e fim.
IDX_TASK_TYPE, IDX_INICIO, IDX_FIM = 6, 10, 11
APP_GPU_TASK_TYPE = 0   # índice do YOLO_DETECTION em todos os pontos


def latencias_do_ponto(num: str, so_gpu: bool = True) -> np.ndarray:
    """FRTT por tarefa concluída, em ms, juntando as execuções com registro por tarefa.

    Usa pandas.read_csv com usecols, pois há cerca de 9 milhões de linhas por ponto.
    """
    arquivos = sorted(config.ponto(num)["deeplog"].glob("run_*/*_SUCCESS.log"))
    if not arquivos:
        return np.array([])

    colunas = [IDX_TASK_TYPE, IDX_INICIO, IDX_FIM]
    partes = []
    for arq in arquivos:
        d = pd.read_csv(arq, sep=";", header=None, comment="#",
                        usecols=colunas, names=["tipo", "inicio", "fim"],
                        engine="c", on_bad_lines="skip")
        if so_gpu:
            d = d[d["tipo"] == APP_GPU_TASK_TYPE]
        partes.append(((d["fim"] - d["inicio"]) * 1000.0).to_numpy())

    return np.concatenate(partes) if partes else np.array([])


def cdf(valores: np.ndarray, max_pontos: int = 4000):
    """Curva CDF reduzida a max_pontos, por amostragem em quantis."""
    x = np.sort(valores)
    y = np.arange(1, len(x) + 1) / len(x)
    if len(x) > max_pontos:
        # Amostragem em quantis, que preserva a cauda da distribuição.
        q = np.linspace(0, 1, max_pontos)
        x = np.quantile(x, q)
        y = q
    return x, y


def variavel_da_serie(num: str) -> float:
    """N (clientes) ou K (GPUs) do ponto."""
    return config.ponto(num)["valor"]


def painel_cdf(ax, dados: dict, fs: float = 1.0, legenda: bool = False):
    # Marcador pela ordem da variável (estável entre figuras); altura do rótulo pela
    # ordem das medianas.
    ordem = sorted(dados, key=variavel_da_serie)
    por_mediana = sorted(dados, key=lambda n: np.median(dados[n]))
    rotulos = []

    for i, num in enumerate(ordem):
        vals = dados[num]
        cfg = config.ponto(num)
        x, y = cdf(vals)
        ax.plot(x, 100 * y, "-", color=cfg["cor"], linewidth=2.2,
                solid_capstyle="round", label=cfg["rotulo"], zorder=3)

        niveis = NIVEIS_MARCA + i * PASSO_MARCA
        niveis = niveis[niveis < 0.99]
        ax.plot(np.quantile(vals, niveis), 100 * niveis, linestyle="none",
                marker=MARCADORES[i % len(MARCADORES)], color=cfg["cor"],
                markersize=6.4 * fs, markeredgecolor="white", markeredgewidth=1.0,
                zorder=4)

        nivel = NIVEIS_ROTULO[por_mediana.index(num) % len(NIVEIS_ROTULO)]
        rotulos.append((float(np.quantile(vals, nivel)), 100 * nivel,
                        cfg["rotulo_curto"], cfg["cor"]))

    for valor, texto in REQUISITOS_MS:
        ax.axvline(valor, color=INK_MUTED, linestyle="--", linewidth=1.5)
        ax.text(valor, 2, f" {texto}", rotation=90, va="bottom", ha="left",
                fontsize=8.5 * fs, color=INK_MUTED)

    ax.set_xscale("log")
    ax.autoscale(enable=True, axis="x")
    x0, x1 = ax.get_xlim()
    # Folga à direita para o rótulo da última curva.
    ax.set_xlim(x0, x1 * 1.28)
    x0, x1 = ax.get_xlim()
    meio = np.sqrt(x0 * x1)

    for xr, yr, texto, cor in rotulos:
        # Linha-guia entre rótulo e curva, necessária onde as curvas são próximas.
        direita = xr > meio
        ax.annotate(texto,
                    xy=(xr, yr),
                    xytext=(-26 if direita else 26, 0), textcoords="offset points",
                    ha="right" if direita else "left", va="center",
                    fontsize=8.8 * fs, fontweight="bold", color=cor,
                    bbox=dict(boxstyle="round,pad=0.18", facecolor="white",
                              edgecolor="none", alpha=0.85),
                    arrowprops=dict(arrowstyle="-", color=cor, linewidth=1.1,
                                    shrinkA=1.5, shrinkB=1.5),
                    zorder=5)

    ax.set_xlabel("FRTT por tarefa (ms, escala log)", fontweight="bold",
                  color=INK, fontsize=10 * fs)
    ax.set_ylabel("Tarefas concluídas até esse tempo (%)", fontweight="bold",
                  color=INK, fontsize=10 * fs)
    ax.set_title("(a) Distribuição acumulada da latência",
                 fontweight="bold", color=INK, pad=10, fontsize=11.5 * fs)
    ax.set_ylim(0, 100)
    ax.tick_params(labelsize=9 * fs)
    ax.grid(True, alpha=0.25, linestyle="--")
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    if legenda:
        # Apenas no layout duplo.
        ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False,
                  fontsize=8.5 * fs)


def painel_percentis(ax, dados: dict, fs: float = 1.0):
    nums = sorted(dados, key=variavel_da_serie)
    largura = 0.26
    base = np.arange(len(nums))

    todos = []
    for j, chave in enumerate(("p50", "p95", "p99")):
        q = int(chave[1:])
        valores = [float(np.percentile(dados[n], q)) for n in nums]
        todos.extend(valores)
        pos = base + (j - 1) * largura
        ax.bar(pos, valores, largura, label=chave.upper(), color=COR_P[chave],
               edgecolor="white", linewidth=1.5)
        for x, v in zip(pos, valores):
            # Uma casa decimal, para distinguir percentis próximos; texto vertical,
            # pois barras de alturas semelhantes ficam próximas em escala log.
            ax.text(x, v, f" {v:.1f}", ha="center", va="bottom", fontsize=8 * fs,
                    fontweight="bold", color=INK, rotation=90)

    # O rótulo da linha de 33 ms fica numa margem à esquerda, fora da área das barras.
    esq, dir_ = -1.38, len(nums) - 0.5
    ax.set_xlim(esq, dir_)
    # A linha começa após a margem do rótulo.
    inicio = (-0.55 - esq) / (dir_ - esq)
    for valor, texto in REQUISITOS_MS:
        ax.axhline(valor, xmin=inicio, xmax=1.0, color=INK_MUTED,
                   linestyle="--", linewidth=1.5)
        ax.text(-1.30, valor, textwrap.fill(texto, 11), va="center", ha="left",
                fontsize=8.0 * fs, color=INK_MUTED, linespacing=1.35)

    ax.set_xticks(base)
    # Cada marca é rotulada pela condição física (número de GPUs ou de clientes).
    ax.set_xticklabels([config.ponto(n)["rotulo_curto"].replace(" de ", "\nde ")
                        for n in nums], fontsize=9 * fs)
    ax.set_yscale("log")
    ax.set_xlabel("Configuração", fontweight="bold", color=INK, fontsize=10 * fs)
    ax.set_ylabel("FRTT (ms, escala log)", fontweight="bold", color=INK,
                  fontsize=10 * fs)
    ax.set_title("(b) Mediana, p95 e p99 — a distância entre elas é a cauda",
                 fontweight="bold", color=INK, pad=10, fontsize=11.5 * fs)
    ax.tick_params(axis="y", labelsize=9 * fs)
    ax.grid(True, axis="y", alpha=0.25, linestyle="--")
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.legend(loc="upper left", frameon=False, fontsize=9 * fs, ncol=3)
    # Limites do eixo y ajustados aos dados, com folga apenas no topo para os rótulos.
    ax.set_ylim(min(todos) / 1.7, max(todos) * 2.6)


def plotar(dados: dict, output_file: Path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6.6))
    # Sem legenda: o rótulo direto identifica cada curva.
    painel_cdf(ax1, dados)
    painel_percentis(ax2, dados)

    fig.suptitle("Distribuição da latência por tarefa — o que a média não mostra",
                 fontweight="bold", fontsize=13, color=INK, y=0.99)
    fig.text(0.5, 0.005,
             "Apenas tarefas CONCLUÍDAS (SUCCESS.log): tarefa que falhou não tem "
             "latência. Nos pontos saturados, leia sempre junto com a taxa de falha "
             "— num ponto que perde metade dos quadros, o p99 descreve os que "
             "passaram, não o ponto.\n"
             "Registro por tarefa de 10 seeds por ponto (execucao/rodar_deeplog.sh).",
             ha="center", va="bottom", fontsize=9, color=INK_MUTED)

    plt.tight_layout(rect=[0, 0.07, 1, 0.94])
    plt.savefig(output_file, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"\n✓ Gerado: {output_file}")


NOTA_AMOSTRA = ("Apenas tarefas CONCLUÍDAS (SUCCESS.log): tarefa que falhou não tem "
                "latência — tem destino. Nos pontos saturados, leia sempre junto com "
                "a taxa de falha.\nRegistro por tarefa de 10 seeds por ponto "
                "(execucao/rodar_deeplog.sh).")


def plotar_separado(dados: dict, saida: Path, sufixo: str):
    """Um arquivo por painel, dimensionado para a largura útil de uma página A4.

    A figura de painel duplo (16 pol) seria reduzida 2,8 vezes na página, tornando os
    rótulos ilegíveis.
    """
    for letra, nome, altura, pintar in (
            ("a", "a_cdf", 5.6, lambda ax: painel_cdf(ax, dados, fs=1.22)),
            ("b", "b_percentis", 5.2, lambda ax: painel_percentis(ax, dados, fs=1.22)),
    ):
        fig, ax = plt.subplots(figsize=(8.2, altura))
        pintar(ax)
        fig.text(0.5, 0.005, NOTA_AMOSTRA, ha="center", va="bottom",
                 fontsize=8.5, color=INK_MUTED)
        plt.tight_layout(rect=[0, 0.10, 1, 1])
        arq = saida / f"distribuicao_latencia{sufixo}_{nome}.png"
        plt.savefig(arq, dpi=300, bbox_inches="tight", facecolor="white")
        plt.close()
        print(f"✓ Gerado: {arq}")


def plotar_empilhado(dados: dict, saida: Path, sufixo: str):
    """Os dois painéis empilhados num único arquivo, sem nota de rodapé.

    O empilhamento preserva a largura de cada painel. Sem o rodapé, a legenda no texto
    deve informar que apenas tarefas concluídas são consideradas.
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.2, 10.2))
    painel_cdf(ax1, dados, fs=1.22)
    painel_percentis(ax2, dados, fs=1.22)
    plt.tight_layout(h_pad=2.6)
    arq = saida / f"distribuicao_latencia{sufixo}_empilhado.png"
    plt.savefig(arq, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"✓ Gerado: {arq}")


def plotar_lado_a_lado(dados: dict, saida: Path, sufixo: str):
    """Os dois painéis lado a lado, sem rodapé nem título geral.

    Com 14 pol de largura, a figura é reduzida 2,2 vezes numa página A4; o layout
    empilhado é preferível. A legenda no texto deve informar que apenas tarefas
    concluídas são consideradas.
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6.2))
    painel_cdf(ax1, dados)
    painel_percentis(ax2, dados)
    plt.tight_layout(w_pad=2.4)
    arq = saida / f"distribuicao_latencia{sufixo}_lado_a_lado.png"
    plt.savefig(arq, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"✓ Gerado: {arq}")


def atualizar_percentis(resumo: list) -> None:
    """Atualiza, no CSV de cada experimento, as linhas dos pontos calculados."""
    campos = ["ponto", "tarefas", "media_ms", "p50_ms", "p95_ms", "p99_ms", "max_ms"]
    for serie in ("densidade", "escala"):
        novos = {r[0]: r for r in resumo if config.ponto(r[0])["serie"] == serie}
        if not novos:
            continue
        caminho = config.SERIES[serie]["pasta"] / "resultados" / "percentis_latencia.csv"
        linhas = {}
        if caminho.exists():
            with open(caminho, newline="", encoding="utf-8") as fh:
                linhas = {l["ponto"]: l for l in csv.DictReader(fh)}
        for num, n, media, p50, p95, p99, mx in novos.values():
            linhas[num] = {"ponto": num, "tarefas": n, "media_ms": f"{media:.4f}",
                           "p50_ms": f"{p50:.4f}", "p95_ms": f"{p95:.4f}",
                           "p99_ms": f"{p99:.4f}", "max_ms": f"{mx:.4f}"}
        with open(caminho, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=campos)
            w.writeheader()
            w.writerows(linhas[p] for p in sorted(linhas, key=variavel_da_serie))
        print(f"✓ Tabela:  {caminho}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CDF e percentis da latência por tarefa (exige o registro por tarefa).")
    parser.add_argument("--pontos", default=None,
                        help=f"lista separada por vírgula (padrão: {','.join(PADRAO)})")
    parser.add_argument("--serie", choices=sorted(SERIES),
                        help="escolhe os pontos de um experimento e grava as figuras nele")
    parser.add_argument("--layout",
                        choices=("duplo", "separado", "empilhado",
                                 "lado_a_lado", "ambos"),
                        default="duplo",
                        help="duplo: os dois painéis num arquivo (padrão). separado: um "
                             "arquivo por painel, na largura de uma página. empilhado: "
                             "os dois painéis um sobre o outro, sem rodapé.")
    parser.add_argument("--sufixo", default=None,
                        help="sufixo no nome de saída; obrigatório com --pontos fora do "
                             "padrão, para não sobrescrever a figura existente")
    parser.add_argument("--permitir-parcial", action="store_true",
                        help="grava a figura mesmo que falte o registro de algum ponto")
    args = parser.parse_args()

    if args.serie and args.pontos:
        print("ERRO: use --serie OU --pontos, não os dois.")
        return 1

    if args.serie:
        nums, sufixo = SERIES[args.serie]
        saida = config.SERIES[args.serie]["pasta"] / "resultados" / "figuras"
    else:
        nums = [v.strip().upper() for v in (args.pontos or ",".join(PADRAO)).split(",")
                if v.strip()]
        sufixo = args.sufixo or ""
        saida = config.COMPARATIVOS_DIR / "figuras"
        if args.pontos and sorted(nums) != sorted(PADRAO) and not args.sufixo:
            print("ERRO: conjunto de pontos fora do padrão exige --sufixo, senão a "
                  "figura sobrescreve a existente.")
            return 1

    print("=" * 78)
    print("Distribuição da latência por tarefa (YOLO_DETECTION)")
    print("=" * 78)

    dados, resumo, faltando = {}, [], []
    for num in nums:
        if num not in config.PONTOS:
            print(f"ERRO: ponto {num} desconhecido. Use um de: {', '.join(config.PONTOS)}.")
            return 1
        vals = latencias_do_ponto(num)
        if vals.size == 0:
            faltando.append(num)
            print(f"  AVISO: {num} sem registro por tarefa em "
                  f"{config.ponto(num)['deeplog'].relative_to(config.REPO_ROOT)}.")
            print(f"         Gere com: bash execucao/rodar_deeplog.sh {num} 10 1")
            continue
        dados[num] = vals
        p50, p95, p99 = np.percentile(vals, [50, 95, 99])
        resumo.append((num, len(vals), vals.mean(), p50, p95, p99, vals.max()))

    if not dados:
        print("ERRO: nenhum ponto com registro por tarefa.")
        return 1

    print(f"\n{'ponto':<6}{'tarefas':>12}{'média':>10}{'p50':>10}{'p95':>10}"
          f"{'p99':>10}{'máx':>11}")
    for num, n, media, p50, p95, p99, mx in resumo:
        print(f"{num:<6}{n:>12,}{media:>10.2f}{p50:>10.2f}{p95:>10.2f}"
              f"{p99:>10.2f}{mx:>11.2f}")
    print()

    atualizar_percentis(resumo)
    if faltando and not args.permitir_parcial:
        print(f"Figura não gravada: faltam {', '.join(faltando)}. "
              f"Use --permitir-parcial para gravá-la assim mesmo.")
        return 0

    saida.mkdir(parents=True, exist_ok=True)
    if args.layout in ("duplo", "ambos"):
        plotar(dados, saida / f"distribuicao_latencia{sufixo}.png")
    if args.layout in ("separado", "ambos"):
        plotar_separado(dados, saida, sufixo)
    if args.layout in ("empilhado", "ambos"):
        plotar_empilhado(dados, saida, sufixo)
    if args.layout in ("lado_a_lado", "ambos"):
        plotar_lado_a_lado(dados, saida, sufixo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
