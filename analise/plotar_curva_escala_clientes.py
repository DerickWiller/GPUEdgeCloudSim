#!/usr/bin/env python3
"""Curva de escala de clientes numa GPU: N = 1, 4, 6, 8, 9, 10, 12 e 14.

A infraestrutura é a mesma em todos os pontos (uma GPU RTX 3050, YOLO com chegada
periódica a 30 fps); a variável é N, o número de clientes. As linhas verticais marcam
os limites analíticos de saturação:

    GPU:  N = 250 fps / 30,3 fps por cliente      = 8,25
    WLAN: N = 480 Mbps / 48,24 Mbps por cliente   = 9,95

O limite da WLAN refere-se ao tráfego ofertado. Como a GPU satura antes e rejeita
quadros na admissão, o tráfego servido permanece abaixo da capacidade da WLAN e
nenhuma falha decorre de banda; a contenção acrescenta atraso sem causar perda.

Ressalva de interpretação: a memória de vídeo livre diminui com N, e com ela a fila
da GPU (de 286 para 16 quadros). Carga e tamanho da fila variam juntos, e o CSV inclui
fila_frames para que os dois efeitos não sejam confundidos.

Saída em experimentos/escala-clientes/resultados/:
    curva_escala_clientes.csv     tabela agregada (média, desvio, IC95, fila)
    figuras/curva_latencia.png    FRTT, processamento e rede em função de N, com os joelhos
    figuras/curva_rede.png        atraso de rede em função de N, em escala linear
    figuras/curva_falha.png       taxa de falha em função de N

Os pontos sem saídas brutas nesta máquina são lidos do metrics_runs.csv do ponto, e a
coluna origem do CSV registra a fonte de cada um.

Uso:
    python3 analise/plotar_curva_escala_clientes.py
"""

import csv
import math
import statistics
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config as cfg
# Leitores compartilhados com a densidade de GPU (mesmo formato de SIMRESULT).
from plotar_curva_densidade_gpu import parse_generic, resumo, MINIMO_FISICO_MS

SAIDA = cfg.SERIES["escala"]["pasta"] / "resultados"
FIGURAS = SAIDA / "figuras"
DPI = 300
APP_GPU = "YOLO_DETECTION"

# Parâmetros da RTX 3050 e da carga (Rodrigues et al., 2026; ver experimentos/gerar_configs.py)
CAP_FPS = 22750 / 91            # 250,0 fps
FPS_CLIENTE = 1 / 0.033         # 30,303 fps
MBPS_CLIENTE = (94 + 105) * FPS_CLIENTE * 8 / 1000   # (subida + descida, KB) → 48,24 Mbps
WLAN_MBPS = 480
MEM_POR_FRAME = 20              # memória de vídeo por quadro em processamento, MB

N_SAT_GPU = CAP_FPS / FPS_CLIENTE       # 8,25
N_SAT_WLAN = WLAN_MBPS / MBPS_CLIENTE   # 9,95


def carregar(ponto):
    """Execuções da amostra do ponto que trazem o SIMRESULT do YOLO, indexadas por seed."""
    runs = {}
    for d in cfg.runs_da_amostra(ponto):
        arqs = list(d.glob(f"SIMRESULT_*_{APP_GPU}_GENERIC.log")) if d.is_dir() else []
        if not arqs:
            continue
        dados = parse_generic(arqs[0])
        if dados:
            runs[int(d.name.split("_seed")[-1])] = dados
    return runs


def carregar_do_agregado(ponto):
    """Reconstrói as execuções a partir do metrics_runs.csv do ponto.

    Usado quando as saídas brutas não estão disponíveis (saidas/ não é versionada).
    O arquivo agregado contém, por execução, as grandezas usadas na curva.
    """
    csv_path = cfg.ponto(ponto)["experimento"] / "metrics_runs.csv"
    if not csv_path.exists():
        return {}
    runs = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            runs[int(linha["seed"])] = {
                "completed": int(linha["completed_tasks"]),
                "failed": int(linha["failed_tasks"]),
                "frtt_ms": float(linha["latency_mean_ms"]),
                "processing_ms": float(linha["processing_ms"]),
                "network_ms": float(linha["network_ms"]),
                "failed_vm_capacity": int(linha["failed_tasks"]),
            }
    return runs


def clientes_declarados(ponto):
    """N, lido do config.properties do ponto."""
    cfg_file = cfg.ponto(ponto)["pasta"] / "config.properties"
    for linha in cfg_file.read_text(encoding="utf-8").splitlines():
        if linha.startswith("min_number_of_mobile_devices="):
            return int(linha.split("=", 1)[1])
    raise ValueError(f"min_number_of_mobile_devices ausente em {cfg_file}")


