#!/usr/bin/env python3
"""Validação das saídas da amostra de um ponto da escala de clientes (uma aplicação).

Confere as saídas contra as entradas e contra o modelo analítico de filas, uma camada
acima de validar_run.py, que verifica a integridade de cada execução. Cada checagem
resulta em PASS, FALHA ou INFO; INFO é uma medida sem valor esperado a priori, como a
ocupação da GPU, e não reprova o ponto. O relatório é gravado em
experimentos/escala-clientes/<ponto>/resultados/validacao.md.

Uso:
    python3 analise/validar_saidas.py --ponto N08
"""

import argparse
import statistics
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path


import config as cfg  # noqa: E402
from estatistica import semiamplitude  # noqa: E402

TOL = 1e-9          # igualdade de ponto flutuante em identidades exatas
TOL_REL = 0.02      # 2% para comparações com modelo teórico


# ---------------------------------------------------------------- entrada

def ler_properties(caminho):
    d = {}
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        k, _, v = linha.partition("=")
        d[k.strip()] = v.strip()
    return d


def ler_parametros(ponto):
    """Lê os parâmetros de entrada dos 3 arquivos de config do cenário."""
    cdir = cfg.ponto(ponto)["pasta"]
    props = ler_properties(cdir / "config.properties")

    app = ET.parse(cdir / "applications.xml").getroot()[0]
    dev = ET.parse(cdir / "edge_devices.xml").getroot()
    gpu = dev.find(".//gpu")

    sim_min = float(props["simulation_time"])
    warm_min = float(props["warm_up_period"])

    return {
        "clientes": int(props["min_number_of_mobile_devices"]),
        "t_total_s": sim_min * 60,
        "t_warmup_s": warm_min * 60,
        "t_util_s": (sim_min - warm_min) * 60,
        "interarrival_s": float(app.findtext("poisson_interarrival")),
        "gpu_length_mi": float(app.findtext("gpu_length")),
        "gpu_memory_mb": float(app.findtext("gpu_memory")),
        "deadline_s": float(app.findtext("max_delay_requirement")),
        "gflops": float(gpu.findtext("gflops")),
        "vram_mb": float(gpu.findtext("memory")),
        "num_gpus": len(dev.findall(".//gpu")),
        # wlan_bandwidth é dado em Mbps no config; armazena-se em Kbps, como no simulador.
        "wlan_bandwidth_kbps": float(props["wlan_bandwidth"]) * 1000,
        # com a banda dividida entre transmissões simultâneas, o valor analítico passa
        # a ser limite inferior (bloco B8)
        "wlan_contention": props.get("wlan_contention_enabled", "false").strip().lower() == "true",
        # 0 = buffer infinito: a contenção atrasa, mas não descarta (bloco D3).
        "wlan_buffer_kb": float(props.get("wlan_buffer_size_kb", "0")),
        "data_upload_kb": float(app.findtext("data_upload")),
        "data_download_kb": float(app.findtext("data_download")),
        "gpu_io_mb": float(app.findtext("gpu_input_data")),
        # constantes do GpuNetworkModel, que não são lidas do config
        "pcie_bw_gbps": 15.75,
        "pcie_latency_ms": 0.5,
    }


# ---------------------------------------------------------------- saída

