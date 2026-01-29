# MIDI Monitor

Aplicación con interfaz gráfica para monitorear eventos MIDI. Crea un puerto MIDI virtual al arrancar y muestra en tiempo real todos los eventos que recibe.

## Características

- ✅ Crea un puerto MIDI virtual automáticamente
- ✅ Interfaz gráfica con Tkinter (incluido con Python)
- ✅ Compatible con Windows y Linux
- ✅ Log de eventos MIDI en tiempo real con colores
- ✅ Muestra el estado de conexión MIDI
- ✅ Contador de eventos recibidos
- ✅ Auto-scroll opcional

## Requisitos

- Python 3.7+
- En Windows: [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html) para crear puertos MIDI virtuales
- En Linux: ALSA (generalmente ya instalado)

## Instalación

### Windows

1. Ejecuta el script de configuración:
   ```batch
   setup_env.bat
   ```

2. **Importante**: Instala [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html) para poder crear puertos MIDI virtuales en Windows.

### Linux

1. Ejecuta el script de configuración:
   ```bash
   chmod +x setup_env.sh
   ./setup_env.sh
   ```

## Uso

### Windows

```batch
venv\Scripts\activate.bat
python main.py
```

### Linux

```bash
source venv/bin/activate
python main.py
```

## Interfaz

La aplicación muestra:

1. **Estado del sistema**: Sistema operativo y disponibilidad de mido
2. **Estado del puerto MIDI**: Indicador visual (verde/rojo) y nombre del puerto
3. **Log de eventos**: Todos los eventos MIDI recibidos con timestamp
4. **Contador de eventos**: Número total de eventos recibidos

### Tipos de eventos soportados

| Tipo | Color | Descripción |
|------|-------|-------------|
| NOTE ON/OFF | Púrpura | Notas musicales |
| CC | Turquesa | Control Change |
| PROGRAM | Turquesa | Program Change |
| PITCH | Turquesa | Pitch Bend |
| AFTERTOUCH | Gris | Channel/Poly Aftertouch |

## Conectar otros dispositivos

### Linux

El puerto virtual aparecerá como "MIDI Monitor Virtual" en las aplicaciones MIDI. Puedes conectarlo usando:

```bash
# Ver puertos disponibles
aconnect -l

# Conectar un puerto al monitor
aconnect <puerto_origen> <puerto_monitor>
```

### Windows

1. Abre loopMIDI y crea un puerto virtual
2. Configura tu aplicación MIDI para enviar al puerto de loopMIDI
3. La aplicación detectará automáticamente el puerto

## Solución de problemas

### Windows: "No hay puertos MIDI disponibles"

1. Instala loopMIDI
2. Crea un nuevo puerto virtual en loopMIDI
3. Reinicia la aplicación

### Linux: Error al crear puerto virtual

```bash
# Instala las dependencias de desarrollo de ALSA
sudo apt install libasound2-dev libjack-jackd2-dev
```

### Error al instalar python-rtmidi

```bash
# Windows: Necesitas Visual C++ Build Tools
# Linux: Necesitas las cabeceras de desarrollo de ALSA

# Linux Debian/Ubuntu:
sudo apt install libasound2-dev

# Linux Fedora:
sudo dnf install alsa-lib-devel
```

## Estructura del proyecto

```
midi_monitor/
├── main.py           # Aplicación principal
├── requirements.txt  # Dependencias Python
├── setup_env.bat     # Script de instalación Windows
├── setup_env.sh      # Script de instalación Linux
└── README.md         # Este archivo
```

## Licencia

MIT
