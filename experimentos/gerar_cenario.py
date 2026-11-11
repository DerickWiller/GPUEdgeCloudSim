#!/usr/bin/env python3
"""Gera as configurações de um experimento a partir da sua descrição em cenario.json.

O cenário declara a infraestrutura, a carga, a rede e a política de escolha da GPU, e as
variáveis do experimento (`variar`); cada combinação de valores das variáveis é um ponto,
gravado em experimentos/<nome>/<pasta do ponto>/ com os três arquivos lidos pelo
simulador. Os blocos de XML e de propriedades são os de gerar_configs.py, de modo que um
cenário descrito aqui produz os mesmos valores que os experimentos publicados.

Os experimentos publicados continuam gerados por gerar_configs.py (campo `gerado_por`); para
eles, este script só confere se a descrição reproduz os valores versionados.

Uso:
    python3 experimentos/gerar_cenario.py experimentos/<nome>/cenario.json
    python3 experimentos/gerar_cenario.py experimentos/<nome>/cenario.json --previa
    python3 experimentos/gerar_cenario.py --conferir-todos
"""

import argparse
import copy
import itertools
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))
import gerar_configs as g  # noqa: E402

# Capacidade da WLAN em clientes YOLO: 480 Mbps / 48,24 Mbps por cliente (94 + 105 KB a 30 fps).
# A interface lê estes limites em /api/estado, para que o desenho use os mesmos valores.
CLIENTES_POR_AP = 480 / 48.24
CARGAS = {"yolo": 100, "mista": 30}          # fração de clientes YOLO, em %
NUVENS = {"escala": g.NUVEM_ESCALA, "densidade": g.NUVEM_DENSIDADE}
POLITICAS = {"AUTO": "critério da topologia (rodízio entre as GPUs)",
             "LOCAL": "só a GPU do ponto de acesso do dispositivo",
             "LOCAL_FIRST": "GPU de menor tempo estimado, com a MAN"}

PADRAO = {
    "titulo": "",
    "pergunta": "",
    "duracao_min": 60,
    "aquecimento_min": 5,
    "servidores": {"quantidade": 1, "com_gpu": 1, "modelo": "tocze"},
    "atratividade": "constante",
    "carga": "yolo",
    "dispositivos": 1,
    "dispositivos_por_ponto": None,
    "mobilidade": "nomade",
    "ponto_fixo": 0,
    "man": {"ligada": False, "banda_mbps": 1000, "propagacao_ms": 10},
    "politica": "AUTO",
    "nuvem": "escala",
    "variar": [],
    "excluir": [],
}


class CenarioInvalido(ValueError):
    pass


