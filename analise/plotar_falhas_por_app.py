#!/usr/bin/env python3
"""Perfil de falha de uma execução: dispositivos por aplicação e falhas por aplicação.

  (a) população: dispositivos que executam cada aplicação, lidos do console.log da
      execução. A distribuição é determinística (blocos de identificadores segundo
      usage_percentage) e, portanto, igual em todas as execuções do ponto;
  (b) falhas por aplicação, empilhadas por causa: capacidade (VM/memória de vídeo),
      banda, mobilidade e ausência de cobertura da WLAN.

A comparação indica em quais aplicações a falha se concentra.

Uso:
    python3 analise/plotar_falhas_por_app.py --ponto K01
    python3 analise/plotar_falhas_por_app.py --ponto N14 --run melhor
    python3 analise/plotar_falhas_por_app.py --ponto K01 --run 12
"""

import argparse
import gzip
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import config
from agregar_metricas import app_name_from_log, read_app_gpu_map

# A cor de cada aplicação vem de config.cor_da_app, e não da posição da barra, para
# ser a mesma em todas as figuras. As cores das causas de falha são seguras para
# daltonismo (menor ΔE entre vizinhas: 16,3); as duas mais claras exigem rótulo direto.
CAUSAS = [
    ("failed_vm_capacity", "Capacidade de VM / VRAM", "#e34948"),
    ("failed_bw", "Banda (buffer do enlace)", "#4a3aa7"),
    ("failed_mobility", "Mobilidade", "#eda100"),
    ("rejected_wlan_range", "Fora de alcance da WLAN", "#e87ba4"),
]
INK = "#0b0b0b"
INK_MUTED = "#52514e"

# Índices dos campos na linha de totais do SIMRESULT (SimLogger.java:866-941).
IDX = {
    "completed": 0,
    "failed": 1,
    "failed_bw": 3,
    "failed_vm_capacity": 9,
    "failed_mobility": 10,
    "rejected_wlan_range": 13,
}


def escolher_run(metrics_runs_csv: Path, criterio: str, ponto: str) -> pd.Series:
    """Seleciona a run: 'pior'/'melhor' por taxa de falha, ou um seed explícito."""
    if not metrics_runs_csv.exists():
        print(f"ERRO: {metrics_runs_csv} não encontrado!")
        print(f"Execute antes: python3 analise/agregar_metricas.py --ponto {ponto}")
        sys.exit(1)
    df = pd.read_csv(metrics_runs_csv)

    if criterio == "pior":
        return df.loc[df["failure_rate"].idxmax()]
    if criterio == "melhor":
        return df.loc[df["failure_rate"].idxmin()]

    seed = int(criterio)
    achado = df[df["seed"] == seed]
    if achado.empty:
        print(f"ERRO: seed {seed} não está entre as runs validadas "
              f"({df['seed'].min()}..{df['seed'].max()}).")
        sys.exit(1)
    return achado.iloc[0]


def ler_usuarios_por_app(run_dir: Path) -> dict:
    """Extrai {app: nº de dispositivos} do cabeçalho do console.log da run.

    A tabela está nas primeiras linhas do arquivo, e a leitura termina ao fim dela.
    Aceita console.log e console.log.gz, pois execucao/rodar_simulacao.sh comprime o arquivo.
    """
    console = run_dir / "console.log"
    comprimido = run_dir / "console.log.gz"
    if not console.exists() and not comprimido.exists():
        return {}

    padrao = re.compile(r"Task Type \d+:\s*(\S+)\s*\((\d+) active devices")
    usuarios = {}
    abrir = ((lambda: console.open(encoding="utf-8", errors="replace")) if console.exists()
             else (lambda: gzip.open(comprimido, "rt", encoding="utf-8", errors="replace")))
    with abrir() as fh:
        for i, linha in enumerate(fh):
            m = padrao.search(linha)
            if m:
                usuarios[m.group(1)] = int(m.group(2))
            elif usuarios and i > 200:
                break
    return usuarios


def ler_falhas_por_app(run_dir: Path) -> dict:
    """Lê os SIMRESULT por aplicação da run. Devolve {app: {campo: valor}}."""
    out = {}
    for log in run_dir.glob("*_GENERIC.log"):
        app = app_name_from_log(log)
        if app is None:  # ALL_APPS
            continue
        linhas = [l for l in log.read_text(encoding="utf-8").splitlines()
                  if l.strip() and not l.startswith("#")]
        if not linhas:
            continue
        cols = linhas[0].split(";")
        out[app] = {campo: float(cols[i]) for campo, i in IDX.items()}
    return out


