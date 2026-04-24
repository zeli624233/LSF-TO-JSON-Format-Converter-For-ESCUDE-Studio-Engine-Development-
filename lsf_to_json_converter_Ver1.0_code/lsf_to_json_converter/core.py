from __future__ import annotations

import json
import re
import struct
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

TEXT_ENCODINGS = ("utf-8", "utf-8-sig", "cp932", "shift_jis", "gbk")


class LSFConvertError(Exception):
    """Raised when an LSF file cannot be parsed or converted."""


def natural_sort_key(text: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(text))]


@dataclass(slots=True)
class LSFRecord:
    index: int
    name: str
    left: int
    top: int
    right: int
    bottom: int
    unk1: int
    unk2: int
    tag: int
    unk3: int
    unk4: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def slot_code(self) -> int:
        return self.tag & 0xFF

    @property
    def variant_code(self) -> int:
        return (self.tag >> 8) & 0xFF

    @property
    def mid_code(self) -> int:
        return (self.tag >> 16) & 0xFF

    @property
    def high_code(self) -> int:
        return (self.tag >> 24) & 0xFF

    @property
    def tag_hex(self) -> str:
        return f"0x{self.tag:08X}"


@dataclass(slots=True)
class LSFProject:
    path: Path
    version1: int
    version2: int
    reserved0: int
    count_in_header: int
    canvas_width: int
    canvas_height: int
    preview_width: int
    preview_height: int
    header_words: list[int]
    records: list[LSFRecord]

    @property
    def stem(self) -> str:
        return self.path.stem


def _decode_name(raw: bytes) -> str:
    raw = raw.split(b"\0", 1)[0]
    for enc in TEXT_ENCODINGS:
        try:
            return raw.decode(enc)
        except Exception:
            pass
    return raw.decode("utf-8", errors="replace")


def _join_u16(low: int, high: int) -> int:
    return int(low) | (int(high) << 16)


def parse_lsf_file(path: str | Path) -> LSFProject:
    """Parse the known LSF binary structure used by the game resources.

    Layout observed from the supplied samples:
      header: 4-byte magic b"LSF\\0" + 12 little-endian uint16 values
      record: 128-byte null-terminated PNG stem + 9 little-endian uint32 values

    The seventh uint32 in each record is treated as a packed tag:
      low byte      = slot/group code
      second byte   = variant/option code
      third byte    = mid/helper code; mid==3 often means engine mask/helper layer
      high byte     = extra code
    """
    path = Path(path)
    data = path.read_bytes()
    if len(data) < 28:
        raise LSFConvertError("文件太小，不是有效 LSF。")

    try:
        sig, *words = struct.unpack("<4s12H", data[:28])
    except struct.error as exc:
        raise LSFConvertError(f"LSF 头解析失败: {exc}") from exc

    if sig != b"LSF\0":
        raise LSFConvertError("文件头不是 LSF\\0。")

    version1, version2, reserved0, count = words[:4]
    canvas_width = _join_u16(words[4], words[5])
    canvas_height = _join_u16(words[6], words[7])
    preview_width = _join_u16(words[8], words[9])
    preview_height = _join_u16(words[10], words[11])

    records: list[LSFRecord] = []
    offset = 28
    rec_size = 128 + 9 * 4
    for idx in range(count):
        chunk = data[offset:offset + rec_size]
        if len(chunk) < rec_size:
            break
        name = _decode_name(chunk[:128])
        vals = struct.unpack("<9I", chunk[128:])
        records.append(
            LSFRecord(
                index=idx,
                name=name,
                left=int(vals[0]),
                top=int(vals[1]),
                right=int(vals[2]),
                bottom=int(vals[3]),
                unk1=int(vals[4]),
                unk2=int(vals[5]),
                tag=int(vals[6]),
                unk3=int(vals[7]),
                unk4=int(vals[8]),
            )
        )
        offset += rec_size

    if not records:
        raise LSFConvertError("LSF 中没有解析出记录。")

    max_right = max((r.right for r in records), default=0)
    max_bottom = max((r.bottom for r in records), default=0)
    canvas_width = max(canvas_width, preview_width, max_right)
    canvas_height = max(canvas_height, preview_height, max_bottom)

    return LSFProject(
        path=path,
        version1=version1,
        version2=version2,
        reserved0=reserved0,
        count_in_header=count,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        preview_width=preview_width,
        preview_height=preview_height,
        header_words=list(map(int, words)),
        records=records,
    )


def collect_lsf_files(input_path: str | Path, recursive: bool = False) -> list[Path]:
    p = Path(input_path)
    if p.is_file():
        if p.suffix.lower() != ".lsf":
            return []
        return [p]
    if not p.exists():
        return []
    pattern = "**/*.lsf" if recursive else "*.lsf"
    files = sorted(p.glob(pattern), key=lambda x: natural_sort_key(str(x.relative_to(p))))
    return [x for x in files if x.is_file()]


