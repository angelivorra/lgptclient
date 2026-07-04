#!/usr/bin/env bash
# Precompila el JSX del panel (src/robot.jsx) a JS plano servible en static/robot.js.
#
# Runtime "classic" (el por defecto de @babel/preset-react en Babel 7): las libs se
# cargan como UMD y exponen React/ReactDOM/MaterialUI como globales, así que el JSX
# transpila a React.createElement (NO al jsx-runtime).
#
# La toolchain de Babel se instala UNA vez en la raíz del repo (node_modules/, que
# está en .gitignore y fuera de flaskr/, así el deploy no la copia). Babel resuelve
# el preset subiendo por los directorios padre hasta esa node_modules.
#
#   npm install            # una vez, en la raíz del repo
#   flaskr/build.sh        # luego: git add flaskr/static/robot.js && git commit
set -euo pipefail
cd "$(dirname "$0")"

BABEL="../node_modules/.bin/babel"
if [ ! -x "$BABEL" ]; then
  echo "Falta la toolchain de Babel. Ejecuta 'npm install' en la raíz del repo." >&2
  exit 1
fi

"$BABEL" src/robot.jsx --config-file "$PWD/babel.config.json" -o static/robot.js
echo "OK -> flaskr/static/robot.js ($(wc -c < static/robot.js) bytes)"
