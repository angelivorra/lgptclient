# robotracker2

Clon de la interfaz de **lgptclient**, construido pantalla por pantalla, con la
misma estética que [`robotracker`](../robotracker) (Kivy, fondo oscuro, acento
oro) y sobre el mismo motor de audio/parser de [`../sinte`](../sinte) (vía
`sinte_bridge.py`).

## Estado

1. **Cargar canción** (`screens/load_song.py`): lista vertical de las canciones
   encontradas en `../sinte/songs/`. Flechas ↑/↓ mueven la selección (con wrap),
   **A** carga la canción.
2. **Editor** (`screens/editor.py`): al cargar entra en la pantalla SONG. Las
   pantallas estilo LGPT están dispuestas en rejilla (`navmap.py`):

   ```
           PROJECT   GROOVE
   SONG    CHAIN     PHRASE    INSTRUMENT
           TABLE
   ```

   Se navega con **Ctrl+flechas** hacia la pantalla adyacente. La cabecera
   muestra el nombre de la pantalla + la canción, y a la derecha una tira fija
   **S C P I** (las 4 columnas) con la columna activa resaltada; el color indica
   la altura: **oro** = fila media, **cian** = fila de arriba (PROJECT/GROOVE),
   **magenta** = fila de abajo (TABLE), mostrando en esa celda su letra (P/G/T).
   **Esc** vuelve a la lista de canciones.

3. **SONG** (`screens/song_view.py`): parrilla 256×8 de índices de chain
   (bandas por compás/beat, cursor dorado). Cabecera con el nº de canal
   (1–6) e iconos vectoriales: micrófono en el canal 7 (voz) y robot en el 8.
   Dpad mueve el cursor, **A+dir**
   edita (±1 izq/dcha, ±0x10 arr/abj; en vacío crea chain), **B** borra.
   Portapapeles/selección estilo LGPT: **A** copia/pega/pone 00; **Ctrl+S**
   cicla selección (libre → filas → todo visible); **S** copia selección;
   **Ctrl+A** corta (con selección) o pega (sin selección); **Esc** cancela.
4. **CHAIN** (`screens/chain_view.py`): la chain de la celda de SONG donde
   está el cursor (nº en la cabecera). 16 steps × 2 columnas: **phrase** y
   **transpose**. Dpad mueve (arr/abj step, izq/dcha columna), **A+dir** edita,
   **A** copia/pega/00, **B** borra; crear phrase en un hueco crea la chain si
   hace falta (estilo Piggy). Selección igual que SONG (**Ctrl+S** cicla
   libre→columnas→todo, **S** copia, **Ctrl+A** corta/pega) con su **propio
   portapapeles** (independiente del de SONG).
5. **PHRASE** (`screens/phrase_view.py`): la phrase del step de CHAIN (nº en la
   cabecera). 16 steps × campos **nota · instr · FX1(cmd+param) · FX2(cmd+param)**.
   Dpad mueve (arr/abj step, izq/dcha campo), **A+dir** edita (nota: ±1 semitono
   / ±octava; instr y param: ±1/±0x10; cmd: cicla comandos), **A** copia/pega/def
   por campo (portapapeles propio), **B** borra el campo. Editar un hueco crea la
   chain y la phrase (estilo Piggy). El ciclado de **comandos FX** solo ofrece los
   usados en las canciones de `songs/` (`FX_USED` en `phrase_view.py`: VOLM, KILL,
   DLAY, LEGA, TABL, STOP, MDCC, MDPG, PTCH, RTRG). *(Selección multicelda:
   pendiente — por ahora solo SONG y CHAIN.)*
6. **GROOVE** (`screens/groove_view.py`): el groove seleccionado (nº en la
   cabecera), 16 steps de duración en **ticks** (0xFF = `--`). Dpad: arr/abj
   step, **izq/dcha cambia de groove** (00–1F); **A+dir** edita ticks, **A**
   copia/pega/def (6), **B** lo deja en `--`. Es global; **se guarda** (writer
   de sinte extendido para serializar GROOVES) y afecta a la reproducción.
7. **TABLE** (`screens/table_view.py`): la tabla ligada al contexto (desde
   PHRASE, la del comando TABL del step; si no, la primera existente; nº en la
   cabecera). 16 filas × **3 columnas FX** (cmd+param). Dpad mueve (arr/abj fila,
   izq/dcha campo), **A+dir** edita (cmd cicla `TABLE_FX` — los FX de tablas
   usados en songs: VOLM/PTCH/RTRG/HOP/KILL/ARPG/CRSH/filtros/PAN…; param ±),
   **A** copia/pega/def por campo, **B** borra. Se guarda (writer extendido para
   TABLES). Las dos posiciones TABLE de la rejilla abren esta vista.
8. **INSTRUMENT** (`screens/instrument_view.py`): menú moderno con scroll y los
   params útiles del instrumento (nº en cabecera): Instrument (selector), Sample,
   Volume, Pan, Fine tune, Root note, Filter cut/res/type/mode, Crush, Downsample,
   Loop, **Print FX** y **FX amount** (el efecto), Feedback mix, Table. Arr/abj
   navega, izq/dcha edita (A+izq/dcha paso grande); los enums ciclan valores y
   **se conservan** los params no editados. Al entrar **desde PHRASE va al
   instrumento del step**. En **Sample**, **A abre el navegador de samples**
   (`screens/sample_browser.py`): navega la biblioteca, **previsualiza** al pasar
   por cada .wav y **A carga** (copia el wav a la canción y lo asigna). Se guarda
   (writer extendido para INSTRUMENTBANK).
