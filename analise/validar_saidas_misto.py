#!/usr/bin/env python3
"""Validação das saídas da amostra de um ponto da densidade de GPU (carga mista).

validar_saidas.py supõe uma única aplicação e servidores homogêneos. Aqui os
dispositivos são distribuídos entre as aplicações conforme usage_percentage, e cada
aplicação é validada com o seu próprio modelo:
  - aplicação com gpu_length > 0: tempo mínimo = gpu_length / gflops   (GPU)
  - aplicação com gpu_length = 0: tempo mínimo = task_length / mips_vm (CPU)

Cada checagem resulta em PASS, FALHA ou INFO; INFO é uma medida sem valor esperado a
priori e não reprova o ponto. O relatório é gravado em
experimentos/densidade-gpu/<ponto>/resultados/validacao.md.

Uso:
    python3 analise/validar_saidas_misto.py --ponto K02
"""

import argparse
import math
import statistics
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path


import config as cfg  # noqa: E402
from estatistica import semiamplitude  # noqa: E402

TOL_REL = 0.02      # 2% para comparações com modelo teórico
TOL_ABS_MS = 0.05   # 0,05 ms de folga absoluta em tempos


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


def _f(el, tag, default=None):
    t = el.findtext(tag)
    if t is None:
        return default
    return float(t)


def ler_parametros(ponto):
    """Lê parâmetros de todas as apps e da topologia de GPU/VM."""
    cdir = cfg.ponto(ponto)["pasta"]
    props = ler_properties(cdir / "config.properties")
    apps_root = ET.parse(cdir / "applications.xml").getroot()
    dev = ET.parse(cdir / "edge_devices.xml").getroot()

    sim_min = float(props["simulation_time"])
    warm_min = float(props["warm_up_period"])
    n_dev = int(props["min_number_of_mobile_devices"])

    # --- topologia ---
    gpus = dev.findall(".//gpu")
    hosts = dev.findall(".//host")
    vms = dev.findall(".//VM")
    vms_gpu = [v for v in vms if (v.get("requiresGpu") or "").lower() == "true"]
    mips_vm = float(vms[0].findtext("mips")) if vms else 0.0

    # --- apps ---
    apps = {}
    # distribuição dos dispositivos na ordem do XML, com arredondamento para cima e
    # limitada ao total (GpuLoadGeneratorModel.initializeModel)
    restante = n_dev
    for el in apps_root.findall("application"):
        nome = el.get("name")
        uso = _f(el, "usage_percentage", 0.0)
        querem = math.ceil(n_dev * uso / 100.0)
        cabem = max(0, min(querem, restante))
        restante -= cabem
        gpu_len = _f(el, "gpu_length", 0.0) or 0.0
        apps[nome] = {
            "usage_pct": uso,
            "clientes": cabem,
            "interarrival_s": _f(el, "poisson_interarrival"),
            "task_length_mi": _f(el, "task_length", 0.0),
            "required_core": _f(el, "required_core", 1.0),
            "gpu_length_mi": gpu_len,
            "gpu_memory_mb": _f(el, "gpu_memory", 0.0) or 0.0,
            "usa_gpu": gpu_len > 0,
            "data_upload_kb": _f(el, "data_upload", 0.0),
            "data_download_kb": _f(el, "data_download", 0.0),
            "gpu_io_mb": _f(el, "gpu_input_data", 0.0) or 0.0,
            "deadline_s": _f(el, "max_delay_requirement"),
        }

    return {
        "clientes_total": n_dev,
        "t_total_s": sim_min * 60,
        "t_warmup_s": warm_min * 60,
        "t_util_s": (sim_min - warm_min) * 60,
        "apps": apps,
        "num_gpus": len(gpus),
        "num_hosts": len(hosts),
        "num_vms": len(vms),
        "num_vms_gpu": len(vms_gpu),
        "gflops": float(gpus[0].findtext("gflops")) if gpus else 0.0,
        "vram_mb": float(gpus[0].findtext("memory")) if gpus else 0.0,
        "mips_vm": mips_vm,
        "wlan_bandwidth_kbps": float(props["wlan_bandwidth"]) * 1000,
        # com a banda dividida entre transmissões simultâneas, o valor analítico passa
        # a ser limite inferior (bloco B8)
        "wlan_contention": props.get("wlan_contention_enabled", "false").strip().lower() == "true",
        # constantes do GpuNetworkModel, que não são lidas do config
        "pcie_bw_gbps": 15.75,
        "pcie_latency_ms": 0.5,
    }


