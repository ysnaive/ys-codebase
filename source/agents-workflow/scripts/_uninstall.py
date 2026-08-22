#!/usr/bin/env python3
"""
agents-workflow 卸載生命週期 Hook (_uninstall.py)
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
    target_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    mode = sys.argv[2] if len(sys.argv) > 2 else "build"

    print(f"[HOOK:agents-workflow] 正在卸載模組 (模式: {mode}, 目標: {target_dir.name})，清理工作流相關配置。")
    return 0

if __name__ == "__main__":
    sys.exit(main())
