# lgptclient

Sistema de robot de percusión controlado por LGPT (Little GP Tracker). Convierte notas MIDI en eventos GPIO, animaciones en pantalla y audio, con despliegue en clústeres Raspberry Pi.

## Flujo general

```
LGPT (tracker) → MIDI → servidores Python → GPIO / animaciones / audio
                                          → Flask / QML (monitorización)
```

## Estructura de directorios

| Directorio | Descripción |
|---|---|
| `bin/` | Scripts principales: orquestación LGPT, servidores MIDI/TCP, gestión de audio y samples |
| `flaskr/` | Dashboard web Flask — monitorización de CPU/RAM/disco y estado de servicios |
| `lgpt/` | Binario LGPT compilado para RPi + configuración (`config.xml`, `mapping.xml`) |
| `midi_monitor_linux/` | App de escritorio Qt/QML para monitorizar MIDI y drum pads en tiempo real |
| `ansible/` | Playbooks de despliegue e inicialización de clústeres Raspberry Pi |
| `images/` | Recursos de animaciones e imágenes indexadas por número |
| `samples/` | Samples de audio organizados en `origen/` y `destino/` |

## Archivos raíz clave

| Archivo | Descripción |
|---|---|
| `main_server.py` | Servidor principal — gestiona eventos GPIO y MIDI |
| `image_events2.py` | Manejo de eventos de imagen sincronizados con MIDI |
| `robot_display.py` | Gestión del display del robot |
| `lgpt-runner.service` | Servicio systemd para arranque automático de LGPT |
| `jack.sh` / `asound.conf` | Configuración del servidor de audio JACK y ALSA |
| `NOTAS.md` | Mapeado de notas MIDI (C1–B4) a acciones del robot |
| `Imagenes.md` | Galería de referencia de imágenes con códigos hex |

## Stack tecnológico

- **Audio**: JACK, ALSA, FFmpeg, `pyalsaaudio`
- **MIDI**: `alsa_midi`, servidores Python propios
- **UI**: Flask (web), Qt/QML (escritorio)
- **Hardware**: Raspberry Pi, GPIO, IQaudIODAC
- **Despliegue**: Ansible

## Notas de desarrollo

- El mapeado MIDI → acción está documentado en `NOTAS.md` (instrumentos 80–81 para imágenes/animaciones)
- Los clientes se configuran con perfiles JSON en `bin/cliente.*.json`
- `bin/run-lgpt.py` es el punto de entrada principal: arranca jackd, alsa_in y el binario LGPT
- El bridge ALSA/JACK con compensación de latencia está en `bin/alsa_delay_bridge.py`