# ---------------------------------------------------------------- saída

def _parse_generic(arq):
    """Formato do SimLogger: usam-se as 4 primeiras linhas de dados (total, borda,
    nuvem e dispositivo), presentes tanto no ALL_APPS quanto nos arquivos por aplicação."""
    linhas = [l for l in arq.read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
    if len(linhas) < 5:
        return None
    c = [campo.split(";") for campo in linhas]
    total, edge, cloud, mobile = c[0], c[1], c[2], c[3]
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
        "cloud_completed": int(cloud[0]),
        "mobile_completed": int(mobile[0]),
    }


def ler_run(run_dir, nomes_apps):
    todos = list(run_dir.glob("SIMRESULT_*ALL_APPS_GENERIC.log"))
    if not todos:
        return None
    dados = _parse_generic(todos[0])
    if dados is None:
        return None
    dados["apps"] = {}
    for nome in nomes_apps:
        arqs = list(run_dir.glob(f"SIMRESULT_*_{nome}_GENERIC.log"))
        if arqs:
            d = _parse_generic(arqs[0])
            if d:
                dados["apps"][nome] = d
    return dados


def carregar_runs(ponto, nomes_apps):
    """Carrega apenas execuções completas, com o ALL_APPS e o GENERIC de todas as
    aplicações, excluindo execuções em andamento ou truncadas."""
    runs, parciais = {}, []
    for d in cfg.runs_da_amostra(ponto):
        if not d.is_dir():
            continue
        dados = ler_run(d, nomes_apps)
        if dados is None or set(dados["apps"]) != set(nomes_apps):
            parciais.append(d.name)
            continue
        runs[int(d.name.split("_seed")[-1])] = dados
    if parciais:
        print(f"AVISO: {len(parciais)} run(s) incompleto(s) ignorado(s): "
              f"{', '.join(parciais[:5])}{' ...' if len(parciais) > 5 else ''}",
              file=sys.stderr)
    return runs


# ---------------------------------------------------------------- relatório

class Relatorio:
    def __init__(self):
        self.itens = []

    def add(self, s, t, d):
        self.itens.append((s, t, d))

    def passou(self, t, d):
        self.add("PASS", t, d)

    def falhou(self, t, d):
        self.add("FALHA", t, d)

    def info(self, t, d):
        self.add("INFO", t, d)

    def checa(self, cond, t, d):
        (self.passou if cond else self.falhou)(t, d)

    @property
    def n_falhas(self):
        return sum(1 for s, _, _ in self.itens if s == "FALHA")


def media(runs, f):
    return statistics.fmean(f(r) for r in runs)


