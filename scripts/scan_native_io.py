#!/usr/bin/env python3
"""
YS-Codebase 全生態系原生檔案讀寫 AST 靜態檢測工具 (Ecosystem Native IO Scanner)。
100% Python 標準庫，以 AST 靜態語法樹全面盤點模組源碼中之原生 open()、Pathlib 與 OS/Shutil IO 調用點。
"""

import ast
import os
import sys
import json
import argparse
from typing import List, Dict, Any, Optional


class NativeIOCallVisitor(ast.NodeVisitor):
    """AST 拜訪器，偵測原生檔案 IO 調用。"""

    def __init__(self, filename: str, rel_path: str, module_name: str):
        self.filename = filename
        self.rel_path = rel_path
        self.module_name = module_name
        self.findings: List[Dict[str, Any]] = []

    def visit_Call(self, node: ast.Call) -> None:
        call_name = ""
        category = ""

        # 1. 檢測直接函式調用 (例如 open(...))
        if isinstance(node.func, ast.Name):
            if node.func.id == "open":
                call_name = "open"
                category = "native_open"

        # 2. 檢測屬性調用 (例如 os.remove, Path.read_text, shutil.copy)
        elif isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            # os.xxx / os.path.xxx
            if isinstance(node.func.value, ast.Name):
                caller_obj = node.func.value.id
                if caller_obj == "os" and attr in ("remove", "unlink", "mkdir", "makedirs", "listdir", "replace"):
                    call_name = f"os.{attr}"
                    category = "os_io"
                elif caller_obj == "shutil" and attr in ("copy", "copy2", "copytree", "move", "rmtree"):
                    call_name = f"shutil.{attr}"
                    category = "shutil_io"
                elif attr in ("read_text", "write_text", "read_bytes", "write_bytes", "mkdir", "unlink"):
                    call_name = f"Path.{attr}"
                    category = "pathlib_io"
            elif isinstance(node.func.value, ast.Attribute):
                # 處理更深層屬性如 os.path 等
                pass

        if call_name:
            self.findings.append({
                "module": self.module_name,
                "file": self.rel_path,
                "line": node.lineno,
                "call": call_name,
                "category": category,
            })

        self.generic_visit(node)


def scan_directory(source_root: str, include_tests: bool = False) -> List[Dict[str, Any]]:
    """掃描 source 目錄下的所有模組。"""
    all_findings: List[Dict[str, Any]] = []

    if not os.path.isdir(source_root):
        return all_findings

    for mod_name in sorted(os.listdir(source_root)):
        mod_dir = os.path.join(source_root, mod_name)
        if not os.path.isdir(mod_dir) or mod_name.startswith("."):
            continue

        for root, _, files in os.walk(mod_dir):
            for file in files:
                if not file.endswith(".py"):
                    continue

                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, source_root)

                # 排除測試目錄 (除非指定 include_tests)
                if not include_tests and ("/tests/" in abs_path or abs_path.endswith("/test_vfs.py") or "test_" in file):
                    continue

                # 排除 vfs 自身實作
                if "/core/vfs/" in abs_path:
                    continue

                try:
                    with open(abs_path, "r", encoding="utf-8") as f:
                        source_code = f.read()
                    tree = ast.parse(source_code, filename=abs_path)
                    visitor = NativeIOCallVisitor(abs_path, rel_path, mod_name)
                    visitor.visit(tree)
                    all_findings.extend(visitor.findings)
                except Exception as e:
                    print(f"Warning: Failed to parse {abs_path}: {e}", file=sys.stderr)

    return all_findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan ecosystem modules for native file IO usages.")
    parser.add_argument("--source-root", default="ys_codebase/source", help="Path to source root")
    parser.add_argument("--include-tests", action="store_true", help="Include test files in scan")
    parser.add_argument("--json", action="store_true", help="Output findings in JSON format")
    parser.add_argument("--summary", action="store_true", help="Display aggregated summary table")
    parser.add_argument("--markdown", action="store_true", help="Output markdown table for plan documentation")

    args = parser.parse_args()
    findings = scan_directory(args.source_root, include_tests=args.include_tests)

    if args.json:
        print(json.dumps(findings, indent=2, ensure_ascii=False))
        return 0

    # 聚合統計
    by_mod: Dict[str, Dict[str, int]] = {}
    for f in findings:
        m = f["module"]
        cat = f["category"]
        if m not in by_mod:
            by_mod[m] = {"native_open": 0, "pathlib_io": 0, "os_io": 0, "shutil_io": 0, "total": 0}
        by_mod[m][cat] = by_mod[m].get(cat, 0) + 1
        by_mod[m]["total"] += 1

    if args.markdown:
        print("| 模組名稱 | 原生 open() | Pathlib IO | OS/Shutil IO | 總原生 IO 點 | 建議處置策略 |")
        print("| :--- | :---: | :---: | :---: | :---: | :--- |")
        for m, stats in sorted(by_mod.items()):
            print(f"| `{m}` | {stats['native_open']} | {stats['pathlib_io']} | {stats['os_io'] + stats['shutil_io']} | **{stats['total']}** | 優先遷移至 `core.vfs` |")
        return 0

    print("=" * 80)
    print("YS-Codebase Ecosystem Native File IO Scan Report")
    print("=" * 80)
    print(f"{'MODULE':<20} {'OPEN()':<10} {'PATHLIB':<10} {'OS/SHUTIL':<12} {'TOTAL':<8}")
    print("-" * 80)
    for m, stats in sorted(by_mod.items()):
        print(f"{m:<20} {stats['native_open']:<10} {stats['pathlib_io']:<10} {stats['os_io'] + stats['shutil_io']:<12} {stats['total']:<8}")
    print("-" * 80)
    total_all = sum(s["total"] for s in by_mod.values())
    print(f"Total Native IO points detected: {total_all}")
    print("=" * 80)

    if not args.summary:
        print("\nTop 20 Native open() Call Sites:")
        opens = [f for f in findings if f["category"] == "native_open"][:20]
        for o in opens:
            print(f"  • [{o['module']}] {o['file']}:{o['line']} -> {o['call']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
