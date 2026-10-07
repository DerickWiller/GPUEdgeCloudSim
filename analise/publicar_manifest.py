#!/usr/bin/env python3
"""Valida um conjunto de execuções de um ponto e grava o manifesto que define a amostra.

O manifesto, experimentos/<experimento>/<ponto>/resultados/run_manifest.csv, lista as
execuções que compõem a amostra oficial do ponto; agregar_metricas.py considera apenas
as de status OK. O manifesto anterior é substituído; o histórico fica no controle de
versão. Por isso a publicação é um passo explícito, separado da execução da bateria.

As execuções são indicadas pela lista que execucao/rodar_experimento.sh grava ao fim de
cada bateria (saidas/<experimento>/<ponto>/bateria_<data>_<hora>.txt) ou, para baterias
antigas, por um prefixo do nome da pasta. A publicação é recusada se uma semente aparecer
mais de uma vez, o que indicaria execuções de baterias diferentes na mesma amostra.

Uso:
    python3 analise/publicar_manifest.py --ponto K02 --lista saidas/densidade-gpu/02-gpus/bateria_20261007_101500.txt
    python3 analise/publicar_manifest.py --ponto K02 --prefixo run_20261006_
"""

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

import config
from validar_run import validar

CAMPOS = ["run_id", "seed", "status", "output_dir", "sha256_simresult",
          "sha256_console", "notes"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Publica o manifesto de um ponto.")
    ap.add_argument("--ponto", required=True, choices=list(config.PONTOS))
    origem = ap.add_mutually_exclusive_group(required=True)
    origem.add_argument("--lista", type=Path,
                        help="arquivo com uma pasta de execução por linha")
    origem.add_argument("--prefixo",
                        help='prefixo das pastas de execução, por exemplo "run_20261006_"')
    args = ap.parse_args()

    cfg = config.ponto(args.ponto)
    if args.lista:
        nomes = [l.strip() for l in args.lista.read_text(encoding="utf-8").splitlines()
                 if l.strip()]
        pastas = [config.REPO_ROOT / n if not Path(n).is_absolute() else Path(n)
                  for n in nomes]
        ausentes = [p for p in pastas if not p.is_dir()]
        if ausentes:
            print(f"ERRO: pastas da lista inexistentes: {ausentes[:3]}", file=sys.stderr)
            return 1
    else:
        pastas = [p for p in cfg["resultados"].glob(f"{args.prefixo}*") if p.is_dir()]
    if not pastas:
        print(f"Nenhuma execução encontrada para {args.ponto}.", file=sys.stderr)
        return 1
    pastas.sort(key=lambda p: int(p.name.rsplit("seed", 1)[-1]))

    repetidas = [s for s, n in Counter(p.name.rsplit("seed", 1)[-1] for p in pastas).items()
                 if n > 1]
    if repetidas:
        print(f"ERRO: sementes repetidas na seleção ({', '.join(repetidas)}); a seleção "
              f"mistura execuções de baterias diferentes. Use --lista ou um prefixo mais "
              f"específico. Nada foi gravado.", file=sys.stderr)
        return 1

    linhas, falhas = [], 0
    for i, pasta in enumerate(pastas, start=1):
        # Execuções antigas: a verificação de data não se aplica.
        r = validar(args.ponto, pasta, inicio=0)
        falhas += r["status"] != "OK"
        hashes = list(r["hashes"].items())
        linhas.append({
            "run_id": i, "seed": r["seed"], "status": r["status"],
            "output_dir": r["output_dir"],
            "sha256_simresult": next((h for n, h in hashes if n.endswith("GENERIC.log")), ""),
            "sha256_console": next((h for n, h in hashes if n.startswith("console")), ""),
            "notes": " | ".join(r["notas"]),
        })
        print(f"[{i}/{len(pastas)}] {r['status']} {pasta.name}")

    destino = cfg["experimento"] / "run_manifest.csv"
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows(linhas)
    print(f"Manifesto: {destino.relative_to(config.REPO_ROOT)} "
          f"({len(linhas) - falhas} OK, {falhas} com falha)")
    return 0 if falhas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
