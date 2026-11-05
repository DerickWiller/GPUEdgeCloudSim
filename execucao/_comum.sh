#!/bin/bash
# Definições comuns aos scripts de execução: raiz do repositório, classpath do
# simulador e resolução do código de um ponto (K02, N08) na sua pasta de configuração.

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SIMULADOR="$RAIZ/GPUEdgeCloudSim"
CLASSE_PRINCIPAL="gpuedgecloudsim.core.GpuSimulationMain"
# No Git Bash (Windows), o Java recebe caminhos no formato C:/... e separa o classpath
# com ";"; no Linux, com ":".
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) SIMULADOR_JAVA="$(cygpath -m "$SIMULADOR")"; SEP=";" ;;
    *)                    SIMULADOR_JAVA="$SIMULADOR"; SEP=":" ;;
esac
CLASSPATH_SIM="$SIMULADOR_JAVA/bin$SEP$SIMULADOR_JAVA/lib/*"

# No Windows, python3 pode ser apenas o atalho da Microsoft Store, que não executa scripts.
if python3 -c "" >/dev/null 2>&1; then
    PYTHON=python3
elif python -c "import sys; sys.exit(sys.version_info < (3, 8))" >/dev/null 2>&1; then
    PYTHON=python
else
    echo "Python 3 não encontrado (python3 ou python)" >&2
    exit 1
fi

# Define SERIE, PASTA_PONTO (relativa a experimentos/) e CONFIG_DIR. A correspondência
# entre código (K02, N08) e pasta vem de analise/config.py, fonte única.
resolver_ponto() {
    PONTO="${1^^}"
    PASTA_PONTO="$("$PYTHON" "$RAIZ/analise/config.py" "$PONTO")" || return 1
    SERIE="${PASTA_PONTO%%/*}"
    CONFIG_DIR="$RAIZ/experimentos/$PASTA_PONTO"
    if [ ! -f "$CONFIG_DIR/config.properties" ]; then
        echo "Configuração não encontrada: $CONFIG_DIR" >&2
        return 1
    fi
}

# Recompila se não houver classes ou se alguma fonte for mais nova que a compilação.
garantir_compilado() {
    local marca="$SIMULADOR/bin/gpuedgecloudsim/core/GpuSimulationMain.class"
    if [ ! -f "$marca" ] || [ -n "$(find "$SIMULADOR/src" -name '*.java' -newer "$marca" -print -quit)" ]; then
        bash "$RAIZ/execucao/compilar.sh"
    fi
}
