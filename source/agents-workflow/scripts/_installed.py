#!/usr/bin/env python3
"""
agents-workflow 安裝生命週期 Hook (_installed.py)
"""

import sys
from pathlib import Path

# Windows 控制台編碼防呆
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def main():
    dest_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    mode = sys.argv[2] if len(sys.argv) > 2 else "build"

    print(f"[HOOK:agents-workflow] 初始化安裝成功 (模式: {mode}, 目標: {dest_path.name})。SOP 規範與定式工具庫已就緒。")
    return 0

if __name__ == "__main__":
    sys.exit(main())