def _mesclar(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        out[k] = _mesclar(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def carregar(caminho: Path) -> dict:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    dados.setdefault("nome", Path(caminho).parent.name)
    return _mesclar(PADRAO, dados)


def _atribuir(par: dict, campo: str, valor) -> None:
    """Atribui `valor` ao campo em notação de pontos (servidores.com_gpu, dispositivos_por_ponto.0)."""
    partes = campo.split(".")
    alvo = par
    for p in partes[:-1]:
        alvo = alvo[int(p)] if isinstance(alvo, list) else alvo[p]
    ultimo = partes[-1]
    if isinstance(alvo, list):
        alvo[int(ultimo)] = valor
    else:
        alvo[ultimo] = valor


PARTE_DE_PASTA = __import__("re").compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _nome_pasta(var: dict, valor) -> str:
    """Nome da pasta do ponto para um valor: só letras, números, ponto, hífen e sublinhado."""
    pasta = var.get("pasta", "{v}")
    if isinstance(pasta, dict):
        nome = pasta[str(valor)]
    else:
        try:
            nome = pasta.format(v=valor)
        except (ValueError, TypeError):
            nome = pasta.replace(":02d", "").format(v=valor)
    nome = str(nome).replace(",", ".")
    if not PARTE_DE_PASTA.match(nome) or ".." in nome:
        raise CenarioInvalido(f"nome de pasta inválido para {var.get('campo')} = {valor}: {nome!r}")
    return nome


def pontos(cen: dict) -> list:
    """Pontos do cenário: [(pasta relativa, parâmetros, {campo: valor})], na ordem das variáveis."""
    variaveis = cen["variar"] or [{"campo": None, "valores": [None], "pasta": "ponto"}]
    out = []
    for combinacao in itertools.product(*[v["valores"] for v in variaveis]):
        valores = {v["campo"]: x for v, x in zip(variaveis, combinacao) if v["campo"]}
        if any(all(valores.get(k) == x for k, x in exc.items()) for exc in cen["excluir"]):
            continue
        par = copy.deepcopy(cen)
        for campo, x in valores.items():
            _atribuir(par, campo, x)
        pasta = "/".join(_nome_pasta(v, x) for v, x in zip(variaveis, combinacao))
        out.append((pasta, par, valores))
    return out


def _resolver(par: dict) -> dict:
    """Completa os parâmetros derivados e confere os limites; devolve avisos e erros."""
    erros, avisos = [], []
    srv = par["servidores"]
    if par["dispositivos_por_ponto"]:
        par["dispositivos"] = sum(par["dispositivos_por_ponto"])
        par["mobilidade"] = "por_ponto"
        if len(par["dispositivos_por_ponto"]) > srv["quantidade"]:
            erros.append("há mais pontos de acesso com dispositivos que servidores")
        if any(n < 0 for n in par["dispositivos_por_ponto"]):
            erros.append("número negativo de dispositivos num ponto de acesso")
    if par["carga"] not in CARGAS:
        erros.append(f"carga desconhecida: {par['carga']} (use {', '.join(CARGAS)})")
    if par["nuvem"] not in NUVENS:
        erros.append(f"nuvem desconhecida: {par['nuvem']} (use {', '.join(NUVENS)})")
    if par["politica"] not in POLITICAS:
        erros.append(f"política desconhecida: {par['politica']} (use {', '.join(POLITICAS)})")
    if srv["modelo"] not in ("tocze", "rodrigues"):
        erros.append("modelo de servidor deve ser tocze ou rodrigues")
    if srv["modelo"] == "rodrigues" and srv["quantidade"] != 1:
        erros.append("o modelo rodrigues descreve um único servidor")
    if not 0 <= srv["com_gpu"] <= srv["quantidade"]:
        erros.append("servidores com GPU deve estar entre 0 e a quantidade de servidores")
    if par["dispositivos"] < 1:
        erros.append("é preciso ao menos um dispositivo")
    if par["mobilidade"] == "fixa" and not 0 <= par["ponto_fixo"] < srv["quantidade"]:
        erros.append("ponto_fixo fora dos pontos de acesso existentes")
    if erros:
        return {"erros": erros, "avisos": avisos}

    yolo = round(par["dispositivos"] * CARGAS[par["carga"]] / 100)
    if yolo and srv["com_gpu"] == 0:
        erros.append("há clientes YOLO, mas nenhum servidor com GPU")
    memoria = g.vram_livre(yolo)
    if memoria < g.MEM_POR_QUADRO:
        limite = (g.VRAM_FISICA - g.MEM_POR_QUADRO) // g.VRAM_POR_CLIENTE
        erros.append(f"memória da GPU insuficiente: cada GPU guarda o modelo de todos os {yolo} clientes "
                     f"YOLO (416 MB cada; 6 144 MB na RTX 3050); cabem no máximo {limite}")
    if par["mobilidade"] == "por_ponto":
        maior = round(max(par["dispositivos_por_ponto"]) * CARGAS[par["carga"]] / 100)
    elif par["mobilidade"] == "fixa":
        maior = yolo
    else:
        maior = 0
    if maior > CLIENTES_POR_AP:
        avisos.append(f"{maior} clientes YOLO num ponto de acesso saturam a WLAN "
                      f"(capacidade de {CLIENTES_POR_AP:.2f}); a execução pode durar horas".replace(".", ",", 1))
    if par["politica"] != "AUTO" and not par["man"]["ligada"] and srv["quantidade"] > 1:
        avisos.append("sem MAN, a escolha entre GPU local e remota não tem custo de rede")
    par["_yolo"], par["_memoria"] = yolo, memoria
    return {"erros": erros, "avisos": avisos}


def _config(par: dict) -> str:
    extra = []
    if par["man"]["ligada"]:
        extra.append("\n# Rede metropolitana entre os servidores de borda.\nman_enabled=true\n")
    if par["mobilidade"] == "fixa":
        extra.append(f"\n# Dispositivos fixos no ponto de acesso {par['ponto_fixo']}.\n"
                     f"mobility_static_wlan_id={par['ponto_fixo']}\n")
    elif par["mobilidade"] == "por_ponto":
        extra.append("\n# Dispositivos fixos, por ponto de acesso (wlan_id 0, 1, ...).\n"
                     "mobility_static_devices_per_wlan="
                     + ",".join(map(str, par["dispositivos_por_ponto"])) + "\n")
    if par["politica"] != "AUTO":
        extra.append(f"\n# Escolha da GPU: {POLITICAS[par['politica']]}.\n"
                     f"edge_vm_selection={par['politica']}\n")
    titulo = f"{par['titulo'] or par['nome']}: {par['_descricao']}"
    texto = g.config_properties(titulo, par["dispositivos"], NUVENS[par["nuvem"]],
                                chegada_periodica_global=par["carga"] == "yolo",
                                extra="".join(extra), duracao_min=par["duracao_min"],
                                aquecimento_min=par["aquecimento_min"],
                                man_banda_mbps=par["man"]["banda_mbps"],
                                lan_atraso_s=par["man"]["propagacao_ms"] / 1000)
    return texto.replace("Arquivo gerado por experimentos/gerar_configs.py.",
                         "Arquivo gerado por experimentos/gerar_cenario.py a partir de cenario.json.")


def _edge(par: dict) -> str:
    srv = par["servidores"]
    if srv["modelo"] == "rodrigues":
        texto = g.edge_devices_escala(par["_yolo"])
    else:
        dcs = []
        for i in range(srv["quantidade"]):
            atr = (2 if i % 3 == 0 else 1) if par["atratividade"] == "ciclo" else 2
            dcs.append(g.datacenter(i, 200 + 400 * i, atr, g.host_borda(i < srv["com_gpu"], par["_memoria"])))
        texto = f"""<?xml version='1.0' encoding='utf-8'?>
<!--
  {srv['quantidade']} servidores de borda com 8 VMs de 2 núcleos e 10 000 MIPS cada (Toczé et al.,
  2020, Tabela 5); os {srv['com_gpu']} primeiros têm uma RTX 3050, atribuída à primeira VM.
  Memória livre de cada GPU: 6144 − {par['_yolo']} × 416 = {par['_memoria']} MB.
  Arquivo gerado por experimentos/gerar_cenario.py a partir de cenario.json.
-->
<edge_devices>

{"".join(dcs)}
</edge_devices>
"""
    return texto.replace("Arquivo gerado por experimentos/gerar_configs.py.",
                         "Arquivo gerado por experimentos/gerar_cenario.py a partir de cenario.json.")


def _apps(par: dict) -> str:
    texto = g.applications_yolo() if par["carga"] == "yolo" else g.applications_misto()
    return texto.replace("Arquivo gerado por experimentos/gerar_configs.py.",
                         "Arquivo gerado por experimentos/gerar_cenario.py a partir de cenario.json.")


def montar(cen: dict) -> dict:
    """Arquivos de todos os pontos, com avisos e erros por ponto, sem gravar nada."""
    resultado = {"pontos": [], "erros": [], "avisos": []}
    try:
        lista = pontos(cen)
    except CenarioInvalido as e:
        resultado["erros"].append(str(e))
        return resultado
    except (KeyError, IndexError, TypeError) as e:
        resultado["erros"].append(f"variável inválida em 'variar': {e}")
        return resultado
    if not lista:
        resultado["erros"].append("nenhum ponto: as exclusões removem todas as combinações")
    for pasta, par, valores in lista:
        par["_descricao"] = ", ".join(f"{k} = {v}" for k, v in valores.items()) or "ponto único"
        r = _resolver(par)
        item = {"pasta": pasta, "valores": valores, "erros": r["erros"], "avisos": r["avisos"]}
        if not r["erros"]:
            item["arquivos"] = {"config.properties": _config(par), "edge_devices.xml": _edge(par),
                                "applications.xml": _apps(par)}
            item["dispositivos"], item["clientes_yolo"] = par["dispositivos"], par["_yolo"]
        resultado["pontos"].append(item)
        resultado["erros"] += [f"{pasta}: {e}" for e in r["erros"]]
        resultado["avisos"] += [f"{pasta}: {a}" for a in r["avisos"]]
    return resultado


def gravar(cen: dict, destino: Path) -> list:
    """Grava os pontos em `destino`; recusa cenário com erro ou gerado por gerar_configs.py."""
    if cen.get("gerado_por"):
        raise CenarioInvalido(f"{cen['nome']} é gerado por {cen['gerado_por']}; edite aquele script")
    r = montar(cen)
    if r["erros"]:
        raise CenarioInvalido("; ".join(r["erros"]))
    escritos = []
    for item in r["pontos"]:
        pasta = destino / item["pasta"]
        if destino.resolve() not in pasta.resolve().parents:
            raise CenarioInvalido(f"ponto fora da pasta do experimento: {item['pasta']}")
        pasta.mkdir(parents=True, exist_ok=True)
        for nome, texto in item["arquivos"].items():
            (pasta / nome).write_text(texto, encoding="utf-8", newline="\n")
        escritos.append(pasta)
    return escritos


def _props(texto: str) -> dict:
    pares = (l.split("=", 1) for l in texto.splitlines() if "=" in l and not l.lstrip().startswith("#"))
    d = {k.strip(): v.strip() for k, v in pares}
    for chave, padrao in {"edge_vm_selection": "AUTO", "man_enabled": "false",
                          "mobility_static_wlan_id": "-1"}.items():
        d.setdefault(chave, padrao)
    return d


def _arvore(texto: str):
    import xml.etree.ElementTree as ET

    def no(n):
        return (n.tag, sorted(n.attrib.items()), (n.text or "").strip(),
                [no(f) for f in n if isinstance(f.tag, str)])
    return no(ET.fromstring(texto.encode("utf-8")))


def conferir(cen: dict, pasta_exp: Path) -> list:
    """Diferenças de valores entre os pontos descritos e os arquivos versionados; vazia se iguais."""
    r = montar(cen)
    difs = list(r["erros"])
    descritos = {item["pasta"] for item in r["pontos"]}
    existentes = {p.parent.relative_to(pasta_exp).as_posix() for p in pasta_exp.rglob("config.properties")}
    difs += [f"{p}: versionado, mas ausente do cenário" for p in sorted(existentes - descritos)]
    for item in r["pontos"]:
        pasta = pasta_exp / item["pasta"]
        if not pasta.is_dir():
            difs.append(f"{item['pasta']}: descrito, mas sem pasta versionada")
            continue
        for nome, texto in item.get("arquivos", {}).items():
            atual = (pasta / nome).read_text(encoding="utf-8")
            igual = (_props(texto) == _props(atual) if nome.endswith(".properties")
                     else _arvore(texto) == _arvore(atual))
            if not igual:
                difs.append(f"{item['pasta']}/{nome}: valores diferentes")
    return difs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cenario", nargs="?", help="caminho do cenario.json")
    ap.add_argument("--previa", action="store_true", help="lista os pontos e avisos sem gravar")
    ap.add_argument("--conferir-todos", action="store_true",
                    help="confere os experimentos publicados contra os seus cenario.json")
    a = ap.parse_args()
    if a.conferir_todos:
        falhas = 0
        for arq in sorted(RAIZ.glob("*/cenario.json")):
            difs = conferir(carregar(arq), arq.parent)
            n = len(montar(carregar(arq))["pontos"])
            print(f"{arq.parent.name}: {n} pontos, " + ("valores iguais aos versionados" if not difs
                                                         else f"{len(difs)} diferença(s)"))
            for d in difs:
                print("  " + d)
            falhas += bool(difs)
        return 1 if falhas else 0
    if not a.cenario:
        ap.error("informe o cenario.json ou --conferir-todos")
    cen = carregar(Path(a.cenario))
    r = montar(cen)
    for item in r["pontos"]:
        print(f"{item['pasta']}: " + ("; ".join(item["erros"]) if item["erros"]
                                      else f"{item['dispositivos']} dispositivos"))
    for aviso in r["avisos"]:
        print("AVISO", aviso)
    if r["erros"]:
        return 1
    if not a.previa:
        for pasta in gravar(cen, Path(a.cenario).resolve().parent):
            print("gravado", pasta.relative_to(RAIZ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
