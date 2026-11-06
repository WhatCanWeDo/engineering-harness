#!/bin/sh
# Bootstrap only; installation logic lives in setup_knowledge.py.
set -eu
SETUP_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SETUP_OFFLINE=0
for arg in "$@"; do
  case "$arg" in
    --offline) SETUP_OFFLINE=1 ;;
    --help|-h)
      cat <<'HELP'
Usage: sh scripts/setup.sh [--offline] [--lexical-only]
       [--model-dir PATH] [--mode semantic|hybrid|lexical]
       [--agents codex|claude|both] [--home PATH] [--skip-skills]
Installs managed Python 3.12, locked dependencies, a local model, all skills,
native adapters and managed instruction blocks. Existing knowledge is not transferred.
macOS/Linux/WSL; no sudo or shell profile changes. Run inside a copied/cloned repo.
--offline requires cached uv, Python, packages and an existing model bundle.
HELP
      exit 0 ;;
  esac
done
case "$(uname -s)" in Darwin|Linux) ;; *) echo 'Use macOS, Linux or WSL; native Windows bootstrap is not provided.' >&2; exit 2;; esac
if [ -x "$SETUP_ROOT/.harness/bin/uv" ]; then
  SETUP_UV="$SETUP_ROOT/.harness/bin/uv"
elif command -v uv >/dev/null 2>&1; then
  SETUP_UV=$(command -v uv)
else
  if [ "$SETUP_OFFLINE" = 1 ]; then echo 'Offline setup needs an installed uv.' >&2; exit 2; fi
  command -v curl >/dev/null 2>&1 || { echo 'Install curl or uv, then rerun setup.' >&2; exit 2; }
  mkdir -p "$SETUP_ROOT/.harness/bin"
  SETUP_INSTALLER=$(mktemp)
  trap 'rm -f "$SETUP_INSTALLER"' EXIT HUP INT TERM
  curl --proto '=https' --tlsv1.2 -fsSL https://astral.sh/uv/0.12.5/install.sh -o "$SETUP_INSTALLER"
  UV_UNMANAGED_INSTALL="$SETUP_ROOT/.harness/bin" sh "$SETUP_INSTALLER"
  rm -f "$SETUP_INSTALLER"
  trap - EXIT HUP INT TERM
  SETUP_UV="$SETUP_ROOT/.harness/bin/uv"
fi
# Do not install Python launchers into the user's PATH.
if [ "$SETUP_OFFLINE" = 1 ]; then
  "$SETUP_UV" python install 3.12 --no-bin --offline
else
  "$SETUP_UV" python install 3.12 --no-bin
fi
SETUP_PYTHON=$("$SETUP_UV" python find 3.12 --managed-python --no-project --system)
exec "$SETUP_PYTHON" "$SETUP_ROOT/scripts/setup_knowledge.py" --uv "$SETUP_UV" "$@"
