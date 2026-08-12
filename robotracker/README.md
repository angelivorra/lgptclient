# robotracker

Editor/reproductor táctil de canciones [LittleGPTracker](https://github.com/djdiskmachine/LittleGPTracker)
(LGPT) con UI Kivy: 8 canales, pantalla completa, scroll cinético y tap,
pensado para PC Linux y la Odin 2 Portal.

Comparte el motor con `../sinte` (mismo repo): `lgpt_engine.py` para el
audio, `lgpt_parser.py` para leer `lgptsav.dat` y `lgpt_writer.py` para
guardarlo, así que lo que se edita aquí es exactamente lo que reproduce la
Pi. Pantallas estilo Piggy: **SONG** (256×8 chains) → **CHAIN** (16 steps)
→ **PHRASE** (16 steps: nota/instr/fx1/fx2).

## Archivos

- `robotracker.py` — app Kivy (toolbar: play/stop, canción, pantallas,
  contexto, BPM, octava, guardar).
- `pattern_editor.py` — widget del editor (canvas puro, scroll por píxeles
  con inercia, rueda de ratón, tap = cursor).
- `lgpt_model.py` — `SongView` / `ChainView` / `PhraseView` sobre los arrays
  del parser, con setters para la edición en memoria.
- `player.py` — `Engine` + stream `sounddevice` perezoso (sin tarjeta de
  audio la UI abre igual).
- `sinte_bridge.py` — puente `sys.path` hacia `../sinte` (si sinte se mueve,
  se toca solo aquí).

## Uso

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # Kivy compila desde fuente (~5 min)
.venv/bin/python robotracker.py             # canciones de ../sinte/songs
.venv/bin/python robotracker.py --songs /ruta/a/canciones
```

Controles:

- **Espacio** = play/pausa, **Stop** = parar; **`<`/`>`** = cambiar canción.
- **F3/F4/F5** o botones = pantalla Song/Chain/Phrase (al bajar de pantalla
  se arrastra la fila/step del cursor, estilo Piggy).
- Edición (PHRASE): piano **Z S X D C V G B H N J M** (octava actual) y
  **Q 2 W 3 E R 5 T 6 Y 7 U** (octava+1) en la columna de nota; hex de dos
  dígitos en instrumento y en los índices de SONG/CHAIN; **F1/F2** = octava;
  **Supr/Retroceso** = borrar celda.
- Edición de fx (fx1/fx2): una **letra** salta al primer comando que empieza
  por ella (repetir cicla: VOLM, KILL, DLAY, LEGA, TABL, STOP, HOP, MDCC,
  MDPG, MVEL); los **dígitos** teclean el param hex de 4 posiciones (tras un
  dígito, a-f también valen como hex); Supr limpia el fx.
- **Insert** en una celda vacía de SONG/CHAIN crea una chain/phrase nueva;
  en PHRASE se crean solas al editar un hueco `--` (estilo Piggy).
- **Ctrl+S** o botón Save = guardar `lgptsav.dat` (backup automático en
  `.dat.bak`). El `*` junto al nombre indica cambios sin guardar.
- Flechas/Tab = cursor, tap = cursor, arrastre/rueda = scroll.

En PC arranca a pantalla completa (el tamaño ventana 1280×720 queda como
respaldo); en Android/Odin va fullscreen de serie.

## Pendiente

- Pad táctil de notas/fx para la Odin (sin teclado físico).
- Deploy a Odin 2 (buildozer/p4a).
