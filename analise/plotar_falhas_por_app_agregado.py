#!/usr/bin/env python3
"""Falha por aplicação, média de 30 execuções com IC95, e a causa de cada falha.

  (a) taxa de falha por aplicação e ponto;
  (b) número de tarefas perdidas por causa: capacidade (VM/memória de vídeo), banda,
      mobilidade e ausência de cobertura da WLAN.

O painel (b) usa contagem absoluta, e não percentual, para preservar a diferença de
escala entre pontos. O IC95 vem da coluna failure_rate_ic95 de metrics_by_app.csv;
na ausência dela, a barra é desenhada sem intervalo e o subtítulo o informa.

A figura é gravada em experimentos/<experimento>/resultados/figuras/.

Uso:
    python3 analise/plotar_falhas_por_app_agregado.py --serie densidade
    python3 analise/plotar_falhas_por_app_agregado.py --serie escala
"""

import argparse
import csv
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import config as cfg

DPI = 300
INK = "#1a1a1a"
INK_MUTED = "#6b6b6b"

# Cor por causa de falha: vermelho para capacidade, a causa predominante, e tons frios
# para as demais, que se destacariam caso ocorressem.
CORES_CAUSA = {
    "failed_vm_capacity": ("#c0392b", "VM/VRAM cheia"),
    "failed_bw": ("#2a78d6", "Banda insuficiente"),
    "failed_mobility": ("#eda100", "Mobilidade"),
}


