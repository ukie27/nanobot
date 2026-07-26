"""Native folder selection for the local Windows control plane."""

from __future__ import annotations

import sys
from pathlib import Path


class DirectoryPickerUnavailableError(RuntimeError):
    """Raised when the current runtime cannot show a native folder dialog."""


class NativeDirectoryPicker:
    """Open a native Windows folder dialog and return the selected directory."""

    def pick(self, *, initial_directory: Path | None = None) -> Path | None:
        if sys.platform != "win32":
            raise DirectoryPickerUnavailableError(
                "当前运行环境不支持原生文件夹选择器，请手动输入绝对路径。"
            )
        try:
            import tkinter as tk
            from tkinter import filedialog
        except ImportError as exc:
            raise DirectoryPickerUnavailableError(
                "Python 未安装 Tk 图形组件，请手动输入绝对路径。"
            ) from exc

        try:
            root = tk.Tk()
        except tk.TclError as exc:
            raise DirectoryPickerUnavailableError(
                "无法打开原生文件夹选择器，请手动输入绝对路径。"
            ) from exc
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            selected = filedialog.askdirectory(
                parent=root,
                title="选择 CareerConsole 工作区父目录",
                initialdir=(
                    str(initial_directory)
                    if initial_directory is not None and initial_directory.is_dir()
                    else None
                ),
                mustexist=True,
            )
        except tk.TclError as exc:
            raise DirectoryPickerUnavailableError(
                "无法打开原生文件夹选择器，请手动输入绝对路径。"
            ) from exc
        finally:
            root.destroy()
        return Path(selected).resolve() if selected else None
