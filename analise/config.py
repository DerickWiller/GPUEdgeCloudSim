"""Caminhos, pontos experimentais e cores, centralizados para todos os scripts de análise.

Cada ponto é identificado por um código curto, que nomeia a variável do experimento:

    K01 … K14   densidade de GPU: K servidores com GPU entre 14, com 9 clientes YOLO;
    N01 … N14   escala de clientes: N clientes YOLO sobre uma GPU.

As pastas seguem o mesmo esquema: experimentos/<experimento>/<ponto>/ guarda a
configuração e os resultados agregados (versionados), e saidas/<experimento>/<ponto>/
guarda as saídas brutas do simulador (não versionadas).
"""

import sys
from pathlib import Path

# No Windows, a saída redirecionada usa cp1252, que não representa símbolos como ✓.
for _fluxo in (sys.stdout, sys.stderr):
    if (getattr(_fluxo, "encoding", "") or "").lower().replace("-", "") != "utf8" \
            and hasattr(_fluxo, "reconfigure"):
        _fluxo.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTOS_DIR = REPO_ROOT / "experimentos"
SAIDAS_DIR = REPO_ROOT / "saidas"
DEEPLOG_DIR = SAIDAS_DIR / "deeplog"
COMPARATIVOS_DIR = EXPERIMENTOS_DIR / "comparativos"

SERIES = {
    "densidade": {
        "pasta": EXPERIMENTOS_DIR / "densidade-gpu",
        "variavel": "K",
        "titulo": "Densidade de GPU na borda",
    },
    "escala": {
        "pasta": EXPERIMENTOS_DIR / "escala-clientes",
        "variavel": "N",
        "titulo": "Escala de clientes numa GPU",
    },
}

# Ponto -> valor da variável. A ordem segue a variável crescente.
SERIE_DENSIDADE_GPU = {"K01": 1, "K02": 2, "K03": 3, "K07": 7, "K14": 14}
SERIE_ESCALA_CLIENTES = {"N01": 1, "N04": 4, "N06": 6, "N08": 8,
                         "N09": 9, "N10": 10, "N12": 12, "N14": 14}

# Rampa sequencial por experimento, pois K e N são variáveis ordenadas: laranja para a
# densidade de GPU, azul para a escala de clientes; tons mais escuros indicam mais GPUs
# ou mais clientes. O tom mais claro tem contraste de 3,11:1 com o fundo branco (mínimo
# de 3:1). Como tons vizinhos são próximos, as figuras usam também marcador e rótulo.
_RAMPA_GPUS = ["#e56e13", "#ab520e", "#7e3d0a", "#5c2c07", "#421f05"]
_RAMPA_CLIENTES = ["#5893d8", "#327bcf", "#2968b0", "#235793",
                   "#1d497c", "#183d68", "#143255", "#102946"]


def pasta_do_ponto(serie: str, valor: int) -> str:
    """Nome da pasta do ponto: 02-gpus, 08-clientes. Fonte única para Python e shell."""
    if serie == "densidade":
        return f"{valor:02d}-{'gpu' if valor == 1 else 'gpus'}"
    return f"{valor:02d}-{'cliente' if valor == 1 else 'clientes'}"


def _registrar(serie: str, pontos: dict, rampa: list) -> dict:
    registro = {}
    for i, (ponto, valor) in enumerate(pontos.items()):
        nome_pasta = pasta_do_ponto(serie, valor)
        if serie == "densidade":
            rotulo = f"{valor} de 14 servidores com GPU"
            rotulo_curto = f"{valor} GPU{'s' if valor > 1 else ''} de 14"
        else:
            rotulo = f"{valor} cliente{'s' if valor > 1 else ''} YOLO sobre 1 GPU"
            rotulo_curto = f"{valor} cliente{'s' if valor > 1 else ''}"
        pasta = SERIES[serie]["pasta"] / nome_pasta
        registro[ponto] = {
            "nome": ponto,
            "serie": serie,
            "valor": valor,
            "rotulo": rotulo,
            "rotulo_curto": rotulo_curto,
            "pasta": pasta,                        # configuração do ponto
            "experimento": pasta / "resultados",   # métricas agregadas e figuras
            "resultados": SAIDAS_DIR / SERIES[serie]["pasta"].name / nome_pasta,
            "deeplog": DEEPLOG_DIR / SERIES[serie]["pasta"].name / nome_pasta,
            "simulation_time_default": 60,
            "cor": rampa[i],
        }
    return registro


PONTOS = {**_registrar("densidade", SERIE_DENSIDADE_GPU, _RAMPA_GPUS),
          **_registrar("escala", SERIE_ESCALA_CLIENTES, _RAMPA_CLIENTES)}

