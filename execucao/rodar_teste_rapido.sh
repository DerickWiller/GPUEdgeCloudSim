#!/bin/bash
# Verificação rápida do ambiente: compila, executa uma simulação de um ponto e valida a
# saída. A execução vai para saidas/, mas não entra no manifesto nem nas métricas
# agregadas do ponto.
#
# Uso:
#   bash execucao/rodar_teste_rapido.sh [PONTO] [SEED]      (padrão: N01, seed 1)

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_comum.sh"

resolver_ponto "${1:-N01}"
bash "$RAIZ/execucao/compilar.sh"
INICIO=$(date +%s)
SAIDA=$(bash "$RAIZ/execucao/rodar_simulacao.sh" "$PONTO" "${2:-1}" | tail -1)
python3 "$RAIZ/analise/validar_run.py" --ponto "$PONTO" --output-dir "$SAIDA" \
    --start-time "$INICIO"