def validar(ponto, p, runs, rel):
    seeds = sorted(runs)
    lista = [runs[s] for s in seeds]
    apps = p["apps"]

    # ---------------- A. conservação ----------------
    ger_esperado = 0
    for nome, a in apps.items():
        if a["clientes"] and a["interarrival_s"]:
            ger_esperado += a["clientes"] * p["t_util_s"] / a["interarrival_s"]

    obs = media(lista, lambda r: r["completed"] + r["failed"] + r["uncompleted"])
    rel.checa(
        abs(obs - ger_esperado) / ger_esperado < 0.01,
        "A1 — conservação de tarefas (todas as apps)",
        f"esperado ≈ {ger_esperado:,.0f} | observado {obs:,.1f} "
        f"(completed+failed+uncompleted) | erro {abs(obs-ger_esperado)/ger_esperado*100:.3f}%",
    )

    somas_ok = all(
        r["failed"] == r["failed_bw"] + r["failed_vm_capacity"]
        + r["failed_mobility"] + r["rejected_wlan_range"]
        for r in lista
    )
    rel.checa(somas_ok, "A3 — toda falha tem causa atribuída",
              f"falhas médias {media(lista, lambda r: r['failed']):,.1f}; "
              "bw + vm_capacity + mobility + wlan_range fecha em todos os runs")

    camadas_ok = all(
        r["edge_completed"] + r["cloud_completed"] + r["mobile_completed"] == r["completed"]
        for r in lista
    )
    rel.checa(camadas_ok, "A4 — edge + cloud + mobile = completed",
              f"edge {media(lista, lambda r: r['edge_completed']):,.0f} | "
              f"cloud {media(lista, lambda r: r['cloud_completed']):,.0f} | "
              f"mobile {media(lista, lambda r: r['mobile_completed']):,.0f}")

    # ---------------- A2 por app: tarefas geradas ----------------
    for nome, a in apps.items():
        if not a["clientes"] or nome not in lista[0]["apps"]:
            continue
        esp = a["clientes"] * p["t_util_s"] / a["interarrival_s"]
        got = media(lista, lambda r, n=nome: r["apps"][n]["completed"]
                    + r["apps"][n]["failed"] + r["apps"][n]["uncompleted"])
        # aplicações com períodos de atividade e inatividade geram menos tarefas que o
        # limite contínuo; apenas o YOLO, periódico e contínuo, deve atingi-lo.
        if a["usa_gpu"]:
            rel.checa(abs(got - esp) / esp < 0.01,
                      f"A2[{nome}] — tarefas geradas (stream contínuo)",
                      f"{a['clientes']} clientes × {p['t_util_s']:.0f}s ÷ "
                      f"{a['interarrival_s']}s = {esp:,.0f} | observado {got:,.1f}")
        else:
            rel.info(f"A2[{nome}] — tarefas geradas",
                     f"observado {got:,.1f} (teto contínuo seria {esp:,.0f}; "
                     "a app tem active/idle period, então gerar menos é esperado)")

    # ---------------- B1 por app: mínimo físico ----------------
    # Para aplicações de CPU, a folga corresponde à granularidade do CloudSim:
    # ResCloudlet.getRemainingCloudletLength() trunca o restante em MI inteiros, e a
    # tarefa é concluída até 1 MI antes do total, o que dá folga de até 1 MI / MIPS.
    # O tempo na GPU é calculado diretamente (gpu_length / capacidade), e a exigência
    # é estrita.
    for nome, a in apps.items():
        if nome not in lista[0]["apps"] or not a["clientes"]:
            continue
        proc_ms = media(lista, lambda r, n=nome: r["apps"][n]["processing_s"]) * 1000
        if a["usa_gpu"]:
            minimo_ms = a["gpu_length_mi"] / p["gflops"] * 1000
            fonte = f"gpu_length {a['gpu_length_mi']:.0f} MI ÷ gflops {p['gflops']:.0f} MI/s"
            folga_ms = 1e-9  # sem granularidade de MI neste caminho
            origem_folga = "exigência estrita (caminho da GPU não trunca MI)"
        else:
            mips_efetivo = p["mips_vm"] * a["required_core"]
            minimo_ms = a["task_length_mi"] / mips_efetivo * 1000
            fonte = (f"task_length {a['task_length_mi']:.0f} MI ÷ "
                     f"({p['mips_vm']:.0f} MIPS × {a['required_core']:.0f} core)")
            folga_ms = 1.0 / mips_efetivo * 1000
            origem_folga = f"1 MI ÷ {mips_efetivo:.0f} MIPS = granularidade do CloudSim"
        deficit_ms = minimo_ms - proc_ms
        rel.checa(proc_ms >= minimo_ms - folga_ms,
                  f"B1[{nome}] — processamento ≥ mínimo físico",
                  f"mínimo {minimo_ms:.4f} ms ({fonte}) | medido {proc_ms:.4f} ms "
                  f"| déficit {deficit_ms:+.6f} ms de uma folga de {folga_ms:.4f} ms "
                  f"({origem_folga})")

    # ---------------- B2: throughput ----------------
    tput = media(lista, lambda r: r["completed"]) / p["t_util_s"]
    rel.info("B2 — throughput agregado",
             f"{tput:,.2f} tarefas/s = {media(lista, lambda r: r['completed']):,.0f} "
             f"completadas ÷ {p['t_util_s']:.0f}s úteis")

    # ---------------- B3: ocupação da GPU ----------------
    nome_gpu = next((n for n, a in apps.items() if a["usa_gpu"]), None)
    if nome_gpu and p["num_gpus"]:
        comp = media(lista, lambda r: r["apps"][nome_gpu]["completed"])
        fps = comp / p["t_util_s"]
        cap = p["num_gpus"] * p["gflops"] / apps[nome_gpu]["gpu_length_mi"]
        rel.checa(fps <= cap * (1 + TOL_REL),
                  f"B3 — ocupação da GPU ({nome_gpu})",
                  f"servido {fps:,.2f} fps de capacidade {cap:,.2f} fps "
                  f"({p['num_gpus']} GPUs) = {fps/cap*100:.1f}% de ocupação")

        lam = apps[nome_gpu]["clientes"] / apps[nome_gpu]["interarrival_s"]
        rel.info("B4 — demanda vs capacidade (app GPU)",
                 f"λ = {lam:,.2f} fps ({apps[nome_gpu]['clientes']} clientes ÷ "
                 f"{apps[nome_gpu]['interarrival_s']}s) | capacidade {cap:,.2f} fps "
                 f"| folga {cap/lam:.2f}×")

        falha_prev = max(0.0, 1 - fps / lam)
        falha_med = media(lista, lambda r: r["apps"][nome_gpu]["failed"]) / max(
            1e-9, media(lista, lambda r: r["apps"][nome_gpu]["completed"]
                        + r["apps"][nome_gpu]["failed"]))
        rel.checa(abs(falha_prev - falha_med) < 0.01,
                  f"B5 — conservação de fluxo ({nome_gpu})",
                  f"1 − throughput/λ = {falha_prev*100:.3f}% | falha medida "
                  f"{falha_med*100:.3f}% | Δ {abs(falha_prev-falha_med)*100:.3f} p.p.")

    # ---------------- B8 por app: rede analítica ----------------
    # O valor analítico supõe o enlace inteiro para cada transmissão. Com contenção,
    # o atraso medido deve ser maior ou igual a ele, e a razão entre o atraso de WLAN
    # medido e o analítico estima o número médio de fluxos simultâneos.
    for nome, a in apps.items():
        if nome not in lista[0]["apps"] or not a["clientes"]:
            continue
        wlan_ms = (a["data_upload_kb"] + a["data_download_kb"]) * 8 / p["wlan_bandwidth_kbps"] * 1000
        pcie_ms = 0.0
        if a["usa_gpu"]:
            pcie_ms = 2 * (p["pcie_latency_ms"] + (a["gpu_io_mb"] / 1024) / p["pcie_bw_gbps"] * 1000)
        esperado = wlan_ms + pcie_ms
        medido = media(lista, lambda r, n=nome: r["apps"][n]["network_s"]) * 1000
        folga = max(TOL_ABS_MS, esperado * 1e-6)
        if p["wlan_contention"]:
            fluxos = (medido - pcie_ms) / wlan_ms if wlan_ms else float("nan")
            rel.checa(medido >= esperado - folga,
                      f"B8[{nome}] — atraso de rede ≥ piso analítico (contenção ON)",
                      f"piso WLAN {wlan_ms:.6f} + PCIe {pcie_ms:.6f} = {esperado:.6f} ms "
                      f"| medido {medido:.6f} ms | disputa implícita = "
                      f"{fluxos:.3f} fluxos simultâneos no AP")
        else:
            rel.checa(abs(medido - esperado) <= folga,
                      f"B8[{nome}] — atraso de rede = modelo analítico",
                      f"WLAN {wlan_ms:.6f} ms + PCIe {pcie_ms:.6f} ms = {esperado:.6f} ms "
                      f"| medido {medido:.6f} ms")

    # ---------------- C. estatística ----------------
    contig = seeds == list(range(min(seeds), min(seeds) + len(seeds)))
    rel.checa(len(seeds) == len(set(seeds)) and contig,
              "C1 — amostra",
              f"n = {len(seeds)} runs, seeds {min(seeds)}..{max(seeds)}, "
              f"{'contíguas e sem repetição' if contig else 'com lacuna'}")

    def stat(vals, rot, unid):
        m = statistics.fmean(vals)
        s = statistics.stdev(vals) if len(vals) > 1 else 0.0
        ic = semiamplitude(s, len(vals))
        cv = (s / m * 100) if m else 0.0
        rel.info(f"C2 — {rot}",
                 f"{m:.4f} ± {s:.4f} {unid} | IC95% [{m-ic:.4f}, {m+ic:.4f}] | CV {cv:.2f}%")

    stat([r["frtt_s"] * 1000 for r in lista], "latência agregada", "ms")
    stat([r["completed"] / p["t_util_s"] for r in lista], "throughput", "tarefas/s")
    for nome in apps:
        if nome in lista[0]["apps"]:
            stat([r["apps"][nome]["frtt_s"] * 1000 for r in lista], f"latência [{nome}]", "ms")

    if len(seeds) > 2:
        xs, ys = seeds, [runs[s]["frtt_s"] for s in seeds]
        mx, my = statistics.fmean(xs), statistics.fmean(ys)
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
        r = num / den if den else 0.0
        rel.checa(abs(r) < 0.5, "C3 — independência (seed × latência)",
                  f"Pearson r = {r:+.4f} (|r| < 0,5 ⇒ sem deriva sistemática)")

    # ---------------- D. limitações ----------------
    rel.info("D1 — deadline não é lido pelo motor",
             "max_delay_requirement não entra na simulação: nenhuma tarefa falha por "
             "estourar prazo. 'Atende o deadline' é comparação pós-hoc sobre a média.")
    rel.info("D2 — percentis exigem deep log",
             "o SIMRESULT agregado só traz a média por aplicação. Percentis exigem o "
             "registro por tarefa (execucao/rodar_deeplog.sh e "
             "analise/plotar_distribuicao_latencia.py).")
    rel.info("D3 — contenção de WLAN (ligada nesta bateria)",
             "Com wlan_contention_enabled=true, a banda do ponto de acesso é repartida "
             "entre as transmissões simultâneas nele; o atraso de rede passa a depender "
             "do número de dispositivos que transmitem ao mesmo tempo.")
    rel.info("D4 — heterogeneidade é intra-host",
             f"{p['num_hosts']} hosts, {p['num_gpus']} GPUs, {p['num_vms']} VMs "
             f"({p['num_vms_gpu']} com GPU). A app GPU só pode usar as VMs com GPU; "
             "as apps CPU usam qualquer VM.")
    return rel