def _slot_groups(project: LSFProject) -> dict[int, dict[int, list[LSFRecord]]]:
    out: dict[int, dict[int, list[LSFRecord]]] = defaultdict(lambda: defaultdict(list))
    for rec in sorted(project.records, key=lambda r: r.index):
        out[rec.slot_code][rec.variant_code].append(rec)
    return out


def _slot_meta(project: LSFProject, slots: dict[int, dict[int, list[LSFRecord]]]) -> dict[int, dict[str, Any]]:
    canvas_area = max(1, project.canvas_width * project.canvas_height)
    meta: dict[int, dict[str, Any]] = {}
    for slot, variants in slots.items():
        all_records = [r for records in variants.values() for r in records]
        if all_records:
            max_area = max(r.area for r in all_records)
            avg_area = sum(r.area for r in all_records) / len(all_records)
            avg_center_x = sum((r.left + r.right) / 2 for r in all_records) / len(all_records)
            avg_center_y = sum((r.top + r.bottom) / 2 for r in all_records) / len(all_records)
        else:
            max_area = avg_area = avg_center_x = avg_center_y = 0
        meta[slot] = {
            "slot_hex": f"{slot:02X}",
            "variant_count": len(variants),
            "record_count": len(all_records),
            "max_area_ratio": round(max_area / canvas_area, 6),
            "avg_area_ratio": round(avg_area / canvas_area, 6),
            "avg_center_x": round(avg_center_x, 3),
            "avg_center_y": round(avg_center_y, 3),
        }
    return meta


def classify_slot(project: LSFProject, slot: int, meta: dict[int, dict[str, Any]]) -> str:
    """Best-effort role classification based on patterns observed in the supplied LSFs.

    The JSON always keeps raw slot/variant/tag values, so this role is only a helpful
    label for GUI/composition tools and can be adjusted later if another title differs.
    """
    m = meta.get(slot, {})
    variant_count = int(m.get("variant_count", 0))
    max_ratio = float(m.get("max_area_ratio", 0))
    stem = project.stem.lower()
    is_ev_adv = stem.startswith("ev_") or project.canvas_width >= project.canvas_height * 0.70

    if slot == 0xFF:
        return "holy"

    # ADV/EV event CGs often use 0x0A,0x14,0x1E... for expression slots,
    # and the following slot for blush/cheek overlays.
    if is_ev_adv and 0x0A <= slot < 0xF0:
        rem = slot % 0x0A
        if rem == 0:
            return "expression"
        if rem == 1:
            return "blush"
        return "special"

    # The face/st/stage resources we inspected use this compact layout.
    if slot == 0:
        if variant_count <= 1 and max_ratio >= 0.70:
            return "fixed"
        return "body_time"
    if slot == 1:
        return "expression"
    if slot == 2:
        return "blush"
    if slot == 3:
        return "body_time"
    if slot == 4:
        return "accessory"
    if slot in (5, 6):
        return "special"

    # Fallback by size/variant count.
    if variant_count >= 2 and max_ratio >= 0.12:
        return "body_time"
    if variant_count >= 4 and max_ratio < 0.12:
        return "expression"
    if 1 <= variant_count <= 4 and max_ratio < 0.08:
        return "special"
    return "body_time"


ROLE_LABELS = {
    "fixed": "固定图层",
    "body_time": "衣服或者其他时间端",
    "expression": "表情",
    "blush": "红晕",
    "accessory": "饰品",
    "special": "特殊",
    "holy": "圣光",
}


def _record_to_json(rec: LSFRecord) -> dict[str, Any]:
    return {
        "index": rec.index,
        "name": rec.name,
        "png": f"{rec.name}.png",
        "left": rec.left,
        "top": rec.top,
        "right": rec.right,
        "bottom": rec.bottom,
        "width": rec.width,
        "height": rec.height,
        "area": rec.area,
        "tag_raw": rec.tag,
        "tag_hex": rec.tag_hex,
        "slot_code": rec.slot_code,
        "slot_hex": f"{rec.slot_code:02X}",
        "variant_code": rec.variant_code,
        "variant_hex": f"{rec.variant_code:02X}",
        "mid_code": rec.mid_code,
        "high_code": rec.high_code,
        "is_helper_mask": rec.mid_code == 3,
        "unknown": [rec.unk1, rec.unk2, rec.unk3, rec.unk4],
    }


