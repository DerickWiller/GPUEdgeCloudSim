#!/usr/bin/env python3
"""Agrega as métricas das execuções validadas de um ponto.

Lê o manifesto do ponto (apenas execuções com status OK), extrai as métricas de cada
execução e grava, em experimentos/<experimento>/<ponto>/resultados/:

    metrics_runs.csv      uma linha por execução;
    metrics_by_app.csv    média, desvio padrão e IC95 por aplicação;
    metrics_summary.csv   média, desvio padrão e IC95 do ponto.

Uso:
    python3 analise/agregar_metricas.py --ponto K02
"""

import argparse
import csv
import os
import re
import statistics
import sys
from math import sqrt
from pathlib import Path
from typing import Dict, List, Optional

import config

def read_deadline_ms(pasta: Path) -> Optional[float]:
    """Menor max_delay_requirement do applications.xml do cenário, em ms.

    O motor não aplica o prazo; a comparação é feita aqui, entre a latência média
    agregada e o requisito. É um indicador agregado, e não a fração de tarefas que
    violam o prazo, que exigiria a distribuição por tarefa.
    """
    xml = pasta / "applications.xml"
    if not xml.exists():
        return None
    try:
        valores = [float(v) for v in
                   re.findall(r"<max_delay_requirement>\s*([\d.]+)\s*</max_delay_requirement>",
                              xml.read_text(encoding="utf-8"))]
        return min(valores) * 1000 if valores else None  # segundos → ms
    except Exception:
        return None


def read_sim_params(pasta: Path) -> tuple:
    """(simulation_time, warm_up_period) do config.properties do ponto, em minutos.

    Devolve (None, None) se o arquivo não existir.
    """
    cfg_file = pasta / "config.properties"
    if not cfg_file.exists():
        return (None, None)
    sim_t = warm = None
    try:
        for line in cfg_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("simulation_time="):
                sim_t = float(line.split("=")[1].split("#")[0].strip())
            elif line.startswith("warm_up_period="):
                warm = float(line.split("=")[1].split("#")[0].strip())
    except Exception:
        pass
    return (sim_t, warm)


def read_app_gpu_map(pasta: Path) -> Dict[str, bool]:
    """Mapeia nome_da_app -> usa_gpu (gpu_length > 0) a partir do applications.xml.

    Distingue, nos gráficos por aplicação, as aplicações de GPU das de CPU.
    """
    xml = pasta / "applications.xml"
    result: Dict[str, bool] = {}
    if not xml.exists():
        return result
    try:
        text = xml.read_text(encoding="utf-8")
        # Cada bloco <application name="X"> ... </application>
        for m in re.finditer(r'<application\s+name="([^"]+)".*?</application>', text, re.DOTALL):
            name, body = m.group(1), m.group(0)
            gl = re.search(r"<gpu_length>\s*([\d.]+)\s*</gpu_length>", body)
            result[name] = bool(gl and float(gl.group(1)) > 0)
    except Exception:
        pass
    return result


def app_name_from_log(path: Path) -> Optional[str]:
    """Extrai o nome da app de um *_<APP>_GENERIC.log. Ignora o ALL_APPS."""
    m = re.search(r"DEVICES_(.+)_GENERIC\.log$", path.name)
    if not m:
        return None
    app = m.group(1)
    return None if app == "ALL_APPS" else app


def parse_app_logs(run_dir: Path) -> Dict[str, Dict]:
    """Lê os logs por aplicação de uma execução. Devolve {app: métricas em ms}."""
    out: Dict[str, Dict] = {}
    for log in run_dir.glob("*_GENERIC.log"):
        app = app_name_from_log(log)
        if app is None:
            continue
        raw = parse_generic_log(log)
        if not raw:
            continue
        completed = raw["completed_tasks"]
        failed = raw["failed_tasks"]
        total = completed + failed
        out[app] = {
            "latency_ms": raw["service_time_avg"] * 1000,
            "processing_ms": raw["processing_time_avg"] * 1000,
            "network_ms": raw["network_delay_avg"] * 1000,
            "completed": completed,
            "failed": failed,
            "failure_rate": (failed / total) * 100 if total > 0 else 0.0,
            "failed_bw": raw["failed_bw"],
            "failed_vm_capacity": raw["failed_vm_capacity"],
            "failed_mobility": raw["failed_mobility"],
        }
    return out


def find_generic_log(run_dir: Path) -> Optional[Path]:
    """Localiza o *_ALL_APPS_GENERIC.log, cujo nome inclui o número de dispositivos."""
    return next(run_dir.glob("*ALL_APPS_GENERIC.log"), None)


