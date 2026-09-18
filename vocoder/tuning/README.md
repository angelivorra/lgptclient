# Ajuste en directo del vocoder (Carla GUI + señal de prueba)

Para diseñar el rack de Carla (añadir/quitar plugins, mover knobs) sin
depender del sinte ni de estar hablando al micro todo el rato, y sin arriesgar
la producción: `loop_signal.py` sustituye el micro por un WAV en bucle
(modulador) y dispara un patrón MIDI rítmico al carrier (`Noize Mak3r`) por
`Carla:events-in`, igual que hace `carla_runner.py` con el ACRD del sinte —
así el vocoder suena solo, en bucle y en compás.

**`template01.carxp` es siempre producción y nunca se toca desde aquí.**
`start-tuning.sh` trabaja sobre una copia local en la Pi, `sandbox.carxp`
(no versionada, ver `.gitignore`): la crea a partir de `template01.carxp` la
primera vez y luego la reutiliza entre sesiones, hasta que pidas `--reset`.
Cuando el resultado te convenza, `pull-tuning.sh` la trae al repo como
candidato a nueva producción — revisas el diff y decides si comiteas.

Solo puede haber un Carla usando esos puertos JACK a la vez, así que la
sesión de ajuste para la producción (el Carla headless que gestiona
`flask/app.py`) mientras dura.

## Uso

En la Pi del vocoder (o por SSH):

```bash
cd /home/patch/pivocoder/tuning
./start-tuning.sh                                  # WAV/notas/bpm por defecto
./start-tuning.sh --wav recordings/1234.wav --bpm 90
./start-tuning.sh --reset                           # descarta el sandbox y parte de cero
```

Esto para `pivocoder-flask.service` y deja `loop_signal.py` sonando en bucle.

Desde tu PC, abre la GUI real de Carla sobre la copia de pruebas (X11
forwarding, ya configurado en la Pi — `xauth`/`X11Forwarding yes`):

```bash
ssh -X patch@192.168.0.10 carla /home/patch/pivocoder/tuning/sandbox.carxp
```

Añade/quita plugins, mueve knobs, escucha el resultado en directo (el audio
suena en la propia Pi, solo la ventana viaja por X). Guarda con Ctrl+S las
veces que quieras — es `sandbox.carxp`, producción no se entera.

Al terminar, cierra la ventana de Carla y:

```bash
./stop-tuning.sh
```

Esto mata `loop_signal.py` (devuelve el micro a `Carla:audio-in1/2`) y
reanuda `pivocoder-flask.service`.

### Llevar el resultado a producción

Desde tu PC (no desde la Pi):

```bash
cd vocoder/tuning
./pull-tuning.sh
git diff -- vocoder/prod/template01.carxp   # revisa qué cambió
git add vocoder/prod/template01.carxp && git commit && git push
ansible-playbook ansible/actualiza-vocoder.yaml -i ansible/inventario
```

## Grabar una señal de prueba más realista

`record_input.py` graba `system:capture_1` — el mismo micro que entra a
Carla en producción — a un WAV. No hace falta parar nada: es solo otro
cliente JACK escuchando el mismo puerto, así que puedes grabar durante una
reproducción real del sinte con alguien hablando al micro, la señal más
parecida posible a un directo:

```bash
cd /home/patch/pivocoder/tuning
./record_input.py --seconds 20                     # -> recordings/<timestamp>.wav
./record_input.py --seconds 15 --out recordings/voz_gobiernoIA.wav
```

Luego úsalo como modulador de la sesión de ajuste:

```bash
./start-tuning.sh --wav recordings/voz_gobiernoIA.wav
```

Las grabaciones viven en `recordings/`, local a la Pi (no se versionan ni se
tocan en el deploy — ver `.gitignore` y el `--exclude` del rol de ansible).

## Parámetros de `loop_signal.py`

| Flag | Por defecto | Qué hace |
|---|---|---|
| `--wav` | `/home/patch/pivocoder/mic_test.wav` | WAV a reproducir en bucle como modulador. Se remuestrea en memoria si no está al sample rate de JACK. |
| `--notes` | `60,63,67` | Notas MIDI del patrón (se ciclan una tras otra). |
| `--bpm` | `100` | Tempo del patrón. |
| `--vel` | `100` | Velocidad MIDI de cada nota. |

Ctrl+C (o `kill`, que es lo que hace `stop-tuning.sh`) desconecta limpio y
devuelve el micro antes de salir.
