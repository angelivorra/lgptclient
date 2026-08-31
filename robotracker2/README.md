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
   CONFIG            TABLE     TABLE
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
   **Ctrl+A** con selección **duplica la chain** de la celda del cursor a la
   primera chain libre con índice mayor (si no hay ninguna por encima, da la
   vuelta y usa la primera libre desde 00; copia sus 16 steps + transposes y
   apunta la celda a la copia) o pega (sin selección); **Esc** cancela.
4. **CHAIN** (`screens/chain_view.py`): la chain de la celda de SONG donde
   está el cursor (nº en la cabecera). 16 steps × 2 columnas: **phrase** y
   **transpose**. Dpad mueve (arr/abj step, izq/dcha columna), **A+dir** edita,
   **A** copia/pega/00, **B** borra; crear phrase en un hueco crea la chain si
   hace falta (estilo Piggy). Selección igual que SONG (**Ctrl+S** cicla
   libre→columnas→todo, **S** copia, **Ctrl+A** con selección **duplica la
   phrase** del step del cursor (columna PHRASE) a la primera phrase libre con
   índice mayor (o la primera libre desde 00 si no hay por encima), o pega sin
   selección) con su **propio portapapeles**
   (independiente del de SONG).

5. **PHRASE** (`screens/phrase_view.py`): la phrase del step de CHAIN (nº en la
   cabecera). 16 steps × campos **nota · instr · FX1(cmd+param) · FX2(cmd+param)**.
   Dpad mueve (arr/abj step, izq/dcha campo), **A+dir** edita (nota: ±1 semitono
   / ±octava; instr y param: ±1/±0x10; cmd: cicla comandos), **A** copia/pega/def
   por campo (portapapeles propio), **B** borra el campo. Editar un hueco crea la
   chain y la phrase (estilo Piggy). El ciclado de **comandos FX** solo ofrece los
   usados en las canciones de `songs/` (`FX_USED` en `phrase_view.py`: VOLM, KILL,
   DLAY, LEGA, TABL, STOP, MDCC, MDPG, PTCH, RTRG). Selección multicelda igual que
   SONG/CHAIN (**Ctrl+S** cicla libre→columnas→todo, **S** copia, **Ctrl+A**
   corta/pega, **Esc** cancela) con su **propio portapapeles de bloque**
   (independiente del de SONG/CHAIN y del portapapeles por campo).

   **Pintado MIDI en vivo**: si hay una interfaz **MIDI Notas** configurada en
   CONFIG (y disponible), **R2+START** activa el modo de pintar notas del
   controlador en la phrase **mientras suena** (indicador **●** rojo en la
   cabecera; se apaga con R2+START). Con play activo en PHRASE, cada nota que
   se pulse en el controlador se escribe en el **step del playhead** de la
   phrase que se está editando: nota + velocidad como comando **VOL** en el
   primer hueco de FX libre (o actualizando el VOL existente, sin pisar otros
   efectos). Escala velocidad MIDI 0-127 → volumen LGPT 0-254 (`VOL 00FF` =
   máximo). Solo pinta si la phrase que suena es la que se ve en pantalla.
   R2+START **no** toca play/stop: mientras está activo, Start sigue
   arrancando/parando la reproducción normalmente.

   **Canal de robotas** (canal 8, `robots.py`): en vez de las 6 columnas
   genéricas se muestran solo 2, con datos reales (migrado del control MIDI

   que usaba lgpt/LGPT tracker clásico):
   - **HIT** — el golpe de percusión (BOMBO/CAJA1/CAJA2/BOM+C1/BOM+C2/C1+C2,
     notas 62/63/65/64/66/67 — el mapeo real de `bin/cliente.*.json`, no el de
     NOTAS.md que ya no coincide con lo que usan las robotas) en vez de una
     nota LGPT críptica. A+dir cicla los 6 golpes; fija el instrumento a
     `ROBOT_INSTR` (0x80) sola.
   - **SCREEN** — el evento de pantalla (FX1 "MDCC ccvv", decodificado a
     "IMG 007" / "ANI 003" / "TXT 000"). **A** siempre abre el **navegador
     visual de `images/`** (`screens/image_browser.py`): elige la categoría
     — **imágenes estáticas**, **animación** o **texto sincronizado**
     (líneas de `images/002/textos`, compartido y no por canción: cada
     línea es un `value`) —, ve la miniatura real de cada entrada al pasar
     por ella, **A** entra/elige (inmediato, sin doble-tap — la vista previa
     ya es gratis al moverse), **B** vuelve/cancela. Al elegir, escribe el
     MDCC correspondiente. FX2 no se usa para esto en las canciones reales y
     queda fuera de esta vista especial (se conserva, no es editable aquí).
   - **HIT y SCREEN son independientes**: un MDCC se ejecuta cada tick
     igual con la nota vacía (verificado contra el motor de sinte:
     `_process_row_commands` no comprueba `notes[row]`, y `set_fx_cmd`/
     `set_fx_param` crean la phrase por sí solos) — así que un step puede
     llevar solo SCREEN sin HIT, sin necesidad de ningún "golpe vacío"
     inventado para mantener una nota activa.
   - **Las miniaturas son las ya renderizadas** por `bin/genera.py
     --markdown` en `ayuda_imagenes/` — el mismo fondo+icono compuesto /
     glow de texto / frame que verá el dispositivo real (el propio
     dispositivo nunca recibe `images/` crudo: Ansible ejecuta `genera.py`
     en este PC y solo sincroniza los `.bin` resultantes a
     `/home/angel/images`). Si falta la miniatura de algo nuevo, hay que
     regenerar `ayuda_imagenes/` con `bin/genera.py --markdown` — sin ella
     la entrada se sigue listando y se puede elegir, solo sin vista previa.
     Con el cursor en una fila del canal de robotas se ve la misma
     miniatura a la derecha, sola, sin abrir el navegador.
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
10. **CONFIG** (`screens/config_view.py`): selección de las **interfaces MIDI
    de entrada** (debajo de SONG en la rejilla). Dos campos editables
    (izq/dcha ciclan entre los puertos MIDI de entrada disponibles, A+izq/dcha
    salta al primero/último): **MIDI Notas** (entrada para notas) y **MIDI
    Control** (entrada para control). **No pueden ser la misma interfaz** (al
    ciclar salta al siguiente puerto distinto). **B** pone el campo a
    "(ninguna)". La selección **se persiste** en `robotracker2/config.json`
    (módulo `config`), entre ejecuciones. Si una interfaz guardada ya no
    existe al arrancar, se conserva en el fichero pero se muestra en rojo
    "(no disponible)" y se avisa con un toast al entrar en la pantalla.