def _num(cols: List[str], idx: int, cast=float, default=0.0):
    """Lê a coluna idx de uma linha já split por ';', com fallback seguro."""
    try:
        return cast(cols[idx]) if idx < len(cols) and cols[idx].strip() else default
    except Exception:
        return default


def parse_generic_log(log_file: Path) -> Optional[Dict]:
    """Extrai as métricas da primeira linha de dados de um *_GENERIC.log.

    Layout das colunas (SimLogger.java:867-880), 0-based:
      0 completed  1 failed  2 uncompleted  3 failedBw  4 serviceTime
      5 processingTime  6 networkDelay  8 cost  9 failedVmCapacity  10 failedMobility
    processingTime é o tempo de processamento no servidor (GPU ou CPU, conforme a
    aplicação); serviceTime = processingTime + networkDelay.
    """
    if not log_file.exists():
        return None
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
        if not lines:
            return None
        c = lines[0].split(";")
        return {
            "completed_tasks": _num(c, 0, int, 0),
            "failed_tasks": _num(c, 1, int, 0),
            "uncompleted_tasks": _num(c, 2, int, 0),
            "service_time_avg": _num(c, 4),      # FRTT (s)
            "processing_time_avg": _num(c, 5),   # compute/GPU (s)
            "network_delay_avg": _num(c, 6),     # rede (s)
            "failed_bw": _num(c, 3, int, 0),
            "failed_vm_capacity": _num(c, 9, int, 0),
            "failed_mobility": _num(c, 10, int, 0),
        }
    except Exception as e:
        print(f"Erro ao parsear {log_file}: {e}")
        return None


def extract_metrics_from_run(run_dir: Path, run_id: int, seed: int,
                             simulation_time_default: int,
                             warm_up_default: float = 10.0) -> Optional[Dict]:
    """Extrai métricas normalizadas de um diretório de run.

    simulation_time_default e warm_up_default vêm do config.properties do cenário. Um
    config.properties na pasta da execução, se existir, tem precedência.
    """
    log_file = find_generic_log(run_dir)
    raw = parse_generic_log(log_file) if log_file else None
    if not raw:
        return None

    simulation_time = simulation_time_default
    warm_up_period = warm_up_default
    config_file = run_dir / "config.properties"
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("simulation_time="):
                        simulation_time = float(line.split("=")[1].split("#")[0].strip())
                    elif line.startswith("warm_up_period="):
                        warm_up_period = float(line.split("=")[1].split("#")[0].strip())
        except Exception:
            pass

    # simulation_time e warm_up_period estão em minutos no config; o motor os converte
    # para segundos (× 60), e a vazão deve usar a mesma conversão.
    ENGINE_MINUTES_TO_SECONDS = 60
    effective_time = (simulation_time - warm_up_period) * ENGINE_MINUTES_TO_SECONDS
    completed = raw["completed_tasks"]
    failed = raw["failed_tasks"]
    total = completed + failed

    return {
        "run_id": run_id,
        "seed": seed,
        "latency_mean_ms": raw["service_time_avg"] * 1000,
        "processing_ms": raw["processing_time_avg"] * 1000,   # compute/GPU
        "network_ms": raw["network_delay_avg"] * 1000,        # rede
        "throughput": completed / effective_time if effective_time > 0 else 0.0,
        "failure_rate": (failed / total) * 100 if total > 0 else 0.0,
        "completed_tasks": completed,
        "failed_tasks": failed,
        "total_tasks": total,
        "simulation_time": simulation_time,
        "effective_time": effective_time,
        "output_dir": Path(os.path.relpath(run_dir, config.REPO_ROOT)).as_posix(),
    }


def confidence_interval(data: List[float]) -> tuple:
    """Retorna (média, margem) para IC 95%."""
    if len(data) < 2:
        return (data[0] if data else 0.0, 0.0)
    mean = statistics.mean(data)
    std_dev = statistics.stdev(data)
    n = len(data)
    z_score = 1.96 if n >= 30 else 2.045
    return (mean, z_score * (std_dev / sqrt(n)))


