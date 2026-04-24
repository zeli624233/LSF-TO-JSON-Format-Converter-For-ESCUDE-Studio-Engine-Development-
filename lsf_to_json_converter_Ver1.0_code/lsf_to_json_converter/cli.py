from __future__ import annotations

import argparse
import csv
import fnmatch
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from lsf_to_json_converter import APP_TITLE, APP_SHORT_TITLE, __version__
from lsf_to_json_converter.core import (
    build_lsf_json,
    classify_slot,
    collect_lsf_files,
    convert_lsf_file,
    convert_many,
    natural_sort_key,
    parse_lsf_file,
    _slot_groups,
    _slot_meta,
)

def _json_dumps(data: Any, *, compact: bool = False) -> str:
    return json.dumps(data, ensure_ascii=False, indent=None if compact else 2)


def _print_json(data: Any, *, compact: bool = False) -> None:
    print(_json_dumps(data, compact=compact))


def _norm_suffix(suffix: str) -> str:
    suffix = suffix.strip() or ".json"
    return suffix if suffix.startswith(".") else f".{suffix}"


def _matches_any(path: Path, patterns: list[str], root: Path | None = None) -> bool:
    if not patterns:
        return True
    candidates = [path.name, path.stem, str(path)]
    if root is not None:
        try:
            candidates.append(str(path.relative_to(root)).replace("\\", "/"))
        except Exception:
            pass
    return any(fnmatch.fnmatchcase(c, pat) for pat in patterns for c in candidates)



