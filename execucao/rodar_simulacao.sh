#!/bin/bash
# Executa uma simulação de um ponto e grava a saída em
# saidas/<experimento>/<ponto>/run_<data>_<hora>_seed<N>/, com a cópia da configuração
# utilizada e o console comprimido (console.log.gz).
#
# Com --deeplog, liga o registro por tarefa (SUCCESS.log e FAIL.log), necessário para
# percentis e distribuições; a saída vai para saidas/deeplog/, fora da amostra oficial.
# A configuração versionada não é alterada: o registro é ligado numa cópia temporária.
#
# Uso:
#   bash execucao/rodar_simulacao.sh <PONTO> [SEED] [--deeplog]
# Exemplo:
#   bash execucao/rodar_simulacao.sh K02 1

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_comum.sh"

[ $# -ge 1 ] || { sed -n '2,13p' "$0"; exit 1; }
resolver_ponto "$1"
SEED="${2:-1}"
DEEPLOG="${3:-}"
garantir_compilado

CONFIG_USADA="$CONFIG_DIR"
if [ "$DEEPLOG" = "--deeplog" ]; then
    BASE="$RAIZ/saidas/deeplog/$PASTA_PONTO"
    CONFIG_USADA="$(mktemp -d)"
    trap 'rm -rf -- "${CONFIG_USADA:?}"' EXIT
    cp "$CONFIG_DIR"/config.properties "$CONFIG_DIR"/*.xml "$CONFIG_USADA/"
    sed -i 's/^deep_file_log_enabled=.*/deep_file_log_enabled=true/' "$CONFIG_USADA/config.properties"
else
    BASE="$RAIZ/saidas/$PASTA_PONTO"
fi

SAIDA="$BASE/run_$(date +%Y%m%d_%H%M%S)_seed${SEED}"
mkdir -p "$SAIDA"
echo "$PONTO, seed $SEED -> ${SAIDA#$RAIZ/}"

# O console registra cerca de 7 linhas por tarefa e é comprimido durante a execução.
# Ele e a configuração só entram na pasta de saída ao final, porque o simulador a
# esvazia ao iniciar. Cada JVM ocupa cerca de 2 GB; o limite de 6 GB acomoda o ponto
# mais carregado.
CONSOLE="$BASE/.console_${SEED}_$$.log.gz"
set +e
java -Xmx6g -Xms2g -cp "$CLASSPATH_SIM" "$CLASSE_PRINCIPAL" \
    "$CONFIG_USADA/config.properties" \
    "$CONFIG_USADA/edge_devices.xml" \
    "$CONFIG_USADA/applications.xml" \
    "$SAIDA" "$SEED" 2>&1 | gzip -1 > "$CONSOLE"
CODIGO=${PIPESTATUS[0]}
set -e
mv "$CONSOLE" "$SAIDA/console.log.gz"
cp "$CONFIG_USADA"/config.properties "$CONFIG_USADA"/*.xml "$SAIDA/"

# O simulador captura as próprias exceções e termina com código 0 mesmo em caso de erro;
# por isso a execução só é considerada bem-sucedida se os SIMRESULT existirem.
if [ "$CODIGO" -ne 0 ] || ! ls "$SAIDA"/SIMRESULT_*.log >/dev/null 2>&1; then
    echo "FALHA: a simulação não produziu SIMRESULT (código $CODIGO). Trecho do console:" >&2
    zgrep -m5 -E "Exception|Error|terminated" "$SAIDA/console.log.gz" >&2 || true
    exit 1
fi
echo "$SAIDA"
