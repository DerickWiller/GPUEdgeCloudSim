#!/bin/bash
# Compila o simulador: as fontes de GPUEdgeCloudSim/src, com os JARs de
# GPUEdgeCloudSim/lib, geram as classes em GPUEdgeCloudSim/bin.
#
# Uso: bash execucao/compilar.sh

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_comum.sh"

mkdir -p "$SIMULADOR/bin"
find "$SIMULADOR/bin" -name '*.class' -delete

mapfile -t FONTES < <(find "$SIMULADOR/src" -name '*.java')
echo "Compilando ${#FONTES[@]} fontes Java"
javac -encoding UTF-8 -nowarn -d "$SIMULADOR_JAVA/bin" -cp "$SIMULADOR_JAVA/lib/*" "${FONTES[@]}"
echo "OK: $(find "$SIMULADOR/bin" -name '*.class' | wc -l) classes em GPUEdgeCloudSim/bin"