**Reproducción**: **Espacio** (PC) / **Start** (Odin) arranca y vuelve a

pulsarse para parar. El **playhead** se resalta en verde: en SONG por canal
(cada canal en su fila), en CHAIN el step activo del canal de esa chain, en
PHRASE el step activo de esa phrase. El alcance depende de la pantalla:
- En **SONG** arranca desde la fila del cursor (canción completa, como LGPT).
- En **CHAIN** reproduce **solo esa chain en bucle** (el canal de esa chain,
  ignorando el resto de la canción).
- En **PHRASE** reproduce **solo esa phrase en bucle** (el canal de esa phrase,
  sin transpose ni avance de chain).

Usa el motor de `../sinte` sobre el proyecto en memoria (`player.py`), así que
refleja las ediciones sin guardar. El loop de chain/phrase lo gestiona el
propio motor (`Engine.loop_scope` en `../sinte/lgpt_engine.py`): solo se
arranca ese canal y, al terminar la chain/phrase, vuelve a su step 0.


**Mute (SONG, mientras suena)**: con **L2** mantenido, **cada pulsación nueva
de S** alterna el mute de la pista del cursor (columna atenuada + cabecera en
rojo) — se puede tocar varias veces seguidas para ir probando; una tecla
mantenida no repite el toggle sola (se ignora la autorepetición del SO). Lo
que quede al soltar **L2** es lo que se queda; soltar S no hace nada especial
por sí sola.

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
  `Supr/Retroceso` = B. **R2+START** (Ctrl derecho + Espacio) alterna el
  **pintado MIDI en vivo** en PHRASE (ver arriba).
- **Odin 2 Portal (gamepad)**: ROCKNIX (InputPlumber) oculta el mando a SDL;
  **toda la entrada la lee la app por evdev** del DualSense virtual de
  InputPlumber (`evdev_triggers.py`): cruceta y stick izquierdo = cursor,
  X = A, B = B, **L2 = navegar pantallas con dpad, R2 = selección**
  (L1/R1 valen igual), Start = play, Back = Esc. En el mando, **R2+Start**
  es el pintado MIDI en vivo.

Para adaptar a otro hardware solo se toca `controls.py`.

