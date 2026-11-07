#!/bin/sh
# Solo construye localmente: no AWS CLI, despliegues ni recursos cloud.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
case "${1:-all}" in
    all) FLAVORS="alexa admin" ;;
    alexa) FLAVORS="alexa" ;;
    admin) FLAVORS="admin" ;;
    *) echo 'Uso: build.sh [all|alexa|admin]' >&2; exit 1 ;;
esac
export PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
if [ -n "${PYTHON313:-}" ]; then
    PY=$PYTHON313
elif [ -x "$ROOT/.venv/bin/python" ]; then
    PY=$ROOT/.venv/bin/python
elif command -v python3.13 >/dev/null 2>&1; then
    PY=$(command -v python3.13)
elif command -v uv >/dev/null 2>&1; then
    PY=$(uv python find --no-python-downloads 3.13)
else
    echo 'Se requiere Python 3.13. Configure PYTHON313 con la ruta al interprete.' >&2
    exit 1
fi
"$PY" -c 'import sys; assert sys.version_info[:2] == (3,13), "Se requiere Python 3.13"'
if [ ! -x .venv/bin/python ]; then
    "$PY" -m venv .venv
fi
PY=$ROOT/.venv/bin/python
"$PY" -c 'import sys; assert sys.version_info[:2] == (3,13), "Recrear .venv con Python 3.13"'
mkdir -p build/wheels dist
# Solo wheels universales pure-Python: portables a Lambda Linux x86_64.
# Si en el futuro se necesita una extension nativa, este paso falla en vez de
# empaquetar accidentalmente un binario macOS/ARM; ver README.
if [ "${BUILD_OFFLINE:-0}" = "1" ]; then
    set -- --no-index --find-links "$ROOT/build/wheels"
else
    set --
fi
"$PY" -m pip --no-cache-dir download "$@" --require-hashes --retries 1 --only-binary=:all: \
    --platform any --implementation py --python-version 3.13 --abi none \
    -r requirements.txt -d build/wheels
"$PY" -m pip --no-cache-dir install --no-index --find-links build/wheels \
    --require-hashes --no-compile -r requirements.txt
"$PY" -m pip check
# Pruebas y sintaxis ANTES de crear los paquetes; sockets AWS prohibidos.
"$PY" -B - <<'PYTEST'
import ast
from pathlib import Path
import socket
import unittest
for path in Path('.').rglob('*.py'):
    if any(part in {'.venv', 'build', 'dist', '.local', '__pycache__'} for part in path.parts):
        continue
    ast.parse(path.read_text(), filename=str(path))
def no_network(*args, **kwargs):
    raise AssertionError("Network forbidden during tests")
socket.create_connection = no_network
socket.socket.connect = no_network
result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover('tests'))
if not result.wasSuccessful():
    raise SystemExit(1)
PYTEST
STAGE=$(mktemp -d "$ROOT/build/packages.XXXXXX")
cleanup() { "$PY" -c 'import shutil,sys; shutil.rmtree(sys.argv[1])' "$STAGE"; }
trap cleanup EXIT HUP INT TERM
for FLAVOR in $FLAVORS; do
    if [ "$FLAVOR" = "alexa" ]; then
        REQUIREMENTS=requirements.txt
    else
        REQUIREMENTS=requirements-admin.txt
    fi
    TARGET=$STAGE/$FLAVOR
    mkdir -p "$TARGET"
    "$PY" -m pip --no-cache-dir install --no-index --find-links build/wheels \
        --require-hashes --no-compile --target "$TARGET" -r "$REQUIREMENTS"
    "$PY" - "$ROOT" "$TARGET" "$FLAVOR" <<'PYCOPY'
from pathlib import Path
import shutil
import sys
root, stage = map(Path, sys.argv[1:3])
flavor = sys.argv[3]
ignore = shutil.ignore_patterns('__pycache__', '*.pyc')
if flavor == 'alexa':
    shutil.copy2(root / 'lambda_function.py', stage / 'lambda_function.py')
    for name in ('handlers', 'services'):
        shutil.copytree(root / name, stage / name, ignore=ignore)
else:
    shutil.copy2(root / 'admin_lambda_function.py', stage / 'admin_lambda_function.py')
    shutil.copytree(root / 'administration', stage / 'administration', ignore=ignore)
    (stage / 'services').mkdir()
    for name in ('__init__.py', 'validation.py', 'errors.py', 'pairing_policy.py'):
        shutil.copy2(root / 'services' / name, stage / 'services' / name)
if (stage / 'bin').exists():
    shutil.rmtree(stage / 'bin')
PYCOPY
    "$PY" -B scripts/verify_package.py "$TARGET" "$FLAVOR"
done
