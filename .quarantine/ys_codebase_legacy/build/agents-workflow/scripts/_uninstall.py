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

    # 清理 sync_workflow.py 時代遺留的舊設定檔
    project_root = target_dir.parent.parent
    legacy_cfg = project_root / ".agents" / ".workflow_config.json"
    if legacy_cfg.is_file():
        try:
            legacy_cfg.unlink()
            print(f"  • [CLEANUP] 已移除舊版 sync_workflow 設定檔: {legacy_cfg}")
        except Exception as e:
            print(f"  • [WARN] 清理舊版設定檔失敗: {e}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