## Controlador MIDI del reproductor (botones + knobs)

La misma maquinaria que el mixer (sinte/midi_control.py, compartida): con la
interfaz **MIDI Control** configurada en CONFIG, el reproductor reacciona al
controlador físico y a la configuración de cada canción:

- **Botones** (`buttons` en `config.json`, por defecto el mapeo LPD8 de
  `sinte/lttileplayer.toml`): **play** arranca/para, **stop** para,
  **up/down** cambian de canción (en la pantalla de carga mueven el cursor y
  cargan), **sample1-4** disparan los pads sampler del engine (sin canción
  cargada no hacen nada).
- **Knobs** (`hw_pots` en `config.json`, por defecto CC 70-77 del canal 0):
  los targets se leen de `robotraca.json` de cada canción (`"pots"`), igual
  que en el mixer — al cambiar de canción se reconfiguran solos. Si la
  canción no define pots, los CC sueltos caen al mapeo por defecto del
  engine (1/7/10/20).
- **Al cargar la canción se aplica su `robotraca.json`**: mute, vocoder,
  presence, cantidades/mezcla de efectos (fx/fx_mix), master y volúmenes de
  pads (`pad_volume` global en `config.json`, por defecto 45).

### Pantalla EFECTOS (knobs por canción)

Encima de PADS (L2+arriba desde PADS, columna D de la cabecera). Configura
**solo los 4 knobs del LPD8: POT 1, 2, 5 y 6** (los pot3/4/7/8 no se tocan),
**por canción** — no hay configuración global. Para cada knob se define su
**canal** (1-8), su **efecto** y su **porcentaje** de mezcla dry/wet, igual
que en el mixer; se guarda en el `robotraca.json` de la canción con las
claves `"pots"` y `"fx_mix"`:

```json
{
  "pots": {"pot1": "2:acid", "pot2": "5:delay", "pot5": "0:valve"},
  "fx_mix": {"2": {"acid": 40}, "5": {"delay": 80}}
}
```

(En `"pots"`, el canal se guarda 0-7 como en el mixer; la pantalla lo
muestra 1-8. Un target multicanal tipo `"1,2:acid"` muestra el **primer**
canal y, al editarlo, queda como un solo canal.) Sin entrada en
`"fx_mix"`, el % es 100 (100% wet, como en el mixer).

Controles, estilo tracker: **arr/abj** elige knob (y baja a la fila
**GUARDAR** de abajo del todo) · **izq/dcha** cambia de columna (canal /
efecto / %) · en **CANAL**, **A+arr/abj** cicla (1-8) · en **EFECTO**, **A**
abre la **lista** de efectos (off + los del engine; arr/abj mueve, **A**
elige, **B** cierra) · en **%**, **A+izq/dcha** fino (±1) y **A+arr/abj**
de 10 en 10 · **A sobre GUARDAR** guarda. Los cambios quedan **en
memoria** (los targets del MIDI y el fx_mix se aplican en vivo al engine) y
solo se persisten al guardar, igual que PADS: con A sobre la fila GUARDAR o
al **Guardar la canción**. Con knobs sin guardar, cambiar de canción o
salir pide confirmación igual que con el lgptsav.dat. El efecto "off"
borra el target del knob.

### Pantalla PADS (pads sampler por canción)

A la izquierda de SONG (L2+izquierda desde SONG). Los pads **no tienen
configuración global: solo la de cada canción**. Cada canción define los
suyos en su `robotraca.json`, clave `"pads"` (nombres resueltos contra la
**biblioteca de pads**, `pads/` en la raíz del repo — en la Odin
`/storage/pads` —, con subcarpetas como `"Distorted metal/Dip Spit.wav"`)
junto al `"pad_volume"` por pad ya existente:

```json
{
  "pads": {"1": "abduccion.wav", "2": "Kick 10.wav", "4": "risa.wav"},
  "pad_volume": {"1": 27, "2": 14, "3": 42, "4": 55}
}
```

Controles de la pantalla: **arr/abj** elige pad (y baja a la fila
**GUARDAR** de abajo del todo) · **izq/dcha** volumen ±5 · **A** abre el
navegador de la biblioteca de pads (enseña solo `pads/`, no la biblioteca
general de samples; asigna el WAV elegido sin copiarlo) · **B** quita la
asignación. Los cambios quedan **en memoria** (suenan al momento sobre el
engine) y solo se persisten al guardar: con **A sobre la fila GUARDAR**, o
al **Guardar la canción** (menú PROJECT o el diálogo de cambios sin
guardar). Con pads sin guardar, cambiar de canción o salir pide
confirmación igual que con el lgptsav.dat.