def montar_tabela(usuarios: dict, falhas: dict, gpu_map: dict) -> pd.DataFrame:
    """Junta população e falhas numa linha por app, ordenadas por falhas desc."""
    apps = sorted(set(usuarios) | set(falhas))
    linhas = []
    for app in apps:
        f = falhas.get(app, {})
        completed = f.get("completed", 0.0)
        failed = f.get("failed", 0.0)
        total = completed + failed
        linhas.append({
            "app": app,
            "usuarios": usuarios.get(app, 0),
            "usa_gpu": bool(gpu_map.get(app, False)),
            "completed": completed,
            "failed": failed,
            "geradas": total,
            "taxa_falha": 100.0 * failed / total if total else 0.0,
            **{c: f.get(c, 0.0) for c, _, _ in CAUSAS},
        })
    df = pd.DataFrame(linhas)
    # Ordem decrescente de falhas; em empate, a aplicação de GPU primeiro, para que a
    # ordem seja estável entre cenários.
    return (df.sort_values(["failed", "usa_gpu", "usuarios", "app"],
                           ascending=[False, False, False, True])
              .reset_index(drop=True))


def rotulo_app(row) -> str:
    tag = "GPU" if row["usa_gpu"] else "CPU"
    return f"{str(row['app']).replace('_', chr(10))}\n({tag})"


def formatar_milhar(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


def limpar_eixo(ax):
    ax.grid(True, axis="y", alpha=0.25, linestyle="--")
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.margins(y=0.18)


def largura_barra(n: int) -> float:
    """Barra estreita quando há uma app só, senão ela ocupa o painel inteiro."""
    return 0.6 if n > 1 else 0.35


def painel_usuarios(ax, df: pd.DataFrame):
    total = df["usuarios"].sum()
    x = range(len(df))
    # Borda branca para separar barras adjacentes.
    ax.bar(x, df["usuarios"], largura_barra(len(df)),
           color=[config.cor_da_app(df.iloc[i]["app"]) for i in x],
           edgecolor="white", linewidth=2)

    for i, u in enumerate(df["usuarios"]):
        pct = 100.0 * u / total if total else 0.0
        ax.text(i, u, f"{u}\n({pct:.0f}%)", ha="center", va="bottom",
                fontsize=10, fontweight="bold", color=INK)

    ax.set_xticks(list(x))
    ax.set_xticklabels([rotulo_app(df.iloc[i]) for i in x], fontsize=9)
    ax.set_ylabel("Dispositivos móveis", fontweight="bold", color=INK)
    ax.set_title(f"(a) Usuários por aplicação — {total} no total",
                 fontweight="bold", color=INK, pad=10)
    limpar_eixo(ax)


def painel_falhas(ax, df: pd.DataFrame):
    x = range(len(df))
    presentes = [c for c in CAUSAS if df[c[0]].sum() > 0]
    base = [0.0] * len(df)

    for campo, rotulo, cor in presentes:
        valores = df[campo].values
        ax.bar(x, valores, largura_barra(len(df)), bottom=base, label=rotulo,
               color=cor, edgecolor="white", linewidth=2)
        base = [b + v for b, v in zip(base, valores)]

    if not presentes:
        # Sem dados, a escala do eixo é fixada explicitamente.
        ax.set_ylim(0, 1)
        ax.set_yticks([0])
        ax.text(0.5, 0.5, "Nenhuma tarefa falhou nesta run",
                transform=ax.transAxes, ha="center", va="center",
                fontsize=12, color=INK_MUTED)
    else:
        for i, row in df.iterrows():
            if row["failed"] > 0:
                ax.text(i, row["failed"],
                        f"{formatar_milhar(row['failed'])}\n({row['taxa_falha']:.1f}% da app)",
                        ha="center", va="bottom", fontsize=10,
                        fontweight="bold", color=INK)
            else:
                ax.text(i, 0, "0", ha="center", va="bottom", fontsize=10,
                        fontweight="bold", color=INK_MUTED)

    ax.set_xticks(list(x))
    ax.set_xticklabels([rotulo_app(df.iloc[i]) for i in x], fontsize=9)
    ax.set_ylabel("Tarefas falhas", fontweight="bold", color=INK)
    ax.set_title("(b) Falhas por aplicação e por causa",
                 fontweight="bold", color=INK, pad=10)
    ax.yaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda v, _: formatar_milhar(v)))
    limpar_eixo(ax)
    # Legenda apenas quando há mais de uma causa.
    if len(presentes) > 1:
        ax.legend(loc="upper right", frameon=False, fontsize=9)
    elif presentes:
        ax.text(0.99, 0.99, f"Causa única: {presentes[0][1].lower()}",
                transform=ax.transAxes, ha="right", va="top",
                fontsize=9, color=INK_MUTED)


