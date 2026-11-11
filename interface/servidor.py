#!/usr/bin/env python3
"""Servidor local da interface do GPUEdgeCloudSim.

Serve a tela (interface/web/) em http://127.0.0.1:<porta> e uma API em JSON que lê os
experimentos e as saídas do repositório e dispara os scripts de execucao/. Não contém lógica
de simulação nem de análise própria: as baterias rodam execucao/rodar_simulacao.sh e são
validadas por analise/validar_run.py, como no terminal. Usa só a biblioteca padrão.

Uso: bash execucao/interface.sh [porta]
"""

import atexit
import csv
import io
import json
import math
import os
import platform
import re
import shutil
import signal
import statistics
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

RAIZ = Path(__file__).resolve().parent.parent
WEB = Path(__file__).resolve().parent / "web"
sys.path.insert(0, str(RAIZ / "analise"))
sys.path.insert(0, str(RAIZ / "experimentos"))
import config  # noqa: E402
from estatistica import ic95  # noqa: E402
import gerar_cenario as gc  # noqa: E402
from validar_run import localizar_arquivos, validar, verificar_metricas  # noqa: E402

EXP = config.EXPERIMENTOS_DIR
SAIDAS = config.SAIDAS_DIR
BASH = os.environ.get("GPU_BASH") or shutil.which("bash") or "bash"
WINDOWS = platform.system() == "Windows"
NOME_VALIDO = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")



def _memoria_gb() -> float:
    try:
        if WINDOWS:
            import ctypes

            class Mem(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = Mem()
            m.dwLength = ctypes.sizeof(Mem)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.ullTotalPhys / 2 ** 30
        for linha in open("/proc/meminfo", encoding="utf-8"):
            if linha.startswith("MemTotal"):
                return int(linha.split()[1]) / 2 ** 20
    except Exception:
        pass
    return 0.0


def _executar(cmd: list, timeout=10) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=RAIZ)
        return (r.stdout + r.stderr).strip()
    except Exception:
        return ""


