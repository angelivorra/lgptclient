#!/usr/bin/env python3
"""Writer de lgptsav.dat (LGPT).

Reencodifica los buffers del nodo SONG (SONG/CHAINS/TRANSPOSES/NOTES/
INSTRUMENTS/COMMAND1/PARAM1/COMMAND2/PARAM2) desde los arrays del
LGPTProject y escribe XML plano. El lector del upstream (y
`lgpt_parser.decompress_lgptsav`) aceptan tanto el XML plano como el
comprimido LZ77, así que no hace falta comprimir para que el archivo siga
abriéndose en LGPT y en sinte.

Los nodos que robotracker no edita (TABLES, GROOVES, INSTRUMENTBANK, MIXER)
se conservan tal cual del árbol original parseado.
"""

from __future__ import annotations

import shutil
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

from lgpt_parser import LGPTProject

# tag XML -> atributo de LGPTProject con el contenido del buffer
_BYTE_BUFFERS = {
    "SONG": "song",
    "CHAINS": "chains",
    "TRANSPOSES": "transposes",
    "NOTES": "notes",
    "INSTRUMENTS": "instruments",
}
_FOURCC_BUFFERS = {"COMMAND1": "cmd1", "COMMAND2": "cmd2"}
_SHORT_BUFFERS = {"PARAM1": "param1", "PARAM2": "param2"}


def _encode_buffer(project: LGPTProject, tag: str) -> bytes:
    if tag in _BYTE_BUFFERS:
        return bytes(getattr(project, _BYTE_BUFFERS[tag]))
    if tag in _FOURCC_BUFFERS:
        cmds = getattr(project, _FOURCC_BUFFERS[tag])
        return b"".join(c.encode("ascii") for c in cmds)
    if tag in _SHORT_BUFFERS:
        params = getattr(project, _SHORT_BUFFERS[tag])
        # little-endian, igual que los lee el parser (ver _decode_shorts)
        return b"".join(struct.pack("<H", p) for p in params)
    raise KeyError(tag)


def project_to_xml(project: LGPTProject) -> str:
    """Serializa el proyecto a XML plano, actualizando los buffers SONG y
    los PARAMETER de PROJECT desde los arrays en memoria."""
    if project.root is None:
        raise ValueError("proyecto no cargado (root es None)")
    root = project.root

    project_node = root.find("PROJECT")
    if project_node is not None:
        for param in project_node.findall("PARAMETER"):
            name = param.get("NAME")
            if name in project.project:
                param.set("VALUE", str(project.project[name]))

    song_node = root.find("SONG")
    for child in song_node:
        tag = child.tag
        if tag in _BYTE_BUFFERS or tag in _FOURCC_BUFFERS or tag in _SHORT_BUFFERS:
            data = _encode_buffer(project, tag)
            del child[:]  # fuera los DATA antiguos (runs + hex mezclados)
            node = ET.SubElement(child, "DATA")
            node.text = data.hex().upper()

    ET.indent(root, space="    ")
    return ET.tostring(root, encoding="unicode")


def save_project(project: LGPTProject, path: Path | None = None,
                 backup: bool = True) -> Path:
    """Escribe el proyecto en `path` (defecto: su lgptsav.dat original).
    Con `backup=True` guarda antes una copia en lgptsav.dat.bak."""
    path = Path(path) if path else Path(project.dir) / "lgptsav.dat"
    if backup and path.exists():
        shutil.copy2(path, path.with_suffix(".dat.bak"))
    path.write_text(project_to_xml(project), encoding="utf-8")
    return path
