#!/usr/bin/env python3
"""
Reorganiza los samples ya generados en `samples/destino` agrupándolos POR TIPO
DE INSTRUMENTO *dentro de cada pack* (carpeta de primer nivel). No se cruzan
packs entre sí: cada pack conserva su carpeta y dentro se crean subcarpetas
(bass/, lead/, drums-kick/, fx/, otros/...).

Uso:
    python organiza_samples.py --report      # solo análisis, NO mueve nada (read-only)
    python organiza_samples.py                # dry-run: muestra el plan, NO mueve nada
    python organiza_samples.py --apply        # APLICA: mueve los archivos de verdad
    python organiza_samples.py --root /otra/ruta   # opera sobre otra carpeta

Recomendado: ejecutar primero `--report`, revisar el reparto y los nombres que
caen en "otros", ajustar el diccionario CATEGORIES de abajo si hace falta, y
sólo entonces lanzar `--apply`.

NO lo ejecutes con --apply mientras se estén generando los samples.
"""

import argparse
import os
import re
import shutil
from collections import defaultdict

# ---------------------------------------------------------------------------
# Reglas de clasificación.
#
# Se evalúan EN ORDEN: la primera categoría que coincida gana. Por eso lo
# específico va antes que lo genérico (p.ej. "synthlead" debe caer en lead
# antes de que el genérico "synth" lo capture).
#
# Cada regla es (categoria, [substrings], [tokens_exactos]).
#  - substrings: coincide si el texto del nombre CONTIENE la cadena.
#  - tokens:     coincide sólo si aparece como "palabra" suelta (separada por
#                espacios, guiones, guiones bajos, puntos o dígitos). Útil para
#                códigos cortos y ambiguos como bd/sd/hh/cr/rd.
# ---------------------------------------------------------------------------
CATEGORIES = [
    # --- Percusión / batería (lo más específico primero) ---------------------
    ("drums-kick",  ["kick", "bassdrum", "bass drum", "boom"],            ["bd", "kick1", "kick2"]),
    ("drums-snare", ["snare", "snappy"],                                  ["sd", "sn"]),
    ("drums-clap",  ["clap", "handclap"],                                 []),
    ("drums-hihat", ["hihat", "hi-hat", "hi hat", "hat", "closed", "open-hh", "openhh"],
                                                                          ["hh", "oh", "ch", "chh", "ohh"]),
    ("drums-tom",   ["tom"],                                              ["lt", "mt", "ht"]),
    ("drums-cymbal",["cymbal", "crash", "ride", "cowbell"],               ["cr", "rd", "cym"]),
    ("perc",        ["perc", "rimshot", "rim", "conga", "bongo", "shaker",
                     "tambour", "clave", "woodblock", "wood block", "block",
                     "metal", "click", "cabasa", "guiro", "triangle",
                     "castanet", "agogo", "timbale", "djembe", "tabla"],   ["rs"]),

    # --- Instrumentos tonales (compuestos antes que genéricos) ---------------
    ("bass",     ["bass", "fretless", "contrabass", "contrabus", "upright"], []),  # epbass, resbass, doublebass, synthbass, volcabass
    ("lead",     ["lead"],                                                []),  # synthlead
    ("pad",      ["pad"],                                                 []),  # synthpad
    ("brass",    ["brass", "trumpet", "trombone", "flugelhorn", "horn",
                  "tuba", "saxophone", "sax", "cornet", "bugle",
                  "fanfar"],                                              []),
    ("strings",  ["string", "strng", "violin", "cello", "viola",
                  "orchestra", "orkest", "pizz", "fiddle", "ensemble"],   []),
    ("guitar",   ["guitar", "gtr", "mandolin", "banjo", "ukulele",
                  "fuzzguit"],                                            []),
    ("mallet",   ["vibraphone", "marimba", "xylophone", "glocken", "glock",
                  "celesta", "celeste", "toypiano", "toy piano", "kalimba",
                  "bell", "chime", "tubular"],                            ["vib", "vibe", "vibes"]),
    ("winds",    ["flute", "clarinet", "clari", "oboe", "harmonica",
                  "whistle", "recorder", "bassoon", "piccolo", "ocarina",
                  "panflute", "pan flute", "chiff"],                      []),
    ("keys",     ["piano", "organ", "comorg", "hammond", "hammnd",
                  "harpsichord", "clavi", "clavichord", "accordion",
                  "keys", "rhodes", "wurli", "epiano", "e.piano",
                  "harpejji"],                                            []),
    ("voice",    ["voice", "vocal", "choir", "vox", "aah", "ooh",
                  "speak", "talk"],                                       []),

    # --- Sintes / chip (tonal sintético) -------------------------------------
    ("synth",    ["synth", "pulse", "square", "sine", "pokey", "sms2",
                  "ym2413", "c64", "atari", "saa", "sid", "hardpcm",
                  "chip", "8bit", "8-bit", "8 bit", "oscillator",
                  "waveform", "poly", "tapepoly", "ms20", "moog", "analog",
                  "analogue", "digalog", "vco"],                          ["saw", "sqr", "tri", "pwm", "am", "fm", "sub"]),

    # --- Efectos / SFX / sonidos de juego ------------------------------------
    ("fx",       ["fx", "sfx", "noise", "blip", "bleep", "blop", "zap",
                  "laser", "ufo", "cosmic", "sweep", "glitch", "drone",
                  "siren", "explos", "rocket", "space", "funny", "irrlicht",
                  "mother", "warp", "beam", "alien", "pew", "wobble",
                  "vocoder",
                  # nombres/acciones típicos de arcade
                  "coin", "death", "die", "fire", "jump", "bonus",
                  "warning", "success", "background", "thrust", "shoot",
                  "kill", "score", "beep", "gameover", "game over", "extra",
                  "fruit", "thump", "cascade", "tone", "song", "intro",
                  # consolas/juegos concretos del pack arcade
                  "nintendo", "pacman", "galaxian", "galaga", "asteroids",
                  "centipede", "frogger", "donkeykong", "qbert", "qix",
                  "carnival", "burgertime", "defender", "joust", "tron",
                  "tetris", "mario", "sonic"],                            []),
]

