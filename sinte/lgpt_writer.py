#!/usr/bin/env python3
"""Writer de lgptsav.dat (LGPT).

Reencodifica los buffers del nodo SONG (SONG/CHAINS/TRANSPOSES/NOTES/
INSTRUMENTS/COMMAND1/PARAM1/COMMAND2/PARAM2) desde los arrays del
LGPTProject y escribe XML plano. El lector del upstream (y
`lgpt_parser.decompress_lgptsav`) aceptan tanto el XML plano como el
comprimido LZ77, así que no hace falta comprimir para que el archivo siga
abriéndose en LGPT y en sinte.

Los nodos que robotracker no edita (TABLES, GROOVES, MIXER) se conservan
tal cual del árbol original parseado. INSTRUMENTBANK sí se sincroniza con
el banco en memoria: actualiza PARAM existentes, quita los INSTRUMENT que
ya no están (Compact Instruments) y **añade** los IDs nuevos (pista 0
creada al cargar una canción legacy, u otros inyectados en memoria).
"""

from __future__ import annotations

import shutil
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

from lgpt_parser import LGPTProject, collapse_song_for_disk

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

# Orden de PARAM al crear un INSTRUMENT nuevo (el de las canciones LGPT).
# Las claves que no están aquí se añaden al final, ordenadas.
_SAMPLE_PARAM_ORDER = (
    "sample", "volume", "interpol", "crush", "crushdrive", "downsample",
    "root note", "fine tune", "pan", "filter cut", "filter res",
    "filter type", "filter mode", "attenuate", "start", "loopmode",
    "slices", "loopstart", "end", "table", "table automation",
    "feedback tune", "feedback mix", "print fx", "pad with silence",
    "effect amount",
)
_MIDI_PARAM_ORDER = (
    "channel", "note length", "volume", "table", "table automation",
)


def _param_order(itype: str, params: dict) -> list[str]:
    preferred = _MIDI_PARAM_ORDER if itype == "Midi" else _SAMPLE_PARAM_ORDER
    seen = set()
    out = []
    for name in preferred:
        if name in params:
            out.append(name)
            seen.add(name)
    for name in sorted(params):
        if name not in seen:
            out.append(name)
    return out


def _write_instrument_node(parent: ET.Element, iid: int, data: dict) -> None:
    itype = data.get("type", "Sample")
    node = ET.SubElement(parent, "INSTRUMENT",
                         {"ID": f"{iid:02X}", "TYPE": itype})
    params = data.get("params") or {}
    for name in _param_order(itype, params):
        ET.SubElement(node, "PARAM",
                      {"NAME": name, "VALUE": str(params[name])})


def _instrument_id(node: ET.Element) -> int | None:
    try:
        return int(node.get("ID"), 16)
    except (TypeError, ValueError):
        return None


def _encode_buffer(project: LGPTProject, tag: str) -> bytes:
    if tag == "SONG":
        return collapse_song_for_disk(project.song)
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

    # GROOVES (nodo top-level): reencodifica desde project.grooves si hay datos
    # en memoria. Sin ediciones, el hex resultante es idéntico al original.
    groove_node = root.find("GROOVES")
    if groove_node is not None and project.grooves:
        del groove_node[:]
        node = ET.SubElement(groove_node, "DATA")
        node.text = bytes(project.grooves).hex().upper()

    # TABLES (nodo top-level): reencodifica cada TABLE desde project.tables.
    tables_node = root.find("TABLES")
    if tables_node is not None and project.tables:
        del tables_node[:]
        for tid in sorted(project.tables):
            t = project.tables[tid]
            te = ET.SubElement(tables_node, "TABLE", {"ID": f"{tid:02X}"})
            for ck, pk in (("cmd1", "param1"), ("cmd2", "param2"),
                           ("cmd3", "param3")):
                cn = ET.SubElement(te, ck.upper())
                ET.SubElement(cn, "DATA").text = b"".join(
                    c.encode("ascii") for c in t[ck]).hex().upper()
                pn = ET.SubElement(te, pk.upper())
                ET.SubElement(pn, "DATA").text = b"".join(
                    struct.pack("<H", p) for p in t[pk]).hex().upper()

    # INSTRUMENTBANK: sincroniza con project.instrument_bank.
    # 1) actualiza VALUE de cada PARAM existente
    # 2) quita los INSTRUMENT cuyo ID ya no está en el banco (si no, el
    #    parser los resucita al guardar+recargar, p.ej. Compact Instruments)
    # 3) añade los IDs del banco que no tenían nodo (pista 0 de canciones
    #    legacy, u otros creados en memoria)
    bank_node = root.find("INSTRUMENTBANK")
    if bank_node is None and project.instrument_bank:
        bank_node = ET.SubElement(root, "INSTRUMENTBANK")
    if bank_node is not None:
        for instr in bank_node.findall("INSTRUMENT"):
            iid = _instrument_id(instr)
            if iid is None:
                continue
            data = project.instrument_bank.get(iid)
            if not data:
                continue
            for param in instr.findall("PARAM"):
                name = param.get("NAME")
                if name in data["params"]:
                    param.set("VALUE", str(data["params"][name]))

        for instr in list(bank_node.findall("INSTRUMENT")):
            iid = _instrument_id(instr)
            if iid is not None and iid not in project.instrument_bank:
                bank_node.remove(instr)

        existing = {_instrument_id(instr)
                    for instr in bank_node.findall("INSTRUMENT")}
        existing.discard(None)
        for iid in sorted(project.instrument_bank):
            if iid not in existing:
                _write_instrument_node(bank_node, iid,
                                       project.instrument_bank[iid])

        nodes = list(bank_node.findall("INSTRUMENT"))
        nodes.sort(key=lambda n: _instrument_id(n) if _instrument_id(n)
                   is not None else 0xFFFF)
        for n in nodes:
            bank_node.remove(n)
            bank_node.append(n)

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