def ler_apps(ponto):
    caminho = cfg.ponto(ponto)["experimento"] / "metrics_by_app.csv"
    if not caminho.exists():
        return []
    with open(caminho, newline="", encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    for l in linhas:
        for k, v in list(l.items()):
            if k not in ("app", "uses_gpu"):
                l[k] = float(v)
        l["uses_gpu"] = l["uses_gpu"] == "True"
    return linhas


def coletar(pontos):
    dados, sem_ic95 = [], []
    for c in pontos:
        apps = ler_apps(c)
        if not apps:
            print(f"AVISO: {c} sem metrics_by_app.csv; ponto ignorado", file=sys.stderr)
            continue
        if "failure_rate_ic95" not in apps[0]:
            sem_ic95.append(c)
        dados.append({"ponto": c, "rotulo": cfg.ponto(c)["rotulo_curto"],
                      "apps": apps})
    return dados, sem_ic95


def plotar(dados, sem_ic95, saida, nome, titulo, eixo_x):
    apps = sorted({a["app"] for d in dados for a in d["apps"]})
    x = np.arange(len(dados))
    largura = min(0.8 / len(apps), 0.35)

    fig, (ax, axb) = plt.subplots(2, 1, figsize=(max(10, 1.7 * len(dados) + 4), 9),
                                  gridspec_kw={"height_ratios": [1.15, 1]})

    # ---- (a) taxa de falha por app, barras agrupadas -----------------------
    for i, app in enumerate(apps):
        valores, erros = [], []
        for d in dados:
            linha = next((a for a in d["apps"] if a["app"] == app), None)
            valores.append(linha["failure_rate"] if linha else 0.0)
            erros.append(linha.get("failure_rate_ic95", 0.0) if linha else 0.0)
        desloc = (i - (len(apps) - 1) / 2) * largura
        barras = ax.bar(x + desloc, valores, largura * 0.92,
                        yerr=erros if any(erros) else None, capsize=3,
                        color=cfg.cor_da_app(app), label=app.replace("_", " "))
        # Rótulo direto, que distingue falha nula de aplicação ausente.
        for barra, valor in zip(barras, valores):
            ax.annotate("0" if valor == 0 else f"{valor:.1f}",
                        (barra.get_x() + barra.get_width() / 2, valor),
                        textcoords="offset points", xytext=(0, 3), ha="center",
                        fontsize=7.5, color=INK if valor else INK_MUTED)

    ax.set_ylabel("Taxa de falha (%)", fontweight="bold", color=INK)
    nota = ("barras = IC95 da média de 30 runs" if not sem_ic95 else
            "sem IC95: " + ", ".join(sem_ic95) +
            " (métricas agregadas sem a coluna de IC95; reagregar exige as saídas brutas)")
    ax.set_title(f"(a) Onde a falha se concentra  ·  {nota}",
                 fontweight="bold", color=INK, pad=10, fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels([d["rotulo"] for d in dados], fontsize=10)
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(fontsize=9, ncol=min(4, len(apps)))

    # ---- (b) causa da falha, contagem absoluta empilhada -------------------
    base = np.zeros(len(dados))
    houve = False
    for chave, (cor, rotulo) in CORES_CAUSA.items():
        valores = np.array([sum(a.get(chave, 0.0) for a in d["apps"]) for d in dados])
        if not valores.any():
            continue
        houve = True
        axb.bar(x, valores, 0.55, bottom=base, color=cor, label=rotulo)
        base += valores

    for i, total in enumerate(base):
        if total:
            axb.annotate(f"{total:,.0f}".replace(",", "."), (i, total),
                         textcoords="offset points", xytext=(0, 4), ha="center",
                         fontsize=9, fontweight="bold", color=INK)

    axb.set_ylabel("Tarefas perdidas (média por run)", fontweight="bold", color=INK)
    axb.set_xlabel(eixo_x, fontweight="bold", color=INK)
    causas_ausentes = [r for k, (_, r) in CORES_CAUSA.items()
                       if not any(sum(a.get(k, 0.0) for a in d["apps"]) for d in dados)]
    sub = "(b) Por que se perderam"
    if causas_ausentes:
        sub += "  ·  nenhuma perda por " + ", ".join(c.lower() for c in causas_ausentes)
    axb.set_title(sub, fontweight="bold", color=INK, pad=10, fontsize=11)
    axb.set_xticks(x)
    axb.set_xticklabels([d["rotulo"] for d in dados], fontsize=10)
    axb.grid(True, axis="y", alpha=0.3)
    if houve:
        axb.legend(fontsize=9)
    else:
        axb.text(0.5, 0.5, "Nenhuma falha em nenhum cenário desta série",
                 transform=axb.transAxes, ha="center", va="center",
                 fontsize=12, color=INK_MUTED)

    fig.suptitle(titulo, fontweight="bold", color=INK, fontsize=13.5)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    destino = saida / nome
    destino.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destino, dpi=DPI)
    plt.close(fig)
    print(f"✓ Gerado: {destino}")


SERIES = {
    "densidade": {
        "pontos": lambda: cfg.pontos_da_serie("densidade"),
        "nome": "falhas_por_app_densidade.png",
        "eixo": "Servidores de borda com GPU (de 14), com 9 clientes YOLO fixos",
        "titulo": ("Falha por aplicação e por causa — densidade de GPU na borda\n"
                   "as três apps de CPU atravessam a saturação em zero absoluto"),
    },
    "escala": {
        "pontos": lambda: cfg.pontos_da_serie("escala"),
        "nome": "falhas_por_app_escala.png",
        "eixo": "Clientes YOLO sobre 1 GPU (RTX 3050)",
        "titulo": ("Falha e causa — escala de clientes sobre uma GPU\n"
                   "100% das perdas são de VRAM; nenhuma por banda, mesmo com a "
                   "WLAN em contenção"),
    },
}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--serie", choices=sorted(SERIES), default="densidade")
    args = ap.parse_args()

    spec = SERIES[args.serie]
    dados, sem_ic95 = coletar(spec["pontos"]())
    if not dados:
        print("Nenhum ponto com metrics_by_app.csv.", file=sys.stderr)
        return 1
    plotar(dados, sem_ic95, cfg.SERIES[args.serie]["pasta"] / "resultados" / "figuras",
           spec["nome"], spec["titulo"], spec["eixo"])

    print()
    print(f"{'ponto':>16}  {'app':>18}  {'falha %':>10}  {'IC95':>7}  {'VRAM':>12}  {'banda':>7}")
    for d in dados:
        for a in d["apps"]:
            print(f"{d['rotulo']:>16}  {a['app']:>18}  {a['failure_rate']:>9.3f}  "
                  f"{a.get('failure_rate_ic95', float('nan')):>7.3f}  "
                  f"{a.get('failed_vm_capacity', 0):>12,.0f}  "
                  f"{a.get('failed_bw', 0):>7,.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