def _option_label(variant: int, records: Iterable[LSFRecord]) -> str:
    records = list(records)
    names: list[str] = []
    seen: set[str] = set()
    for rec in sorted(records, key=lambda r: (r.index, natural_sort_key(r.name))):
        if rec.name not in seen:
            seen.add(rec.name)
            names.append(rec.name)
    shown = " + ".join(names[:3])
    if len(names) > 3:
        shown += f" + ...({len(names)})"
    if shown:
        return shown
    return f"variant_{variant:02X}"


def build_lsf_json(project: LSFProject, *, include_compatible_layers: bool = True) -> dict[str, Any]:
    slots = _slot_groups(project)
    meta = _slot_meta(project, slots)
    slot_roles = {slot: classify_slot(project, slot, meta) for slot in slots}

    records = [_record_to_json(r) for r in project.records]
    slots_json: dict[str, Any] = {}
    selection_groups: dict[str, Any] = defaultdict(list)

    for slot in sorted(slots):
        role = slot_roles[slot]
        role_label = ROLE_LABELS.get(role, role)
        variants_json: dict[str, Any] = {}
        for variant in sorted(slots[slot]):
            recs = sorted(slots[slot][variant], key=lambda r: r.index)
            variants_json[f"{variant:02X}"] = {
                "variant_code": variant,
                "label": _option_label(variant, recs),
                "record_indices": [r.index for r in recs],
                "record_names": [r.name for r in recs],
                "contains_helper_mask": any(r.mid_code == 3 for r in recs),
            }
        slots_json[f"{slot:02X}"] = {
            "slot_code": slot,
            "role": role,
            "role_label": role_label,
            "meta": meta[slot],
            "variants": variants_json,
        }

    # Make user-facing selectable groups. Multiple slots with the same role are kept separate.
    counters: dict[str, int] = defaultdict(int)
    for slot in sorted(slots):
        role = slot_roles[slot]
        if role == "fixed":
            continue
        counters[role] += 1
        role_label = ROLE_LABELS.get(role, role)
        group_name = role_label if counters[role] == 1 else f"{role_label}{counters[role]}"
        options = []
        if role in {"expression", "blush", "accessory", "special", "holy"}:
            none_label = {
                "expression": "(无表情)",
                "blush": "(无红晕)",
                "accessory": "(无饰品)",
                "special": "(无特殊)",
                "holy": "(无圣光)",
            }.get(role, "(无)")
            options.append({"key": "__none__", "label": none_label, "record_indices": [], "record_names": []})
        for variant in sorted(slots[slot]):
            recs = sorted(slots[slot][variant], key=lambda r: r.index)
            options.append({
                "key": f"slot{slot:02X}_var{variant:02X}",
                "label": _option_label(variant, recs),
                "slot_code": slot,
                "variant_code": variant,
                "record_indices": [r.index for r in recs if r.mid_code != 3],
                "all_record_indices": [r.index for r in recs],
                "record_names": [r.name for r in recs if r.mid_code != 3],
                "all_record_names": [r.name for r in recs],
                "contains_helper_mask": any(r.mid_code == 3 for r in recs),
            })
        selection_groups[role].append({
            "name": group_name,
            "slot_code": slot,
            "slot_hex": f"{slot:02X}",
            "role": role,
            "options": options,
        })

    fixed_indices = [r.index for r in project.records if slot_roles.get(r.slot_code) == "fixed" and r.mid_code != 3]

    result: dict[str, Any] = {
        "schema": "lsf-json-v1",
        "generator": "lsf_to_json_converter_v1",
        "source_file": project.path.name,
        "source_path": str(project.path),
        "header": {
            "version1": project.version1,
            "version2": project.version2,
            "reserved0": project.reserved0,
            "record_count_in_header": project.count_in_header,
            "header_words": project.header_words,
        },
        "canvas_width": project.canvas_width,
        "canvas_height": project.canvas_height,
        "preview_width": project.preview_width,
        "preview_height": project.preview_height,
        "canvas": {
            "width": project.canvas_width,
            "height": project.canvas_height,
            "preview_width": project.preview_width,
            "preview_height": project.preview_height,
        },
        "records": records,
        "slots": slots_json,
        "selection_groups": dict(selection_groups),
        "fixed_record_indices": fixed_indices,
        "notes": [
            "tag 的低字节是 slot_code；第二字节是 variant_code；第三字节 mid_code==3 时常见为引擎辅助遮罩层。",
            "role/selection_groups 是根据已分析样本生成的启发式分类；records/slots 中保留了完整原始数据。",
        ],
    }

    if include_compatible_layers:
        result["layers"] = build_compatible_layers(project, slots, slot_roles)
        result["compatibility_note"] = (
            "layers 字段可被部分 JSON+PNG 合成工具读取；复杂的多 PNG 组合仍应优先使用 selection_groups。"
        )
    return result


