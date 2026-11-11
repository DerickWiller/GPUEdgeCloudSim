#!/bin/bash
# Abre a interface do simulador no navegador: compila, se preciso, e sobe o servidor local
# (interface/servidor.py) em http://127.0.0.1:<porta>. As baterias disparadas pela tela
# executam os mesmos scripts deste diretório. Ctrl+C encerra o servidor.
#
# Uso:
#   bash execucao/interface.sh [PORTA]      (padrão: 8765)

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_comum.sh"
garantir_compilado

# O servidor dispara os scripts com este mesmo bash; no Windows, em formato C:\..., para não
# cair no bash.exe do WSL que fica no PATH do sistema.
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) GPU_BASH="$(cygpath -w "$BASH")" ;;
    *)                    GPU_BASH="$BASH" ;;
esac
export GPU_BASH
exec "$PYTHON" "$RAIZ/interface/servidor.py" "${1:-8765}"
