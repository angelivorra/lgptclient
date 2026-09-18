# Ajuste en directo del vocoder (Carla GUI + señal de prueba)

Para diseñar el rack de Carla (añadir/quitar plugins, mover knobs) sin
depender del sinte ni de estar hablando al micro todo el rato: `loop_signal.py`
sustituye el micro por un WAV en bucle (modulador) y dispara un patrón MIDI
rítmico al carrier (`Noize Mak3r`) por `Carla:events-in`, igual que hace
`carla_runner.py` con el ACRD del sinte — así el vocoder suena solo, en
bucle y en compás.

Solo puede haber un Carla usando esos puertos JACK a la vez, así que la
sesión de ajuste para la producción (el Carla headless que gestiona
`flask/app.py`) mientras dura.

## Uso

En la Pi del vocoder (o por SSH):

```bash
cd /home/patch/pivocoder/tuning
./start-tuning.sh                                  # WAV/notas/bpm por defecto
./start-tuning.sh --wav /home/patch/pivocoder/test.wav --notes 60,63,67 --bpm 90
```

Esto para `pivocoder-flask.service` y deja `loop_signal.py` sonando en bucle.

Desde tu PC, abre la GUI real de Carla con el mismo proyecto (X11 forwarding,
ya configurado en la Pi — `xauth`/`X11Forwarding yes`):

```bash
ssh -X patch@192.168.0.10 carla /home/patch/pivocoder/prod/template01.carxp
```

Añade/quita plugins, mueve knobs, escucha el resultado en directo (el audio
suena en la propia Pi, solo la ventana viaja por X). Si quieres conservar los
cambios para producción, guarda con Ctrl+S — es el mismo `template01.carxp`
que arranca `carla_runner.py` en producción.

Al terminar, cierra la ventana de Carla y:

```bash
./stop-tuning.sh
```

Esto mata `loop_signal.py` (devuelve el micro a `Carla:audio-in1/2`) y
reanuda `pivocoder-flask.service`.

## Parámetros de `loop_signal.py`

| Flag | Por defecto | Qué hace |
|---|---|---|
| `--wav` | `/home/patch/pivocoder/mic_test.wav` | WAV a reproducir en bucle como modulador. Se remuestrea en memoria si no está al sample rate de JACK. |
| `--notes` | `60,63,67` | Notas MIDI del patrón (se ciclan una tras otra). |
| `--bpm` | `100` | Tempo del patrón. |
| `--vel` | `100` | Velocidad MIDI de cada nota. |

Ctrl+C (o `kill`, que es lo que hace `stop-tuning.sh`) desconecta limpio y
devuelve el micro antes de salir.
