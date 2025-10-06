# Sistema de Display - Imágenes y Animaciones

## 📋 Descripción General

Sistema completo de gestión y reproducción de imágenes estáticas y animaciones en framebuffer, integrado con el cliente MIDI. Diseñado para ejecutar eventos de imagen/animación con 1 segundo de delay, con pre-carga inteligente y gestión eficiente de memoria.

## 🏗️ Arquitectura

### Componentes Principales

```
┌─────────────────────────────────────────────────────────┐
│                    main.py (MIDIClient)                  │
│  - Inicializa todos los componentes                     │
│  - Gestiona conexión TCP con servidor                   │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│              event_orchestrator.py                       │
│  - Recibe eventos CC del servidor                       │
│  - Pre-carga imágenes/animaciones                       │
│  - Programa ejecución en scheduler (1s delay)           │
└─────────────────────────────────────────────────────────┘
              │                         │
    ┌─────────┴──────────┐    ┌─────────┴──────────┐
    ▼                    ▼    ▼                    ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│media_manager │   │scheduler.py  │   │display_      │
│   .py        │   │ - Ejecuta    │   │executor.py   │
│- Cache LRU   │   │   tareas en  │   │- Framebuffer │
│  (10 imgs)   │   │   tiempo     │   │- Animaciones │
│- Carga       │   │   preciso    │   │- Threading   │
│  animaciones │   │              │   │              │
└──────────────┘   └──────────────┘   └──────────────┘
```

### 1. **media_manager.py** - Gestor de Medios

**Responsabilidades:**
- Mantener cache LRU de hasta 10 imágenes en RAM
- Cargar configuración de animaciones bajo demanda
- Detectar si un CC/value es imagen o animación
- Proporcionar estadísticas de uso

**Características:**
- **Cache inteligente**: Las imágenes más recientes se mantienen en RAM
- **Sin cache de animaciones**: Las animaciones se cargan cuando se necesitan (solo configuración)
- **Auto-detección**: Distingue automáticamente entre imagen (archivo `.bin`) y animación (directorio)

**API Principal:**
```python
media_manager = MediaManager(base_path="/path/to/images", max_image_cache=10)

# Obtener imagen (con cache automático)
image_data = media_manager.get_image(cc=2, value=3)

# Obtener configuración de animación
anim_config = media_manager.get_animation(cc=3, value=1)

# Verificar tipo
is_anim = media_manager.is_animation(cc=3, value=1)
```

### 2. **display_executor.py** - Ejecutor de Display

**Responsabilidades:**
- Escribir imágenes al framebuffer
- Reproducir animaciones frame por frame en thread dedicado
- Parar animaciones anteriores automáticamente
- Gestionar timing preciso (FPS)

**Características clave:**
- **Una animación a la vez**: Al iniciar una nueva, para la anterior automáticamente
- **Threading dedicado**: Cada animación corre en su propio thread sin bloquear
- **Control de parada limpio**: Las animaciones se pueden interrumpir instantáneamente
- **Soporte de loop**: Las animaciones pueden repetirse infinitamente

**API Principal:**
```python
display = DisplayExecutor(fb_device="/dev/fb0", simulate=False)

# Mostrar imagen estática (para cualquier animación activa)
display.show_image(image_data, cc=2, value=3)

# Reproducir animación (para la anterior si existe)
display.play_animation(anim_config)

# Parar animación manualmente
display.stop_animation()
```

### 3. **event_orchestrator.py** - Orquestador de Eventos

**Responsabilidades:**
- Recibir eventos CC del servidor MIDI
- Pre-cargar imágenes en cache antes de mostrarlas
- Programar ejecución con 1 segundo de delay
- Coordinar entre media_manager y display_executor

**Flujo de trabajo:**

```
Evento CC recibido (ts=T)
    │
    ├─ ¿Es animación?
    │   └─ SÍ → Cargar configuración en memoria
    │           Programar play_animation(config) en T+1000ms
    │
    └─ ¿Es imagen?
        └─ SÍ → Cargar imagen en cache
                Programar show_image(data) en T+1000ms
```

## 📁 Estructura de Archivos

### Imágenes Estáticas

```
img_output/sombrilla/
├── 002/                    # CC número 2
│   ├── 003.bin            # Valor 3
│   ├── 009.bin            # Valor 9
│   └── ...
└── ...
```

- Archivo: `{CC:03d}/{VALUE:03d}.bin`
- Formato: Raw binary RGB565 (800x480x2 = 768000 bytes)

### Animaciones

```
img_output/sombrilla/
└── 003/                    # CC número 3
    ├── 001/                # Valor 1
    │   ├── pack.bin        # Archivo con todos los frames
    │   ├── pack.bin.index.json  # Índice de frames
    │   └── anim.cfg        # Configuración de animación
    └── ...
```

#### `anim.cfg` (JSON):
```json
{
  "fps": 30,         // Frames por segundo
  "loop": true,      // Repetir infinitamente
  "max_delay": 2     // (No usado actualmente)
}
```

