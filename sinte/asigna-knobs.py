#!/usr/bin/env python3
"""Propone knobs para una canción midiendo, no adivinando.

Uso:  ./asigna-knobs.py lgpt_Sartenazo.VERSION1 [--escribe]

Para cada canal que suene y no esté muteado, prueba todos los efectos y
mide dos cosas sobre el audio real del canal:

* **cambio audible** — cuánto se mueve el espectro entre 60 Hz y 4 kHz
  después de un paso alto a 60 Hz. Ese paso alto imita lo que de verdad
  sale por un altavoz de PA: sin él, un efecto que solo añade subgraves
  parece enorme en la medida y no se oye en el bolo.
* **cambio de nivel** — un efecto que sube 12 dB parece impresionante y
  solo está subiendo el volumen. Los que pasan de `TOPE_NIVEL` se
  descartan aunque midan mucho.

Con eso ordena los efectos por canal y reparte los knobs libres siguiendo
la pauta de la casa: el LPD8 tiene dos filas de cuatro, así que los knobs
N y N+4 son la misma columna y van al mismo canal.

Los canales se miden en su propia ventana de actividad: varias canciones
tienen pistas que no entran hasta el segundo 30, y midiéndolas desde el
principio salen todas a cero (pasó con el bajo de EBLUES).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

from lgpt_engine import Engine, EFFECT_PRESETS       # noqa: E402
from lgpt_player import parse_pot_target             # noqa: E402

SR = 44100
BLOQUE = 2048
TOPE_NIVEL = 6.0        # dB; por encima de esto el efecto es un subidón de volumen
MIN_CAMBIO = 3.0        # dB; por debajo no se nota y no merece gastar un knob
VENTANA = 20.0          # segundos de medida por efecto
# `tempo` es global y no compite por canal: se reserva al último knob.
SIN_INTERES = {"satan", "space"}     # casi siempre disparan el nivel


def paso_alto(m, fc=60.0):
    X = np.fft.rfft(m)
    fr = np.fft.rfftfreq(len(m), 1 / SR)
    return np.fft.irfft(X * (1.0 / (1.0 + (fc / np.maximum(fr, 1.0)) ** 4)), len(m))


def cambio_audible(seco, proc):
    """Cuánto cambia lo que se oye: dB por banda de tercio de octava,
    ponderados por la energía que esa banda tenía en seco.

    Las dos cosas importan y las dos costaron una versión fallida:

    * **Por bandas y no por bins.** Promediando bin a bin, un espectro
      disperso (los `seq` de sartenazo tienen el 70% de sus bins a menos de
      1e-6 del máximo) sale disparado: en las bandas vacías la relación la
      marca el epsilon, no la señal, y cualquier efecto que meta algo ahí
      medía 88 dB y parecía el mejor de todos.
    * **Ponderando por energía.** Sin ponderar, una banda muda pesa igual
      que una donde está todo el sonido. Eso hundía a `acid_lp` a 3 dB
      cuando por bandas se ve que quita 19 dB en 800-2000 Hz y 35 dB en
      2-4 kHz, o sea que se lo lleva por delante. Ponderando, el número
      vuelve a ordenar los efectos como los ordena el oído.
    """
    a, b = paso_alto(seco), paso_alto(proc)
    A = np.abs(np.fft.rfft(a * np.hanning(len(a)))) ** 2
    B = np.abs(np.fft.rfft(b * np.hanning(len(b)))) ** 2
    fr = np.fft.rfftfreq(len(a), 1 / SR)
    bordes = 60.0 * 2 ** (np.arange(0, 22) / 3.0)      # tercios hasta ~8 kHz
    dif, peso = [], []
    for lo, hi in zip(bordes[:-1], bordes[1:]):
        m = (fr >= lo) & (fr < hi)
        if not m.any():
            continue
        ea, eb = float(A[m].sum()), float(B[m].sum())
        if ea <= 0.0:
            continue
        dif.append(abs(10 * np.log10(max(eb, 1e-20) / ea)))
        # Ponderación A sobre la energía: en un bajo casi toda la energía
        # está por debajo de 200 Hz, donde el oído es mucho menos sensible.
        # Sin esto, tocar los agudos de un bajo "no cuenta" aunque se oiga
        # perfectamente el cambio de timbre.
        peso.append(ea * pond_a(np.sqrt(lo * hi)) ** 2)
    if not dif:
        return 0.0
    peso = np.array(peso)
    if peso.sum() <= 0:
        return 0.0
    peso /= peso.sum()
    return float(np.dot(np.array(dif), peso))


def pond_a(f):
    """Curva A (IEC 61672), en veces (no en dB)."""
    f2 = f * f
    num = 12194.0 ** 2 * f2 * f2
    den = ((f2 + 20.6 ** 2)
           * np.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2))
           * (f2 + 12194.0 ** 2))
    return num / den / 0.7943  # normalizada a 1 en 1 kHz


def render(proyecto, canal, efecto, valor, salto, dur, mute):
    eng = Engine(proyecto, sample_rate=SR)
    eng.start()
    for c in mute:
        eng.push_event("param", c, "volume", 0)
    if canal is not None:
        for c in range(8):
            if c != canal:
                eng.push_event("param", c, "volume", 0)
    n = int(SR * (salto + dur))
    out = np.zeros((n, 2), dtype=np.float32)
    pos = 0
    while pos < n - BLOQUE:
        if efecto:
            eng.push_event("param", canal, efecto, int(round(valor * 127)))
        out[pos:pos + BLOQUE] = eng.render(BLOQUE)[:BLOQUE]
        pos += BLOQUE
    return out.mean(1)[int(SR * salto):]


def ventana_activa(proyecto, canal, mute, total=120.0):
    """Cuándo suena el canal, para medirlo donde hay señal."""
    m = np.abs(render(proyecto, canal, None, 0, 0.0, total, mute))
    w = int(SR * 0.5)
    env = np.array([m[i * w:(i + 1) * w].max() for i in range(len(m) // w)])
    act = np.where(env > 0.002)[0]
    if not len(act):
        return None
    ini = act[0] * 0.5
    largo = (act[-1] - act[0]) * 0.5
    return ini, min(max(largo, 5.0), VENTANA)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cancion")
    ap.add_argument("--escribe", action="store_true",
                    help="guarda los knobs propuestos en el robotraca.json")
    args = ap.parse_args()

    proyecto = AQUI / "songs" / args.cancion
    if not (proyecto / "lgptsav.dat").is_file():
        sys.exit(f"no encuentro {proyecto}")
    cfg_path = proyecto / "robotraca.json"
    cfg = json.loads(cfg_path.read_text()) if cfg_path.is_file() else {}
    mute = [int(c) for c in (cfg.get("mute") or [])]
    pots = dict(cfg.get("pots") or {})

    ocupados = {}          # canal -> efectos ya asignados
    for k, t in pots.items():
        r = parse_pot_target(t)
        if r and r[1] != "tempo":
            ocupados.setdefault(r[0][0], set()).add(r[1])
    libres = [f"pot{i}" for i in range(1, 9) if f"pot{i}" not in pots]
    print(f"{args.cancion}: mute {mute}, "
          f"{len(pots)} knobs puestos, libres {libres}\n")
    if not libres:
        sys.exit("no queda ningún knob libre")

    efectos = [e for e in EFFECT_PRESETS if e not in SIN_INTERES]
    candidatos = {}
    for canal in range(8):
        if canal in mute:
            continue
        v = ventana_activa(proyecto, canal, mute)
        if v is None:
            continue
        salto, dur = v
        seco = render(proyecto, canal, None, 0, salto, dur, mute)
        r0 = float(np.sqrt((seco ** 2).mean()))
        if r0 < 1e-4:
            continue
        filas = []
        for ef in efectos:
            y = render(proyecto, canal, ef, 1.0, salto, dur, mute)
            db = 20 * np.log10(max(float(np.sqrt((y ** 2).mean())), 1e-9) / r0)
            if abs(db) > TOPE_NIVEL:
                continue
            c = cambio_audible(seco, y)
            if c >= MIN_CAMBIO and ef not in ocupados.get(canal, set()):
                filas.append((c, db, ef))
        filas.sort(reverse=True)
        if filas:
            candidatos[canal] = (salto, dur, filas)
            print(f"canal {canal} (pista {canal+1}), mide {salto:.0f}-"
                  f"{salto+dur:.0f}s:")
            for c, db, ef in filas[:4]:
                print(f"    {ef:12}{c:7.1f} dB de cambio{db:+7.1f} dB de nivel")

    # Reparto: primero las columnas completas (N y N+4 libres), a los canales
    # con más margen de mejora; el resto, uno a uno.
    orden = sorted(candidatos, key=lambda c: -candidatos[c][2][0][0])
    orden = [c for c in orden if c not in ocupados] + \
            [c for c in orden if c in ocupados]
    nuevos = {}
    columnas = [(f"pot{i}", f"pot{i+4}") for i in range(1, 5)
                if f"pot{i}" in libres and f"pot{i+4}" in libres]
    sueltos = [k for k in libres
               if not any(k in par for par in columnas)]
    for canal in list(orden):
        if not columnas:
            break
        arriba, abajo = columnas.pop(0)
        top = candidatos[canal][2][:2]
        nuevos[arriba] = f"{canal}:{top[0][2]}"
        if len(top) > 1:
            nuevos[abajo] = f"{canal}:{top[1][2]}"
        orden.remove(canal)
    for canal in orden:
        if not sueltos:
            break
        nuevos[sueltos.pop(0)] = f"{canal}:{candidatos[canal][2][0][2]}"

    print("\npropuesta:")
    for k in sorted(nuevos, key=lambda x: int(x[3:])):
        ch, par, _ = parse_pot_target(nuevos[k])
        print(f"   {k} -> pista {ch[0]+1} : {par}")
    if args.escribe:
        pots.update(nuevos)
        cfg["pots"] = pots
        cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
        print(f"\nescrito en {cfg_path}")
    else:
        print("\n(no se ha escrito nada; usa --escribe para guardarlo)")


if __name__ == "__main__":
    main()
