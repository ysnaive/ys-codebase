"""
yscb_core.console — YS-Codebase 統一控制台格式化輸出 (Unified Console & Logger)
"""

import sys
from typing import List, Optional


class Console:
    """提供全平台統一風格的控制台輸出與日誌記錄工具"""

    # ANSI 顏色碼
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"

    _use_color = True

    @classmethod
    def set_color_enabled(cls, enabled: bool) -> None:
        cls._use_color = enabled

    @classmethod
    def _colorize(cls, text: str, color_code: str) -> str:
        if cls._use_color and sys.stdout.isatty():
            return f"{color_code}{text}{cls.RESET}"
        return text

    @classmethod
    def header(cls, title: str, width: int = 80) -> None:
        print("=" * width)
        print(f"  {title}")
        print("=" * width)

    @classmethod
    def subheader(cls, title: str) -> None:
        print(f"\n--- {title} ---")

    @classmethod
    def info(cls, msg: str) -> None:
        prefix = cls._colorize("[INFO]", cls.BLUE)
        print(f"{prefix} {msg}")

    @classmethod
    def success(cls, msg: str) -> None:
        prefix = cls._colorize("[SUCCESS]", cls.GREEN)
        print(f"{prefix} {msg}")

    @classmethod
    def warn(cls, msg: str) -> None:
        prefix = cls._colorize("[WARN]", cls.YELLOW)
        print(f"{prefix} {msg}")

    @classmethod
    def error(cls, msg: str) -> None:
        prefix = cls._colorize("[ERROR]", cls.RED)
        print(f"{prefix} {msg}", file=sys.stderr)

    @classmethod
    def hook(cls, msg: str) -> None:
        prefix = cls._colorize("[HOOK]", cls.MAGENTA)
        print(f"{prefix} {msg}")

    @classmethod
    def table(cls, headers: List[str], rows: List[List[str]]) -> None:
        """純文字結構化表格輸出"""
        if not headers:
            return

        col_widths = [len(str(h)) for h in headers]
        for row in rows:
            for idx, cell in enumerate(row):
                if idx < len(col_widths):
                    col_widths[idx] = max(col_widths[idx], len(str(cell)))

        fmt = " | ".join([f"{{:<{w}}}" for w in col_widths])
        sep = "-+-".join(["-" * w for w in col_widths])

        print(fmt.format(*headers))
        print(sep)
        for row in rows:
            padded_row = list(row) + [""] * (len(headers) - len(row))
            print(fmt.format(*padded_row[:len(headers)]))
