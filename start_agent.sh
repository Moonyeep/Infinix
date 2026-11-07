#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export ZS_AGENT_ENABLED=1
export ZS_ROBLOX_ENABLED=0
export ZS_AGENT_WORKSPACE="${ZS_AGENT_WORKSPACE:-$SCRIPT_DIR}"
export ZS_AGENT_WORKSPACE_ROOTS="${ZS_AGENT_WORKSPACE_ROOTS:-$SCRIPT_DIR:${HOME}/Downloads:${HOME}/Desktop:${HOME}/Documents}"
export ZS_BRIDGE_PORT="${ZS_BRIDGE_PORT:-17613}"

# Keep downloaded tooling under the user's home directory; never use sudo or
# mutate the distribution's Python packages. This also supports Ubuntu 20.04,
# whose default `python3` is 3.8 and cannot run this project.
TOOL_HOME="${ZS_TOOL_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/zeroscript}"
UV_INSTALL_DIR="$TOOL_HOME/bin"
UV_CACHE_DIR="${ZS_UV_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/zeroscript/uv}"
mkdir -p "$UV_INSTALL_DIR" "$UV_CACHE_DIR"
UV_BIN="$(command -v uv || true)"

python_usable() {
  local candidate="$1"
  command -v "$candidate" >/dev/null 2>&1 || return 1
  "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1 || return 1
  PYTHON_BIN="$(command -v "$candidate")"
}

find_python() {
  PYTHON_BIN=""
  if [[ -n "${PYTHON:-}" ]]; then
    python_usable "$PYTHON" && return 0
    echo "Python definido em PYTHON não atende ao requisito 3.10+: ${PYTHON}" >&2
    return 1
  fi
  local candidate
  for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3 python; do
    if python_usable "$candidate"; then return 0; fi
  done
  return 1
}

ensure_uv() {
  if [[ -n "$UV_BIN" && -x "$UV_BIN" ]]; then return 0; fi
  if [[ -x "$UV_INSTALL_DIR/uv" ]]; then UV_BIN="$UV_INSTALL_DIR/uv"; return 0; fi
  local installer
  installer="$(mktemp)"
  if command -v curl >/dev/null 2>&1; then
    curl --fail --silent --show-error --location https://astral.sh/uv/install.sh -o "$installer"
  elif command -v wget >/dev/null 2>&1; then
    wget -q https://astral.sh/uv/install.sh -O "$installer"
  else
    echo "curl ou wget é necessário para obter Python 3.12 isolado. Instale um deles e tente novamente; não foi usado sudo." >&2
    rm -f "$installer"
    return 1
  fi
  echo "Instalando uv em $UV_INSTALL_DIR (somente no seu usuário; sem sudo)..."
  UV_INSTALL_DIR="$UV_INSTALL_DIR" UV_NO_MODIFY_PATH=1 sh "$installer"
  rm -f "$installer"
  UV_BIN="$UV_INSTALL_DIR/uv"
  [[ -x "$UV_BIN" ]] || { echo "A instalação isolada do uv não foi concluída." >&2; return 1; }
}

VENV="${ZS_VENV:-$SCRIPT_DIR/.venv}"
if [[ -e "$VENV" ]] && ! [[ -x "$VENV/bin/python" ]] || { [[ -x "$VENV/bin/python" ]] && ! "$VENV/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; }; then
  if [[ -n "${ZS_VENV:-}" ]]; then
    echo "ZS_VENV existente não contém Python 3.10+; escolha outro caminho em ZS_VENV. O ambiente existente não foi alterado." >&2
    exit 1
  fi
  VENV="$SCRIPT_DIR/.venv-linux"
fi
if [[ -x "$VENV/bin/python" ]] && "$VENV/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
  VENV_PYTHON="$VENV/bin/python"
else
  if find_python; then
    echo "Criando ambiente virtual local com $PYTHON_BIN: $VENV"
    if ! "$PYTHON_BIN" -m venv "$VENV"; then
      echo "Python do sistema não tem suporte a venv; vou usar Python 3.12 isolado no diretório do usuário."
      ensure_uv
      "$UV_BIN" python install 3.12
      "$UV_BIN" venv --python 3.12 "$VENV"
    fi
  else
    echo "Python 3.10+ não encontrado (este sistema pode fornecer apenas Python 3.8). Obtendo Python 3.12 isolado no seu usuário; sem sudo/alterações no sistema."
    ensure_uv
    "$UV_BIN" python install 3.12
    "$UV_BIN" venv --python 3.12 "$VENV"
  fi
  VENV_PYTHON="$VENV/bin/python"
fi

if ! "$VENV_PYTHON" -c 'import websockets' >/dev/null 2>&1; then
  echo "Instalando websockets no venv local..."
  if "$VENV_PYTHON" -m pip --version >/dev/null 2>&1; then
    "$VENV_PYTHON" -m pip install --disable-pip-version-check websockets
  else
    ensure_uv
    "$UV_BIN" pip install --python "$VENV_PYTHON" websockets
  fi
fi

if [[ "${ZS_BROWSER_ENABLED:-0}" =~ ^(1|true|yes|on)$ ]] && ! "$VENV_PYTHON" -c 'import playwright' >/dev/null 2>&1; then
  echo "ZS_BROWSER_ENABLED está ativo; instalando Playwright no venv local..."
  if "$VENV_PYTHON" -m pip --version >/dev/null 2>&1; then
    "$VENV_PYTHON" -m pip install --disable-pip-version-check playwright
  else
    ensure_uv
    "$UV_BIN" pip install --python "$VENV_PYTHON" playwright
  fi
  echo "Instalando Chromium do Playwright para o usuário..."
  "$VENV_PYTHON" -m playwright install chromium
fi

echo "Infinix Agent iniciado (Linux; Python $($VENV_PYTHON --version 2>&1 | awk '{print $2}')). Mantenha este terminal aberto."
exec "$VENV_PYTHON" bridge.py
