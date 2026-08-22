#!/usr/bin/env python3
"""
agents-workflow 安裝生命週期 Hook (_installed.py)
"""

import sys
import shutil
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

    # 1. 實體設定檔生成 (Eager Generation)
    proj_tpl = dest_path / "config.project.template.json"
    proj_cfg = dest_path / "config.project.json"
    if proj_tpl.is_file() and not proj_cfg.exists():
        try:
            shutil.copy2(proj_tpl, proj_cfg)
        except Exception:
            pass

    local_tpl = dest_path / "config.local.template.json"
    local_cfg = dest_path / "config.local.json"
    if local_tpl.is_file() and not local_cfg.exists():
        try:
            shutil.copy2(local_tpl, local_cfg)
        except Exception:
            pass

    # 2. 自動執行 AGENTS.md 軟合併同步（若已存在設定且非 !undefined）
    try:
        scripts_dir = dest_path / "scripts"
        if scripts_dir.is_dir() and str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from config_utils import sync_agents_md
        sync_agents_md(dest_path)
    except Exception:
        pass

    # 3. 自動更新 IDE 工作流指令（若先前已啟用生成且 config.local.json 有記錄）
    try:
        local_cfg_file = dest_path / "config.local.json"
        if local_cfg_file.is_file():
            import json
            l_data = json.loads(local_cfg_file.read_text(encoding="utf-8"))
            antigravity_cfg = l_data.get("ide_integrations", {}).get("antigravity")
            if antigravity_cfg:
                prefix = antigravity_cfg.get("prefix", "")
                postfix = antigravity_cfg.get("postfix", "")
                from cli import generate_antigravity_ide_commands
                print("[HOOK:agents-workflow] 偵測到既有 Antigravity IDE 整合設定，自動同步最新全量 SOP 指令...")
                generate_antigravity_ide_commands(prefix=prefix, postfix=postfix)
    except Exception:
        pass

    # 3. 終端引導提示
    print(f"[HOOK:agents-workflow] 模組安裝成功 (模式: {mode}, 目標: {dest_path.name})！")
    print("────────────────────────────────────────────────────────────────────────")
    print("💡 下一步操作建議：")
    print("  1. 初始化專案 SOP 路徑設定 (消除 !undefined)：")
    print("     • 完整自訂：python yscb_cli.py agents-workflow init --plans-dir plans --archive-dir archive_plans --docs-dir docs --extensions-dir extensions --agents-md AGENTS.md")
    print("     • 推薦預設：python yscb_cli.py agents-workflow init --default")
    print(f"     (亦可直接編輯 {dest_path.name}/config.project.json)")
    print("  2. 生成 Antigravity IDE 引用式工作流指令：")
    print("     python yscb_cli.py agents-workflow --ide-antigravity")
    print("  3. 查看模組可用指令手冊：")
    print("     python yscb_cli.py agents-workflow --help")
    print("────────────────────────────────────────────────────────────────────────")
    return 0


if __name__ == "__main__":
    sys.exit(main())