def build_compatible_layers(
    project: LSFProject,
    slots: dict[int, dict[int, list[LSFRecord]]],
    slot_roles: dict[int, str],
) -> list[dict[str, Any]]:
    """Build a simple parent/child layer list for tools that expect layer JSON.

    This keeps one PNG record as one JSON layer. Complex LSF options that are made
    from several records are preserved in selection_groups, not flattened here.
    """
    layers: list[dict[str, Any]] = []
    next_group_id = 1_000_000
    draw_index = 0
    role_counter: dict[str, int] = defaultdict(int)

    for slot in sorted(slots):
        role = slot_roles.get(slot, "body_time")
        if role == "fixed":
            for variant in sorted(slots[slot]):
                for rec in sorted(slots[slot][variant], key=lambda r: r.index):
                    if rec.mid_code == 3:
                        continue
                    layers.append({
                        "layer_id": rec.index,
                        "name": rec.name,
                        "left": rec.left,
                        "top": rec.top,
                        "right": rec.right,
                        "bottom": rec.bottom,
                        "width": rec.width,
                        "height": rec.height,
                        "visible": True,
                        "draw_index": draw_index,
                    })
                    draw_index += 1
            continue

        role_counter[role] += 1
        label = ROLE_LABELS.get(role, role)
        group_name = label if role_counter[role] == 1 else f"{label}{role_counter[role]}"
        group_id = next_group_id
        next_group_id += 1
        layers.append({
            "layer_id": group_id,
            "name": group_name,
            "visible": False,
            "is_group": True,
            "draw_index": draw_index,
        })
        draw_index += 1
        for variant in sorted(slots[slot]):
            for rec in sorted(slots[slot][variant], key=lambda r: r.index):
                if rec.mid_code == 3:
                    continue
                layers.append({
                    "layer_id": rec.index,
                    "name": rec.name,
                    "group_layer_id": group_id,
                    "left": rec.left,
                    "top": rec.top,
                    "right": rec.right,
                    "bottom": rec.bottom,
                    "width": rec.width,
                    "height": rec.height,
                    "visible": False,
                    "draw_index": draw_index,
                    "slot_code": rec.slot_code,
                    "variant_code": rec.variant_code,
                })
                draw_index += 1
    return layers


def write_json_file(data: dict[str, Any], out_path: str | Path, pretty: bool = True) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2 if pretty else None)
    out_path.write_text(text, encoding="utf-8")


def convert_lsf_file(
    lsf_path: str | Path,
    output_dir: str | Path,
    *,
    input_root: str | Path | None = None,
    recursive: bool = False,
    preserve_tree: bool = True,
    overwrite: bool = True,
    suffix: str = ".json",
    pretty: bool = True,
    include_compatible_layers: bool = True,
) -> tuple[Path, dict[str, Any]]:
    lsf_path = Path(lsf_path)
    output_dir = Path(output_dir)
    project = parse_lsf_file(lsf_path)
    data = build_lsf_json(project, include_compatible_layers=include_compatible_layers)

    if input_root and preserve_tree:
        try:
            rel_parent = lsf_path.parent.relative_to(Path(input_root))
        except Exception:
            rel_parent = Path()
        out_dir = output_dir / rel_parent
    else:
        out_dir = output_dir

    clean_suffix = suffix if suffix.startswith(".") else f".{suffix}"
    out_path = out_dir / f"{lsf_path.stem}{clean_suffix}"
    if out_path.exists() and not overwrite:
        raise LSFConvertError(f"目标已存在，已跳过: {out_path}")
    write_json_file(data, out_path, pretty=pretty)
    return out_path, data


def convert_many(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    recursive: bool = False,
    preserve_tree: bool = True,
    overwrite: bool = True,
    suffix: str = ".json",
    pretty: bool = True,
    include_compatible_layers: bool = True,
) -> dict[str, Any]:
    files = collect_lsf_files(input_path, recursive=recursive)
    root = Path(input_path) if Path(input_path).is_dir() else Path(input_path).parent
    summary = {"total": len(files), "ok": 0, "failed": 0, "outputs": [], "errors": []}
    for path in files:
        try:
            out_path, data = convert_lsf_file(
                path,
                output_dir,
                input_root=root,
                recursive=recursive,
                preserve_tree=preserve_tree,
                overwrite=overwrite,
                suffix=suffix,
                pretty=pretty,
                include_compatible_layers=include_compatible_layers,
            )
            summary["ok"] += 1
            summary["outputs"].append({
                "input": str(path),
                "output": str(out_path),
                "records": len(data.get("records", [])),
                "canvas": [data.get("canvas_width"), data.get("canvas_height")],
            })
        except Exception as exc:
            summary["failed"] += 1
            summary["errors"].append({"input": str(path), "error": str(exc)})
    return summary
