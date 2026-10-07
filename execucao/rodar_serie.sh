#!/bin/bash
# Executa a bateria de todos os pontos de um experimento, em sequência. A falha de um
# ponto não interrompe os seguintes; os pontos com falha são listados ao final.
#
# A execução em paralelo foi medida e não reduziu o tempo total: o gargalo é a escrita
# em disco, não a CPU, e cada JVM ocupa cerca de 2 GB de memória.
#
# Uso:
#   bash execucao/rodar_serie.sh <densidade|escala> [NUM_RUNS] [SEED_INICIAL]

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_comum.sh"

case "${1:-}" in
    densidade) PONTOS=(K01 K02 K03 K07 K14) ;;
    escala)    PONTOS=(N01 N04 N06 N08 N09 N10 N12 N14) ;;
    *) sed -n '2,8p' "$0"; exit 1 ;;
esac

COM_FALHA=()
for p in "${PONTOS[@]}"; do
    bash "$RAIZ/execucao/rodar_experimento.sh" "$p" "${2:-30}" "${3:-1}" || COM_FALHA+=("$p")
done
if [ ${#COM_FALHA[@]} -gt 0 ]; then
    echo "Pontos com alguma execução falha: ${COM_FALHA[*]}" >&2
    exit 1
fi
