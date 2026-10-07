#!/bin/bash
# Definições comuns aos scripts de execução: raiz do repositório, classpath do
# simulador e resolução do código de um ponto (K02, N08) na sua pasta de configuração.

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SIMULADOR="$RAIZ/GPUEdgeCloudSim"
CLASSE_PRINCIPAL="gpuedgecloudsim.core.GpuSimulationMain"
CLASSPATH_SIM="$SIMULADOR/bin:$SIMULADOR/lib/*"

# Define SERIE, PASTA_PONTO (relativa a experimentos/) e CONFIG_DIR. A correspondência
# entre código (K02, N08) e pasta vem de analise/config.py, fonte única.
resolver_ponto() {
    PONTO="${1^^}"
    PASTA_PONTO="$(python3 "$RAIZ/analise/config.py" "$PONTO")" || return 1
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
