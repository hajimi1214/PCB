"""Bounded structural checks for native JLCEDA manufacturing exports."""
from __future__ import annotations

import csv
import math
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree


class ManufacturingError(ValueError):
    pass


def _checked_zip(path: Path, *, max_entries: int = 2000, max_uncompressed: int = 200 * 1024 * 1024):
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ManufacturingError(f"{path.name} is not a readable ZIP archive.") from exc
    try:
        entries = archive.infolist()
        if len(entries) > max_entries or sum(item.file_size for item in entries) > max_uncompressed:
            raise ManufacturingError(f"{path.name} exceeds bounded archive inspection limits.")
        names = []
        for item in entries:
            normalized = item.filename.replace("\\", "/")
            if item.flag_bits & 1 or normalized.startswith("/") or ".." in normalized.split("/"):
                raise ManufacturingError(f"{path.name} contains an encrypted or unsafe archive member.")
            if not item.is_dir():
                names.append(normalized)
        if archive.testzip() is not None:
            raise ManufacturingError(f"{path.name} failed ZIP CRC validation.")
        return archive, names
    except BaseException:
        archive.close()
        raise


def validate_gerber_zip(path: Path, expected_copper_layers: int = 4) -> dict:
    archive, names = _checked_zip(path)
    try:
        copper = set()
        has_outline = False
        has_drill = False
        for name in names:
            lower = name.lower()
            extension = Path(lower).suffix
            member = archive.read(name)
            if not member:
                raise ManufacturingError(f"Gerber member {Path(name).name} is empty.")
            header = member[:65536].decode("latin-1", errors="ignore").lower()
            if extension in {".gtl", ".gbl"} or re.fullmatch(r"\.g\d+", extension):
                copper.add(name)
            if "%tffilefunction,copper," in header:
                copper.add(name)
            if extension in {".gko", ".gm1", ".gm2", ".gm3", ".gml"} or "outline" in lower or "edge.cuts" in lower or "%tffilefunction,profile" in header:
                has_outline = True
            if extension in {".drl", ".xln", ".nc"} or "drill" in lower or header.lstrip().startswith("m48"):
                has_drill = True
        if len(copper) < expected_copper_layers:
            raise ManufacturingError(f"Gerber ZIP has {len(copper)} copper-layer files, expected at least {expected_copper_layers}.")
        if not has_outline:
            raise ManufacturingError("Gerber ZIP has no recognizable board-outline layer.")
        if not has_drill:
            raise ManufacturingError("Gerber ZIP has no recognizable drill file.")
        return {"zip_crc_verified":True,"member_count":len(names),"copper_layer_count":len(copper),
                "outline_present":True,"drill_present":True}
    finally:
        archive.close()


def validate_bom_xlsx(path: Path) -> dict:
    archive, names = _checked_zip(path)
    try:
        if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
            raise ManufacturingError("BOM is missing required XLSX workbook parts.")
        sheets = [name for name in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)]
        if not sheets:
            raise ManufacturingError("BOM contains no worksheet.")
        shared_strings = []
        if "xl/sharedStrings.xml" in names:
            try:
                root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            except ElementTree.ParseError as exc:
                raise ManufacturingError("BOM shared strings XML is malformed.") from exc
            shared_strings = ["".join(node.itertext()) for node in root if node.tag.rsplit("}", 1)[-1] == "si"]
        rows = []
        for name in sheets[:1]:
            try:
                root = ElementTree.fromstring(archive.read(name))
            except ElementTree.ParseError as exc:
                raise ManufacturingError("BOM worksheet XML is malformed.") from exc
            for row in (node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "row"):
                cells = {}
                for cell in (node for node in row if node.tag.rsplit("}", 1)[-1] == "c"):
                    match = re.fullmatch(r"([A-Z]+)\d+", cell.get("r", "").upper())
                    if not match:
                        raise ManufacturingError("BOM worksheet has an invalid cell reference.")
                    column = 0
                    for character in match.group(1):
                        column = column * 26 + ord(character) - ord("A") + 1
                    if column > 256:
                        raise ManufacturingError("BOM worksheet exceeds the 256-column inspection limit.")
                    value = next((child.text or "" for child in cell if child.tag.rsplit("}", 1)[-1] == "v"), "")
                    cell_type = cell.get("t")
                    if cell_type == "s":
                        try:
                            value = shared_strings[int(value)]
                        except (ValueError, IndexError) as exc:
                            raise ManufacturingError("BOM references an invalid shared string.") from exc
                    elif cell_type == "inlineStr":
                        value = "".join(text for node in cell if node.tag.rsplit("}", 1)[-1] == "is"
                                         for text in node.itertext())
                    cells[column - 1] = value
                if cells:
                    rows.append([cells.get(index, "") for index in range(max(cells) + 1)])
        normalize = lambda value: re.sub(r"\s+", "", value).casefold()
        header_index = next((index for index, row in enumerate(rows)
            if any(normalize(cell) in {"designator", "reference", "refdes", "位号", "元件位号"} for cell in row)
            and any(normalize(cell) in {"quantity", "qty", "数量"} for cell in row)), None)
        if header_index is None:
            raise ManufacturingError("BOM is missing recognizable designator and quantity columns.")
        header = [normalize(value) for value in rows[header_index]]
        reference_column = next(index for index, value in enumerate(header)
            if value in {"designator", "reference", "refdes", "位号", "元件位号"})
        quantity_column = next(index for index, value in enumerate(header)
            if value in {"quantity", "qty", "数量"})
        references = set()
        component_rows = 0
        for row in rows[header_index + 1:]:
            row += [""] * max(0, len(header) - len(row))
            if not any(value.strip() for value in row):
                continue
            if reference_column >= len(row) or quantity_column >= len(row):
                raise ManufacturingError("BOM row is missing a designator or quantity value.")
            designators = [item for item in re.split(r"[,，;；\s、]+", row[reference_column].strip()) if item]
            try:
                quantity = float(row[quantity_column])
            except ValueError as exc:
                raise ManufacturingError("BOM quantity is not numeric.") from exc
            if not designators or not math.isfinite(quantity) or quantity <= 0 or not quantity.is_integer():
                raise ManufacturingError("BOM rows require designators and a positive integer quantity.")
            if int(quantity) != len(designators):
                raise ManufacturingError("BOM quantity does not match its listed designator count.")
            if references.intersection(designators):
                raise ManufacturingError("BOM contains a duplicate component designator.")
            references.update(designators)
            component_rows += 1
        if component_rows == 0:
            raise ManufacturingError("BOM has no populated component rows.")
        return {"zip_crc_verified":True,"worksheet_count":len(sheets),"component_row_count":component_rows,
                "component_reference_count":len(references)}
    finally:
        archive.close()