# ---------------------------------------------------------------- saída

def imprimir(rel, titulo):
    print("=" * 78)
    print(titulo)
    print("=" * 78)
    simbolo = {"PASS": "✓", "FALHA": "✗", "INFO": "·"}
    for s, t, d in rel.itens:
        print(f"{simbolo[s]} [{s:5s}] {t}")
        print(f"          {d}")
    print("=" * 78)
    n = rel.n_falhas
    print(f"{'Todas as checagens passaram' if n == 0 else f'{n} checagem(ns) reprovada(s)'}"
          f" — {len(rel.itens)} itens")
    print("=" * 78)


def escrever_markdown(rel, caminho, ponto, p, runs):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    L = [
        f"# Validação de saídas — {cfg.ponto(ponto)['rotulo']} ({ponto})",
        "",
        f"Gerado em {datetime.now():%Y-%m-%d %H:%M} · {len(runs)} runs · "
        f"{rel.n_falhas} falha(s)",
        "",
        "## Topologia",
        "",
        f"- {p['num_hosts']} hosts, {p['num_gpus']} GPUs, {p['num_vms']} VMs "
        f"({p['num_vms_gpu']} com GPU)",
        f"- {p['clientes_total']} dispositivos, {p['t_util_s']:.0f}s úteis "
        f"(de {p['t_total_s']:.0f}s, warm-up {p['t_warmup_s']:.0f}s)",
        "",
        "| App | usa GPU | clientes | interarrival |",
        "|---|---|---|---|",
    ]
    for n, a in p["apps"].items():
        L.append(f"| {n} | {'sim' if a['usa_gpu'] else 'não'} | {a['clientes']} | "
                 f"{a['interarrival_s']}s |")
    L += ["", "## Checagens", "", "| | Status | Detalhe |", "|---|---|---|"]
    for s, t, d in rel.itens:
        L.append(f"| {t} | {s} | {d} |")
    caminho.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"Relatório: {caminho}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ponto", required=True, choices=cfg.pontos_da_serie("densidade"),
                    help="ponto da densidade de GPU a validar")
    ap.add_argument("--relatorio", type=Path, default=None,
                    help="caminho do .md (padrão: resultados/validacao.md do ponto)")
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

    p = ler_parametros(args.ponto)
    runs = carregar_runs(args.ponto, list(p["apps"]))
    if not runs:
        print(f"Nenhum run encontrado em {cfg.ponto(args.ponto)['experimento'] / 'run_manifest.csv'}",
              file=sys.stderr)
        return 2

    rel = validar(args.ponto, p, runs, Relatorio())
    imprimir(rel, f"Validação de saídas — {cfg.ponto(args.ponto)['rotulo']} "
                  f"({len(runs)} runs)")
    escrever_markdown(rel, args.relatorio or cfg.ponto(args.ponto)["experimento"] / "validacao.md",
                      args.ponto, p, runs)
    return 1 if rel.n_falhas else 0


if __name__ == "__main__":
    sys.exit(main())
