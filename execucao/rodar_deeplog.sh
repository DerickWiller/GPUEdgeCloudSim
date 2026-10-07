#!/bin/bash
# Executa NUM_SEEDS simulações de um ponto com o registro por tarefa ligado, em
# saidas/deeplog/<experimento>/<ponto>/. As métricas do SIMRESULT são médias; percentis
# e distribuições exigem a latência de cada tarefa. O registro ocupa cerca de 90 MB por
# execução.
#
# Uso:
#   bash execucao/rodar_deeplog.sh <PONTO> [NUM_SEEDS] [SEED_INICIAL]
# Exemplo:
#   bash execucao/rodar_deeplog.sh N14 10 1

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_comum.sh"

[ $# -ge 1 ] || { sed -n '2,10p' "$0"; exit 1; }
resolver_ponto "$1"
for i in $(seq 0 $(( ${2:-10} - 1 ))); do
    bash "$RAIZ/execucao/rodar_simulacao.sh" "$PONTO" $(( ${3:-1} + i )) --deeplog | tail -1
done