def load_validated_runs(manifest_csv: Path) -> List[Dict]:
    """Lê o manifest e devolve apenas runs com status=OK."""
    if not manifest_csv.exists():
        print(f"ERRO: Manifest não encontrado: {manifest_csv}")
        return []
    runs = []
    with open(manifest_csv, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["status"] == "OK":
                runs.append({
                    "run_id": int(row["run_id"]),
                    "seed": int(row["seed"]) if row["seed"].isdigit() else int(row["run_id"]),
                    "output_dir": row["output_dir"],
                })
    return runs


def main() -> int:
    parser = argparse.ArgumentParser(description="Agrega as métricas das execuções validadas de um ponto.")
    parser.add_argument("--ponto", required=True, choices=list(config.PONTOS),
                        help="Código do ponto (K01…K14 ou N01…N14)")
    parser.add_argument("--permitir-parcial", action="store_true",
                        help="agrega mesmo que faltem pastas do manifesto nesta máquina")
    args = parser.parse_args()

    cfg = config.ponto(args.ponto)
    experimento_dir = cfg["experimento"]
    manifest_csv = experimento_dir / "run_manifest.csv"
    metrics_runs_csv = experimento_dir / "metrics_runs.csv"
    metrics_summary_csv = experimento_dir / "metrics_summary.csv"
    experimento_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(f"Agregando métricas — {cfg['rotulo']} (apenas runs validados)")
    print("=" * 70)
    print()

    validated_runs = load_validated_runs(manifest_csv)
    if not validated_runs:
        print("ERRO: Nenhum run validado encontrado!")
        print(f"Execute primeiro: bash execucao/rodar_experimento.sh {args.ponto}")
        return 1
    print(f"  {len(validated_runs)} runs validados encontrados\n")
    faltando = config.amostra_incompleta(args.ponto)
    if faltando and not args.permitir_parcial:
        print(f"ERRO: {len(faltando)} das {len(validated_runs)} execuções do manifesto não "
              f"estão nesta máquina (ex.: {faltando[0].relative_to(config.REPO_ROOT)}).")
        print("Nada foi gravado, para não substituir as métricas da amostra completa. "
              "Use --permitir-parcial para agregar assim mesmo.")
        return 1

    sim_t_cfg, warm_cfg = read_sim_params(cfg["pasta"])
    sim_time_default = sim_t_cfg if sim_t_cfg is not None else cfg["simulation_time_default"]
    warm_default = warm_cfg if warm_cfg is not None else 10.0

    all_metrics = []
    app_accum: Dict[str, List[Dict]] = {}   # app -> lista de métricas por run
    seen_dirs = set()
    for run_info in validated_runs:
        run_dir = config.REPO_ROOT / run_info["output_dir"]
        if not run_dir.exists():
            print(f"  WARNING: diretório não existe: {run_dir}")
            continue
        # Evita contar duas vezes o mesmo diretório (manifest com linha duplicada).
        if str(run_dir) in seen_dirs:
            print(f"  (ignorado) run duplicado no manifest: {run_dir.name}")
            continue
        seen_dirs.add(str(run_dir))
        m = extract_metrics_from_run(run_dir, run_info["run_id"], run_info["seed"],
                                     sim_time_default, warm_default)
        for app, am in parse_app_logs(run_dir).items():
            app_accum.setdefault(app, []).append(am)
        if m:
            all_metrics.append(m)
            print(f"  ✓ Run {m['run_id']} (seed={m['seed']}): "
                  f"latency={m['latency_mean_ms']:.2f}ms, "
                  f"throughput={m['throughput']:.2f} tps, "
                  f"failure_rate={m['failure_rate']:.2f}%, tasks={m['completed_tasks']}")
        else:
            print(f"  ✗ Run {run_info['run_id']}: falha ao extrair métricas")

    if not all_metrics:
        print("ERRO: Nenhuma métrica extraída!")
        return 1
    print(f"\nTotal de runs com métricas: {len(all_metrics)}\n")

    fieldnames = ["run_id", "seed", "latency_mean_ms", "processing_ms", "network_ms",
                  "throughput", "failure_rate",
                  "completed_tasks", "failed_tasks", "total_tasks",
                  "simulation_time", "effective_time", "output_dir"]
    with open(metrics_runs_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_metrics)
    print(f"✓ Salvo: {metrics_runs_csv} ({len(all_metrics)} runs)")

    # Métricas por aplicação, com média e IC95 sobre as execuções.
    gpu_map = read_app_gpu_map(cfg["pasta"])
    metrics_by_app_csv = experimento_dir / "metrics_by_app.csv"

    def _avg(rows, key):
        vals = [r[key] for r in rows]
        return statistics.mean(vals) if vals else 0.0

    def _std(rows, key):
        vals = [r[key] for r in rows]
        return statistics.stdev(vals) if len(vals) > 1 else 0.0

    def _ic95(rows, key):
        """Semiamplitude do IC95 da média, na mesma convenção do resumo geral."""
        return confidence_interval([r[key] for r in rows])[1]

    app_rows = []
    for app in sorted(app_accum):
        rows = app_accum[app]
        app_rows.append({
            "app": app,
            "uses_gpu": gpu_map.get(app, False),
            "num_runs": len(rows),
            "latency_ms": _avg(rows, "latency_ms"),
            "latency_std": _std(rows, "latency_ms"),
            "latency_ic95": _ic95(rows, "latency_ms"),
            "processing_ms": _avg(rows, "processing_ms"),  # compute (GPU ou CPU)
            "network_ms": _avg(rows, "network_ms"),
            "failure_rate": _avg(rows, "failure_rate"),
            "failure_rate_std": _std(rows, "failure_rate"),
            "failure_rate_ic95": _ic95(rows, "failure_rate"),
            "failed_bw": _avg(rows, "failed_bw"),
            "failed_vm_capacity": _avg(rows, "failed_vm_capacity"),
            "failed_mobility": _avg(rows, "failed_mobility"),
            "completed": _avg(rows, "completed"),
        })
    if app_rows:
        with open(metrics_by_app_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(app_rows[0].keys()))
            writer.writeheader()
            writer.writerows(app_rows)
        print(f"✓ Salvo: {metrics_by_app_csv} ({len(app_rows)} apps)")

    latencies = [m["latency_mean_ms"] for m in all_metrics]
    throughputs = [m["throughput"] for m in all_metrics]
    failure_rates = [m["failure_rate"] for m in all_metrics]

    latency_mean, latency_ci = confidence_interval(latencies)
    throughput_mean, throughput_ci = confidence_interval(throughputs)
    failure_mean, failure_ci = confidence_interval(failure_rates)
    latency_std = statistics.stdev(latencies) if len(latencies) > 1 else 0.0
    throughput_std = statistics.stdev(throughputs) if len(throughputs) > 1 else 0.0
    failure_std = statistics.stdev(failure_rates) if len(failure_rates) > 1 else 0.0

    summary = {
        "ponto": cfg["nome"],
        "num_runs": len(all_metrics),
        "latency_mean_ms": latency_mean,
        "latency_std_ms": latency_std,
        "latency_ci_lower_ms": latency_mean - latency_ci,
        "latency_ci_upper_ms": latency_mean + latency_ci,
        "throughput_mean": throughput_mean,
        "throughput_std": throughput_std,
        "throughput_ci_lower": throughput_mean - throughput_ci,
        "throughput_ci_upper": throughput_mean + throughput_ci,
        "failure_rate_mean": failure_mean,
        "failure_rate_std": failure_std,
        "failure_rate_ci_lower": failure_mean - failure_ci,
        "failure_rate_ci_upper": failure_mean + failure_ci,
    }
    # Prazo de QoS: comparação da latência média com max_delay_requirement.
    deadline_ms = read_deadline_ms(cfg["pasta"])
    if deadline_ms:
        summary["deadline_requirement_ms"] = deadline_ms
        summary["latency_vs_deadline_ratio"] = latency_mean / deadline_ms
        summary["deadline_met_by_mean"] = latency_mean <= deadline_ms

    with open(metrics_summary_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary.keys()))
        writer.writeheader()
        writer.writerow(summary)
    print(f"✓ Salvo: {metrics_summary_csv}\n")

    print("=" * 70)
    print("Resumo Agregado")
    print("=" * 70)
    print(f"Latency:      {latency_mean:.2f} ± {latency_std:.2f} ms "
          f"(95% CI: {latency_mean - latency_ci:.2f} - {latency_mean + latency_ci:.2f})")
    print(f"Throughput:   {throughput_mean:.2f} ± {throughput_std:.2f} tps "
          f"(95% CI: {throughput_mean - throughput_ci:.2f} - {throughput_mean + throughput_ci:.2f})")
    print(f"Failure Rate: {failure_mean:.2f} ± {failure_std:.2f}% "
          f"(95% CI: {failure_mean - failure_ci:.2f} - {failure_mean + failure_ci:.2f})")
    if deadline_ms:
        status = "ATENDE" if latency_mean <= deadline_ms else "VIOLA"
        print(f"Deadline AR:  requisito {deadline_ms:.0f} ms | latência média "
              f"{latency_mean:.1f} ms = {latency_mean / deadline_ms:.2f}× → {status}")
        print("              (indicador sobre a média, e não a fração de tarefas "
              "que violam o prazo)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
