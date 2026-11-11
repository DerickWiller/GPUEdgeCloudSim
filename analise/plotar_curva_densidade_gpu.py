#!/usr/bin/env python3
"""Curva de densidade de GPU na borda: K = 1, 2, 3, 7 e 14 servidores com GPU entre 14.

Os cinco pontos diferem apenas em K, o número de servidores de borda com GPU entre 14.
Lê o SIMRESULT do YOLO de cada execução da amostra e plota latência, processamento, rede
e taxa de falha em função de K. Sem as saídas brutas, replota a partir do CSV publicado.

Saída em experimentos/densidade-gpu/resultados/:
    curva_densidade_gpu.csv       tabela agregada (média, desvio, IC95)
    figuras/curva_latencia.png    FRTT, processamento e rede em função de K
    figuras/curva_rede.png        atraso de rede em função de K, em escala linear
    figuras/curva_falha.png       taxa de falha em função de K

Uso:
    python3 analise/plotar_curva_densidade_gpu.py
"""

import csv
import statistics
import sys
import xml.etree.ElementTree as ET

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config as cfg
from estatistica import semiamplitude

APP_GPU = "YOLO_DETECTION"
SAIDA = cfg.SERIES["densidade"]["pasta"] / "resultados"
DPI = 300
# Tempo de inferência: 91 MI / 22 750 MI/s (RTX 3050) = 4 ms
MINIMO_FISICO_MS = 4.0


