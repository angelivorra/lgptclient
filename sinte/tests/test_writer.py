"""Round-trip del writer de lgptsav.dat: guardar y recargar produce los
mismos arrays que el proyecto original."""

import tempfile
import unittest
from pathlib import Path

from lgpt_parser import LGPTProject
from lgpt_writer import project_to_xml, save_project

SONGS_DIR = Path(__file__).resolve().parent.parent / "songs"

ARRAY_ATTRS = ("song", "chains", "transposes", "notes", "instruments",
               "cmd1", "param1", "cmd2", "param2")


def _load(path: Path) -> LGPTProject:
    project = LGPTProject(path)
    project.load()
    return project


class TestWriterRoundTrip(unittest.TestCase):
    def test_all_songs(self):
        songs = sorted(d for d in SONGS_DIR.iterdir()
                       if (d / "lgptsav.dat").exists())
        self.assertTrue(songs, f"sin canciones en {SONGS_DIR}")
        for song_dir in songs:
            with self.subTest(song=song_dir.name):
                self._round_trip(song_dir)

    def _round_trip(self, song_dir: Path):
        original = _load(song_dir)
        # tocar algo para verificar que se guardan los cambios en memoria
        original.notes[0] = 60
        original.project["tempo"] = "123"

        with tempfile.TemporaryDirectory() as tmp:
            out = save_project(original, Path(tmp) / "lgptsav.dat",
                               backup=False)
            reloaded = _load(out.parent)

        for attr in ARRAY_ATTRS:
            self.assertEqual(getattr(original, attr), getattr(reloaded, attr),
                             f"array {attr} difiere")
        self.assertEqual(original.project["tempo"], "123")
        self.assertEqual(reloaded.project["tempo"], "123")
        self.assertEqual(original.tables, reloaded.tables)
        self.assertEqual(original.grooves, reloaded.grooves)
        self.assertEqual(original.instrument_bank, reloaded.instrument_bank)

    def test_backup(self):
        song_dir = sorted(d for d in SONGS_DIR.iterdir()
                          if (d / "lgptsav.dat").exists())[0]
        project = _load(song_dir)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            out = tmp / "lgptsav.dat"
            out.write_text("ORIGINAL")
            save_project(project, out, backup=True)
            self.assertEqual((tmp / "lgptsav.dat.bak").read_text(), "ORIGINAL")

    def test_xml_sin_comprimir_legible(self):
        song_dir = sorted(d for d in SONGS_DIR.iterdir()
                          if (d / "lgptsav.dat").exists())[0]
        project = _load(song_dir)
        text = project_to_xml(project)
        self.assertTrue(text.startswith("<LITTLEGPTRACKER>"))


if __name__ == "__main__":
    unittest.main()