def ambiente() -> dict:
    mem = _memoria_gb()
    java = _executar(["java", "-version"]).splitlines()
    branch = _executar(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    compilado = (RAIZ / "GPUEdgeCloudSim/bin/gpuedgecloudsim/core/GpuSimulationMain.class").exists()
    # rodar_simulacao.sh reserva 2 GB de heap por execução (-Xms2g); reservam-se 2 GB ao sistema.
    paralelo = max(1, min(os.cpu_count() or 1, int((mem - 2) / 2))) if mem else 2
    return {"java": java[0] if java else "não encontrado", "python": platform.python_version(),
            "sistema": platform.system(), "branch": branch, "compilado": compilado,
            "memoria_gb": round(mem, 1), "paralelo_max": paralelo}



_cache = {}


def _ler_simresult(run: Path) -> dict | None:
    """Métricas do YOLO (ou de todas as aplicações, sem YOLO) de uma execução, com cache por mtime."""
    arq = next(run.glob("*_YOLO_DETECTION_GENERIC.log"), None) or next(run.glob("*_ALL_APPS_GENERIC.log"), None)
    if arq is None:
        return None
    chave = (str(arq), arq.stat().st_mtime)
    if chave in _cache:
        return _cache[chave]
    linhas = [l for l in arq.read_text(encoding="utf-8", errors="ignore").splitlines()
              if l.strip() and not l.startswith("#")]
    try:
        c = linhas[0].split(";")
        ok, falhas = int(c[0]), int(c[1])
        m = {"latencia_ms": float(c[4]) * 1000, "processamento_ms": float(c[5]) * 1000,
             "rede_ms": float(c[6]) * 1000, "falha_pct": 100 * falhas / (ok + falhas) if ok + falhas else 0.0,
             "concluidas": ok}
    except (IndexError, ValueError):
        m = None
    _cache[chave] = m
    return m


def execucoes(rel: str) -> list:
    """Execuções locais do ponto, nas pastas oficiais de saída e de registro por tarefa. Com a
    mesma semente repetida, vale a mais recente, para que a média não conte uma semente duas vezes."""
    runs = []
    for base in (SAIDAS / rel, SAIDAS / "deeplog" / rel):
        if base.is_dir():
            runs += [r for r in sorted(base.iterdir()) if r.name.startswith("run_") and r.is_dir()]
    runs = [r for r in runs if _ler_simresult(r)]  # sem SIMRESULT legível, não entra
    por_semente = {}
    for r in runs:
        s = _semente(r)
        if s is None or s not in por_semente or r.stat().st_mtime > por_semente[s].stat().st_mtime:
            por_semente[s if s is not None else r] = r
    return sorted(por_semente.values())


def _semente(run: Path):
    s = run.name.rsplit("seed", 1)[-1]
    return int(s) if s.isdigit() else None


def _resumo(valores: list) -> dict | None:
    if not valores:
        return None
    n = len(valores)
    media = statistics.fmean(valores)
    return {"media": media, "ic95": ic95(valores), "n": n}


def _publicado(pasta: Path) -> dict | None:
    """Métricas da amostra oficial (resultados/metrics_by_app.csv), quando o ponto as tem."""
    arq = pasta / "resultados" / "metrics_by_app.csv"
    if not arq.exists():
        return None
    with open(arq, newline="", encoding="utf-8") as f:
        for l in csv.DictReader(f):
            if l["app"] == "YOLO_DETECTION":
                return {"latencia_ms": {"media": float(l["latency_ms"]), "ic95": float(l["latency_ic95"]),
                                        "n": int(float(l["num_runs"]))},
                        "falha_pct": {"media": float(l["failure_rate"]), "ic95": float(l["failure_rate_ic95"]),
                                      "n": int(float(l["num_runs"]))}}
    return None


def info_ponto(rel: str, valores: dict) -> dict:
    runs = execucoes(rel)
    metricas = [_ler_simresult(r) for r in runs]
    sementes = sorted({s for s in map(_semente, runs) if s is not None})
    publicado = _publicado(EXP / rel)
    local = {k: _resumo([m[k] for m in metricas]) for k in ("latencia_ms", "falha_pct", "rede_ms", "processamento_ms")}
    return {"pasta": rel, "valores": valores, "execucoes": len(metricas), "sementes": sementes,
            "local": local, "publicado": publicado,
            "figuras": sorted(p.relative_to(RAIZ).as_posix() for p in (EXP / rel / "resultados" / "figuras").glob("*.png"))}


def limites() -> dict:
    """Limites físicos do gerador, usados pelo desenho da topologia."""
    g = gc.g
    return {"clientes_por_ap": gc.CLIENTES_POR_AP, "vram": g.VRAM_FISICA, "vram_por_cliente": g.VRAM_POR_CLIENTE,
            "mem_por_quadro": g.MEM_POR_QUADRO, "fracao_yolo": {k: v / 100 for k, v in gc.CARGAS.items()},
            "max_clientes_yolo": (g.VRAM_FISICA - g.MEM_POR_QUADRO) // g.VRAM_POR_CLIENTE}


def _cenario(d: Path) -> dict | None:
    arq = d / "cenario.json"
    return gc.carregar(arq) if arq.exists() else None


def lista_experimentos() -> list:
    out = []
    for d in sorted(p for p in EXP.iterdir() if p.is_dir()):
        pontos = sorted(p.parent.relative_to(EXP).as_posix() for p in d.rglob("config.properties"))
        if not pontos:
            continue
        cen = _cenario(d)
        out.append({"nome": d.name, "titulo": (cen or {}).get("titulo") or d.name,
                    "pergunta": (cen or {}).get("pergunta", ""), "pontos": len(pontos),
                    "publicado": bool(cen and cen.get("gerado_por")), "tem_cenario": cen is not None})
    return out


def experimento(nome: str) -> dict:
    d = EXP / nome
    if not NOME_VALIDO.match(nome) or not d.is_dir():
        raise ValueError("experimento inexistente")
    cen = _cenario(d)
    mapa = {}
    variaveis = []
    if cen:
        mapa = {f"{nome}/{pasta}": valores for pasta, _, valores in gc.pontos(cen)}
        variaveis = [{"campo": v["campo"], "rotulo": v.get("rotulo", v["campo"]), "valores": v["valores"]}
                     for v in cen["variar"]]
    existentes = {p.parent.relative_to(EXP).as_posix() for p in d.rglob("config.properties")}
    # Ordem do cenário (variáveis crescentes); pastas fora dele vão ao fim, em ordem alfabética.
    pastas = [p for p in mapa if p in existentes] + sorted(existentes - set(mapa))
    figuras = sorted(p.relative_to(RAIZ).as_posix() for p in (EXP / "comparativos" / "figuras").glob("*.png")) \
        if nome in ("densidade-gpu", "escala-clientes") else []
    return {"nome": nome, "titulo": (cen or {}).get("titulo") or nome, "pergunta": (cen or {}).get("pergunta", ""),
            "publicado": bool(cen and cen.get("gerado_por")), "variaveis": variaveis,
            "pontos": [info_ponto(p, mapa.get(p, {})) for p in pastas], "figuras_comparativas": figuras}


def tabela_csv(nome: str) -> str:
    e = experimento(nome)
    buf = io.StringIO()
    campos = [v["campo"] for v in e["variaveis"]]
    w = csv.writer(buf)
    w.writerow(["ponto", *campos, "fonte", "n", "latencia_ms", "latencia_ic95_ms", "falha_pct"])
    for p in e["pontos"]:
        fonte, m = ("publicado", p["publicado"]) if p["publicado"] else ("local", p["local"])
        lat, fal = m.get("latencia_ms"), m.get("falha_pct")
        w.writerow([p["pasta"], *[p["valores"].get(c, "") for c in campos], fonte,
                    lat["n"] if lat else 0, f"{lat['media']:.4f}" if lat else "",
                    f"{lat['ic95']:.4f}" if lat else "", f"{fal['media']:.4f}" if fal else ""])
    return buf.getvalue()



class Bateria:
    """Execuções de um ou mais pontos com sementes consecutivas, `paralelo` de cada vez, cada uma
    por execucao/rodar_simulacao.sh e validada por analise/validar_run.py."""

    def __init__(self, pontos: list, de: int, ate: int, paralelo: int, deeplog: bool):
        self.id = uuid.uuid4().hex[:8]
        self.pontos, self.de, self.ate = pontos, de, ate
        self.deeplog, self.paralelo = deeplog, paralelo
        self.criada = time.time()
        self.itens = {(p, s): {"estado": "fila"} for p in pontos for s in range(de, ate + 1)}
        self.parar = False
        self.processos = {}
        self.trava = threading.Lock()
        carimbo = time.strftime("%Y%m%d_%H%M%S")
        self.listas = {}
        for p in pontos:
            base = SAIDAS / ("deeplog" if deeplog else "") / p
            base.mkdir(parents=True, exist_ok=True)
            self.listas[p] = base / f"bateria_{carimbo}.txt"
            if not deeplog:
                self.listas[p].write_text("", encoding="utf-8")
        threading.Thread(target=self._iniciar, daemon=True).start()

    def _iniciar(self):
        # Compila uma vez antes das execuções: em paralelo, cada rodar_simulacao.sh poderia
        # recompilar sobre o mesmo bin/ ao mesmo tempo.
        r = subprocess.run([BASH, "-c", "source execucao/_comum.sh && garantir_compilado"], cwd=RAIZ,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            for e in self.itens.values():
                e.update(estado="falha", inicio=time.time(), fim=time.time(),
                         msg="compilação falhou: " + (r.stdout + r.stderr).strip()[-300:])
            return
        for _ in range(self.paralelo):
            threading.Thread(target=self._trabalhar, daemon=True).start()

    def comando(self) -> str:
        n = self.ate - self.de + 1
        alvo = self.pontos[0] if len(self.pontos) == 1 else "$p"
        cmd = (f"bash execucao/rodar_experimento.sh {alvo} {n} {self.de}" if not self.deeplog else
               f"for s in $(seq {self.de} {self.ate}); do bash execucao/rodar_simulacao.sh {alvo} $s --deeplog; done")
        return cmd if len(self.pontos) == 1 else f"for p in {' '.join(self.pontos)}; do {cmd}; done"

    def _proxima(self):
        with self.trava:
            for chave, e in self.itens.items():
                if e["estado"] == "fila" and not self.parar:
                    e.update(estado="rodando", inicio=time.time())
                    return chave
        return None

    def _trabalhar(self):
        while (chave := self._proxima()) is not None:
            try:
                self._executar_item(chave)
            except Exception as erro:  # a thread não pode morrer com o item em "rodando"
                self.itens[chave].update(estado="falha", fim=time.time(), msg=f"{type(erro).__name__}: {erro}")

    def _executar_item(self, chave):
        ponto, s = chave
        e = self.itens[chave]
        cmd = [BASH, "execucao/rodar_simulacao.sh", ponto, str(s)] + (["--deeplog"] if self.deeplog else [])
        opcoes = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {"start_new_session": True}
        with self.trava:
            if self.parar:
                e.update(estado="parada", fim=time.time())
                return
            try:
                p = subprocess.Popen(cmd, cwd=RAIZ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", errors="replace", **opcoes)
            except OSError as erro:
                e.update(estado="falha", fim=time.time(), msg=str(erro))
                return
            self.processos[chave] = p
        saida, _ = p.communicate()
        self.processos.pop(chave, None)
        linhas = [l for l in saida.splitlines() if l.strip()]
        pasta = _caminho_do_shell(linhas[-1]) if linhas else None
        if self.parar:
            e.update(estado="parada", fim=time.time())
        elif p.returncode != 0 or pasta is None or not pasta.is_dir():
            e.update(estado="falha", fim=time.time(), msg=" | ".join(linhas[-3:]))
        else:
            e.update(self._validar(ponto, pasta, e["inicio"]), fim=time.time(),
                     saida=Path(os.path.relpath(pasta, RAIZ)).as_posix())

    def _validar(self, ponto: str, pasta: Path, inicio: float) -> dict:
        if self.deeplog:
            # O registro por tarefa altera deep_file_log_enabled; confere-se só a coerência das métricas.
            simresult = localizar_arquivos(pasta)["simresult"]
            if simresult is None:
                return {"estado": "falha", "msg": "SIMRESULT ausente"}
            ok, msg = verificar_metricas(simresult)
            return {"estado": "ok" if ok else "falha", "msg": msg}
        r = validar(ponto, pasta, inicio)
        if r["status"] == "OK":
            with self.trava, open(self.listas[ponto], "a", encoding="utf-8") as f:
                f.write(Path(os.path.relpath(pasta, RAIZ)).as_posix() + "\n")
        return {"estado": "ok" if r["status"] == "OK" else "falha", "msg": "; ".join(r["notas"])}

    def interromper(self):
        with self.trava:
            self.parar = True
            for e in self.itens.values():
                if e["estado"] == "fila":
                    e.update(estado="parada", inicio=time.time(), fim=time.time())
            processos = list(self.processos.values())
        for p in processos:
            try:
                if WINDOWS:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
                else:
                    os.killpg(p.pid, 15)
            except Exception:
                pass

    def estado(self) -> dict:
        duracoes = [e["fim"] - e["inicio"] for e in self.itens.values() if e["estado"] == "ok"]
        contagem = {}
        for e in self.itens.values():
            contagem[e["estado"]] = contagem.get(e["estado"], 0) + 1
        faltam = contagem.get("fila", 0) + contagem.get("rodando", 0)
        estimativa = (statistics.median(duracoes) * math.ceil(faltam / self.paralelo)) if duracoes and faltam else None
        agora = time.time()
        return {"id": self.id, "pontos": self.pontos, "deeplog": self.deeplog, "paralelo": self.paralelo,
                "comando": self.comando(), "contagem": contagem, "estimativa_s": estimativa,
                "terminada": faltam == 0, "parada": self.parar,
                "listas": {} if self.deeplog else {p: Path(os.path.relpath(l, RAIZ)).as_posix() for p, l in self.listas.items()},
                "itens": [{"ponto": p, "semente": s, "estado": e["estado"], "msg": e.get("msg", ""),
                           "decorrido_s": (e.get("fim") or agora) - e["inicio"] if "inicio" in e else None}
                          for (p, s), e in self.itens.items()]}


BATERIAS = {}


def _caminho_do_shell(texto: str) -> Path:
    """Caminho impresso pelo Git Bash (/c/Users/...) no formato do Windows (C:/Users/...)."""
    m = re.match(r"^/([a-zA-Z])/(.*)$", texto.strip())
    return Path(f"{m.group(1).upper()}:/{m.group(2)}") if WINDOWS and m else Path(texto.strip())


def nova_bateria(d: dict) -> Bateria:
    pontos = [str(p) for p in (d.get("pontos") or [d.get("ponto", "")])]
    for p in pontos:
        config.ponto(p)  # recusa ponto inexistente
    de, ate, paralelo = int(d.get("de", 1)), int(d.get("ate", 1)), int(d.get("paralelo", 1))
    if not pontos or not 1 <= de <= ate or (ate - de + 1) * len(pontos) > 2000 or not 1 <= paralelo <= 32:
        raise ValueError("pontos, sementes ou paralelo fora dos limites")
    b = Bateria(pontos, de, ate, paralelo, bool(d.get("deeplog")))
    BATERIAS[b.id] = b
    return b


def publicar(d: dict) -> dict:
    """Torna a bateria a amostra oficial de um ponto de cenário criado pela tela: manifesto,
    métricas agregadas e figuras do ponto. Recusa os experimentos publicados."""
    ponto, lista = str(d.get("ponto", "")), str(d.get("lista", ""))
    config.ponto(ponto)
    cen = _cenario(EXP / ponto.split("/")[0])
    if not cen or cen.get("gerado_por"):
        raise ValueError("a amostra dos experimentos publicados só muda pelo terminal")
    if not (RAIZ / lista).is_file() or not lista.startswith("saidas/"):
        raise ValueError("lista da bateria inexistente")
    py = sys.executable
    passos = [[py, "analise/publicar_manifest.py", "--ponto", ponto, "--lista", lista],
              [py, "analise/agregar_metricas.py", "--ponto", ponto],
              [py, "analise/plotar_metricas.py", "--ponto", ponto]]
    saida = []
    for cmd in passos:
        r = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace")
        saida.append("$ " + " ".join(cmd[1:]) + "\n" + "\n".join((r.stdout + r.stderr).strip().splitlines()[-4:]))
        if r.returncode != 0:
            raise ValueError("\n\n".join(saida))
    return {"saida": "\n\n".join(saida)}



def _cenario_da_tela(d: dict) -> dict:
    nome = str(d.get("nome", ""))
    if not NOME_VALIDO.match(nome):
        raise ValueError("nome deve ter de 2 a 41 caracteres: letras minúsculas, números e hífen")
    dados = {k: v for k, v in d.items() if not k.startswith("_")}
    dados.pop("gerado_por", None)
    return gc._mesclar(gc.PADRAO, dados)


def previa(d: dict) -> dict:
    r = gc.montar(_cenario_da_tela(d))
    return {"erros": r["erros"], "avisos": r["avisos"],
            "pontos": [{"pasta": p["pasta"], "valores": p["valores"], "dispositivos": p.get("dispositivos"),
                        "erros": p["erros"]} for p in r["pontos"]],
            "exemplo": r["pontos"][0]["arquivos"]["config.properties"]
            if r["pontos"] and "arquivos" in r["pontos"][0] else ""}


def criar(d: dict) -> dict:
    cen = _cenario_da_tela(d)
    destino = EXP / cen["nome"]
    if destino.exists():
        raise ValueError(f"já existe experimentos/{cen['nome']}")
    gc.montar(cen)
    salvar = {k: v for k, v in d.items() if not k.startswith("_")}
    try:
        escritos = gc.gravar(cen, destino)
    except gc.CenarioInvalido:
        shutil.rmtree(destino, ignore_errors=True)
        raise
    (destino / "cenario.json").write_text(json.dumps(salvar, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8", newline="\n")
    return {"nome": cen["nome"], "pontos": len(escritos)}



TIPOS = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml"}


class Tratador(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _origem_local(self) -> bool:
        """Aceita só pedidos com Host e Origin locais (127.0.0.1 ou localhost), para que outras
        páginas abertas no navegador não disparem baterias."""
        porta = self.server.server_address[1]
        locais = {f"127.0.0.1:{porta}", f"localhost:{porta}"}
        if self.headers.get("Host", "") not in locais:
            return False
        origem = self.headers.get("Origin")
        return origem is None or origem in {f"http://{h}" for h in locais}

    def _enviar(self, codigo: int, corpo, tipo="application/json; charset=utf-8", extra=None):
        dados = corpo if isinstance(corpo, bytes) else (
            corpo.encode("utf-8") if isinstance(corpo, str) else json.dumps(corpo, ensure_ascii=False).encode("utf-8"))
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(dados)

    def _arquivo(self, caminho: Path, raiz: Path):
        caminho = caminho.resolve()
        if raiz.resolve() not in caminho.parents or not caminho.is_file() or caminho.suffix not in TIPOS:
            return self._enviar(404, {"erro": "não encontrado"})
        self._enviar(200, caminho.read_bytes(), TIPOS[caminho.suffix])

    def do_GET(self):
        if not self._origem_local():
            return self._enviar(403, {"erro": "origem não permitida"})
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/index.html"):
                return self._arquivo(WEB / "index.html", WEB)
            if u.path.startswith("/web/"):
                return self._arquivo(WEB / u.path[5:], WEB)
            if u.path == "/arquivo":
                return self._arquivo(RAIZ / q.get("caminho", ""), EXP)
            if u.path == "/api/estado":
                return self._enviar(200, {"ambiente": ambiente(), "experimentos": lista_experimentos(),
                                          "limites": limites(),
                                          "baterias": [b.estado() for b in sorted(BATERIAS.values(), key=lambda b: -b.criada)]})
            if u.path == "/api/experimento":
                return self._enviar(200, experimento(q.get("nome", "")))
            if u.path == "/api/cenario":
                cen = _cenario(EXP / q.get("nome", ""))
                if not cen or not NOME_VALIDO.match(q.get("nome", "")):
                    return self._enviar(404, {"erro": "experimento sem cenario.json"})
                return self._enviar(200, cen)
            if u.path == "/api/tabela.csv":
                nome = q.get("nome", "")
                return self._enviar(200, tabela_csv(nome), "text/csv; charset=utf-8",
                                    {"Content-Disposition": f'attachment; filename="{nome}.csv"'})
            return self._enviar(404, {"erro": "rota desconhecida"})
        except ValueError as e:
            return self._enviar(400, {"erro": str(e)})

    def do_POST(self):
        if not self._origem_local() or not self.headers.get("Content-Type", "").startswith("application/json"):
            return self._enviar(403, {"erro": "origem ou tipo de conteúdo não permitido"})
        try:
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
            if self.path == "/api/bateria":
                return self._enviar(200, nova_bateria(d).estado())
            if self.path == "/api/bateria/parar":
                b = BATERIAS.get(str(d.get("id")))
                if not b:
                    return self._enviar(404, {"erro": "bateria inexistente"})
                b.interromper()
                return self._enviar(200, b.estado())
            if self.path == "/api/publicar":
                return self._enviar(200, publicar(d))
            if self.path == "/api/cenario/previa":
                return self._enviar(200, previa(d))
            if self.path == "/api/cenario/criar":
                return self._enviar(200, criar(d))
            return self._enviar(404, {"erro": "rota desconhecida"})
        except (ValueError, KeyError, TypeError, gc.CenarioInvalido) as e:
            return self._enviar(400, {"erro": str(e)})


def main():
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), Tratador)
    url = f"http://127.0.0.1:{porta}/"
    print(f"Interface em {url} (Ctrl+C encerra; baterias em andamento são interrompidas)")
    if os.environ.get("GPU_NAO_ABRIR") != "1":
        threading.Timer(0.8, lambda: __import__("webbrowser").open(url)).start()
    def encerrar(*_):
        for b in BATERIAS.values():
            b.interromper()
    # Ao fechar o terminal ou encerrar o servidor, as simulações, que rodam em sessões
    # próprias, também são interrompidas.
    atexit.register(encerrar)
    for sinal in ("SIGHUP", "SIGTERM"):
        if hasattr(signal, sinal):
            signal.signal(getattr(signal, sinal), lambda *_: sys.exit(0))
    try:
        servidor.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        encerrar()
        print("\nEncerrado.")


if __name__ == "__main__":
    main()