def parse_generic(arq):
    """Layout de SimLogger.java:866-941; a 1a linha de dados é o total."""
    linhas = [l for l in arq.read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
    if len(linhas) < 5:
        return None
    t = linhas[0].split(";")
    return {
        "completed": int(t[0]),
        "failed": int(t[1]),
        "frtt_ms": float(t[4]) * 1000,
        "processing_ms": float(t[5]) * 1000,
        "network_ms": float(t[6]) * 1000,
        "failed_vm_capacity": int(t[9]),
    }


def carregar(ponto):
    """Execuções da amostra do ponto que trazem o SIMRESULT do YOLO, indexadas por seed."""
    runs = {}
    for d in cfg.runs_da_amostra(ponto):
        arqs = list(d.glob(f"SIMRESULT_*_{APP_GPU}_GENERIC.log"))
        if not arqs:
            continue
        dados = parse_generic(arqs[0])
        if dados:
            runs[int(d.name.split("_seed")[-1])] = dados
    return runs


def num_gpus(ponto):
    """Número de GPUs declaradas no edge_devices.xml, que define K."""
    xml = cfg.ponto(ponto)["pasta"] / "edge_devices.xml"
    return len(ET.parse(xml).getroot().findall(".//gpu"))


def resumo(valores):
    """Média, desvio-padrão amostral e semiamplitude do IC95 (t de n - 1 graus de liberdade)."""
    media = statistics.fmean(valores)
    desvio = statistics.stdev(valores) if len(valores) > 1 else 0.0
    ic = semiamplitude(desvio, len(valores))
    return media, desvio, ic


def coletar():
    linhas = []
    for ponto, k_esperado in sorted(cfg.SERIE_DENSIDADE_GPU.items(), key=lambda x: x[1]):
        runs = carregar(ponto)
        if not runs:
            print(f"AVISO: ponto {ponto} sem execuções — pulado", file=sys.stderr)
            continue
        k = num_gpus(ponto)
        if k != k_esperado:
            print(f"AVISO: {ponto} declara {k} GPUs, mas SERIE_DENSIDADE_GPU indica "
                  f"{k_esperado}; usa-se o XML", file=sys.stderr)
        lista = list(runs.values())
        frtts = [r["frtt_ms"] for r in lista]
        procs = [r["processing_ms"] for r in lista]
        redes = [r["network_ms"] for r in lista]
        frtt = resumo(frtts)
        proc = resumo(procs)
        rede = resumo(redes)
        falha = resumo([100.0 * r["failed"] / max(1, r["completed"] + r["failed"])
                        for r in lista])
        # Fora do platô, a distribuição entre sementes é assimétrica: a maioria das
        # execuções fica no mínimo físico e algumas se afastam dele, conforme a fase
        # relativa dos clientes periódicos. Registra-se mín./máx., pois uma barra de
        # ±desvio cruzaria o mínimo físico.
        linhas.append({
            "ponto": ponto,
            "gpus": k,
            "num_runs": len(lista),
            "frtt_ms": frtt[0], "frtt_std": frtt[1], "frtt_ic95": frtt[2],
            "frtt_min": min(frtts), "frtt_max": max(frtts),
            "processing_ms": proc[0], "processing_std": proc[1],
            "processing_min": min(procs), "processing_max": max(procs),
            "runs_no_minimo": sum(1 for v in procs if v < MINIMO_FISICO_MS + 1e-6),
            "network_ms": rede[0], "network_std": rede[1], "network_ic95": rede[2],
            "network_min": min(redes), "network_max": max(redes),
            "falha_pct": falha[0], "falha_std": falha[1],
            "completed": statistics.fmean(r["completed"] for r in lista),
        })
    return linhas


def salvar_csv(linhas):
    SAIDA.mkdir(parents=True, exist_ok=True)
    destino = SAIDA / "curva_densidade_gpu.csv"
    with open(destino, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)
    print(f"✓ Salvo: {destino}")


def faixa(linhas, chave):
    """Barras assimétricas (média→mín., média→máx.) no formato do errorbar.

    Devolve None quando o CSV não contém mínimo e máximo; nesse caso, só a média é
    desenhada.
    """
    if any(chave + "_min" not in l or chave + "_max" not in l for l in linhas):
        return None
    baixo = [l[chave + "_ms"] - l[chave + "_min"] for l in linhas]
    alto = [l[chave + "_max"] - l[chave + "_ms"] for l in linhas]
    return [baixo, alto]


def plotar_latencia(linhas):
    ks = [l["gpus"] for l in linhas]
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.errorbar(ks, [l["frtt_ms"] for l in linhas], yerr=faixa(linhas, "frtt"),
                marker="o", capsize=4, linewidth=2, label="FRTT (serviço)")
    ax.errorbar(ks, [l["processing_ms"] for l in linhas], yerr=faixa(linhas, "processing"),
                marker="s", capsize=4, linewidth=2, linestyle="--",
                label="Processamento (inferência)")
    # Decomposição FRTT = processamento + rede; sem a rede, a diferença entre as curvas
    # seria atribuída inteiramente à fila da GPU.
    ax.errorbar(ks, [l["network_ms"] for l in linhas], yerr=faixa(linhas, "network"),
                marker="^", capsize=4, linewidth=2, linestyle=":", color="#2a78d6",
                label="Rede (subida + descida + PCIe)")
    ax.axhline(MINIMO_FISICO_MS, color="gray", linestyle=":", linewidth=1.5,
               label=f"Mínimo físico (91 MI ÷ 22750 MI/s = {MINIMO_FISICO_MS:.0f} ms)")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xticks(ks); ax.set_xticklabels([str(k) for k in ks])
    ax.set_xlabel("Servidores de borda com GPU (de 14)")
    ax.set_ylabel("Latência do YOLO (ms, escala log)")
    ax.set_title("Densidade de GPU na borda — latência do YOLO_DETECTION\n"
                 "(30 runs por ponto; barras = faixa min–max entre seeds)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(loc="upper right")
    for l in linhas:
        # abaixo do ponto, para que o rótulo de K = 1 permaneça na área do gráfico
        ax.annotate(f"{l['frtt_ms']:.2f} ms\n({l['runs_no_minimo']}/{l['num_runs']} no mín.)",
                    (l["gpus"], l["frtt_ms"]), textcoords="offset points",
                    xytext=(0, -34), ha="center", fontsize=8.5)
    ax.set_ylim(top=ax.get_ylim()[1] * 1.6)
    fig.tight_layout()
    destino = SAIDA / "figuras" / "curva_latencia.png"
    destino.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destino, dpi=DPI)
    plt.close(fig)
    print(f"✓ Salvo: {destino}")


def plotar_rede(linhas):
    """Atraso de rede vs K, em escala linear a partir de zero.

    A rede varia pouco nesta série (4,6 a 5,0 ms), e a escala logarítmica ocultaria a
    variação.
    """
    ks = [l["gpus"] for l in linhas]
    barras = faixa(linhas, "network")
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.errorbar(ks, [l["network_ms"] for l in linhas], yerr=barras,
                marker="^", capsize=4, linewidth=2, color="#2a78d6",
                label="Rede (subida + descida + PCIe)")
    ax.set_xscale("log")
    ax.set_xticks(ks); ax.set_xticklabels([str(k) for k in ks])
    ax.set_ylim(bottom=0)
    # margem no eixo x para o rótulo do último ponto
    ax.set_xlim(ks[0] * 0.75, ks[-1] * 1.45)
    ax.set_xlabel("Servidores de borda com GPU (de 14)")
    ax.set_ylabel("Atraso de rede do YOLO (ms)")
    # o subtítulo só menciona as barras quando elas são desenhadas
    nota = ("barras = faixa min-max entre seeds" if barras
            else "replotado do CSV agregado — sem faixa entre seeds")
    ax.set_title("Densidade de GPU na borda — atraso de rede do YOLO_DETECTION\n"
                 f"(30 runs por ponto; {nota})")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right")
    for l in linhas:
        pct = 100.0 * l["network_ms"] / l["frtt_ms"]
        ax.annotate(f"{l['network_ms']:.2f} ms\n({pct:.1f}% do FRTT)",
                    (l["gpus"], l["network_ms"]), textcoords="offset points",
                    xytext=(0, 10), ha="center", fontsize=8.5)
    ax.set_ylim(top=ax.get_ylim()[1] * 1.25)
    fig.tight_layout()
    destino = SAIDA / "figuras" / "curva_rede.png"
    destino.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destino, dpi=DPI)
    plt.close(fig)
    print(f"\u2713 Salvo: {destino}")