# Cor fixa por aplicação, a mesma em todas as figuras. Paleta categórica segura para
# daltonismo (menor ΔE entre pares: 9,1 sob deuteranopia, 22,9 na visão normal). Duas
# cores têm contraste inferior a 3:1 com o fundo e exigem rótulo direto.
CORES_APP = {
    "YOLO_DETECTION": "#2a78d6",    # azul
    "HEALTH_APP": "#eb6834",        # laranja
    "HEAVY_COMP_APP": "#1baf7a",    # aqua
    "INFOTAINMENT_APP": "#eda100",  # amarelo
}
COR_APP_FALLBACK = "#4a3aa7"        # violeta, para aplicação fora do mapa


def cor_da_app(nome: str) -> str:
    """Cor fixa da aplicação; aplicações não mapeadas recebem o violeta."""
    return CORES_APP.get(nome, COR_APP_FALLBACK)


def ponto(codigo: str) -> dict:
    """Configuração do ponto, a partir do código (K02, N08) ou do caminho da pasta."""
    codigo = str(codigo).strip().rstrip("/")
    if codigo.upper() in PONTOS:
        return PONTOS[codigo.upper()]
    for p in PONTOS.values():
        if codigo in (str(p["pasta"]), str(p["pasta"].relative_to(REPO_ROOT)),
                      str(p["pasta"].relative_to(EXPERIMENTOS_DIR))):
            return p
    pasta = Path(codigo) if Path(codigo).is_absolute() else EXPERIMENTOS_DIR / codigo
    if not (pasta / "config.properties").is_file() and (REPO_ROOT / codigo / "config.properties").is_file():
        pasta = REPO_ROOT / codigo
    if (pasta / "config.properties").is_file() and EXPERIMENTOS_DIR.resolve() in pasta.resolve().parents:
        # Pasta de ponto registrado (./densidade-gpu/02-gpus, barras do Windows): vale o código.
        for p in PONTOS.values():
            if p["pasta"].resolve() == pasta.resolve():
                return p
        return ponto_da_pasta(pasta)
    validos = ", ".join(PONTOS)
    raise ValueError(f"Ponto inválido: {codigo}. Use um de: {validos}, "
                     "ou a pasta de um ponto em experimentos/.")


def ponto_da_pasta(pasta: Path) -> dict:
    """Ponto descrito só pela pasta de configuração, para experimentos sem código curto
    (dois-servidores, cameras-fixas e os cenários de gerar_cenario.py)."""
    rel = pasta.resolve().relative_to(EXPERIMENTOS_DIR.resolve()).as_posix()
    return {
        "nome": rel,
        "serie": rel.split("/")[0],
        "valor": None,
        "rotulo": rel,
        "rotulo_curto": rel.split("/", 1)[-1],
        "pasta": EXPERIMENTOS_DIR / rel,
        "experimento": EXPERIMENTOS_DIR / rel / "resultados",
        "resultados": SAIDAS_DIR / rel,
        "deeplog": DEEPLOG_DIR / rel,
        "simulation_time_default": 60,
        "cor": COR_APP_FALLBACK,
    }


def argumento_ponto(texto: str) -> str:
    """Tipo de argparse para --ponto: código curto (K02) ou pasta de um ponto em experimentos/."""
    import argparse
    try:
        ponto(texto)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))
    return texto.strip().upper() if texto.strip().upper() in PONTOS else texto.strip().rstrip("/")


def pontos_da_serie(serie: str) -> list:
    """Códigos dos pontos do experimento, em ordem crescente da variável."""
    return list(SERIE_DENSIDADE_GPU if serie == "densidade" else SERIE_ESCALA_CLIENTES)


def runs_da_amostra(codigo: str) -> list:
    """Pastas das execuções com status OK no manifesto do ponto (a amostra oficial)."""
    import csv
    manifesto = ponto(codigo)["experimento"] / "run_manifest.csv"
    if not manifesto.exists():
        return []
    with open(manifesto, newline="", encoding="utf-8") as f:
        return [REPO_ROOT / l["output_dir"] for l in csv.DictReader(f) if l["status"] == "OK"]


def amostra_incompleta(codigo: str) -> list:
    """Execuções do manifesto (status OK) cuja pasta de saída não existe nesta máquina.

    Os scripts que regravam tabelas, relatórios ou figuras versionados consultam esta
    lista e se recusam a gravar uma versão calculada sobre parte da amostra.
    """
    return [p for p in runs_da_amostra(codigo) if not p.is_dir()]


if __name__ == "__main__":
    # Uso pelos scripts de shell: `python3 analise/config.py K02` imprime o caminho da
    # pasta do ponto relativo a experimentos/ (densidade-gpu/02-gpus).
    import sys
    try:
        print(ponto(sys.argv[1])["pasta"].relative_to(EXPERIMENTOS_DIR).as_posix())
    except (IndexError, ValueError) as e:
        print(e if str(e) else "Uso: config.py <PONTO>", file=sys.stderr)
        sys.exit(1)
