from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import APP_TITLE
from .core import collect_lsf_files, convert_lsf_file, convert_many


class LSFToJSONApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("820x580")
        self._apply_app_icon()
        self.minsize(700, 500)

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.recursive_var = tk.BooleanVar(value=False)
        self.preserve_tree_var = tk.BooleanVar(value=True)
        self.overwrite_var = tk.BooleanVar(value=True)
        self.pretty_var = tk.BooleanVar(value=True)
        self.compat_layers_var = tk.BooleanVar(value=True)
        self.suffix_var = tk.StringVar(value=".json")
        self.status_var = tk.StringVar(value="请选择 LSF 文件或目录。")

        self._build_ui()

    def _resource_path(self, relative: str) -> Path:
        # 兼容源码运行和 PyInstaller 打包后的临时目录。
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
        return base / relative

    def _apply_app_icon(self) -> None:
        ico_path = self._resource_path("assets/app.ico")
        png_path = self._resource_path("assets/app.png")
        try:
            if ico_path.exists():
                self.iconbitmap(default=str(ico_path))
        except Exception:
            pass
        try:
            if png_path.exists():
                self._app_icon_photo = tk.PhotoImage(file=str(png_path))
                self.iconphoto(True, self._app_icon_photo)
        except Exception:
            pass

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(5, weight=1)

        input_frame = ttk.LabelFrame(root, text="输入 / 输出", padding=8)
        input_frame.grid(row=0, column=0, columnspan=3, sticky="ew")
        input_frame.columnconfigure(1, weight=1)

        ttk.Label(input_frame, text="LSF 文件或目录").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(input_frame, textvariable=self.input_var).grid(row=0, column=1, sticky="ew", pady=3)
        btns = ttk.Frame(input_frame)
        btns.grid(row=0, column=2, sticky="e", padx=(8, 0))
        ttk.Button(btns, text="选文件", command=self.choose_file).pack(side="left", padx=(0, 4))
        ttk.Button(btns, text="选目录", command=self.choose_input_dir).pack(side="left")

        ttk.Label(input_frame, text="输出目录").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(input_frame, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Button(input_frame, text="选择", command=self.choose_output_dir).grid(row=1, column=2, sticky="e", padx=(8, 0))

        option_frame = ttk.LabelFrame(root, text="转换选项", padding=8)
        option_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        for i in range(4):
            option_frame.columnconfigure(i, weight=1)
        ttk.Checkbutton(option_frame, text="包含子目录", variable=self.recursive_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(option_frame, text="保留目录结构", variable=self.preserve_tree_var).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(option_frame, text="覆盖已有 JSON", variable=self.overwrite_var).grid(row=0, column=2, sticky="w")
        ttk.Checkbutton(option_frame, text="格式化缩进", variable=self.pretty_var).grid(row=0, column=3, sticky="w")
        ttk.Checkbutton(option_frame, text="附带 layers 兼容字段", variable=self.compat_layers_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(option_frame, text="输出后缀").grid(row=1, column=2, sticky="e", pady=(6, 0), padx=(0, 6))
        ttk.Entry(option_frame, textvariable=self.suffix_var, width=12).grid(row=1, column=3, sticky="w", pady=(6, 0))

        actions = ttk.Frame(root)
        actions.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text="扫描数量", command=self.scan_files).pack(side="left")
        ttk.Button(actions, text="开始批量转换", command=self.start_convert).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="打开输出目录", command=self.open_output_dir).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="清空日志", command=lambda: self.log_text.delete("1.0", "end")).pack(side="right")

        ttk.Label(root, textvariable=self.status_var).grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self.progress = ttk.Progressbar(root, mode="determinate")
        self.progress.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(6, 0))

        log_frame = ttk.LabelFrame(root, text="日志", padding=4)
        log_frame.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, height=14, wrap="none")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll = ttk.Scrollbar(log_frame, orient="horizontal", command=self.log_text.xview)
        xscroll.grid(row=1, column=0, sticky="ew")
        self.log_text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        self._log("LSF文件转JSON文件Ver1.0（此工具针对小E社引擎开发  ユイ可愛ね制作  编译日期26-4-25）")
        self._log("说明：输出 JSON 会保留 records 原始坐标/tag，也会生成 slots 和 selection_groups 方便后续合成工具读取。")

    def choose_file(self) -> None:
        path = filedialog.askopenfilename(title="选择 LSF 文件", filetypes=[("LSF 文件", "*.lsf"), ("所有文件", "*.*")])
        if path:
            self.input_var.set(path)
            if not self.output_var.get().strip():
                self.output_var.set(str(Path(path).parent / "json"))

    def choose_input_dir(self) -> None:
        path = filedialog.askdirectory(title="选择 LSF 目录")
        if path:
            self.input_var.set(path)
            if not self.output_var.get().strip():
                self.output_var.set(str(Path(path) / "json"))

    def choose_output_dir(self) -> None:
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_var.set(path)

    def scan_files(self) -> None:
        inp = self.input_var.get().strip()
        if not inp:
            messagebox.showwarning("提示", "请先选择 LSF 文件或目录。")
            return
        files = collect_lsf_files(inp, recursive=self.recursive_var.get())
        self.status_var.set(f"扫描到 {len(files)} 个 LSF 文件。")
        self._log(f"扫描: {inp}")
        for f in files[:80]:
            self._log(f"  - {f}")
        if len(files) > 80:
            self._log(f"  ... 还有 {len(files) - 80} 个未显示")

    def start_convert(self) -> None:
        inp = self.input_var.get().strip()
        out = self.output_var.get().strip()
        if not inp:
            messagebox.showwarning("提示", "请先选择 LSF 文件或目录。")
            return
        if not out:
            messagebox.showwarning("提示", "请先选择输出目录。")
            return
        files = collect_lsf_files(inp, recursive=self.recursive_var.get())
        if not files:
            messagebox.showwarning("提示", "没有找到 .lsf 文件。")
            return
        self.progress.configure(maximum=len(files), value=0)
        self.status_var.set("转换中...")
        self._log(f"开始转换，共 {len(files)} 个。")

        t = threading.Thread(target=self._convert_worker, args=(inp, out, files), daemon=True)
        t.start()

    def _convert_worker(self, inp: str, out: str, files: list[Path]) -> None:
        root = Path(inp) if Path(inp).is_dir() else Path(inp).parent
        ok = 0
        failed = 0
        errors: list[str] = []
        for i, path in enumerate(files, start=1):
            try:
                out_path, data = convert_lsf_file(
                    path,
                    out,
                    input_root=root,
                    preserve_tree=self.preserve_tree_var.get(),
                    overwrite=self.overwrite_var.get(),
                    suffix=self.suffix_var.get().strip() or ".json",
                    pretty=self.pretty_var.get(),
                    include_compatible_layers=self.compat_layers_var.get(),
                )
                ok += 1
                self.after(0, self._log, f"[OK] {path.name} -> {out_path}  records={len(data.get('records', []))}")
            except Exception as exc:
                failed += 1
                msg = f"[失败] {path}: {exc}"
                errors.append(msg)
                self.after(0, self._log, msg)
            self.after(0, self.progress.configure, {"value": i})
            self.after(0, self.status_var.set, f"转换中 {i}/{len(files)}，成功 {ok}，失败 {failed}")

        def done() -> None:
            self.status_var.set(f"完成：成功 {ok}，失败 {failed}。")
            if failed:
                messagebox.showwarning("完成", f"转换完成，成功 {ok}，失败 {failed}。详情看日志。")
            else:
                messagebox.showinfo("完成", f"转换完成，成功 {ok} 个。")
        self.after(0, done)

    def open_output_dir(self) -> None:
        path = self.output_var.get().strip()
        if not path:
            return
        Path(path).mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception:
            messagebox.showinfo("输出目录", path)

    def _log(self, msg: str) -> None:
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")


def run_gui() -> None:
    app = LSFToJSONApp()
    app.mainloop()