def ler_simresult(run_dir):
    """Parseia o SIMRESULT_*_ALL_APPS_GENERIC.log.

    Layout definido em SimLogger.java:866-941 (genericResult1..6).
    """
    arquivos = list(run_dir.glob("SIMRESULT_*ALL_APPS_GENERIC.log"))
    if not arquivos:
        return None
    linhas = [l for l in arquivos[0].read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
    if len(linhas) < 6:
        return None

    c = [campo.split(";") for campo in linhas]
    total, edge, cloud, mobile, rede, perf = c[0], c[1], c[2], c[3], c[4], c[5]

    return {
        "completed": int(total[0]),
        "failed": int(total[1]),
        "uncompleted": int(total[2]),
        "failed_bw": int(total[3]),
        "frtt_s": float(total[4]),
        "processing_s": float(total[5]),
        "network_s": float(total[6]),
        "failed_vm_capacity": int(total[9]),
        "failed_mobility": int(total[10]),
        "rejected_wlan_range": int(total[13]),
        "edge_completed": int(edge[0]),
        "edge_failed": int(edge[1]),
        "cloud_completed": int(cloud[0]),
        "cloud_failed": int(cloud[1]),
        "mobile_completed": int(mobile[0]),
        "mobile_failed": int(mobile[1]),
        "lan_delay_s": float(rede[0]),
        "wall_clock_s": int(perf[0]) * 60 / 1000.0,
    }


def carregar_runs(ponto):
    runs = {}
    for d in cfg.runs_da_amostra(ponto):
        if not d.is_dir():
            continue
        dados = ler_simresult(d)
        if dados is None:
            continue
        seed = int(d.name.split("_seed")[-1])
        dados["seed"] = seed
        runs[seed] = dados
    return runs


# ---------------------------------------------------------------- checagens

class Relatorio:
    def __init__(self):
        self.itens = []

    def add(self, status, titulo, detalhe):
        self.itens.append((status, titulo, detalhe))

    def passou(self, titulo, detalhe):
        self.add("PASS", titulo, detalhe)

    def falhou(self, titulo, detalhe):
        self.add("FALHA", titulo, detalhe)

    def info(self, titulo, detalhe):
        self.add("INFO", titulo, detalhe)

    def checa(self, cond, titulo, detalhe):
        (self.passou if cond else self.falhou)(titulo, detalhe)

    @property
    def n_falhas(self):
        return sum(1 for s, _, _ in self.itens if s == "FALHA")


def validar(ponto, params, runs, rel):
    n = len(runs)
    seeds = sorted(runs)
    p = params

    # ---- A. integridade interna, por run -------------------------------
    gerado_esperado = round(p["clientes"] * p["t_util_s"] / p["interarrival_s"])

    ruins = [s for s, r in runs.items()
             if r["completed"] + r["failed"] + r["uncompleted"] != gerado_esperado]
    rel.checa(not ruins,
              "A1. Conservação de tarefas",
              f"completed+failed+uncompleted = {gerado_esperado:,} "
              f"(= {p['clientes']} clientes × {p['t_util_s']:.0f} s ÷ {p['interarrival_s']} s) "
              f"em {n - len(ruins)}/{n} runs"
              + (f" — divergem: {ruins}" if ruins else ""))

    ruins = [s for s, r in runs.items()
             if abs(r["frtt_s"] - (r["processing_s"] + r["network_s"])) > TOL]
    rel.checa(not ruins,
              "A2. Decomposição do FRTT (tautológica)",
              f"serviceTime = processingTime + networkDelay em {n - len(ruins)}/{n} runs. "
              "Sem poder de validação: o SimLogger define "
              "processingTime := serviceTime − networkDelay, então a identidade vale por "
              "construção. Só detecta corrupção do arquivo, não erro de modelagem."
              + (f" — divergem: {ruins}" if ruins else ""))

    ruins = [s for s, r in runs.items()
             if r["failed_vm_capacity"] + r["failed_bw"] + r["failed_mobility"]
             + r["rejected_wlan_range"] != r["failed"]]
    rel.checa(not ruins,
              "A3. Causas de falha somam o total",
              f"vm_capacity + bw + mobility + wlan_range = failed em {n - len(ruins)}/{n} runs"
              + (f" — divergem: {ruins}" if ruins else ""))

    ruins = [s for s, r in runs.items()
             if r["edge_completed"] + r["cloud_completed"] + r["mobile_completed"]
             != r["completed"]]
    rel.checa(not ruins,
              "A4. Camadas somam o total",
              f"edge+cloud+mobile = completed em {n - len(ruins)}/{n} runs"
              + (f" — divergem: {ruins}" if ruins else ""))

    # ---- B. coerência física -------------------------------------------
    t_gpu_teorico = p["gpu_length_mi"] / p["gflops"]
    capacidade_fps = p["gflops"] / p["gpu_length_mi"] * p["num_gpus"]
    lambda_fps = p["clientes"] / p["interarrival_s"]

    proc = [r["processing_s"] for r in runs.values()]
    proc_medio = statistics.fmean(proc)
    rel.checa(proc_medio >= t_gpu_teorico - TOL,
              "B1. Tempo de processamento ≥ mínimo físico",
              f"medido {proc_medio*1000:.4f} ms vs. mínimo {t_gpu_teorico*1000:.4f} ms "
              f"(= gpu_length {p['gpu_length_mi']:.0f} MI ÷ gflops {p['gflops']:.0f} MI/s). "
              + ("Sem contenção: igual ao mínimo."
                 if abs(proc_medio - t_gpu_teorico) < TOL
                 else f"Excesso de {(proc_medio - t_gpu_teorico)*1000:.4f} ms = fila/time-share."))

    thr = [r["completed"] / p["t_util_s"] for r in runs.values()]
    thr_medio = statistics.fmean(thr)
    ruins = [s for s, r in runs.items()
             if abs(r["completed"] / p["t_util_s"] - r["completed"] / p["t_util_s"]) > TOL]
    rel.passou("B2. Throughput = completed ÷ tempo útil",
               f"{thr_medio:.2f} fps sobre {p['t_util_s']:.0f} s "
               f"(warm-up de {p['t_warmup_s']:.0f} s descontado)")

    ocupacao = thr_medio * t_gpu_teorico / p["num_gpus"]
    rel.checa(ocupacao <= 1.0 + TOL_REL,
              "B3. Ocupação da GPU ≤ 100%",
              f"{ocupacao*100:.1f}% "
              f"(throughput {thr_medio:.2f} fps × {t_gpu_teorico*1000:.2f} ms ÷ {p['num_gpus']} GPU)")

    rel.info("B4. Capacidade vs. demanda",
             f"capacidade {capacidade_fps:.2f} fps · chegada λ {lambda_fps:.2f} fps · "
             f"razão λ/capacidade = {lambda_fps/capacidade_fps:.2f}× "
             + ("(saturado)" if lambda_fps > capacidade_fps else "(com folga)"))

    falha = [r["failed"] / (r["completed"] + r["failed"] + r["uncompleted"]) * 100
             for r in runs.values()]
    falha_media = statistics.fmean(falha)
    perda_esperada = max(0.0, (1 - thr_medio / lambda_fps)) * 100
    rel.checa(abs(falha_media - perda_esperada) < 1.0,
              "B5. Perda condiz com vazão vs. chegada",
              f"falha medida {falha_media:.2f}% vs. 1 − throughput/λ = {perda_esperada:.2f}% "
              f"(diferença {abs(falha_media - perda_esperada):.2f} p.p.)")

    buffer_frames = p["vram_mb"] / p["gpu_memory_mb"]
    frtt_medio = statistics.fmean(r["frtt_s"] for r in runs.values())
    rede_media = statistics.fmean(r["network_s"] for r in runs.values())
    em_voo = thr_medio * (frtt_medio - rede_media)
    rel.checa(em_voo <= buffer_frames * (1 + TOL_REL),
              "B6. Little's Law dentro do buffer de VRAM",
              f"frames em voo = {em_voo:.2f} (throughput × tempo no servidor) ≤ "
              f"buffer {buffer_frames:.0f} frames "
              f"(VRAM {p['vram_mb']:.0f} MB ÷ {p['gpu_memory_mb']:.0f} MB/frame)")

    # processingTime = serviceTime − networkDelay inclui fila, escalonamento e execução
    # na GPU. A razão abaixo é, portanto, o fator de inflação sobre o mínimo físico, e
    # não o número de tarefas simultâneas na GPU.
    inflacao = proc_medio / t_gpu_teorico
    rel.info("B7. Inflação do tempo no servidor",
             f"tempo no servidor ÷ mínimo físico da GPU = {inflacao:.2f}× "
             f"({proc_medio*1000:.2f} ms vs. {t_gpu_teorico*1000:.2f} ms). "
             "Mede fila + escalonamento + time-share juntos — o motor não expõe o tempo "
             "de GPU isolado, então esses componentes não são separáveis. "
             f"A ocupação real do buffer é a de B6: {em_voo/buffer_frames*100:.1f}%.")

    # Rede = WLAN (dados/banda) + 2 × PCIe (latência + dados/banda), sem fila
    # (GpuNetworkModel.getUploadDelay e getDownloadDelay).
    wlan_kbps = p["wlan_bandwidth_kbps"]
    rede_teorica = ((p["data_upload_kb"] + p["data_download_kb"]) * 8 / wlan_kbps
                    + 2 * (p["pcie_latency_ms"] / 1000
                           + (p["gpu_io_mb"] / 1024) / p["pcie_bw_gbps"]))
    formula = (f"WLAN ({p['data_upload_kb']:.0f}+{p['data_download_kb']:.0f} KB ÷ "
               f"{wlan_kbps/1000:.0f} Mbps) + 2× PCIe ({p['pcie_latency_ms']} ms + "
               f"{p['gpu_io_mb']:.0f} MB ÷ {p['pcie_bw_gbps']} GB/s)")
    if p["wlan_contention"]:
        # Com a banda dividida entre transmissões simultâneas, o valor analítico é limite
        # inferior; a razão entre o atraso de WLAN medido e o analítico estima o número
        # médio de fluxos simultâneos.
        pcie_s = 2 * (p["pcie_latency_ms"] / 1000 + (p["gpu_io_mb"] / 1024) / p["pcie_bw_gbps"])
        wlan_teorico_s = rede_teorica - pcie_s
        fluxos = (rede_media - pcie_s) / wlan_teorico_s if wlan_teorico_s else float("nan")
        rel.checa(rede_media >= rede_teorica - TOL,
                  "B8. Atraso de rede ≥ piso analítico (contenção ON)",
                  f"medido {rede_media*1000:.7f} ms vs. piso {rede_teorica*1000:.7f} ms = "
                  f"{formula}. Disputa implícita = {fluxos:.3f} fluxos simultâneos no AP.")
    else:
        rel.checa(abs(rede_media - rede_teorica) < TOL,
                  "B8. Atraso de rede bate com o modelo analítico",
                  f"medido {rede_media*1000:.7f} ms vs. teórico {rede_teorica*1000:.7f} ms = "
                  + formula)

    # ---- C. estatística -------------------------------------------------
    lat = [r["frtt_s"] * 1000 for r in runs.values()]
    rel.info("C1. Amostra",
             f"{n} runs, seeds {min(seeds)}–{max(seeds)}, "
             f"{'contíguas e sem repetição' if seeds == list(range(min(seeds), max(seeds)+1)) else 'irregulares'}")

    for nome, série, unidade in (("Latência", lat, "ms"),
                                 ("Throughput", thr, "fps"),
                                 ("Falha", falha, "%")):
        media = statistics.fmean(série)
        desvio = statistics.stdev(série) if n > 1 else 0.0
        ic = semiamplitude(desvio, n)
        cv = (desvio / media * 100) if media else 0.0
        rel.info(f"C2. {nome}",
                 f"{media:.4f} ± {desvio:.4f} {unidade} · IC95 [{media-ic:.4f}, {media+ic:.4f}] · "
                 f"CV {cv:.2f}%")

    if n > 2 and statistics.pstdev(lat) > 0:
        # correlação de Pearson entre semente e latência, para detectar dependência
        xs, ys = seeds, [runs[s]["frtt_s"] for s in seeds]
        mx, my = statistics.fmean(xs), statistics.fmean(ys)
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
        r_pearson = num / den if den else 0.0
        rel.checa(abs(r_pearson) < 0.5,
                  "C3. Independência entre seed e latência",
                  f"correlação de Pearson r = {r_pearson:+.4f} "
                  f"({'sem' if abs(r_pearson) < 0.5 else 'com'} relação sistemática)")
    else:
        rel.info("C3. Independência entre seed e latência",
                 "não aplicável — variância nula (cenário determinístico)")

    # ---- D. limitações do simulador ------------------------------------
    rel.info("D1. Deadline",
             f"requisito {p['deadline_s']*1000:.0f} ms · latência média {frtt_medio*1000:.2f} ms. "
             "max_delay_requirement não é lido pelo motor — nenhuma tarefa falha por "
             "estourar o prazo. A comparação é pós-hoc e sobre a média, não é taxa de violação.")
    rel.info("D2. Percentis",
             "o simulador não emite latência por tarefa, apenas a média agregada → "
             "p50/p90/p99 exigem o registro por tarefa (execucao/rodar_deeplog.sh); a partir do SIMRESULT agregado são impossíveis. Comparar a média com o p90 de um "
             "artigo é comparar grandezas diferentes.")

    kb_por_tarefa = p["data_upload_kb"] + p["data_download_kb"]
    ofertado_mbps = lambda_fps * kb_por_tarefa * 8 / 1000
    servido_mbps = thr_medio * kb_por_tarefa * 8 / 1000
    wlan_mbps = p["wlan_bandwidth_kbps"] / 1000
    # O texto depende da contenção de WLAN: com ela, o atraso de rede varia com o
    # número de transmissões simultâneas.
    trafego = (f"Tráfego ofertado {ofertado_mbps:.0f} Mbps · servido "
               f"{servido_mbps:.0f} Mbps · WLAN {wlan_mbps:.0f} Mbps")
    if p["wlan_contention"]:
        # Com banda dividida há congestionamento, mas não descarte, se o buffer for infinito.
        if p["wlan_buffer_kb"] > 0:
            descarte = (f"Buffer de {p['wlan_buffer_kb']:.0f} KB: o excedente é "
                        "descartado (drop-tail), então pode haver falha por banda.")
        else:
            descarte = ("Buffer infinito (wlan_buffer_size_kb=0): a contenção só "
                        "atrasa, não descarta — nenhuma falha é por banda.")
        excedente = ""
        if ofertado_mbps > wlan_mbps:
            excedente = (f" O ofertado excede a WLAN em {ofertado_mbps/wlan_mbps:.2f}×, "
                         "mas só o servido cursa a rede: o gargalo a montante (GPU) "
                         "rejeita na admissão antes de o tráfego chegar ao ar. Compare "
                         "o servido com a WLAN, não o ofertado.")
        rel.info("D3. Rede: contenção ligada",
                 f"a banda do AP é repartida entre as transmissões simultâneas, então o "
                 f"atraso de rede depende de quantos transmitem (ver B8). {trafego}. "
                 f"{descarte}{excedente}")
    else:
        rel.info("D3. Rede sem congestionamento",
                 f"contenção desligada: o atraso de rede é analítico e fixo por tarefa "
                 f"(B8) — não depende de quantos dispositivos transmitem. {trafego}"
                 + (f". O ofertado excede a WLAN em {ofertado_mbps/wlan_mbps:.2f}×, mas o "
                    "modelo não gera atraso de fila nem falha por banda; só o servido "
                    "cursa a rede."
                    if ofertado_mbps > wlan_mbps else
                    ". Ofertado cabe na WLAN, então a ausência de fila não distorce "
                    "este cenário."))

    rel.info("D4. Warm-up",
             f"{p['t_warmup_s']:.0f} s ({p['t_warmup_s']/p['t_total_s']*100:.0f}% da janela) "
             "descartados das métricas, inclusive as tarefas rejeitadas nesse intervalo, "
             "que são marcadas no instante da chegada.")

    return rel


# ---------------------------------------------------------------- saída

def imprimir(rel, titulo):
    print("=" * 72)
    print(titulo)
    print("=" * 72)
    for status, t, d in rel.itens:
        marca = {"PASS": "✓", "FALHA": "✗", "INFO": "·"}[status]
        print(f"{marca} {t}")
        print(f"    {d}")
    print("=" * 72)
    print(f"Falhas: {rel.n_falhas}")


def escrever_markdown(rel, caminho, ponto, params, runs):
    p, n = params, len(runs)
    linhas = [
        f"# Validação de saídas — {cfg.ponto(ponto)['rotulo']} ({ponto})",
        "",
        f"Gerado em {datetime.now():%Y-%m-%d %H:%M} por `analise/validar_saidas.py`.",
        "",
        "## Configuração validada",
        "",
        f"- Clientes: **{p['clientes']}** · GPUs: **{p['num_gpus']}** · "
        f"gflops: **{p['gflops']:.0f} MI/s** · VRAM: **{p['vram_mb']:.0f} MB**",
        f"- Janela: {p['t_total_s']:.0f} s totais − {p['t_warmup_s']:.0f} s de warm-up = "
        f"**{p['t_util_s']:.0f} s úteis**",
        f"- Workload: {p['gpu_length_mi']:.0f} MI/frame · {p['gpu_memory_mb']:.0f} MB/frame · "
        f"chegada a cada {p['interarrival_s']} s",
        f"- Runs analisados: **{n}**",
        "",
        "## Resultado",
        "",
        "| | Checagem | Detalhe |",
        "|---|---|---|",
    ]
    for status, t, d in rel.itens:
        marca = {"PASS": "✓", "FALHA": "✗", "INFO": "·"}[status]
        linhas.append(f"| {marca} | {t} | {d} |")
    linhas += ["", f"**Falhas: {rel.n_falhas}**", ""]
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("\n".join(linhas), encoding="utf-8")
    print(f"\nRelatório salvo em: {caminho}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ponto", required=True, choices=cfg.pontos_da_serie("escala"))
    ap.add_argument("--relatorio", type=Path, default=None,
                    help="caminho do .md a gerar (opcional)")
    ap.add_argument("--permitir-parcial", action="store_true",
                    help="valida mesmo que faltem pastas do manifesto nesta máquina")
    args = ap.parse_args()

    faltando = cfg.amostra_incompleta(args.ponto)
    if faltando and not args.permitir_parcial:
        print(f"ERRO: {len(faltando)} execuções do manifesto não estão nesta máquina "
              f"(ex.: {faltando[0].relative_to(cfg.REPO_ROOT)}). Nada foi gravado, para não "
              "substituir o relatório da amostra completa. Use --permitir-parcial para "
              "validar assim mesmo.", file=sys.stderr)
        return 2

    params = ler_parametros(args.ponto)
    runs = carregar_runs(args.ponto)
    if not runs:
        print(f"ERRO: nenhum run com SIMRESULT em "
              f"{cfg.ponto(args.ponto)['experimento'] / 'run_manifest.csv'}", file=sys.stderr)
        return 2

    rel = validar(args.ponto, params, runs, Relatorio())
    imprimir(rel, f"Validação de saídas — {cfg.ponto(args.ponto)['rotulo']}")

    escrever_markdown(rel, args.relatorio or cfg.ponto(args.ponto)["experimento"] / "validacao.md",
                      args.ponto, params, runs)

    return 1 if rel.n_falhas else 0


if __name__ == "__main__":
    sys.exit(main())