9. **PROJECT** (`screens/project_view.py`): menú reducido — **Tempo** y
   **Master** editables (izq/dcha ±1, A+izq/dcha ±10), **Load Song**,
   **Save Song** (persiste el `.dat`), **Exit**; *Compact Sequencer/Instruments*
   y *Save Song As* quedan como pendientes (toast). Arriba/abajo navegan, **A**
   activa.

**Reproducción**: **Espacio** (PC) / **Start** (Odin) arranca desde la fila del
cursor de SONG y vuelve a pulsarse para parar. El **playhead** se resalta en
verde: en SONG por canal (cada canal en su fila), en CHAIN el step activo del
canal de esa chain. Usa el motor de `../sinte` sobre el proyecto en memoria
(`player.py`), así que refleja las ediciones sin guardar.

**Mute (SONG, mientras suena)**: **L2+S** togglea el mute de la pista del
cursor (columna atenuada + cabecera en rojo). Orden de soltado, como LGPT: si
sueltas **L2 antes que S**, el cambio **queda**; si sueltas **S antes**,
**revierte** al estado anterior.

Si hay **cambios sin guardar**, al **salir** o **cargar otra canción** (o cerrar
la ventana) aparece un diálogo modal (`screens/confirm.py`) con **Guardar /
Descartar / Cancelar** (izq/dcha eligen, A confirma, B/Esc cancela).

Pendiente: CHAIN/PHRASE/INSTRUMENT/TABLE/GROOVE, el transporte de audio
(Player) y las acciones Compact/Save As.

## Controles (parametrizables)

Todo pasa por **botones lógicos** estilo LGPT (dpad, A, B, L, R, START, SELECT,
BACK) definidos en `controls.py`. Lo parametrizable es el mapeo desde el
hardware; la semántica (dpad = mover, A+dir = editar, L+dir = cambiar de
pantalla, B = borrar, START = play, BACK = volver) es fija.

- **PC (teclado)**: flechas = dpad, `A` = A, `S` = B, **`Ctrl` izquierdo = L2**
  (navegar entre pantallas con dpad; mute con S), **`Ctrl` derecho = R2**
  (selección: cut/paste, ciclar selección), `Espacio` = START, `Esc` = BACK,
  `Supr/Retroceso` = B.
- **Odin 2 Portal (gamepad)**: gptokeyb (`odin/robotracker2.gptk`) — X=A, B=B,
  **L2 = Ctrl izquierdo (navegar)**, **R2 = Ctrl derecho (selección)**,
  Start = play, Back = Esc. La app también lee joystick nativo (`controls.py`).

Para adaptar a otro hardware solo se toca `controls.py`.

## Ejecutar

Usa el venv propio (`robotracker2/.venv`, con Kivy/numpy/sounddevice). Si no
existe: `python3 -m venv robotracker2/.venv && robotracker2/.venv/bin/pip
install -r robotracker2/requirements.txt` (Kivy compila, ~5 min).

```bash
cd /home/angel/git/lgptclient
robotracker2/.venv/bin/python robotracker2/robotracker2.py [--songs RUTA]
```

En **PC arranca en ventana** (1280×720). Con `--fullscreen` (o
`ROBOTRACKER2_FULLSCREEN=1`) va a pantalla completa; así lo lanza la Odin.

## Odin 2 Portal (ROCKNIX)

Se instala como *port* de EmulationStation. En la Odin el mando se traduce a
teclado con **gptokeyb** (`odin/robotracker2.gptk`): **X → A**, **B → B**,
**R2 → Ctrl** (hombro/navegación), **dpad → cursor**, **A → play**,
**Back → Esc**. El launcher `odin/Robotracker2.sh` fuerza fullscreen (Sway),
fija densidad ×2 y reutiliza el venv y el `sinte` de robotracker
(`/storage/robotracker-venv`, `/storage/sinte`).

Instalar desde este PC (con robotracker ya instalado en la Odin):

```bash
robotracker2/odin/install.sh [usuario@]IP_de_la_odin
```

## Estructura

| Archivo | Descripción |
|---|---|
| `robotracker2.py` | App + `ScreenManager` + input de teclado global |
| `theme.py` | Colores y fuente de iconos (portados de robotracker) |
| `songs.py` | `find_songs` / `display_name` / `load_project` |
| `navmap.py` | Rejilla de pantallas LGPT + `neighbor()` (navegación) |
| `controls.py` | Botones lógicos + perfiles teclado (PC) / gamepad (Odin) |
| `lgpt_model.py` | Modelo LGPT (SongView/ChainView/PhraseView) sobre sinte |
| `sinte_bridge.py` | Puente a `../sinte` (parser + engine) |
| `screens/load_song.py` | Pantalla de cargar canción |
| `screens/editor.py` | Editor: cabecera S C P I + contenido por pantalla + toast |
| `screens/song_view.py` | Rejilla SONG 256×8 (canvas) |
| `screens/chain_view.py` | Chain: 16 steps × phrase/transpose (canvas) |
| `screens/phrase_view.py` | Phrase: 16 steps × nota/instr/fx1/fx2 (canvas) |
| `screens/groove_view.py` | Groove: 16 steps de ticks, 32 grooves (canvas) |
| `screens/table_view.py` | Table: 16 filas × 3 FX (canvas) |
| `screens/instrument_view.py` | Instrument: menú de parámetros (canvas) |
| `screens/project_view.py` | Menú PROJECT (tempo/master/load/save/exit) |
| `screens/confirm.py` | Diálogo modal de cambios sin guardar |
