#!/usr/bin/env python3
"""
_migration.py — 模組版本遷移腳本 (Migration Hook)

介面規範：
  參數 1: old_version (舊版本號，例：1.0.0)
  參數 2: new_version (新版本號，例：1.1.0)

職責：
  當模組進行版本升級更新時由 yscb_installer 自動調用，執行版本間的資料遷移邏輯。
"""

import sys


def migrate(old_version: str, new_version: str) -> bool:
    """執行版本遷移邏輯（目前維持空實作）"""
    # TODO: 待未來有跨版本 Schema / 數據變更需求時在此實作
    return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python _migration.py <old_version> <new_version>")
        sys.exit(1)

    old_ver = sys.argv[1]
    new_ver = sys.argv[2]

    success = migrate(old_ver, new_ver)
    sys.exit(0 if success else 1)
