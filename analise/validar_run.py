#!/usr/bin/env python3
"""Validação das saídas de uma execução do simulador.

Uma execução é aceita quando:

    1. o SIMRESULT agregado e o console existem e não estão vazios;
    2. os arquivos foram gerados depois do início da execução;
    3. a configuração copiada para a pasta de saída tem os mesmos valores da
       configuração versionada do ponto: as mesmas chaves no config.properties (chaves
       adicionais são ignoradas) e a mesma árvore nos XML, desconsiderados os
       comentários. Isso garante que a execução pertence ao ponto;
    4. as métricas são legíveis e coerentes: latência entre 0 e 1 h, ao menos uma tarefa
       concluída e falhas por causa somando o total de falhas.

O resultado inclui o SHA-256 dos arquivos principais, para rastreabilidade. O registro no
manifesto do ponto é feito por publicar_manifest.py.

Uso:
    python3 analise/validar_run.py --ponto K02 --output-dir saidas/densidade-gpu/02-gpus/run_…
"""

import argparse
import hashlib
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import config

ARQUIVOS_CONFIG = ("config.properties", "edge_devices.xml", "applications.xml")


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 16), b""):
            h.update(bloco)
    return h.hexdigest()


def _propriedades(caminho: Path) -> dict:
    pares = (l.split("=", 1) for l in caminho.read_text(encoding="utf-8").splitlines()
             if "=" in l and not l.lstrip().startswith("#"))
    return {k.strip(): v.strip() for k, v in pares}


def _arvore(no) -> tuple:
    return (no.tag, sorted(no.attrib.items()), (no.text or "").strip(),
            [_arvore(f) for f in no if isinstance(f.tag, str)])


def mesma_configuracao(usada: Path, versionada: Path) -> bool:
    """Compara valores, e não bytes: comentários e chaves não lidas não importam."""
    if not usada.exists():
        return False
    if usada.suffix == ".properties":
        a, b = _propriedades(usada), _propriedades(versionada)
        return all(a.get(k) == v for k, v in b.items())
    return _arvore(ET.parse(usada).getroot()) == _arvore(ET.parse(versionada).getroot())


def localizar_arquivos(pasta: Path) -> dict:
    """SIMRESULT agregado e console da execução; None para o que estiver ausente."""
    console = next((pasta / n for n in ("console.log.gz", "console.log")
                    if (pasta / n).exists()), None)
    return {"simresult": next(pasta.glob("*ALL_APPS_GENERIC.log"), None),
            "console": console}


def verificar_metricas(simresult: Path) -> tuple:
    """Lê a primeira linha de dados do *_ALL_APPS_GENERIC.log e confere a coerência.

    Colunas usadas (SimLogger): 0 concluídas, 1 falhas, 3 falhas por banda, 4 tempo de
    serviço (s), 6 atraso de rede (s), 9 falhas por capacidade, 10 falhas por mobilidade.
    """
    linhas = [l.strip() for l in simresult.read_text(encoding="utf-8", errors="ignore")
              .splitlines() if l.strip() and not l.startswith("#")]
    if not linhas:
        return False, "SIMRESULT sem linhas de dados"
    c = linhas[0].split(";")
    if len(c) < 11:
        return False, f"linha com {len(c)} campos, esperados ao menos 11"
    try:
        concluidas, falhas = int(c[0]), int(c[1])
        servico, rede = float(c[4]), float(c[6])
        f_banda, f_capacidade, f_mobilidade = int(c[3]), int(c[9]), int(c[10])
    except ValueError as e:
        return False, f"linha não interpretável ({e})"

    problemas = []
    if not 0 < servico < 3600:
        problemas.append(f"tempo de serviço implausível ({servico} s)")
    if concluidas <= 0:
        problemas.append("nenhuma tarefa concluída")
    if f_banda + f_capacidade + f_mobilidade != falhas:
        problemas.append(f"falhas por causa ({f_banda}+{f_capacidade}+{f_mobilidade}) "
                         f"diferem do total ({falhas})")
    if rede < 0:
        problemas.append(f"atraso de rede negativo ({rede})")
    if problemas:
        return False, "; ".join(problemas)
    taxa = 100.0 * falhas / (concluidas + falhas)
    return True, (f"concluídas={concluidas}, falhas={falhas} ({taxa:.2f}%), "
                  f"latência={servico * 1000:.2f} ms")


def validar(codigo_ponto: str, pasta: Path, inicio: float) -> dict:
    """Valida a execução em `pasta`; devolve status, observações e hashes."""
    cfg = config.ponto(codigo_ponto)
    # Sem resolver ligações simbólicas: saidas/ pode apontar para outro disco.
    pasta = Path(os.path.abspath(pasta))
    seed = pasta.name.rsplit("seed", 1)[-1]
    r = {"seed": int(seed) if seed.isdigit() else "", "status": "FAIL", "notas": [],
         "hashes": {}, "output_dir": Path(os.path.relpath(pasta, config.REPO_ROOT)).as_posix()}

    arquivos = localizar_arquivos(pasta)
    ausentes = [k for k, v in arquivos.items() if v is None or v.stat().st_size == 0]
    if ausentes:
        r["notas"].append("ausente ou vazio: " + ", ".join(ausentes))
        return r

    antigos = [v.name for v in arquivos.values() if v.stat().st_mtime < inicio - 300]
    if antigos:
        r["notas"].append("anterior ao início da execução: " + ", ".join(antigos))

    divergentes = [n for n in ARQUIVOS_CONFIG
                   if not mesma_configuracao(pasta / n, cfg["pasta"] / n)]
    if divergentes:
        r["notas"].append("configuração diferente da versionada: " + ", ".join(divergentes))

    metricas_ok, msg = verificar_metricas(arquivos["simresult"])
    r["notas"].append(msg)

    for v in arquivos.values():
        r["hashes"][v.name] = sha256(v)
    if not antigos and not divergentes and metricas_ok:
        r["status"] = "OK"
    return r


def main() -> int:
    ap = argparse.ArgumentParser(description="Valida as saídas de uma execução.")
    ap.add_argument("--ponto", required=True, help="código do ponto (K02, N08…)")
    ap.add_argument("--output-dir", required=True, type=Path)
    ap.add_argument("--start-time", type=float,
                    help="instante de início (epoch); padrão: data de modificação da pasta")
    args = ap.parse_args()

    inicio = args.start_time or args.output_dir.stat().st_mtime
    r = validar(args.ponto, args.output_dir, inicio)
    print(f"{r['status']}: {args.output_dir.name} — {' | '.join(r['notas'])}")
    return 0 if r["status"] == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