def plotar_falha(linhas):
    ks = [l["gpus"] for l in linhas]
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.bar([str(k) for k in ks], [l["falha_pct"] for l in linhas],
           yerr=[l["falha_std"] for l in linhas], capsize=4,
           color=[cfg.ponto(l["ponto"])["cor"] for l in linhas])
    ax.set_xlabel("Servidores de borda com GPU (de 14)")
    ax.set_ylabel("Taxa de falha do YOLO (%)")
    ax.set_title("Densidade de GPU na borda — falha do YOLO_DETECTION\n"
                 "(30 runs por ponto; barras = desvio-padrão)")
    ax.grid(True, axis="y", alpha=0.3)
    for i, l in enumerate(linhas):
        ax.annotate(f"{l['falha_pct']:.3f}%", (i, l["falha_pct"]),
                    textcoords="offset points", xytext=(0, 6), ha="center", fontsize=9)
    fig.tight_layout()
    destino = SAIDA / "figuras" / "curva_falha.png"
    destino.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destino, dpi=DPI)
    plt.close(fig)
    print(f"✓ Salvo: {destino}")


def carregar_csv_publicado():
    """Relê curva_densidade_gpu.csv para replotar quando os SIMRESULT não estão disponíveis.

    Não se usa metrics_runs.csv, como na escala de clientes: com carga mista, esse
    arquivo agrega todas as aplicações, e a média difere da do YOLO. O CSV não é
    regravado.
    """
    origem = SAIDA / "curva_densidade_gpu.csv"
    if not origem.exists():
        return []
    with open(origem, newline="", encoding="utf-8") as f:
        linhas = [{k: (v if k == "ponto" else
                       int(v) if k in ("gpus", "num_runs", "runs_no_minimo") else float(v))
                   for k, v in linha.items()}
                  for linha in csv.DictReader(f)]
    return sorted(linhas, key=lambda l: l["gpus"])


def tem_faixa_de_rede(linhas):
    """Indica se o CSV contém network_min e network_max."""
    return all("network_min" in l and "network_max" in l for l in linhas)


def main():
    linhas = coletar()
    incompletos = [p for p in cfg.pontos_da_serie("densidade")
                   if cfg.amostra_incompleta(p)]
    if linhas and incompletos:
        print(f"ERRO: as saídas brutas de {', '.join(incompletos)} estão ausentes ou "
              f"incompletas nesta máquina. Nada foi gravado, para não substituir a curva "
              f"completa por uma parcial.", file=sys.stderr)
        return 1
    do_csv = False
    if not linhas:
        linhas = carregar_csv_publicado()
        do_csv = True
        if linhas:
            print("NOTA: sem SIMRESULT em saidas/; replota-se a partir de "
                  "curva_densidade_gpu.csv, que não é reescrito", file=sys.stderr)
    if not linhas:
        print("Nenhum ponto da série tem execuções nem CSV publicado.", file=sys.stderr)
        return 1
    if not do_csv:
        salvar_csv(linhas)
    if not tem_faixa_de_rede(linhas):
        print("AVISO: o CSV não tem network_min/max; as curvas saem sem a faixa da rede. "
              "Reagregar a partir das saídas brutas para obtê-la.", file=sys.stderr)
    plotar_latencia(linhas)
    plotar_rede(linhas)
    plotar_falha(linhas)
    print()
    print(f"{'K':>3}  {'ponto':>8}  {'runs':>5}  {'FRTT (ms)':>18}  "
          f"{'proc (ms)':>18}  {'falha (%)':>10}")
    for l in linhas:
        print(f"{l['gpus']:>3}  {l['ponto']:>8}  {l['num_runs']:>5}  "
              f"{l['frtt_ms']:>10.3f} ±{l['frtt_std']:<6.3f}  "
              f"{l['processing_ms']:>10.3f} ±{l['processing_std']:<6.3f}  "
              f"{l['falha_pct']:>9.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