def _relative_text(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except Exception:
        return path.name

def _filter_files(files: list[Path], *, root: Path | None, include: list[str] | None, exclude: list[str] | None) -> list[Path]:
    include = include or []
    exclude = exclude or []
    out: list[Path] = []
    for f in files:
        if include and not _matches_any(f, include, root):
            continue
        if exclude and _matches_any(f, exclude, root):
            continue
        out.append(f)
    return sorted(out, key=lambda p: natural_sort_key(str(p)))


def _collect_from_inputs(inputs: list[str], recursive: bool, include: list[str] | None, exclude: list[str] | None) -> list[tuple[Path, Path]]:
    """Return (file, root) pairs. root is used for preserving directory structure."""
    pairs: list[tuple[Path, Path]] = []
    seen: set[Path] = set()
    for inp in inputs:
        p = Path(inp)
        root = p if p.is_dir() else p.parent
        files = collect_lsf_files(p, recursive=recursive)
        files = _filter_files(files, root=root, include=include, exclude=exclude)
        for f in files:
            key = f.resolve() if f.exists() else f
            if key in seen:
                continue
            seen.add(key)
            pairs.append((f, root))
    return sorted(pairs, key=lambda x: natural_sort_key(str(x[0])))


def _slot_summary_for_file(path: str | Path) -> dict[str, Any]:
    project = parse_lsf_file(path)
    slots = _slot_groups(project)
    meta = _slot_meta(project, slots)
    roles = {slot: classify_slot(project, slot, meta) for slot in slots}
    slot_rows = []
    for slot in sorted(slots):
        variants = slots[slot]
        slot_rows.append({
            "slot_code": slot,
            "slot_hex": f"{slot:02X}",
            "role": roles[slot],
            "variant_count": len(variants),
            "record_count": sum(len(v) for v in variants.values()),
            "max_area_ratio": meta[slot]["max_area_ratio"],
            "variants": [
                {
                    "variant_code": variant,
                    "variant_hex": f"{variant:02X}",
                    "record_count": len(recs),
                    "record_names": [r.name for r in recs],
                    "contains_helper_mask": any(r.mid_code == 3 for r in recs),
                }
                for variant, recs in sorted(variants.items())
            ],
        })
    return {
        "source_file": project.path.name,
        "source_path": str(project.path),
        "canvas": [project.canvas_width, project.canvas_height],
        "record_count": len(project.records),
        "slot_count": len(slots),
        "slots": slot_rows,
    }


def _record_rows(path: str | Path) -> list[dict[str, Any]]:
    project = parse_lsf_file(path)
    rows: list[dict[str, Any]] = []
    for r in project.records:
        rows.append({
            "index": r.index,
            "name": r.name,
            "png": f"{r.name}.png",
            "left": r.left,
            "top": r.top,
            "right": r.right,
            "bottom": r.bottom,
            "width": r.width,
            "height": r.height,
            "area": r.area,
            "tag_raw": r.tag,
            "tag_hex": r.tag_hex,
            "slot_code": r.slot_code,
            "slot_hex": f"{r.slot_code:02X}",
            "variant_code": r.variant_code,
            "variant_hex": f"{r.variant_code:02X}",
            "mid_code": r.mid_code,
            "high_code": r.high_code,
            "is_helper_mask": r.mid_code == 3,
            "unk1": r.unk1,
            "unk2": r.unk2,
            "unk3": r.unk3,
            "unk4": r.unk4,
        })
    return rows


def _write_table(rows: list[dict[str, Any]], *, fmt: str, output: str | None) -> None:
    if fmt == "json":
        text = _json_dumps(rows)
        if output:
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            Path(output).write_text(text, encoding="utf-8")
        else:
            print(text)
        return

    if not rows:
        if output:
            Path(output).write_text("", encoding="utf-8")
        return

    delimiter = "\t" if fmt == "tsv" else ","
    fieldnames = list(rows[0].keys())
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        f = Path(output).open("w", newline="", encoding="utf-8-sig")
        close = True
    else:
        f = sys.stdout
        close = False
    try:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    finally:
        if close:
            f.close()


def add_common_input_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-r", "--recursive", action="store_true", help="递归处理子目录")
    parser.add_argument("--include", action="append", default=[], metavar="GLOB", help="只处理匹配的文件；可重复，例如 --include 'EV_*.lsf'")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB", help="排除匹配的文件；可重复，例如 --exclude '*test*'")


def add_convert_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-i", "--input", action="append", required=True, help="LSF 文件或目录；可重复传入多个")
    parser.add_argument("-o", "--output", required=True, help="输出目录")
    add_common_input_filters(parser)
    tree = parser.add_mutually_exclusive_group()
    tree.add_argument("--preserve-tree", dest="preserve_tree", action="store_true", default=True, help="保留输入目录结构，默认开启")
    tree.add_argument("--flat", "--no-preserve-tree", dest="preserve_tree", action="store_false", help="不保留目录结构，全部输出到同一目录")
    ow = parser.add_mutually_exclusive_group()
    ow.add_argument("--overwrite", dest="overwrite", action="store_true", default=True, help="覆盖已有 JSON，默认开启")
    ow.add_argument("--skip-existing", "--no-overwrite", dest="overwrite", action="store_false", help="目标已存在时跳过")
    parser.add_argument("--suffix", default=".json", help="输出后缀，默认 .json；例如 .lsf.json")
    parser.add_argument("--compact", action="store_true", help="输出紧凑 JSON，不缩进")
    parser.add_argument("--no-layers", "--no-compatible-layers", dest="compatible_layers", action="store_false", default=True, help="不输出 layers 兼容字段")
    parser.add_argument("--dry-run", action="store_true", help="只扫描和显示将要输出的路径，不实际写入")
    parser.add_argument("--summary", help="把转换统计写入指定 JSON 文件")
    parser.add_argument("--index", help="额外生成一个索引 JSON，汇总所有成功转换的文件")
    parser.add_argument("--json", action="store_true", help="以 JSON 形式输出结果")
    parser.add_argument("--quiet", "-q", action="store_true", help="减少普通文本输出")
    parser.add_argument("--fail-fast", action="store_true", help="遇到第一个错误就停止")


def _run_gui() -> None:
    # tkinter 只在真正需要 GUI 时再导入，避免纯 CLI 模式受图形环境影响。
    from lsf_to_json_converter.gui import run_gui
    run_gui()


def cmd_gui(_: argparse.Namespace) -> int:
    _run_gui()
    return 0


def cmd_version(_: argparse.Namespace) -> int:
    print(f"{APP_TITLE}  version={__version__}")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    pairs = _collect_from_inputs(args.input, args.recursive, args.include, args.exclude)
    data = {
        "total": len(pairs),
        "files": [
            {
                "path": str(path),
                "name": path.name,
                "relative": _relative_text(path, root),
                "root": str(root),
            }
            for path, root in pairs[: args.limit if args.limit and args.limit > 0 else None]
        ],
        "truncated": bool(args.limit and args.limit > 0 and len(pairs) > args.limit),
    }
    if args.json:
        _print_json(data, compact=args.compact)
    else:
        print(f"扫描到 {len(pairs)} 个 LSF 文件")
        for item in data["files"]:
            print(item["path"])
        if data["truncated"]:
            print(f"... 已限制显示 {args.limit} 个")
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    pairs = _collect_from_inputs(args.input, args.recursive, args.include, args.exclude)
    output_dir = Path(args.output)
    suffix = _norm_suffix(args.suffix)
    summary: dict[str, Any] = {
        "version": __version__,
        "total": len(pairs),
        "ok": 0,
        "failed": 0,
        "dry_run": bool(args.dry_run),
        "outputs": [],
        "errors": [],
    }

    if not args.quiet and not args.json:
        print(f"准备转换 {len(pairs)} 个 LSF 文件 -> {output_dir}")

    index_items: list[dict[str, Any]] = []
    for n, (path, root) in enumerate(pairs, start=1):
        try:
            if args.preserve_tree:
                try:
                    rel_parent = path.parent.relative_to(root)
                except Exception:
                    rel_parent = Path()
                out_path = output_dir / rel_parent / f"{path.stem}{suffix}"
            else:
                out_path = output_dir / f"{path.stem}{suffix}"

            if args.dry_run:
                project = parse_lsf_file(path)
                item = {
                    "input": str(path),
                    "output": str(out_path),
                    "records": len(project.records),
                    "canvas": [project.canvas_width, project.canvas_height],
                }
                summary["ok"] += 1
                summary["outputs"].append(item)
                if not args.quiet and not args.json:
                    print(f"[{n}/{len(pairs)}] DRY {path} -> {out_path}")
                continue

            out_path, data = convert_lsf_file(
                path,
                output_dir,
                input_root=root,
                preserve_tree=args.preserve_tree,
                overwrite=args.overwrite,
                suffix=suffix,
                pretty=not args.compact,
                include_compatible_layers=args.compatible_layers,
            )
            item = {
                "input": str(path),
                "output": str(out_path),
                "records": len(data.get("records", [])),
                "canvas": [data.get("canvas_width"), data.get("canvas_height")],
            }
            summary["ok"] += 1
            summary["outputs"].append(item)
            if args.index:
                index_items.append({
                    "source_file": data.get("source_file"),
                    "source_path": data.get("source_path"),
                    "json_path": str(out_path),
                    "canvas": data.get("canvas"),
                    "record_count": len(data.get("records", [])),
                    "selection_group_names": [g.get("name") for role_groups in data.get("selection_groups", {}).values() for g in role_groups],
                })
            if not args.quiet and not args.json:
                print(f"[{n}/{len(pairs)}] OK {path.name} -> {out_path}")
        except Exception as exc:
            summary["failed"] += 1
            err = {"input": str(path), "error": str(exc)}
            summary["errors"].append(err)
            if not args.quiet and not args.json:
                print(f"[{n}/{len(pairs)}] 失败 {path}: {exc}", file=sys.stderr)
            if args.fail_fast:
                break

    if args.summary:
        Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
        Path(args.summary).write_text(_json_dumps(summary), encoding="utf-8")
    if args.index:
        index_data = {
            "schema": "lsf-json-index-v1",
            "generator": f"lsf_to_json_converter_v{__version__}",
            "total": len(index_items),
            "items": index_items,
        }
        Path(args.index).parent.mkdir(parents=True, exist_ok=True)
        Path(args.index).write_text(_json_dumps(index_data), encoding="utf-8")
    if args.json:
        _print_json(summary, compact=args.compact)
    elif not args.quiet:
        print(f"完成：成功 {summary['ok']}，失败 {summary['failed']}。")
    return 0 if summary["failed"] == 0 else 2


def cmd_inspect(args: argparse.Namespace) -> int:
    project = parse_lsf_file(args.file)
    slots_data = _slot_summary_for_file(args.file)
    data = {
        "source_file": project.path.name,
        "source_path": str(project.path),
        "version1": project.version1,
        "version2": project.version2,
        "canvas_width": project.canvas_width,
        "canvas_height": project.canvas_height,
        "preview_width": project.preview_width,
        "preview_height": project.preview_height,
        "record_count_in_header": project.count_in_header,
        "record_count_parsed": len(project.records),
        "slot_count": slots_data["slot_count"],
        "slots": slots_data["slots"],
    }
    if args.records:
        data["records"] = _record_rows(args.file)
    if args.json:
        _print_json(data, compact=args.compact)
    else:
        print(f"文件: {data['source_file']}")
        print(f"画布: {data['canvas_width']} x {data['canvas_height']}    记录: {data['record_count_parsed']}    槽位: {data['slot_count']}")
        print("槽位摘要:")
        for s in data["slots"]:
            print(f"  slot{s['slot_hex']}  role={s['role']}  variants={s['variant_count']}  records={s['record_count']}  max_area={s['max_area_ratio']}")
    return 0


def cmd_slots(args: argparse.Namespace) -> int:
    data = _slot_summary_for_file(args.file)
    if args.json:
        _print_json(data, compact=args.compact)
    else:
        print(f"{data['source_file']}  canvas={data['canvas'][0]}x{data['canvas'][1]}  records={data['record_count']}")
        for s in data["slots"]:
            print(f"slot{s['slot_hex']} | {s['role']} | variants={s['variant_count']} | records={s['record_count']}")
            if args.variants:
                for v in s["variants"]:
                    names = " + ".join(v["record_names"][:4])
                    more = f" ...(+{len(v['record_names'])-4})" if len(v["record_names"]) > 4 else ""
                    print(f"  var{v['variant_hex']} records={v['record_count']} helper={v['contains_helper_mask']} {names}{more}")
    return 0


def cmd_records(args: argparse.Namespace) -> int:
    rows = _record_rows(args.file)
    _write_table(rows, fmt=args.format, output=args.output)
    if args.output:
        print(f"已输出 {len(rows)} 条记录 -> {args.output}")
    return 0


def cmd_dump(args: argparse.Namespace) -> int:
    project = parse_lsf_file(args.file)
    data = build_lsf_json(project, include_compatible_layers=not args.no_layers)
    text = _json_dumps(data, compact=args.compact)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"已输出 JSON -> {args.output}")
    else:
        print(text)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    pairs = _collect_from_inputs(args.input, args.recursive, args.include, args.exclude)
    ok = 0
    failed = 0
    errors: list[dict[str, str]] = []
    for path, _root in pairs:
        try:
            parse_lsf_file(path)
            ok += 1
            if not args.json and not args.quiet:
                print(f"[OK] {path}")
        except Exception as exc:
            failed += 1
            errors.append({"input": str(path), "error": str(exc)})
            if not args.json:
                print(f"[失败] {path}: {exc}", file=sys.stderr)
    data = {"total": len(pairs), "ok": ok, "failed": failed, "errors": errors}
    if args.json:
        _print_json(data, compact=args.compact)
    elif not args.quiet:
        print(f"校验完成：成功 {ok}，失败 {failed}。")
    return 0 if failed == 0 else 2


