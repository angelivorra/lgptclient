# Neones de vocoder (pantalla 800×480)

Visual de las notas de la pista de voz en las robotas: **tubos de neón a
los lados** del framebuffer. Encajan con Tilt Neon, la cinta del horizonte
y el punch del overlay (letras / ojos / iconos).

Este md es el punto de partida. No está implementado.

## Qué llega

El sinte emite `ACRD` (no `NOTA`) por el canal vocoder (pista 6):

```
ACRD,<ts_ms>,<canal>,<velocity>,<nota1>,<nota2>,...
```

- El cliente de maleta/sombrilla **hoy no lo lee**. Solo lo consume el
  nodo vocoder (Carla).
- Reloj: `ts + delay` (1 s, igual que letras y golpes). El mute no lo
  corta: el sinte siempre lo manda.
- No hay note-off. El acorde nuevo sustituye al anterior. Si no llega
  otro, la nota “sigue sonando” en audio; en pantalla hay que **apagarla
  solos** (fade).
- `nota1` es la raíz; el resto, el acorde. `velocity` 1–127.

## Gesto (fijo)

1. **Aparece de golpe** (1 frame: 0 → encendido).
2. **Desaparece en fade** (exponencial, ~0.4–0.8 s). Si llega otro
   `ACRD`, las notas que se mantienen se re-disparan; las que caen
   siguen fundiéndose.
3. **Solo a los lados.** Centro libre: fondo, cinta, letras, iconos.
4. **Barato.** Misma liga que el ribbon: overlay RGB565, no reescribir
   el slideshow. Banda de ~40–56 px por lado.

Capa sugerida: `fondo → ribbon → neones vocoder → overlay CC`. Así las
letras tapan los tubos si se pisan, y los tubos no se comen el horizonte.

## Mapeo (común a todas las opciones)

| Señal | Uso visual |
|---|---|
| Pitch (MIDI 0–127) | Posición Y. Graves abajo, agudos arriba. Ventana útil ~C2–C6 (36–84); fuera, clamp. |
| Pitch class (nota % 12) | Color del tubo (12 hues neón). |
| Velocity | Grosor y/o brillo de pico. |
| Raíz vs tensiones | La raíz más gruesa o en ambos lados; el resto más fino. |
| Nº de notas | 1 tubo o varios apilados. Un acorde de 4 no debe tapar el centro. |

Rango Y: `y = lerp(440, 40, (note - 36) / 48)` (aprox.). Margen para no
tocar el borde.

---

## Opciones de forma

### A — Tubos verticales (recomendado para v1)

Un rectángulo hueco + glow por nota, pegado al borde (izq / der).
Altura ~36–56 px, grosor 6–10 px. Como un tramo de Tilt Neon de pie.

- **A1 simétrico:** la misma nota en los dos lados (marco).
- **A2 partido:** graves a la izquierda, agudos a la derecha (corte en
  C4 / MIDI 60).
- **A3 raíz | acorde:** raíz siempre a la izquierda; tensiones a la
  derecha.

*Pros:* se lee de lejos, barato (blit de franjas). *Contras:* poco
“melodía” si hay una sola nota.

### B — Piano roll lateral

12 (o 24) celdas fijas por lado, una por semitono de una octava. La
nota enciende su celda. El acorde es un acordeón de neones.

*Pros:* se ve el grado (I / III / V). *Contras:* más denso; hay que
elegir octava o apilar 2 octavas.

### C — Arcos / chevrones

Cada nota es un `>` o `(` de neón que abraza el borde, más alto = más
agudo. El fade encoge un poco el arco.

*Pros:* más gesto, menos “UI”. *Contras:* un poco más de raster.

### D — Rayos / streaks

Flash vertical fino (1–3 px) de borde a 80 px hacia dentro, corona
cian/magenta. Aparece y se desvanece. Varias notas = varios rayos a
distinta Y.

*Pros:* muy barato, no tapa casi nada. *Contras:* se confunde con la
cinta si cruzan el horizonte.

### E — Columnas de nivel (EQ)

Barra sólida desde el borde hacia dentro; la longitud ~ velocity, el
color ~ pitch class. Fade = se acorta y pierde brillo.

*Pros:* se lee el ataque. *Contras:* más “analizador” que neón.

### F — Anillos partidos (medio círculo)

Medio aro en cada esquina o a media altura, radio ~ pitch. Mejor para
1–2 notas; un acorde de 4 se empasta.

---

## Opciones de color

1. **12 hues fijos** (C rojo, C# naranja… B violeta). Se memoriza.
2. **Familia del show:** cian / magenta / ámbar / verde matrix (misma
   paleta que `lyric_render.TEMAS_ROBOT`). Menos notas distintas, más
   cohesión.
3. **Raíz cian, tensiones magenta** (o al revés). El acorde se lee como
   “una + las otras”.
4. **Velocity → temperatura:** flojo ámbar, fuerte blanco-azul.

Recomendación v1: **(3) raíz cian / tensiones magenta**, paleta ya
usada. Si se echa de menos el grado, pasar a (1).

---

## Opciones de tiempo

| | Ataque | Fade | Si llega otro ACRD |
|---|---|---|---|
| **T1 golpe + cola** (v1) | 0 ms | 0.55 s exp | notas comunes se re-pegan a 1; las que salen siguen el fade |
| **T2 ligado** | 0 ms | 1.2 s | se ve el legato; puede empastar |
| **T3 staccato** | 0 ms | 0.25 s | muy rítmico; se pierde el acorde sostenido |
| **T4 hold + release** | 0 ms | no fade mientras no haya ACRD nuevo; al cambiar, fade 0.4 s | más fiel al audio; si el último acorde no tiene sucesor, queda encendido hasta STOP |

Recomendación v1: **T1**. En STOP/END, fade forzado de todo.

---

## Cómo no pisar lo que ya hay

- Nunca pintar en `x ∈ [56, 744]` (deja 56 px/lado; la cinta y las
  letras viven al centro).
- Punch igual que el overlay: lum ≤ 6 transparente. El tubo es hueco
  (trazo + glow); el interior del rectángulo no se rellena de negro.
- Si un icono CC o una letra invade el margen, gana el overlay (se
  pinta después).
- Sombrilla: `invert` ya voltea el frame; los lados siguen siendo
  lados físicos.

---

## Implementación (cuando toque)

1. Cliente: parsear `ACRD` en `main.py` y `handle_acrd` en el
   orquestador (mismo `ts + base_delay` que CC/NOTA).
2. `DisplayExecutor.pulse_chord(notes, velocity)` → lista de voces
   `{note, vel, born, peak}`.
3. Módulo chico `vocoder_neon.py` (o métodos en el ribbon): `blit` de
   las bandas laterales sobre el frame **después** del ribbon y
   **antes** del overlay.
4. LIVE de Robotracker: el mismo blit o un draw Kivy, vía
   `shared_visuals`, para no diseñar a ciegas.
5. Tests: parseo ACRD, fade (pico → valle), no pintar el centro, STOP
   apaga.

No hace falta tocar el nodo vocoder ni Carla.

## Propuesta para el primer corte

**A2 + color 3 + T1:** tubos verticales, graves izq / agudos der, raíz
cian y tensiones magenta, fade 0.55 s.

Si al verlo en LIVE se lee mal el acorde, el cambio barato es A3
(raíz siempre a la izquierda) o B (celdas por semitono).
