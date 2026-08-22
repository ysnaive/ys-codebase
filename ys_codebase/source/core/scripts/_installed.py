#!/usr/bin/env python3
"""
core 安裝生命週期 Hook (_installed.py)
"""

import sys
from pathlib import Path

def main():
    target_dir = Path.cwd()
    if len(sys.argv) > 1:
        target_dir = Path(sys.argv[1]).resolve()

    mode = sys.argv[2] if len(sys.argv) > 2 else "build"

    print(f"[HOOK:core] 核心運行期 SDK 安裝成功 (模式: {mode}, 目標: {target_dir.name})！")
    return 0

if __name__ == "__main__":
    sys.exit(main() or 0)