Los pads **suenan aunque la canción no se esté reproduciendo**: su voz se
renderiza en el callback del stream de audio, que se crea perezosamente al
primer disparo de un pad (sin reproducir nada).

Semántica: sin clave `"pads"`, los pads de la canción están **vacíos** (no
se cae a ningún banco global). El mixer conserva su propio banco
(`wavs/pads.json`), independiente y sin efecto en robotracker2.

`buttons`, `hw_pots` y `pad_volume` globales solo se editan a mano en
`config.json` (la pantalla CONFIG edita las interfaces). La lógica vive en
`sinte/midi_control.py`, importada vía `sinte_bridge.py`.

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

Se instala como *port* de EmulationStation. ROCKNIX gestiona el mando con
InputPlumber: **agarra (grab) el mando AYN integrado y lo oculta a SDL**
(reglas udev dinámicas), así que el joystick nativo de Kivy no ve nada. Lo que
InputPlumber expone es un **DualSense virtual** (uhid) que recibe toda la
entrada traducida del mando (cruceta, sticks, botones, gatillos); con el
perfil por defecto su teclado virtual no emite nada. Por eso la app, con
`ROBOTRACKER2_EVDEV_GAMEPAD=1` (la pone el launcher), lee **toda la entrada
por evdev crudo** del DualSense virtual (`evdev_triggers.py`: hat=cruceta,
ejes=stick/gatillos con umbral, BTN_*=botones) y desactiva el joystick
nativo: **cruceta o stick izquierdo → cursor**, **X → A**, **B → B**,
**L2 → navegar pantallas con dpad**, **R2 → selección** (L1/R1 valen
igual), **Start → play**, **Back → Esc**. En el mando, **R2+Start** es
el pintado MIDI en vivo. gptokeyb quedó descartado: traducía los gatillos a
Ctrl por teclado, pero solo si SDL reconocía el DualSense virtual como
gamecontroller (depende de una db de mapeos), y con el mando oculto a SDL
no hay nada que reconocer.
Para depurar la entrada queda `odin/keylog_test.sh` + `odin/keylog.py`
(registran teclado y joystick nativo, más la lectura cruda evdev del mando,
del DualSense virtual y de los teclados virtuales).
El launcher `odin/Robotracker2.sh` fuerza fullscreen (Sway),
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
| `config.py` | Configuración global persistente (interfaces MIDI) en `config.json` |
| `midi_input.py` | Entrada MIDI de notas (hilo daemon → cola) para el pintado en vivo |
| `songs.py` | `find_songs` / `display_name` / `load_project` |
| `navmap.py` | Rejilla de pantallas LGPT + `neighbor()` (navegación) |
| `controls.py` | Botones lógicos + perfiles teclado (PC) / gamepad (Odin) |
| `lgpt_model.py` | Modelo LGPT (SongView/ChainView/PhraseView) sobre sinte |
| `sinte_bridge.py` | Puente a `../sinte` (parser + engine) |
| `robots.py` | Constantes canal de robotas: golpes reales, MDCC↔`images/` |
| `screens/load_song.py` | Pantalla de cargar canción |
| `screens/editor.py` | Editor: cabecera S C P I + contenido por pantalla + toast |
| `screens/song_view.py` | Rejilla SONG 256×8 (canvas) |
| `screens/chain_view.py` | Chain: 16 steps × phrase/transpose (canvas) |
| `screens/phrase_view.py` | Phrase: 16 steps × nota/instr/fx1/fx2 (canal 8: HIT/SCREEN) |
| `screens/groove_view.py` | Groove: 16 steps de ticks, 32 grooves (canvas) |
| `screens/table_view.py` | Table: 16 filas × 3 FX (canvas) |
| `screens/instrument_view.py` | Instrument: menú de parámetros (canvas) |
| `screens/sample_browser.py` | Navegador de samples (escuchar/importar) |
| `screens/image_browser.py` | Navegador visual de `images/` (evento de pantalla) |
| `screens/project_view.py` | Menú PROJECT (tempo/master/load/save/exit) |
| `screens/config_view.py` | Menú CONFIG (interfaces MIDI de entrada) |
| `screens/confirm.py` | Diálogo modal de cambios sin guardar |

