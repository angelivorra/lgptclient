# lgpt_gater — gate rítmico sincronizado a BPM (LADSPA)

Plugin LADSPA propio para el rack de Carla del vocoder. Trocea la voz en un
patrón de bloques **sonido/silencio** sincronizado al compás, con la finura
controlada por un solo knob (el **knob 4** de red, ver más abajo). Va en el
camino de voz **antes** del delay/reverb del `.carxp`, para que las colas de
esos efectos suenen durante los silencios (efecto tipo "trance-gate").

## Por qué un plugin propio y no uno existente

Solo se usa LADSPA (sin LV2). Ningún plugin de `/usr/lib/ladspa` hace esto:
los tremolos/ring-mod no dan silencio real en bloques sincronizados al compás.
El único candidato, `ringmod_1188` en modo AM con onda cuadrada, tiene la
frecuencia mínima en **1 Hz**, con lo que el patrón `SM` (medio compás, ~0.5 Hz
a 120 BPM) es inalcanzable en el rango normal de tempos. De ahí este plugin.

## Puertos

El **orden** de los puertos fija los índices de parámetro que Carla expone por
OSC (los usa `vocoder/flask/tcp_client.py`):

| Puerto | Tipo | Rango | Índice de parámetro Carla |
|--------|------|-------|---------------------------|
| `Input`   | audio in  | — | — |
| `Output`  | audio out | — | — |
| `BPM`     | control in | 30–300 (def 120) | **0** |
| `Pattern` | control in | 0–1 (def 0)      | **1** |

## Patrón (knob 4)

El recorrido del knob se divide en 4 cuartos. `S` = suena, `M` = silencio;
la unidad es **un compás de 4 negras** (`240/BPM` s). El compás se parte en
`2·P` porciones iguales (`P` = nº de pares del paso); las de índice par suenan
y las impares se silencian.

| `Pattern` | Paso | Patrón por compás |
|-----------|------|-------------------|
| 0.00–0.25 | 1 | passthrough (todo suena) |
| 0.25–0.50 | 2 | `SM` |
| 0.50–0.75 | 3 | `SMSM` |
| 0.75–1.00 | 4 | `SMSMSM` |

Hay una rampa anti-clic de ~4 ms en cada transición, y la fase se reinicia al
cambiar de tempo o de paso, para que el patrón arranque siempre en `S` justo
cuando el intérprete gira el knob o cambia de canción. Como LADSPA no expone el
transporte, el gate corre en tiempo libre sincronizado al BPM (no cuadra al
downbeat de la canción, pero sí a su tempo).

## Compilar e instalar

Se compila en la propia máquina de destino (este PC y la Raspberry Pi ARM del
vocoder): así el `.so` tiene la arquitectura correcta sin toolchain cruzado ni
internet en la Pi. `ladspa.h` va vendorado aquí para no depender de `ladspa-sdk`.

```bash
make                 # -> lgpt_gater.so
sudo make install    # -> /usr/lib/ladspa/lgpt_gater.so  (ruta del <Binary> del carxp)
```

En la Pi lo hace Ansible (`ansible/roles/vocoder-actualiza`): sincroniza este
directorio, ejecuta `make` y `make install`, y reinicia Carla si el `.so` cambió.

## Cómo llega el knob 4 y el BPM

- El sinte marca `pot4` como pot de red fijo (`red = true` en
  `sinte/lttileplayer.toml`), igual que el knob 3 (reverb/delay) y el 7 (crusher).
  Reenvía su CC por TCP como `control = 4`.
- El vocoder (`vocoder/flask/tcp_client.py`) mapea `control 4` → parámetro
  `Pattern` del gater (plugin id 8 del rack), y envía el BPM de la canción al
  parámetro `BPM`, ambos por OSC a Carla.
