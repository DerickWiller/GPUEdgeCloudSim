#!/bin/bash
# Executa a bateria de um ponto: NUM_RUNS simulações com sementes consecutivas, cada uma
# validada por analise/validar_run.py. As pastas da bateria são listadas em
# saidas/<experimento>/<ponto>/bateria_<data>_<hora>.txt. A bateria não altera a amostra
# oficial do ponto: para que ela passe a sê-la, publica-se o manifesto explicitamente com
# analise/publicar_manifest.py --lista <arquivo>, comando impresso ao final.
#
# Uso:
#   bash execucao/rodar_experimento.sh <PONTO> [NUM_RUNS] [SEED_INICIAL]
# Exemplos:
#   bash execucao/rodar_experimento.sh K02            # 30 execuções, sementes 1 a 30
#   bash execucao/rodar_experimento.sh N08 10 100     # 10 execuções, sementes 100 a 109

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_comum.sh"

[ $# -ge 1 ] || { sed -n '2,11p' "$0"; exit 1; }
resolver_ponto "$1"
NUM_RUNS="${2:-30}"
SEED_INICIAL="${3:-1}"
garantir_compilado

OK=0; FALHAS=0
INICIO=$(date +%s)
LISTA="$RAIZ/saidas/$PASTA_PONTO/bateria_$(date -d "@$INICIO" +%Y%m%d_%H%M%S).txt"
mkdir -p "$(dirname "$LISTA")"
: > "$LISTA"
for i in $(seq 1 "$NUM_RUNS"); do
    SEED=$((SEED_INICIAL + i - 1))
    INICIO_RUN=$(date +%s)
    echo "[$i/$NUM_RUNS] $PONTO seed $SEED"
    if SAIDA=$(bash "$RAIZ/execucao/rodar_simulacao.sh" "$PONTO" "$SEED" | tail -1) \
       && echo "${SAIDA#$RAIZ/}" >> "$LISTA" \
       && python3 "$RAIZ/analise/validar_run.py" --ponto "$PONTO" \
              --output-dir "$SAIDA" --start-time "$INICIO_RUN"; then
        OK=$((OK + 1))
    else
        FALHAS=$((FALHAS + 1))
        echo "  falha na simulação ou na validação da seed $SEED" >&2
    fi
done

DURACAO=$(( $(date +%s) - INICIO ))
echo "$PONTO: $OK de $NUM_RUNS execuções válidas em $((DURACAO / 60)) min $((DURACAO % 60)) s"
echo "Execuções listadas em ${LISTA#$RAIZ/}. Para torná-las a amostra oficial do ponto:"
echo "  python3 analise/publicar_manifest.py --ponto $PONTO --lista ${LISTA#$RAIZ/}"
[ "$FALHAS" -eq 0 ]
