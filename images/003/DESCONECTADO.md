# Brief: animación «sin conexión» sobre el fondo

Encargo para un agente **sin el historial de este chat**. Objetivo: inventar y generar una animación nueva de **desconectado** que se vea **encima del slideshow de fondo**, no a pantalla llena negra. La wifi actual se sustituye.

Repo: `lgptclient`. Pantalla real de las robotas (maleta / sombrilla): **800×480**, RGB565, framebuffer.

---

## Qué es esto

Sistema de percusión-robot. El **sinte** reproduce canciones y manda eventos por TCP. Las **robotas** (Raspberry Pi) pintan la pantalla y golpean solenoides.

Capas de pantalla, de atrás a delante:

1. Efectos procedurales (plasma) — solo **durante la canción**, si no hay fondo.
2. **Slideshow de fondo** (`images/fondos/001/`, loop de PNGs). En pausa y en canción (si la canción tiene `fondo` en `robotraca.json`).
3. Imágenes estáticas (CC 001) — icono centrado, negro = transparente.
4. Texto (CC 002).
5. **Animaciones** (CC 003) — overlay; negro / alpha = transparente.

Hoy, **conectado y en pausa**: fondo + ojos (`003/003`) encima.  
Hoy, **sin conexión al sinte**: animación wifi (`003/001`) **a pantalla llena**, y se **apaga el slideshow**. Eso hay que cambiarlo.

Constantes en `bin/cliente_final/event_orchestrator.py`:

```text
IDLE_CC / IDLE_VALUE           = 3 / 3   → images/003/003  (ojos, ya overlay)
DISCONNECTED_CC / VALUE        = 3 / 1   → images/003/001  (wifi, aún full-screen)
DEFAULT_FONDO                  = "001"
```

---

## Qué hay que hacer

### 1. Diseñar y generar la animación

Sustituir los frames de `images/003/001/` (hoy: icono wifi blanco sobre negro opaco, ~30 PNG, `anim.cfg` loop 30 FPS).

Requisitos visuales:

- **Fondo transparente de verdad.** El slideshow se tiene que ver alrededor del motivo. No rejilla tron, no lienzo negro opaco, no escena completa.
- Lienzo **800×480** RGBA. Fuera del motivo: alpha 0 (o RGB negro puro; el composite del dispositivo trata `lum ≤ 6` en RGB565 como transparente).
- El motivo **centrado**, tamaño generoso pero con aire (como los ojos: dos cuadrados verdes; o los números 0–3 recién regenerados: icono ~200 px).
- Estética del show: **robótica / neón**, no UI de teléfono. La wifi plana actual no encaja. Ideas válidas (elige una y ejecútala bien; no hace falta pedir permiso):
  - Ojos de robot **apagados / X / dormidos / buscando** (diálogo con `003/003`, que son ojos verdes abiertos).
  - Pulso de “sin señal”: anillos o un punto que no llega a conectar.
  - Cara / glitch / interrogación neón, **sin** tapar todo el frame.
- Loop corto y legible (1–3 s). `anim.cfg` típico:

```json
{ "fps": 30, "loop": true, "max_delay": 2 }
```

- 4–40 frames. Más frames solo si el movimiento lo pide.
- El glow debe ser **parte del sprite** (blanco/neón), no un velo oscuro que ensucie el fondo. Comprueba el PNG compuesto sobre un color chillón (verde/rosa): no debe quedar halo sucio ni restos de rejilla.

Referencias en el mismo repo (no copiar literal, sí el criterio de overlay):

| Carpeta | Qué es | Estado |
|---|---|---|
| `images/003/003/` | Ojos verdes, parpadeo, negro alrededor | Idle conectado; ya va sobre fondo |
| `images/003/002,005,006,007/` | Números 0–3, icono iOS, **alpha real**, 4 frames de glow | Modelo reciente de “sprite sobre vacío” |
| `images/003/001/` | Wifi blanca, negro opaco | **Reemplazar** |
| `images/fondos/001/` | Slideshow de fondo (loop_*.png) | Se verá **detrás** |

### 2. Cablear el overlay (código, imprescindible)

Si solo cambias los PNG y no el código, **sigue sin verse el fondo**: `_show_idle()` en desconectado hace `clear_slideshow()` y pinta la animación a pantalla llena.

Hay que dejar el desconectado **igual que los ojos**:

