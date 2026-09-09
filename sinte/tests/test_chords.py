#!/usr/bin/env python3
"""Tests de la tabla de acordes del comando CHRD."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chords import (  # noqa: E402
    CHORD_TYPES,
    chord_intervals,
    chord_label,
    cycle_chord,
    expand_chord_notes,
)


class TestChordTypes(unittest.TestCase):
    def test_nombres_caben_en_4(self):
        for name, _iv in CHORD_TYPES:
            self.assertLessEqual(len(name), 4, name)

    def test_maj_min(self):
        self.assertEqual(chord_intervals(0), (4, 7))
        self.assertEqual(chord_intervals(1), (3, 7))
        self.assertEqual(chord_label(0).strip(), "maj")
        self.assertEqual(chord_label(1).strip(), "min")

    def test_indice_invalido(self):
        self.assertEqual(chord_intervals(99), ())
        self.assertEqual(chord_label(99), "0063")

    def test_cycle_wrap(self):
        last = len(CHORD_TYPES) - 1
        self.assertEqual(cycle_chord(0, -1), last)
        self.assertEqual(cycle_chord(last, 1), 0)
        self.assertEqual(cycle_chord(0, 1), 1)

    def test_cycle_fuera_de_rango(self):
        self.assertEqual(cycle_chord(0xFF, 1), 1)
        self.assertEqual(cycle_chord(0xFF, -1), len(CHORD_TYPES) - 1)

    def test_expand_descarta_fuera_de_midi(self):
        self.assertEqual(expand_chord_notes(60, (4, 7)), [60, 64, 67])
        # 120 + 14 = 134, fuera
        self.assertEqual(expand_chord_notes(120, (4, 14)), [120, 124])


if __name__ == "__main__":
    unittest.main()