def cmd_index(args: argparse.Namespace) -> int:
    pairs = _collect_from_inputs(args.input, args.recursive, args.include, args.exclude)
    items: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    for path, _root in pairs:
        try:
            project = parse_lsf_file(path)
            summary = _slot_summary_for_file(path)
            items.append({
                "source_file": path.name,
                "source_path": str(path),
                "canvas": [project.canvas_width, project.canvas_height],
                "record_count": len(project.records),
                "slot_count": summary["slot_count"],
                "roles": [s["role"] for s in summary["slots"]],
                "slots": summary["slots"] if args.with_slots else None,
            })
        except Exception as exc:
            failed.append({"input": str(path), "error": str(exc)})
    data = {
        "schema": "lsf-source-index-v1",
        "generator": f"lsf_to_json_converter_v{__version__}",
        "total": len(pairs),
        "ok": len(items),
        "failed": len(failed),
        "items": items,
        "errors": failed,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(_json_dumps(data, compact=args.compact), encoding="utf-8")
    if not args.quiet:
        print(f"已生成索引：{args.output}  成功 {len(items)}，失败 {len(failed)}")
    return 0 if not failed else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lsf2json",
        description=f"{APP_TITLE}：支持 GUI、批量转换、扫描、检查、记录导出、索引生成。",
    )
    parser.add_argument("--version", action="version", version=f"{APP_TITLE}  version={__version__}")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("gui", help="打开图形界面")
    p.set_defaults(func=cmd_gui)

    p = sub.add_parser("version", help="显示版本号")
    p.set_defaults(func=cmd_version)

    p = sub.add_parser("convert", aliases=["batch"], help="转换单个 LSF 或目录中的 LSF 为 JSON")
    add_convert_options(p)
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("scan", aliases=["ls", "list"], help="扫描目录中有哪些 LSF 文件")
    p.add_argument("-i", "--input", action="append", required=True, help="LSF 文件或目录；可重复")
    add_common_input_filters(p)
    p.add_argument("--limit", type=int, default=0, help="限制显示数量，0 表示不限制")
    p.add_argument("--json", action="store_true", help="以 JSON 输出")
    p.add_argument("--compact", action="store_true", help="JSON 紧凑输出")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("inspect", aliases=["info"], help="查看一个 LSF 的头信息、画布、槽位分类")
    p.add_argument("file", help="LSF 文件")
    p.add_argument("--records", action="store_true", help="同时输出 records 明细")
    p.add_argument("--json", action="store_true", help="以 JSON 输出")
    p.add_argument("--compact", action="store_true", help="JSON 紧凑输出")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("slots", help="查看一个 LSF 的 slot/variant 摘要")
    p.add_argument("file", help="LSF 文件")
    p.add_argument("--variants", "-v", action="store_true", help="显示每个 variant 的记录名")
    p.add_argument("--json", action="store_true", help="以 JSON 输出")
    p.add_argument("--compact", action="store_true", help="JSON 紧凑输出")
    p.set_defaults(func=cmd_slots)

    p = sub.add_parser("records", aliases=["dump-records"], help="导出一个 LSF 的 records 表")
    p.add_argument("file", help="LSF 文件")
    p.add_argument("-o", "--output", help="输出文件；不填则打印到终端")
    p.add_argument("--format", choices=["json", "csv", "tsv"], default="csv", help="输出格式，默认 csv")
    p.set_defaults(func=cmd_records)

    p = sub.add_parser("dump", help="把单个 LSF 转成 JSON 并输出到文件或终端")
    p.add_argument("file", help="LSF 文件")
    p.add_argument("-o", "--output", help="输出 JSON 文件；不填则打印到终端")
    p.add_argument("--compact", action="store_true", help="输出紧凑 JSON，不缩进")
    p.add_argument("--no-layers", dest="no_layers", action="store_true", help="不输出 layers 兼容字段")
    p.set_defaults(func=cmd_dump)

    p = sub.add_parser("validate", aliases=["check"], help="批量检查 LSF 是否能解析")
    p.add_argument("-i", "--input", action="append", required=True, help="LSF 文件或目录；可重复")
    add_common_input_filters(p)
    p.add_argument("--json", action="store_true", help="以 JSON 输出")
    p.add_argument("--compact", action="store_true", help="JSON 紧凑输出")
    p.add_argument("--quiet", "-q", action="store_true", help="只输出汇总或错误")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("index", help="为目录生成 LSF 索引 JSON，便于后续检索/调试")
    p.add_argument("-i", "--input", action="append", required=True, help="LSF 文件或目录；可重复")
    p.add_argument("-o", "--output", required=True, help="索引 JSON 输出路径")
    add_common_input_filters(p)
    p.add_argument("--with-slots", action="store_true", help="索引里也写入完整 slot/variant 摘要")
    p.add_argument("--compact", action="store_true", help="输出紧凑 JSON，不缩进")
    p.add_argument("--quiet", "-q", action="store_true", help="减少普通文本输出")
    p.set_defaults(func=cmd_index)

    return parser