AUDIO_EXTS = (".wav",)

# separadores que delimitan "tokens" dentro del nombre
_TOKEN_SPLIT = re.compile(r"[^a-z0-9#]+")


def classify(filename: str) -> str:
    """Devuelve la categoría para un nombre de archivo, o 'otros' si nada casa."""
    name = os.path.splitext(filename)[0].lower()
    tokens = set(t for t in _TOKEN_SPLIT.split(name) if t)
    for category, substrings, exact_tokens in CATEGORIES:
        for sub in substrings:
            if sub in name:
                return category
        for tok in exact_tokens:
            if tok in tokens:
                return category
    return "otros"


def unique_destination(dest_path: str, planned: set) -> str:
    """Evita colisiones: si el destino ya existe (en disco o ya planificado),
    añade un sufijo _1, _2, ... antes de la extensión."""
    if dest_path not in planned and not os.path.exists(dest_path):
        return dest_path
    root, ext = os.path.splitext(dest_path)
    i = 1
    while True:
        candidate = f"{root}_{i}{ext}"
        if candidate not in planned and not os.path.exists(candidate):
            return candidate
        i += 1


def iter_packs(root: str):
    """Cada subcarpeta de primer nivel de `root` es un pack."""
    for entry in sorted(os.listdir(root)):
        pack_dir = os.path.join(root, entry)
        if os.path.isdir(pack_dir):
            yield entry, pack_dir


def build_plan(root: str):
    """Construye el plan de movimientos. Devuelve:
       moves: lista de (origen, destino)
       stats: dict pack -> Counter de categorías
       otros: lista de nombres clasificados como 'otros' (para revisión)
    """
    moves = []
    stats = defaultdict(lambda: defaultdict(int))
    otros = []
    planned = set()

    for pack_name, pack_dir in iter_packs(root):
        # Las subcarpetas existentes pueden indicar el instrumento (p.ej.
        # K4-PickBass/, K4-Oboe/), así que clasificamos por la RUTA relativa
        # dentro del pack, no sólo por el nombre del archivo.
        pack_category = classify(pack_name)
        for cur_root, _dirs, files in os.walk(pack_dir):
            for fname in files:
                if fname.startswith("._") or not fname.lower().endswith(AUDIO_EXTS):
                    continue
                src = os.path.join(cur_root, fname)
                rel_in_pack = os.path.relpath(src, pack_dir)
                category = classify(rel_in_pack)
                # Si nada casa en la ruta, usa la pista del nombre del pack
                # (p.ej. "Low Fat Bass" cuyos archivos son sólo números).
                if category == "otros" and pack_category != "otros":
                    category = pack_category
                stats[pack_name][category] += 1
                if category == "otros":
                    otros.append(fname)

                dest_dir = os.path.join(pack_dir, category)
                dest = os.path.join(dest_dir, fname)

                # Si ya está en su sitio, no hay nada que mover.
                if os.path.normpath(src) == os.path.normpath(dest):
                    continue
                dest = unique_destination(dest, planned)
                planned.add(dest)
                moves.append((src, dest))

    return moves, stats, otros