def validate_pick_and_place_tsv(path: Path) -> dict:
    try:
        data = path.read_bytes()
        if not data.startswith(b"\xff\xfe"):
            raise ManufacturingError("Pick-and-place file is not the documented UTF-16LE format.")
        text = data[2:].decode("utf-16le")
    except (OSError, UnicodeDecodeError) as exc:
        raise ManufacturingError("Pick-and-place file could not be decoded as UTF-16LE.") from exc
    rows = [row for row in csv.reader(text.splitlines(), delimiter="\t") if any(cell.strip() for cell in row)]
    if len(rows) < 2:
        raise ManufacturingError("Pick-and-place file has no placed-component rows.")
    normalize = lambda value: re.sub(r"\s+", "", value.strip()).casefold()
    header = [normalize(value) for value in rows[0]]
    columns = {}
    aliases = {
        "reference":{"designator","reference","refdes","ref","位号","元件位号"},
        "x":{"x","midx","centerx","x(mm)","中心x","x坐标"},
        "y":{"y","midy","centery","y(mm)","中心y","y坐标"},
        "rotation":{"rotation","angle","角度","旋转角度"},
        "side":{"layer","side","器件面","面","顶/底面"},
    }
    for key, accepted in aliases.items():
        index = next((i for i, value in enumerate(header) if value in accepted), None)
        if index is None:
            raise ManufacturingError(f"Pick-and-place header is missing the {key} column.")
        columns[key] = index
    references = set()
    for row in rows[1:]:
        row += [""] * max(0, len(header) - len(row))
        reference = row[columns["reference"]].strip()
        if not reference:
            raise ManufacturingError("Pick-and-place row is missing its component designator.")
        if reference in references:
            raise ManufacturingError("Pick-and-place contains a duplicate component designator.")
        references.add(reference)
        for axis in ("x", "y", "rotation"):
            try:
                coordinate = float(row[columns[axis]].strip().replace("°", ""))
            except ValueError as exc:
                raise ManufacturingError(f"Pick-and-place {axis} value is not numeric.") from exc
            if not math.isfinite(coordinate):
                raise ManufacturingError(f"Pick-and-place {axis} value is not finite.")
        side = normalize(row[columns["side"]])
        if side not in {"top", "toplayer", "topside", "front", "正面", "顶面", "顶层",
                        "bottom", "bottomlayer", "bottomside", "back", "反面", "底面", "底层"}:
            raise ManufacturingError("Pick-and-place side must identify the top or bottom of the PCB.")
    return {"encoding":"UTF-16LE","delimiter":"TAB","component_count":len(references)}


def validate_manufacturing_exports(directory: Path, expected_copper_layers: int = 4) -> dict:
    files = {
        "gerber": directory / "Gerber.zip",
        "bom": directory / "BOM.xlsx",
        "pick_and_place": directory / "PickAndPlace.tsv",
    }
    for path in files.values():
        if path.is_symlink() or not path.is_file() or path.stat().st_size <= 0:
            raise ManufacturingError(f"Expected manufacturing file {path.name} is missing or invalid.")
    return {
        "gerber":validate_gerber_zip(files["gerber"],expected_copper_layers),
        "bom":validate_bom_xlsx(files["bom"]),
        "pick_and_place":validate_pick_and_place_tsv(files["pick_and_place"]),
    }
