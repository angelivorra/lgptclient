#!/usr/bin/env python3
"""Etiquetas amigables del filtro (sin audio ni UI)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from filter_ui import (  # noqa: E402
    FILTER_MODES, cut_label, field_help, mode_from_param, mode_label,
    normalize_mode, res_label, type_label,
)


class TestFilterUi(unittest.TestCase):
    def test_modos_conocidos(self):
        self.assertEqual(normalize_mode("bassy"), "original")
        self.assertEqual(normalize_mode("lp"), "lp")
        self.assertEqual(mode_from_param(2), "lp")
        self.assertEqual(mode_from_param(99), FILTER_MODES[99 % 6])

    def test_cut_lp_vs_hp(self):
        self.assertEqual(cut_label(0, "lp"), "muy sordo")
        self.assertEqual(cut_label(255, "lp"), "abierto")
        self.assertEqual(cut_label(0, "hp"), "abierto")
        self.assertEqual(cut_label(255, "hp"), "solo agudos")
        self.assertEqual(cut_label(0, "bp"), "en graves")

    def test_res_y_type(self):
        self.assertEqual(res_label(0), "limpio")
        self.assertEqual(res_label(255), "chilla")
        self.assertEqual(type_label(0), "grave")
        self.assertEqual(type_label(255), "agudo")

    def test_ayuda_cambia_con_el_modo(self):
        lp = field_help("filter cut", "lp")
        hp = field_help("filter cut", "hp")
        self.assertIn("sordo", lp)
        self.assertIn("agudo", hp)
        self.assertNotEqual(lp, hp)
        self.assertTrue(field_help("filter mode"))
        self.assertIn("no se usa", field_help("filter type", "lp"))

    def test_mode_label(self):
        self.assertEqual(mode_label("lp"), "grave")
        self.assertIn("graves", mode_label("lp", long=True))


if __name__ == "__main__":
    unittest.main()