def print_report(stats, otros, total_files):
    cat_totals = defaultdict(int)
    for pack, cats in stats.items():
        for cat, n in cats.items():
            cat_totals[cat] += n

    print("\n=== Reparto GLOBAL por categoría ===")
    for cat, n in sorted(cat_totals.items(), key=lambda kv: -kv[1]):
        pct = 100 * n / total_files if total_files else 0
        print(f"  {cat:14s} {n:6d}  ({pct:4.1f}%)")
    print(f"  {'TOTAL':14s} {total_files:6d}")

    print("\n=== Reparto por pack ===")
    for pack in sorted(stats):
        cats = stats[pack]
        resumen = ", ".join(f"{c}:{n}" for c, n in sorted(cats.items(), key=lambda kv: -kv[1]))
        print(f"  [{pack}] -> {resumen}")

    if otros:
        print(f"\n=== Muestras en 'otros' ({len(otros)} archivos) — revisa si faltan keywords ===")
        # muestra hasta 60 nombres únicos
        vistos = []
        seen = set()
        for n in otros:
            if n not in seen:
                seen.add(n)
                vistos.append(n)
            if len(vistos) >= 60:
                break
        for n in vistos:
            print(f"    {n}")
        if len(seen) > len(vistos):
            print(f"    ... y {len(seen) - len(vistos)} nombres distintos más")


def apply_moves(moves):
    moved = 0
    errors = 0
    for src, dest in moves:
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(src, dest)
            moved += 1
        except Exception as e:
            errors += 1
            print(f"!! ERROR moviendo {src} -> {dest}: {e}")
    return moved, errors


def remove_empty_dirs(root):
    """Elimina subcarpetas que hayan quedado vacías tras mover los archivos.
    No borra las carpetas de pack (primer nivel) ni la raíz."""
    removed = 0
    for cur_root, dirs, files in os.walk(root, topdown=False):
        if os.path.normpath(cur_root) == os.path.normpath(root):
            continue
        # ¿es un pack de primer nivel?
        if os.path.dirname(os.path.normpath(cur_root)) == os.path.normpath(root):
            continue
        try:
            if not os.listdir(cur_root):
                os.rmdir(cur_root)
                removed += 1
        except OSError:
            pass
    return removed


def main():
    parser = argparse.ArgumentParser(description="Organiza samples por tipo de instrumento dentro de cada pack.")
    default_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples", "destino")
    parser.add_argument("--root", default=default_root, help="Carpeta a organizar (por defecto samples/destino)")
    parser.add_argument("--report", action="store_true", help="Sólo analizar y mostrar el reparto (no mueve nada)")
    parser.add_argument("--apply", action="store_true", help="Aplicar de verdad los movimientos")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        parser.error(f"No existe la carpeta: {root}")

    print(f"Carpeta: {root}")
    moves, stats, otros = build_plan(root)
    total = sum(sum(c.values()) for c in stats.values())

    print_report(stats, otros, total)

    print(f"\n=== Movimientos planificados: {len(moves)} ===")

    if args.report:
        print("\n(modo --report: no se ha movido nada)")
        return

    if not args.apply:
        # dry-run: muestra una muestra del plan
        print("\n(dry-run: no se mueve nada. Usa --apply para ejecutar)")
        for src, dest in moves[:20]:
            print(f"  {os.path.relpath(src, root)}  ->  {os.path.relpath(dest, root)}")
        if len(moves) > 20:
            print(f"  ... y {len(moves) - 20} más")
        return

    # --apply
    moved, errors = apply_moves(moves)
    removed = remove_empty_dirs(root)
    print(f"\nHecho. Movidos: {moved} | Errores: {errors} | Carpetas vacías eliminadas: {removed}")


if __name__ == "__main__":
    main()