#### `pack.bin.index.json`:
```json
{
  "width": 800,
  "height": 480,
  "bpp": 16,
  "entries": [
    {
      "file": "000.bin",
      "offset": 0,          // Offset en pack.bin
      "size": 768000        // Tamaño del frame
    },
    // ... más frames
  ]
}
```

## 🚀 Uso

### Variables de Entorno

```bash
# Ruta base de imágenes/animaciones
export MEDIA_BASE_PATH="/home/angel/lgptclient/img_output/sombrilla"

# Modo simulación de display (sin framebuffer real)
export SIMULATE_DISPLAY="0"  # 0=Real, 1=Simulación

# Modo simulación de GPIO
export SIMULATE_GPIO="0"
```

### Iniciar el Cliente

```bash
cd /home/angel/lgptclient/bin/clientet
python3 main.py
```

### Protocolo de Eventos CC

El servidor envía eventos en formato CSV:

```
CC,<timestamp_ms>,<value>,<channel>,<controller>
```

**Ejemplo:**
```
CC,1696634500123,3,0,2      # CC 2, valor 3 → Imagen 002/003.bin
CC,1696634500456,1,0,3      # CC 3, valor 1 → Animación 003/001/
```

## 🔧 Testing

### Test Individual de Componentes

```bash
# Test MediaManager
python3 media_manager.py

# Test DisplayExecutor
python3 display_executor.py

# Test EventOrchestrator (integrado)
python3 event_orchestrator.py
```

### Modo Simulación

Para probar sin hardware:

```bash
export SIMULATE_GPIO="1"
export SIMULATE_DISPLAY="1"
python3 main.py
```

## ⚡ Rendimiento

### Características de Rendimiento

- **Pre-carga**: Las imágenes se cargan en memoria antes de necesitarse
- **Cache LRU**: Las 10 imágenes más recientes permanecen en RAM (7.3 MB)
- **Threading eficiente**: Animaciones en threads dedicados, sin bloqueo
- **Timing preciso**: Control de FPS con `threading.Event.wait()`
- **Parada instantánea**: Las animaciones se detienen inmediatamente cuando se necesita

### Consumo de Memoria

- Imagen: ~768 KB (800x480x2 bytes)
- Cache de 10 imágenes: ~7.3 MB
- Animación (config): ~2 KB (solo metadata, frames se leen bajo demanda)

## 🎯 Ventajas del Diseño

1. **Parada Garantizada**: Cuando llega una nueva animación, la anterior se para inmediatamente
2. **Sin Sobrecarga**: Las animaciones leen frames directamente del disco, no se cargan en memoria
3. **Cache Inteligente**: Imágenes estáticas se cachean (uso frecuente), animaciones no
4. **Separación Clara**: 3 módulos independientes con responsabilidades bien definidas
5. **Testeable**: Cada componente se puede probar por separado
6. **Modo Simulación**: Desarrollo y testing sin hardware real

## 📊 Estadísticas

Cada componente proporciona estadísticas:

```python
# MediaManager
media_manager.print_stats()
# - Cache hits/misses
# - Imágenes cargadas
# - Animaciones cargadas
# - Errores

# DisplayExecutor
display_executor.print_stats()
# - Imágenes mostradas
# - Animaciones iniciadas/paradas
# - Frames renderizados

# EventOrchestrator
orchestrator.print_stats()
# - Notas procesadas
# - CC procesados
# - GPIO programados
```

## 🐛 Debugging

### Niveles de Log

```python
logging.basicConfig(level=logging.DEBUG)  # Ver todo
logging.basicConfig(level=logging.INFO)   # Solo info importante
```

### Logs Relevantes

- `🖼️  Imagen mostrada`: Imagen escrita al framebuffer
- `🎬 Animación iniciada`: Nueva animación comenzó
- `⏹️  Animación parada`: Animación anterior detenida
- `📥 Imagen cargada`: Imagen cargada desde disco
- `🗑️  Cache lleno`: Imagen eliminada del cache

## ⚠️ Notas Importantes

1. **Framebuffer**: Requiere permisos de escritura en `/dev/fb0`
2. **Sincronización**: El delay de 1 segundo depende de sincronización NTP correcta
3. **Formato de Imágenes**: Solo RGB565, 800x480 pixels (768000 bytes exactos)
4. **Threading**: Las animaciones usan threads daemon, terminan con el programa

## 🔮 Futuras Mejoras

- [ ] Pre-carga predictiva de próxima imagen/animación
- [ ] Transiciones entre imágenes (fade, slide, etc.)
- [ ] Soporte para diferentes resoluciones
- [ ] Compresión de animaciones en memoria
- [ ] Métricas de performance en tiempo real
- [ ] Auto-ajuste de FPS según carga del sistema

---

**Autor**: Sistema de display desde cero para lgptclient  
**Fecha**: Octubre 2025  
**Versión**: 1.0
