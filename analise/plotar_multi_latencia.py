#!/usr/bin/env python3
"""Latência do YOLO de vários pontos sobrepostos num só gráfico, cor por ponto.

Uma linha por ponto e um ponto por semente, o que mostra se as execuções de pontos
diferentes se sobrepõem. O eixo x é a semente, sem ordem temporal; a linha entre os
pontos serve apenas para agrupá-los visualmente.

A figura tem dois painéis, latência e falha, pois na série de escala as duas grandezas
variam em sentidos opostos após a saturação, e a latência isolada levaria a uma leitura
equivocada.

Fonte dos dados: o SIMRESULT do YOLO de cada execução da amostra, quando disponível;
na falta dele, nos pontos de aplicação única, o metrics_runs.csv. Nos pontos de carga
mista o metrics_runs.csv agrega todas as aplicações e não é usado; sem as saídas brutas,
o ponto é omitido com aviso.

As figuras de cada experimento vão para experimentos/<experimento>/resultados/figuras/;
a que sobrepõe os dois, para experimentos/comparativos/figuras/.

Uso:
    python3 analise/plotar_multi_latencia.py --serie escala
    python3 analise/plotar_multi_latencia.py --serie densidade
    python3 analise/plotar_multi_latencia.py --serie todos
"""

import argparse
import csv
import statistics
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config as cfg
from plotar_curva_densidade_gpu import parse_generic, APP_GPU

DPI = 300

# A cor vem de config.PONTOS; como tons vizinhos da rampa são próximos, cada ponto
# recebe também um marcador distinto.
MARCADORES = ["o", "s", "^", "D", "v", "P", "X", "*", "<", ">", "h", "p", "d"]


def apps_do_ponto(ponto):
    """Aplicações que o ponto executa, lidas de metrics_by_app.csv (versionado)."""
    caminho = cfg.ponto(ponto)["experimento"] / "metrics_by_app.csv"
    if not caminho.exists():
        return []
    with open(caminho, newline="", encoding="utf-8") as f:
        return [linha["app"] for linha in csv.DictReader(f)]


def do_bruto(ponto):
    """FRTT e falha do YOLO por seed, do SIMRESULT de cada run. {} se não houver."""
    runs = {}
    for d in cfg.runs_da_amostra(ponto):
        arqs = list(d.glob(f"SIMRESULT_*_{APP_GPU}_GENERIC.log"))
        if not arqs:
            continue
        dados = parse_generic(arqs[0])
        if not dados:
            continue
        total = dados["completed"] + dados["failed"]
        runs[int(d.name.split("_seed")[-1])] = {
            "frtt_ms": dados["frtt_ms"],
            "falha_pct": 100.0 * dados["failed"] / max(1, total),
        }
    return runs


def do_agregado(ponto):
    """FRTT e falha por seed do metrics_runs.csv. Só vale onde ALL_APPS == YOLO."""
    caminho = cfg.ponto(ponto)["experimento"] / "metrics_runs.csv"
    if not caminho.exists():
        return {}
    with open(caminho, newline="", encoding="utf-8") as f:
        return {int(l["seed"]): {"frtt_ms": float(l["latency_mean_ms"]),
                                 "falha_pct": float(l["failure_rate"])}
                for l in csv.DictReader(f)}


def carregar(ponto):
    """Execuções do YOLO por semente, escolhendo a fonte segura para o tipo de carga."""
    runs = do_bruto(ponto)
    if runs:
        return runs, "SIMRESULT"
    apps = apps_do_ponto(ponto)
    if len(apps) > 1:
        # metrics_runs.csv incluiria as aplicações de CPU e não é usado aqui.
        print(f"AVISO: {ponto} tem carga mista ({len(apps)} aplicações) e não tem "
              f"saídas brutas nesta máquina; ponto ignorado. O ALL_APPS não serve como "
              f"latência do YOLO.",
              file=sys.stderr)
        return {}, None
    runs = do_agregado(ponto)
    return runs, "metrics_runs.csv" if runs else None


def coletar(pontos):
    series = []
    for ponto in pontos:
        runs, origem = carregar(ponto)
        if not runs:
            if origem is None and len(apps_do_ponto(ponto)) <= 1:
                print(f"AVISO: {ponto} sem dados; ponto ignorado", file=sys.stderr)
            continue
        seeds = sorted(runs)
        series.append({
            "ponto": ponto,
            "rotulo": cfg.ponto(ponto)["rotulo"],
            "cor": cfg.ponto(ponto)["cor"],
            "origem": origem,
            "seeds": seeds,
            "frtt": [runs[s]["frtt_ms"] for s in seeds],
            "falha": [runs[s]["falha_pct"] for s in seeds],
        })
    return series


def rotulo_curto(serie, chave_ordem):
    """Condição física do ponto ('9 clientes', '2 GPUs de 14'), definida em config."""
    return cfg.ponto(serie["ponto"])["rotulo_curto"]