def vram_livre(ponto):
    """Memória de vídeo livre declarada no edge_devices.xml, em MB."""
    xml = cfg.ponto(ponto)["pasta"] / "edge_devices.xml"
    return int(ET.parse(xml).getroot().find(".//gpu/memory").text)


def coletar():
    linhas = []
    for ponto, n_esperado in sorted(cfg.SERIE_ESCALA_CLIENTES.items(),
                                    key=lambda x: x[1]):
        # Amostra incompleta nesta máquina: usa-se o agregado, que cobre as 30 execuções.
        runs = {} if cfg.amostra_incompleta(ponto) else carregar(ponto)
        origem = "SIMRESULT"
        if not runs:
            runs = carregar_do_agregado(ponto)
            origem = "metrics_runs.csv"
        if not runs:
            print(f"AVISO: {ponto} sem saídas brutas e sem agregado; ponto omitido",
                  file=sys.stderr)
            continue
        if origem != "SIMRESULT":
            print(f"NOTA: {ponto} lido de {origem} (saídas brutas ausentes nesta máquina)",
                  file=sys.stderr)
        n = clientes_declarados(ponto)
        if n != n_esperado:
            print(f"AVISO: {ponto} declara {n} clientes, mas SERIE_ESCALA_CLIENTES "
                  f"indica {n_esperado}; usa-se o config.properties", file=sys.stderr)
        vram = vram_livre(ponto)
        lista = list(runs.values())
        frtts = [r["frtt_ms"] for r in lista]
        procs = [r["processing_ms"] for r in lista]
        redes = [r["network_ms"] for r in lista]
        frtt, proc = resumo(frtts), resumo(procs)
        rede = resumo(redes)
        falha = resumo([100.0 * r["failed"] / max(1, r["completed"] + r["failed"])
                        for r in lista])
        linhas.append({
            "ponto": ponto,
            "clientes": n,
            "num_runs": len(lista),
            "origem": origem,
            "vram_livre_mb": vram,
            "fila_frames": vram // MEM_POR_FRAME,
            "demanda_fps": n * FPS_CLIENTE,
            "razao_gpu": n * FPS_CLIENTE / CAP_FPS,
            "razao_wlan": n * MBPS_CLIENTE / WLAN_MBPS,
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
    destino = SAIDA / "curva_escala_clientes.csv"
    with open(destino, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)
    print(f"✓ Salvo: {destino}")


def faixa(linhas, chave):
    """Barras assimétricas (média→mín., média→máx.); None se faltarem mín. e máx.

    A distribuição entre sementes é assimétrica, e uma barra de ±desvio cruzaria o
    mínimo físico.
    """
    if any(chave + "_min" not in l or chave + "_max" not in l for l in linhas):
        return None
    baixo = [l[chave + "_ms"] - l[chave + "_min"] for l in linhas]
    alto = [l[chave + "_max"] - l[chave + "_ms"] for l in linhas]
    return [baixo, alto]


def marcar_joelhos(ax):
    ax.axvline(N_SAT_GPU, color="#c0392b", linestyle="-.", linewidth=1.5, alpha=0.8,
               label=f"GPU satura (N = {N_SAT_GPU:.2f})")
    # Limite do tráfego ofertado; o tráfego servido é limitado antes, pela GPU.
    ax.axvline(N_SAT_WLAN, color="#2a78d6", linestyle="-.", linewidth=1.5, alpha=0.8,
               label=f"WLAN saturaria (demanda ofertada, N = {N_SAT_WLAN:.2f})")


def plotar_latencia(linhas):
    ns = [l["clientes"] for l in linhas]
    fig, ax = plt.subplots(figsize=(9.5, 6))
    ax.errorbar(ns, [l["frtt_ms"] for l in linhas], yerr=faixa(linhas, "frtt"),
                marker="o", capsize=4, linewidth=2, label="FRTT (serviço)")
    ax.errorbar(ns, [l["processing_ms"] for l in linhas], yerr=faixa(linhas, "processing"),
                marker="s", capsize=4, linewidth=2, linestyle="--",
                label="Processamento (inferência)")
    # Decomposição FRTT = processamento + rede; nesta série a rede cresce 13 vezes.
    ax.errorbar(ns, [l["network_ms"] for l in linhas], yerr=faixa(linhas, "network"),
                marker="^", capsize=4, linewidth=2, linestyle=":", color="#2a78d6",
                label="Rede (subida + descida + PCIe)")
    ax.axhline(MINIMO_FISICO_MS, color="gray", linestyle=":", linewidth=1.5,
               label=f"Mínimo físico (91 MI ÷ 22750 MI/s = {MINIMO_FISICO_MS:.0f} ms)")
    marcar_joelhos(ax)
    ax.set_yscale("log")
    ax.set_xticks(ns)
    ax.set_xlabel("Clientes YOLO sobre 1 GPU (RTX 3050)")
    ax.set_ylabel("Latência do YOLO (ms, escala log)")
    ax.set_title("Escala de clientes — latência do YOLO_DETECTION\n"
                 "(30 runs por ponto; barras = faixa min–max entre seeds)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    destino = FIGURAS / "curva_latencia.png"
    destino.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destino, dpi=DPI)
    plt.close(fig)
    print(f"✓ Salvo: {destino}")


def plotar_rede(linhas):
    """Atraso de rede vs N, em escala linear a partir de zero, com os limites analíticos.

    A linha da WLAN indica onde o tráfego ofertado igualaria a banda, e não um ponto de
    falha da rede: a GPU satura antes e limita o tráfego servido.
    """
    ns = [l["clientes"] for l in linhas]
    barras = faixa(linhas, "network")
    fig, ax = plt.subplots(figsize=(9.5, 6))
    ax.errorbar(ns, [l["network_ms"] for l in linhas], yerr=barras,
                marker="^", capsize=4, linewidth=2, color="#2a78d6",
                label="Rede (subida + descida + PCIe)")
    marcar_joelhos(ax)
    ax.set_xticks(ns)
    ax.set_ylim(bottom=0)
    # margem no eixo x para o rótulo do último ponto
    ax.set_xlim(ns[0] - 0.8, ns[-1] + 1.2)
    ax.set_xlabel("Clientes YOLO sobre 1 GPU (RTX 3050)")
    ax.set_ylabel("Atraso de rede do YOLO (ms)")
    nota = ("barras = faixa min-max entre seeds" if barras
            else "replotado do CSV agregado — sem faixa entre seeds")
    ax.set_title("Escala de clientes — atraso de rede do YOLO_DETECTION\n"
                 f"(30 runs por ponto; {nota})")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", fontsize=9)
    for l in linhas:
        pct = 100.0 * l["network_ms"] / l["frtt_ms"]
        ax.annotate(f"{l['network_ms']:.1f} ms\n({pct:.0f}% do FRTT)",
                    (l["clientes"], l["network_ms"]), textcoords="offset points",
                    xytext=(0, 10), ha="center", fontsize=8)
    ax.set_ylim(top=ax.get_ylim()[1] * 1.2)
    fig.tight_layout()
    destino = FIGURAS / "curva_rede.png"
    destino.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destino, dpi=DPI)
    plt.close(fig)
    print(f"\u2713 Salvo: {destino}")


def plotar_falha(linhas):
    ns = [l["clientes"] for l in linhas]
    fig, ax = plt.subplots(figsize=(9.5, 6))
    ax.plot(ns, [l["falha_pct"] for l in linhas], marker="o", linewidth=2,
            color="#c0392b", label="Falha medida")
    ax.errorbar(ns, [l["falha_pct"] for l in linhas],
                yerr=[l["falha_std"] for l in linhas], fmt="none", capsize=4,
                ecolor="#c0392b", alpha=0.6)
    marcar_joelhos(ax)
    ax.set_xticks(ns)
    ax.set_xlabel("Clientes YOLO sobre 1 GPU (RTX 3050)")
    ax.set_ylabel("Taxa de falha do YOLO (%)")
    ax.set_title("Escala de clientes — falha do YOLO_DETECTION\n"
                 "(30 runs por ponto; barras = desvio-padrão)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", fontsize=9)
    for l in linhas:
        ax.annotate(f"{l['falha_pct']:.2f}%", (l["clientes"], l["falha_pct"]),
                    textcoords="offset points", xytext=(0, 8), ha="center", fontsize=8.5)
    fig.tight_layout()
    destino = FIGURAS / "curva_falha.png"
    destino.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destino, dpi=DPI)
    plt.close(fig)
    print(f"✓ Salvo: {destino}")


def main():
    linhas = coletar()
    if not linhas:
        print("Nenhum ponto da série tem execuções.", file=sys.stderr)
        return 1
    salvar_csv(linhas)
    plotar_latencia(linhas)
    plotar_rede(linhas)
    plotar_falha(linhas)
    print()
    print(f"{'N':>3}  {'ponto':>8}  {'runs':>5}  {'fila':>5}  {'GPU':>6}  {'WLAN':>6}  "
          f"{'FRTT (ms)':>18}  {'falha (%)':>10}")
    for l in linhas:
        print(f"{l['clientes']:>3}  {l['ponto']:>8}  {l['num_runs']:>5}  "
              f"{l['fila_frames']:>5}  {l['razao_gpu']:>5.2f}x  {l['razao_wlan']:>5.2f}x  "
              f"{l['frtt_ms']:>10.3f} ±{l['frtt_std']:<6.3f}  {l['falha_pct']:>9.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
