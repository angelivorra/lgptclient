# Resumen de cambios - Control de logs y modo simulación

## ✅ Cambios realizados

### 1. Variable de entorno `SIMULATE_GPIO`

**Archivo:** `main.py`

```python
# Configuración de modo simulación GPIO
SIMULATE_GPIO = os.environ.get("SIMULATE_GPIO", "0") == "1"
```

- Por defecto: **Desactivado** (modo real)
- Se pasa al `GPIOExecutor` para activar/desactivar simulación
- Se muestra en el inicio del cliente

### 2. Logs de INFO → DEBUG

**Archivo:** `gpio_executor.py`

Logs cambiados a DEBUG:
- ✅ Configuración de pines individuales
- ✅ Mensajes de cleanup
- ✅ Logs internos de simulación

Logs que permanecen INFO:
- ✅ Inicialización completa de GPIO
- ✅ **Activación real de GPIO** (HIGH/LOW) ← PRINCIPAL
- ✅ Errores y warnings

**Archivo:** `event_orchestrator.py`

Logs cambiados a DEBUG:
- ✅ Recepción de notas y mapeo a pines
- ✅ Cálculos de timing y programación
- ✅ Eventos CC, START, END

Logs que permanecen INFO:
- ✅ Errores de mapeo
- ✅ Errores de ejecución

## 📊 Ejemplo de salida con nuevos logs

### Modo INFO (normal):
```
2025-10-06 14:23:15.123 INFO    ✅ GPIO inicializado correctamente (4 pines)
2025-10-06 14:23:20.456 INFO    🎵 NOTA 36 (canal 0, vel 127)
2025-10-06 14:23:21.306 INFO    🔌 Pin 23 (Bombo) → HIGH (por 0.150s)
2025-10-06 14:23:21.456 INFO    🔌 Pin 23 (Bombo) → LOW (estuvo 0.150s)
```

### Modo DEBUG (con -v o logging.DEBUG):
```
2025-10-06 14:23:15.123 INFO    ✅ GPIO inicializado correctamente (4 pines)
2025-10-06 14:23:15.124 DEBUG      ✅ Pin 23 configurado como OUTPUT (LOW)
2025-10-06 14:23:15.125 DEBUG      ✅ Pin 17 configurado como OUTPUT (LOW)
2025-10-06 14:23:20.456 INFO    🎵 NOTA 36 (canal 0, vel 127)
2025-10-06 14:23:20.457 DEBUG   🎵 NOTA 36 → 1 pin(es): [23]
2025-10-06 14:23:20.458 DEBUG      📌 Pin 23 (Bombo): delay=150ms → ejecutar en 849.5ms (activo 0.150s)
2025-10-06 14:23:21.306 INFO    🔌 Pin 23 (Bombo) → HIGH (por 0.150s)
2025-10-06 14:23:21.456 INFO    🔌 Pin 23 (Bombo) → LOW (estuvo 0.150s)
```

## 🚀 Uso

### Modo real (producción):
```bash
python3 main.py
```

### Modo simulación (desarrollo):
```bash
SIMULATE_GPIO=1 python3 main.py
```

### Con NTP desactivado:
```bash
ENABLE_NTP_SYNC=0 python3 main.py
```

### Combinado:
```bash
SIMULATE_GPIO=1 ENABLE_NTP_SYNC=0 SERVER_HOST=192.168.0.2 python3 main.py
```

## 📝 Variables de entorno disponibles

| Variable | Default | Descripción |
|----------|---------|-------------|
| `SERVER_HOST` | 192.168.0.2 | IP del servidor MIDI |
| `SERVER_PORT` | 8888 | Puerto TCP del servidor |
| `ENABLE_NTP_SYNC` | 0 | Sincronización NTP (1=on, 0=off) |
| `SIMULATE_GPIO` | 0 | Modo simulación GPIO (1=on, 0=off) |

## 🎯 Logs importantes para producción

Con el nivel INFO, solo verás:
- ✅ Conexiones y desconexiones
- ✅ Notas MIDI recibidas
- ✅ **Activaciones GPIO reales** (HIGH → LOW)
- ✅ Errores y warnings

Esto mantiene los logs limpios en producción pero informativos.