def plotar(series, destino, titulo, chave_ordem):
    fig, (ax, axf) = plt.subplots(2, 1, figsize=(12, 9), sharex=True,
                                  gridspec_kw={"height_ratios": [2.2, 1]})
    for i, s in enumerate(series):
        rot = rotulo_curto(s, chave_ordem)
        media = statistics.fmean(s["frtt"])
        marca = MARCADORES[i % len(MARCADORES)]
        ax.plot(s["seeds"], s["frtt"], marker=marca, markersize=5, linewidth=1.6,
                color=s["cor"], markeredgecolor="white", markeredgewidth=0.4,
                label=f"{rot} — média {media:.1f} ms")
        axf.plot(s["seeds"], s["falha"], marker=marca, markersize=5, linewidth=1.6,
                 color=s["cor"], markeredgecolor="white", markeredgewidth=0.4,
                 label=rot)

    ax.set_yscale("log")
    ax.set_ylabel("FRTT do YOLO por run (ms, escala log)")
    ax.set_title(titulo)
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=8.5,
              title="ponto", title_fontsize=9)

    axf.set_ylabel("Falha do YOLO (%)")
    # O rótulo do eixo informa que a semente não representa tempo.
    axf.set_xlabel("Seed (amostras independentes — sem ordem temporal)")
    axf.grid(True, alpha=0.3)
    axf.set_ylim(bottom=0)

    fig.tight_layout()

    destino.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destino, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"✓ Salvo: {destino}")


SERIES = {
    "escala": {
        "pontos": lambda: cfg.pontos_da_serie("escala"),
        "saida": cfg.SERIES["escala"]["pasta"] / "resultados" / "figuras",
        "nome": "latencia_multi_escala.png",
        "chave": "clientes",
        "titulo": ("Latência do YOLO run a run — escala de clientes sobre 1 GPU\n"
                   "(uma linha por N; a falha embaixo, porque depois do pico as duas "
                   "andam em direções opostas)"),
    },
    "densidade": {
        "pontos": lambda: cfg.pontos_da_serie("densidade"),
        "saida": cfg.SERIES["densidade"]["pasta"] / "resultados" / "figuras",
        "nome": "latencia_multi_densidade.png",
        "chave": "gpus",
        "titulo": ("Latência do YOLO run a run — densidade de GPU na borda\n"
                   "(uma linha por K, os 9 clientes YOLO fixos)"),
    },
    "todos": {
        "pontos": lambda: cfg.pontos_da_serie("escala") + cfg.pontos_da_serie("densidade"),
        "saida": cfg.COMPARATIVOS_DIR / "figuras",
        "nome": "latencia_multi_todos.png",
        "chave": None,
        "titulo": ("Latência do YOLO run a run — as duas séries sobrepostas\n"
                   "(K e N são variáveis diferentes; comparar dentro de cada experimento)"),
    },
}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--serie", choices=sorted(SERIES), default="escala",
                    help="qual conjunto de pontos sobrepor (padrão: escala)")
    ap.add_argument("--permitir-parcial", action="store_true",
                    help="grava a figura mesmo que falte algum ponto")
    args = ap.parse_args()

    spec = SERIES[args.serie]
    pedidos = spec["pontos"]()
    series = coletar(pedidos)
    if not series:
        print("Nenhum ponto com latência do YOLO por execução.", file=sys.stderr)
        return 1
    # A figura "todos" não é gerada se uma das séries estiver ausente, pois o nome
    # indicaria uma comparação que ela não contém.
    if args.serie == "todos":
        obtidos = {s["ponto"] for s in series}
        for nome_serie, membros in (("escala", cfg.SERIE_ESCALA_CLIENTES),
                                    ("densidade", cfg.SERIE_DENSIDADE_GPU)):
            if not (obtidos & set(membros)):
                print(f"ERRO: nenhum ponto da série de {nome_serie} tem saídas brutas do "
                      f"YOLO; a figura 'todos' mostraria uma série só. Use "
                      f"--serie {'densidade' if nome_serie == 'escala' else 'escala'}.",
                      file=sys.stderr)
                return 1
    faltando = [c for c in pedidos if c not in {s["ponto"] for s in series}]
    if faltando:
        print(f"NOTA: {len(series)} de {len(pedidos)} pontos entraram; sem dados: "
              f"{', '.join(faltando)}", file=sys.stderr)
        if not args.permitir_parcial:
            print("Figura não gravada, para não substituir a completa. Use "
                  "--permitir-parcial para gravá-la assim mesmo.", file=sys.stderr)
            return 1
    plotar(series, spec["saida"] / spec["nome"], spec["titulo"], spec["chave"])
    print()
    print(f"{'ponto':>8}  {'runs':>5}  {'fonte':>16}  {'FRTT médio':>12}  {'falha':>8}")
    for s in series:
        print(f"{s['ponto']:>8}  {len(s['seeds']):>5}  {s['origem']:>16}  "
              f"{statistics.fmean(s['frtt']):>9.2f} ms  "
              f"{statistics.fmean(s['falha']):>7.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
