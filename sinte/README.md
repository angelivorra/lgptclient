# sinte (ROBOTRACA / lttileplayer)

Reproductor standalone de canciones de [LittleGPTracker](https://github.com/djdiskmachine/LittleGPTracker)
(LGPT / Little Piggy Tracker) para consola, pensado para una **Raspberry Pi 4
con HAT de audio** (Raspberry Pi OS Lite, arranque kiosk en HDMI), con
modulación en directo vía **MIDI CC** sobre cada uno de los 8 canales.
Estética Pip-Boy: consola verde fósforo, título ROBOTRACA y lista de
canciones a lo grande.

El motor replica el comportamiento del reproductor original (secuenciador
song → chain → phrase, 6 ticks por step sample-accurate, grooves por canal,
rampas k-rate, pan law original) limitándose a lo que usan las canciones
del proyecto.

## Archivos

- `lttileplayer.toml` — configuración fijada del sistema (audio, MIDI,
  botones, pots, delay).
- `event_server.py` — servidor TCP que emite los eventos
  (`CONFIG/SYNC/NOTA/CC/START/END`) a los clientes del robot (ver
  [CLAUDE.md](../CLAUDE.md)).
- `lgpt_setup.py` — asistente de configuración por terminal (opcional).
- `lgpt_parser.py` — parser de `lgptsav.dat` (XML plano o comprimido LZ77).
- `lgpt_writer.py` — writer de `lgptsav.dat` (XML plano, backup `.bak`);
  lo usa robotracker para guardar.
- `lgpt_engine.py` — motor de audio puro (numpy): voces, secuenciador,
  mixer. Sin dependencia de tarjeta de audio (testable headless).
- `play_stats.py` — al pulsar Play (sinte y robotracker2) escribe
  `songs/<canción>/play_stats.txt` con CPU/RAM/temp, xruns, tiempos de
  render y el coste por canal (voces vs FX) de la última pasada. Se
  sobrescribe en cada Play. `PLAY_STATS=0` lo apaga. En la pantalla de
  reproducción del sinte sale en vivo la carga del callback y los canales
  más caros (`x` = corte PortAudio, `s` = salto del DAC, `a` = bloque
  apurado).
- `lights.py` — luces DMX de la pista LUCES (canal LGPT 9): paleta,
  comandos `BRIL`/`FADE`/`STRB` y `DmxOut`, el hilo que manda la trama
  Open DMX por el cable Eurolite USB-DMX512 (ver "Luces DMX").
- `lgpt_player.py` — reproductor: UI curses retro (estética Pip-Boy),
  salida de audio con `sounddevice`, entrada/salida MIDI.
- `tests/` — tests headless (unittest/pytest).

## Dependencias

Python 3 con lo listado en `requirements.txt` (`numpy`, `soundfile`,
`sounddevice`, `mido`, `python-rtmidi`, `pyserial`; este último solo para
las luces DMX: sin él las luces se desactivan y el player suena igual). En la Pi las instala el rol de
Ansible `sintetizador-actualiza`; para probar en local:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Configuración

La configuración está fijada en `lttileplayer.toml` (incluida en el repo):

- `songs_dir`: carpeta de canciones.
- `[audio]`: salida (HAT), samplerate, blocksize, `delay` (retardo del
  audio en segundos), `record` (WAV de salida, vacío = no grabar),
  `pads_dir` (biblioteca de samples de los pads sampler, resuelve la clave
  `"pads"` del robotraca.json de cada canción; los pads no tienen
  configuración global, solo por canción).
- `[midi]`: entrada del controlador (nombre parcial, sin el nº de cliente
  ALSA que cambia entre arranques) y salida de eventos LGPT.
- `[buttons]`: 4 botones del controlador (up/down/play/stop) como
  `note:canal:nota` o `cc:canal:control`.
- `[pots]`: 8 potenciómetros `potN = { cc = "cc:canal:control",
  target = "canal:parametro" }` con `parametro` ∈ `lp_cutoff`, `lp_res`,
  `volume`, `pan`, `pitch`.

- `[luces]`: salida DMX de la pista LUCES: `puerto` (`/dev/ttyUSB0`) y
  `luces = { IZQ = 1, DER = 8 }` (nombre -> dirección DMX; el orden es el
  del campo LUZ de la phrase). `activo = false` las desactiva.

### Luces DMX

La pista LUCES (canal LGPT 9, la 10 en robotracker2) no suena: cada step
es un evento de luz que se aplica a la hora audible (con el mismo
`delay` que el audio). Por step: **nota** = color (índice de
`lights.PALETTE`: APAGA, ROJO, NARANJA, AMARILLO, VERDE, CIAN, AZUL,
VIOLETA, MAGENTA, ROSA, BLANCO, CALIDO), **instrumento** = luz (vacío = todas,
1 = la primera de `[luces]`…), y en FX1/FX2 `BRIL xx` (brillo), `FADE xx`
(fundido en xx steps) y `STRB xx` (estrobo, 00 = apagado). Cada luz
mantiene su estado hasta el siguiente cambio; STOP/fin de canción = todo
apagado. El mute no corta las luces: solo calla el audio local.

Hardware probado: cable Eurolite USB-DMX512 (FTDI FT232R, protocolo Open
DMX: 250 kbaud 8N2, break + start code 0, refresco continuo a 40 fps) y
PAR U'King 36 LED en modo DMX de 7 canales (`d001`/`d008` en su menú):
dimmer, R, G, B, estrobo, modo, velocidad. Sin cable no pasa nada: la
salida reintenta abrir el puerto cada 3 s.

Los argumentos de línea de comandos (`--songs`, `--device`, `--midi`,
`--midi-out`, `--samplerate`, `--blocksize`, `--delay`, `--record`,
`--config`) tienen prioridad sobre el archivo. Si algún día hace falta
reconfigurar, hay un asistente por terminal: `.venv/bin/python lgpt_setup.py`.

## Uso

```sh
.venv/bin/python lgpt_player.py [--record salida.wav]
```

`--record` (o `record = "ruta.wav"` en `[audio]`) graba a WAV exactamente
lo que sale por el stream (incluye el delay configurado), sin bloquear
el callback de audio.

Controles (botones MIDI o teclado):

- Lista: **arriba/abajo** para moverse (scroll infinito, 3 canciones),
  **play** reproduce, **stop** abre la pantalla de captura de botones/pots.
- Reproducción: **play** = play/pausa, **arriba/abajo** =
  anterior/siguiente canción, **stop** = volver a la lista.

Modulación en directo con los pots configurados. Cada pot tiene un
`target = canal:parametro` donde el canal es 0-7 (0 = columna 1) y el
parámetro puede ser:

| Parámetro   | Efecto                                             |
|-------------|----------------------------------------------------|
| `lp_cutoff` | Filtro low-pass del canal (barrido 40 Hz - 16 kHz) |
| `lp_res`    | Resonancia del low-pass (Q 0.5 - 10, efecto acid)  |
| `volume`    | Volumen del canal                                  |
| `pan`       | Pan del canal                                      |
| `pitch`     | Pitch del canal (±1 octava, centro en 64)          |

Si no hay pots configurados se usa el mapeo por defecto CC1=cutoff,
CC7=volumen, CC10=pan, CC20=pitch (canal MIDI 1-8 → canal tracker 0-7).

Salida MIDI: todos los eventos MIDI que genera LGPT salen por el puerto
configurado para que los recoja otro programa o sintetizador:

- Note on/off de los instrumentos MIDI (0x80-0x8F), con su canal,
  volumen (CC7 al disparar) y `note length`.
- `MDCC` (CC arbitrario), `MDPG` (program change), `VOLM` (CC7) y
  `MVEL` (velocity) cuando el canal tiene un instrumento MIDI activo.
- Al cambiar de canción o salir se envía note off de las notas activas.

Los eventos MIDI salen **en tiempo real**, al compás del secuenciador.
Si se configura `[audio] delay` (o `--delay`), solo el audio se retrasa:
útil cuando otro programa recibe el MIDI por red y suena con latencia —
el audio local se retrasa lo mismo para mantenerse sincronizado.

## App mixer (editor de robotraca.json)

La carpeta `mixer/` del repo es una app de escritorio Kivy **standalone**:
embebe este mismo engine en su proceso (crea el `Player` sin curses ni
EventServer) para probar y configurar cada canción — play/stop, mute,
canal vocoder, presence, efectos por canal, targets de los knobs, pads y
master — y guardar el resultado en el `robotraca.json`. Usa piezas de
aquí que conviene no romper:

- `Player._load_song` / `_apply_song_config` (esta última aplica también
  el campo `fx` del JSON: `{"fx": {"2": {"acid": 80}}}`, valores 0-100).
- Los eventos `mute` / `vocoder` / `presence` de `Engine.push_event`
  (cambios en vivo thread-safe con el callback de audio).
- Si un plugin LADSPA falta (PC sin swh-plugins), el canal suena en seco
  y el preset queda desactivado en vez de morir el callback de audio.

## Despliegue en la Raspberry Pi

```sh
ansible-playbook ansible/actualiza-sinte.yaml -i ansible/inventario
```

El rol `sintetizador-actualiza` (idempotente) sincroniza por rsync los
ficheros versionados del repo al sinte (sin internet, así que nada de
`git pull`), crea/actualiza el venv de `sinte/` con `requirements.txt`, y
deja el arranque configurado: **autologin en tty1** con el player a
pantalla completa (kiosk: si el proceso termina, agetty lo relanza).
Reiniciar el player equivale a reiniciar `getty@tty1.service`, que el
propio rol hace automáticamente si algo cambió.

La UI se ve en la pantalla HDMI de la Pi y se controla con los botones
MIDI (el teclado de la consola también funciona). Para capturar
pots/botones en la Pi, ejecuta allí el asistente por SSH:
`/home/angel/lgptclient/sinte/.venv/bin/python /home/angel/lgptclient/sinte/lgpt_setup.py`
(escribe el mismo `lttileplayer.toml`; reinicia el player después con
Ctrl+Alt+Supr o `sudo pkill -f lgpt_player`).

## Tests y benchmark

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python lgpt_engine.py /ruta/a/lgpt_cancion 60   # benchmark headless
```

## Qué está soportado

Medido sobre las canciones del proyecto (abduccion, Bulebule, Energia,
Sartenazo v1):

- Samples WAV (8/16 bits, mono/estéreo, cualquier frecuencia) por nombre.
- Secuenciador song → chain → phrase con transposes y loop de sección.
- Timing: tempo BPM, avance sample-accurate sin deriva y grooves por
  canal (patrón de longitudes de step en ticks; Bulebule usa [7,5,6,5]).
- Pitch por nota (root note + fine tune), volumen, pan (pan law original),
  master volume, loop oneshot/forward, recorte por `end`.
- Comandos: `VOLM` (rampas; el volumen del instrumento es el MÁXIMO de la
  voz y `VOLM vv` escala relativo a él: FF = el volumen del instrumento,
  80 ≈ la mitad; el volumen del instrumento se re-lee en vivo en cada
  trigger y cada bloque de render, así editarlo desde el editor se oye al
  instante, también en la nota que está sonando), `KILL`, `FADE` (apaga la
  nota: 0 filas = ya con declick; N = rampa el volumen actual a 0 en N
  filas de phrase), `DLAY`, `LEGA`,
  `TABL`, `STOP`, `HOP`, `FCUT`, `FRES`, `FMOD`.
- Tablas (1 fila/tick, 3 columnas, HOP con contador).
- Crush/downsample, filtro LP del upstream (`original`/`scream`) y
  filtros baratos SVF por voz (`lp`/`hp`/`bp`/`notch`).
- Instrumentos MIDI: note on/off, `MDCC`, `MDPG`, `MVEL`, `VOLM` → CC7,
  y `FADE` (0 = note off ya; N = note off tras N filas),
  emitidos por el puerto MIDI de salida configurado.
- Filtro low-pass con resonancia por canal (biquad propio, sin plugins
  LADSPA: no añade dependencias y sobra para 8 canales en la RPi4).

## Limitaciones conocidas

- **Filtro en modo `scream`**: el original desborda punto fijo int32 a
  propósito; aquí se satura a [-2, 2]. Aproximación pendiente de ajuste
  fino a oído (solo afecta al instrumento "accordion").
- Sin instrumentos de tipo soundfont, sin feedback, slices, oscillator
  ni ping-pong.
- El comando `STOP` detiene la canción; no hay avance automático a la
  siguiente (se pulsa `n` o `espacio`).
