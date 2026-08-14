# lgptclient

Sistema de robot de percusión controlado por LGPT (Little GP Tracker). Convierte notas MIDI en eventos GPIO, animaciones en pantalla y audio, con despliegue en clústeres Raspberry Pi.

## Flujo general

El **sinte** (`sinte/`, host `sintetizador`) es la fuente: reproduce las canciones LGPT él mismo (motor propio en Python, sin LGPT binario ni JACK) y emite los eventos por TCP. El resto de nodos son clientes que escuchan ese TCP y actúan:

```
sinte/ (reproductor LGPT + entrada MIDI de un controlador) → TCP 8888 (CONFIG/SYNC/NOTA/CC/START/END)
    → maleta / sombrilla: GPIO (solenoides) + animaciones + Flask (monitorización)
    → vocoder: Carla (síntesis/efectos) + Flask (monitorización)
```

## Estructura de directorios

| Directorio | Descripción |
|---|---|
| `sinte/` | Reproductor standalone de canciones LGPT (motor, parser, efectos, UI curses, servidor de eventos TCP) para el host `sintetizador`. Ver `sinte/README.md`. |
| `mixer/` | App de escritorio Kivy standalone: editor visual del `robotraca.json` de cada canción (play/stop, mute, canal vocoder, efectos por canal, knobs, pads, master) con el engine de `sinte/` embebido en el proceso. Se lanza con `mixer/run.sh` |
| `bin/` | `cliente_final/` (cliente real de maleta/sombrilla: GPIO, display, orquestación de eventos), perfiles `cliente.*.json`, y utilidades de generación de imágenes/samples (`genera*.py`) |
| `flaskr/` | Dashboard web Flask — monitorización de CPU/RAM/disco y estado de servicios; se despliega a maleta y sombrilla (el sinte no lo sirve: solo corre el player en kiosk) |
| `vocoder/` | App Flask + preset de Carla para el nodo vocoder |
| `midi_monitor_linux/` / `tcp_monitor_linux/` | Apps de escritorio Qt/QML: monitorizan la entrada MIDI y el stream TCP de eventos, respectivamente |
| `ansible/` | Playbooks y roles de despliegue de los clústeres Raspberry Pi |
| `images/` | Recursos de animaciones e imágenes indexadas por número |
| `samples/` | Samples de audio organizados en `origen/` y `destino/` |

## Archivos raíz clave

| Archivo | Descripción |
|---|---|
| `NOTAS.md` | Mapeado de notas MIDI (C1–B4) a acciones del robot |
| `Imagenes.md` | Galería de referencia de imágenes con códigos hex |
| `PANTALLA.md` | Notas sobre la pantalla del robot |

## Stack tecnológico

- **sinte** (`sinte/`): Python puro — `numpy`/`soundfile`/`sounddevice` (motor y salida de audio), `mido`/`python-rtmidi` (entrada del controlador MIDI), `curses` (UI). Sin JACK ni binario LGPT: el motor reimplementa el secuenciador.
- **Resto de clientes**: `alsa_midi`, `RPi.GPIO`, `pyalsaaudio`, Flask
- **UI**: Flask (web, todos los nodos), Qt/QML (monitores de escritorio)
- **Hardware**: Raspberry Pi, GPIO, IQaudIODAC
- **Despliegue**: Ansible

## Monitores de desarrollo

Los monitores (`midi_monitor_linux/`, `tcp_monitor_linux/`, `midi_monitor/`) **se ejecutan en este PC**, no en el servidor.

## Despliegue

Todos los nodos se despliegan por Ansible desde este PC; **ninguno hace `git pull`** (el sinte ni siquiera tiene internet). El flujo es siempre:

```bash
# 1. Subir cambios (para tener el historial en remoto; el deploy no depende de esto)
git push

# 2. Desplegar. Playbooks disponibles en ansible/ (usar -i ansible/inventario):
ansible-playbook ansible/actualiza-sinte.yaml -i ansible/inventario      # sintetizador (192.168.0.2)
ansible-playbook ansible/actualiza-maletas.yaml -i ansible/inventario   # maleta + sombrilla
ansible-playbook ansible/actualiza-vocoder.yaml -i ansible/inventario   # vocoder
ansible-playbook ansible/actualiza-todo.yaml -i ansible/inventario      # los tres
```

`actualiza-maletas.yaml` y `actualiza-vocoder.yaml` compilan primero el panel
JSX→JS en este PC (rol `compilar-web`) y luego sincronizan por rsync los
ficheros versionados del repo al host de destino (ninguno tiene acceso a
internet), reiniciando solo los servicios que cambiaron. `actualiza-sinte.yaml`
no compila ningún panel (el sinte no sirve panel web): solo sincroniza el
repo y el rol `sintetizador-actualiza` crea/actualiza el venv de `sinte/` y
deja el player arrancando en kiosk (autologin en tty1) — ver
`ansible/roles/sintetizador-actualiza/tasks/main.yaml`.

## Notas de desarrollo

- El mapeado MIDI → acción está documentado en `NOTAS.md` (instrumentos 80–81 para imágenes/animaciones)
- Los clientes de maleta/sombrilla se configuran con perfiles JSON en `bin/cliente.*.json`, consumidos por `bin/cliente_final/`
- El protocolo de eventos TCP (`CONFIG/SYNC/NOTA/CC/START/END`, puerto 8888) lo emite `sinte/event_server.py`; el detalle de timing (`audio_delay`, cálculo de `event_time_ms`) está documentado en `sinte/README.md`
