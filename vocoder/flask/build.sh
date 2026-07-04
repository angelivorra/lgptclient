#!/usr/bin/env bash
# Precompila el JSX del panel del vocoder (src/robot.jsx) a static/robot.js.
# Runtime "classic": las libs UMD exponen React/ReactDOM/MaterialUI como globales.
#
# La toolchain de Babel se instala UNA vez en la raíz del repo (node_modules/, en
# .gitignore, fuera de vocoder/, así el deploy no la copia). Babel resuelve el preset
# subiendo por los directorios padre hasta esa node_modules.
#
#   npm install                # una vez, en la raíz del repo
#   vocoder/flask/build.sh     # luego: git add vocoder/flask/static/robot.js && git commit
set -euo pipefail
cd "$(dirname "$0")"

BABEL="../../node_modules/.bin/babel"
if [ ! -x "$BABEL" ]; then
  echo "Falta la toolchain de Babel. Ejecuta 'npm install' en la raíz del repo." >&2
  exit 1
fi

"$BABEL" src/robot.jsx --config-file "$PWD/babel.config.json" -o static/robot.js
echo "OK -> vocoder/flask/static/robot.js ($(wc -c < static/robot.js) bytes)"