1. En `EventOrchestrator._show_idle` (rama `not self._connected`): **no** llamar a `clear_slideshow()`. Llamar a `_ensure_idle_fondo()` (carga `fondos/001` si no hay) y luego `_start_idle_animation(DISCONNECTED_CC, DISCONNECTED_VALUE, "desconectado")`.
2. `DisplayExecutor._play_animation_internal` ya pone `_idle_over_fondo = (source == "idle" and bool(self._slideshow_images))`. Con el slideshow puesto, la wifi/nueva anim se mezcla sola. No hace falta un flag nuevo.
3. Tests: el de ojos sobre slideshow en `bin/cliente_final/test_scenes.py` (`test_idle_ojos_sobre_slideshow`) es el patrón. Añade uno análogo `source="idle"` + slideshow + pack de `003/001`. Ajusta `test_orchestrator_stop` si ahora el desconectado también llama `set_slideshow` y ya no `clear_slideshow`.

No toques el idle de ojos (`003/003`) ni el plasma de canción.

### 3. Hornear para las Pi

El dispositivo **no** lee los PNG de `images/`. `bin/genera.py <terminal>` lee `images/003/001/*.png`, convierte a RGB565 800×480 (`png_to_bin`: alpha 0 → negro), empaqueta `img_output/<terminal>/003/001/pack.bin` + `anim.cfg`.

```bash
# En este PC, desde la raíz del repo:
python3 bin/genera.py maleta
python3 bin/genera.py sombrilla   # invert=True (pantalla al revés)
```

Sombrilla: `DATOS_TERMINAL["sombrilla"]["invert"] = True` — no hace falta voltear a mano los PNG fuente.

Tras generar, el deploy es Ansible (`ansible/actualiza-maletas.yaml`); las robotas no tienen git pull. **No despliegues** salvo que el usuario lo pida.

---

## Cómo se pinta un overlay (para no romperlo)

`DisplayExecutor._composite_rgb565` (dispositivo, RGB565):

- Transparente: `r+g+b ≤ 6` (casi negro) **o** azul-dominante oscuro (`b > r` y suma ≤ 25).
- El resto es opaco.

Por eso el sprite tiene que vivir en **negro puro / alpha 0**. Grises, azules oscuros de “ambiente” o una rejilla se comerán el fondo o dejarán suciedad.

En robotracker (preview LIVE, `robotracker2/screens/live_view.py`):

- Carga los PNG de `images/{cc}/{value}/*.png` como RGBA.
- Si el PNG ya tiene alpha, lo respeta.
- Si es opaco, “punch” del mismo criterio de oscuros.

Preview útil: canción con fondo, o el idle de robotracker no replica el cliente; el sitio de verdad es la Pi. Para validar en PC: genera un frame compuesto (fondo + sprite) y míralo.

---

## Estructura de ficheros

```text
images/003/001/
  anim.cfg          # fps, loop, max_delay
  01.png …          # frames fuente (el orden es sorted() de *.png)
images/fondos/001/  # no lo regeneres; es el fondo que debe verse detrás

bin/genera.py                         # hornea PNG → pack.bin
bin/cliente_final/event_orchestrator.py
bin/cliente_final/display_executor.py
bin/cliente_final/media_manager.py    # get_animation(3, 1) → pack de 003/001
bin/cliente_final/test_scenes.py
bin/cliente_final/test_orchestrator_stop.py
```

`media_manager` busca ` /home/angel/images/003/001/pack.bin` en la Pi (rsync de `img_output/<terminal>/`).

---

## Criterio de hecho

- [ ] `images/003/001/` tiene frames RGBA 800×480, motivo centrado, vacío = transparente.
- [ ] Sobre un fondo de color (o `images/fondos/001/loop_01.png`) se lee el motivo y se ve el fondo alrededor, sin caja negra.
- [ ] `anim.cfg` con loop.
- [ ] Desconectado: `_ensure_idle_fondo()` + animación `source="idle"`; **sin** `clear_slideshow()`.
- [ ] Tests de overlay idle y de STOP/idle actualizados y en verde.
- [ ] `genera.py maleta` (y sombrilla si tocas deploy) regenera `003/001` sin romper el resto de `003/`.

## Fuera de alcance

- No rediseñar ojos (`003/003`), números, flash (`003/004`) ni fondos.
- No cambiar el protocolo TCP ni el sinte.
- No commitear ni desplegar a las Pi salvo petición explícita.
- No hace falta una wifi reconocible; hace falta que **se entienda “no hay enlace”** y que **el fondo siga vivo**.