def legacy_main(argv: list[str]) -> int:
    """兼容 v1 的写法：python main.py --cli --input xxx --output yyy"""
    parser = argparse.ArgumentParser(description=f"{APP_TITLE}（兼容旧参数）")
    parser.add_argument("--input", "-i", help="LSF 文件或目录")
    parser.add_argument("--output", "-o", help="输出目录")
    parser.add_argument("--recursive", "-r", action="store_true", help="递归处理子目录")
    parser.add_argument("--no-preserve-tree", action="store_true", help="不保留输入目录结构")
    parser.add_argument("--no-overwrite", action="store_true", help="不覆盖已有 JSON")
    parser.add_argument("--suffix", default=".json", help="输出后缀，默认 .json")
    parser.add_argument("--compact", action="store_true", help="输出紧凑 JSON，不缩进")
    parser.add_argument("--no-compatible-layers", action="store_true", help="不输出 layers 兼容字段")
    parser.add_argument("--cli", action="store_true", help="使用命令行模式；不带此参数时打开 GUI")
    args = parser.parse_args(argv)

    if not args.cli and not (args.input and args.output):
        _run_gui()
        return 0
    if not args.input or not args.output:
        parser.error("CLI 模式需要 --input 和 --output")

    summary = convert_many(
        args.input,
        args.output,
        recursive=args.recursive,
        preserve_tree=not args.no_preserve_tree,
        overwrite=not args.no_overwrite,
        suffix=args.suffix,
        pretty=not args.compact,
        include_compatible_layers=not args.no_compatible_layers,
    )
    _print_json(summary)
    return 0 if summary.get("failed", 0) == 0 else 2


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        _run_gui()
        return 0

    # v1 兼容：第一个参数是 --cli / --input / --output 等选项时，走旧解析。
    known_commands = {
        "gui", "version", "convert", "batch", "scan", "ls", "list", "inspect", "info",
        "slots", "records", "dump-records", "dump", "validate", "check", "index",
    }
    if argv[0].startswith("-") and argv[0] not in {"--version", "-h", "--help"}:
        return legacy_main(argv)

    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
