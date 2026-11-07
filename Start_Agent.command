#!/usr/bin/env bash
set -u
cd "$(dirname "$0")" || exit 1
export ZS_AGENT_ENABLED=1
export ZS_ROBLOX_ENABLED=0
export ZS_AGENT_WORKSPACE="$PWD"
export ZS_AGENT_WORKSPACE_ROOTS="$PWD:$HOME/Downloads:$HOME/Desktop:$HOME/Documents"
export ZS_BRIDGE_PORT="${ZS_BRIDGE_PORT:-17613}"
PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.9+ não encontrado. Instale em https://www.python.org/downloads/"
  read -n 1 -s -r -p "Pressione uma tecla para sair..."
  exit 1
fi
if ! "$PY" -c 'import websockets' >/dev/null 2>&1; then
  echo "Instalando a dependência websockets..."
  "$PY" -m pip install --user websockets || "$PY" -m pip install --user --break-system-packages websockets
fi
echo "Infinix Agent iniciado. Mantenha esta janela aberta."
"$PY" bridge.py
status=$?
echo "Bridge encerrado com código $status"
read -n 1 -s -r -p "Pressione uma tecla para sair..."
exit "$status"