def subtitulo(df: pd.DataFrame) -> str:
    """Frase que compara a fração de usuários com a fração de falhas."""
    total_u = df["usuarios"].sum()
    total_f = df["failed"].sum()
    if total_f == 0 or total_u == 0:
        return "Nenhuma falha nesta run — os painéis mostram só a população."
    lider = df.iloc[0]
    share_u = 100.0 * lider["usuarios"] / total_u
    share_f = 100.0 * lider["failed"] / total_f
    return (f"{lider['app']}: {share_u:.0f}% dos usuários, "
            f"{share_f:.0f}% das falhas ({formatar_milhar(total_f)} tarefas perdidas)")


def plotar(df: pd.DataFrame, rotulo_ponto: str, run_info: str, output_file: Path):
    largura = max(11, 2.6 * len(df) + 5)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(largura, 6.2))

    painel_usuarios(ax1, df)
    painel_falhas(ax2, df)

    fig.suptitle(f"Perfil de falha por aplicação — {rotulo_ponto}\n{run_info}",
                 fontweight="bold", fontsize=13, color=INK, y=0.99)
    fig.text(0.5, 0.005, subtitulo(df), ha="center", fontsize=10, color=INK_MUTED)

    plt.tight_layout(rect=[0, 0.03, 1, 0.92])
    plt.savefig(output_file, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"✓ Gerado: {output_file}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Usuários por aplicação × falhas por aplicação e causa, numa run.")
    parser.add_argument("--ponto", required=True, choices=list(config.PONTOS),
                        help="Código do ponto (K01…K14 ou N01…N14)")
    parser.add_argument("--run", default="pior",
                        help="'pior' (default) / 'melhor' por taxa de falha, ou um seed")
    args = parser.parse_args()

    cfg = config.ponto(args.ponto)
    experimento_dir = cfg["experimento"]
    plots_dir = experimento_dir / "figuras"
    plots_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(f"Perfil de falha por aplicação — {cfg['rotulo']}")
    print("=" * 70)

    run = escolher_run(experimento_dir / "metrics_runs.csv", args.run, args.ponto)
    # output_dir é relativo à raiz do repositório.
    run_dir = config.REPO_ROOT / run["output_dir"]
    if not run_dir.exists():
        print(f"ERRO: diretório da run não existe: {run_dir}")
        return 1

    seletor = {"pior": "maior taxa de falha", "melhor": "menor taxa de falha"}.get(
        args.run, f"seed {args.run}")
    run_info = (f"run seed {int(run['seed'])} ({seletor}) — "
                f"{run['failure_rate']:.2f}% de falha, "
                f"FRTT {run['latency_mean_ms']:.2f} ms")
    print(f"  Run: {run_dir.name}")
    print(f"  {run_info}\n")

    usuarios = ler_usuarios_por_app(run_dir)
    if not usuarios:
        print("  AVISO: console.log não trouxe a tabela de dispositivos; "
              "o painel (a) sairá zerado.")
    falhas = ler_falhas_por_app(run_dir)
    df = montar_tabela(usuarios, falhas, read_app_gpu_map(cfg["pasta"]))

    print(df[["app", "usuarios", "geradas", "failed", "taxa_falha"]].to_string(index=False))
    print()

    plotar(df, cfg["rotulo"], run_info, plots_dir / "falhas_por_app.png")

    csv_out = plots_dir / "falhas_por_app.csv"
    df.to_csv(csv_out, index=False)
    print(f"✓ Tabela:  {csv_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
