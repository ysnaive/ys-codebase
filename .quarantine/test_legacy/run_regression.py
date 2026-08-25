#!/usr/bin/env python3
"""
test/run_regression.py — YS-Codebase 全自動化回歸與下游專案驗證套件

使用方式：
  python test/run_regression.py
  python test/run_regression.py --fast (僅跑單元/整合測試)
"""

import sys
import os
import shutil
import tempfile
import subprocess
import unittest
from pathlib import Path

# Windows 控制台 UTF-8 編碼防呆
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
YS_CODEBASE_DIR = PROJECT_ROOT / "ys_codebase"


def run_unit_tests() -> bool:
    print("=" * 80)
    print("  [階段 1] 執行單元與整合測試套件 (test/)")
    print("=" * 80)
    
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(CURRENT_DIR), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    if result.wasSuccessful():
        print("\n[SUCCESS] 階段 1：所有單元與整合測試均通過！\n")
        return True
    else:
        print("\n[FAIL] 階段 1：測試失敗！請檢查錯誤紀錄。\n")
        return False


def run_e2e_downstream_simulation() -> bool:
    print("=" * 80)
    print("  [階段 2] 模擬下游真實專案端到端 (E2E) 沙盒回歸測試")
    print("=" * 80)

    sandbox_dir = Path(tempfile.mkdtemp(prefix="yscb_downstream_sandbox_"))
    print(f"[INFO] 建立下游模擬沙盒環境: {sandbox_dir}")

    try:
        # 1. 複製核心單檔起手腳本至下游專案
        installer_src = YYS if (YYS := (YS_CODEBASE_DIR / "yscb_installer.py")).is_file() else (PROJECT_ROOT / "yscb_installer.py")
        cli_src = YYC if (YYC := (YS_CODEBASE_DIR / "yscb_cli.py")).is_file() else (PROJECT_ROOT / "yscb_cli.py")

        shutil.copy2(str(installer_src), str(sandbox_dir / "yscb_installer.py"))
        shutil.copy2(str(cli_src), str(sandbox_dir / "yscb_cli.py"))
        print("[+] 複製 yscb_installer.py 與 yscb_cli.py 成功。")

        # 取得當前工作分支
        branch = "main"
        try:
            br_res = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(PROJECT_ROOT), capture_output=True, text=True)
            if br_res.returncode == 0 and br_res.stdout.strip():
                branch = br_res.stdout.strip()
        except Exception:
            pass

        # 2. 測試 init 指令 (指向當前本地 Repo 與分支以進行閉環測試)
        print(f"\n[Step 2.1] 執行 'installer init --repo {PROJECT_ROOT} --branch {branch}' 初始化下游設定檔...")
        res = subprocess.run(
            [sys.executable, "yscb_installer.py", "init", "--repo", str(PROJECT_ROOT), "--branch", branch],
            cwd=str(sandbox_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        if res.returncode != 0:
            print(f"[ERROR] 'installer init' 失敗: {res.stderr}\n{res.stdout}")
            return False
        if not (sandbox_dir / "yscb_config.json").is_file():
            print("[ERROR] yscb_config.json 未生成！")
            return False
        print("[+] 'installer init' 驗證通過。")

        # 3. 測試 install agents-workflow (Build 模式，自動連帶安裝 core SDK)
        print("\n[Step 2.2] 執行 'installer install agents-workflow' 安裝發布物...")
        res = subprocess.run([sys.executable, "yscb_installer.py", "install", "agents-workflow"], cwd=str(sandbox_dir), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode != 0:
            print(f"[ERROR] 'install agents-workflow' 失敗: {res.stderr}\n{res.stdout}")
            return False
        if not (sandbox_dir / "modules" / "agents-workflow").is_dir():
            print("[ERROR] modules/agents-workflow 目錄未正確建立！")
            return False
        if not (sandbox_dir / "modules" / "core").is_dir():
            print("[ERROR] modules/core (Core SDK) 目錄未自動連帶建立！")
            return False
        print("[+] 'installer install agents-workflow' (含 core SDK) 驗證通過。")

        # 4. 測試 yscb_cli.py 調度
        print("\n[Step 2.3] 執行 'yscb_cli.py --help' 與 'yscb_cli.py installer status' 驗證調度器...")
        res_help = subprocess.run([sys.executable, "yscb_cli.py", "--help"], cwd=str(sandbox_dir), capture_output=True, text=True, encoding="utf-8", errors="replace")
        res_status = subprocess.run([sys.executable, "yscb_cli.py", "installer", "status"], cwd=str(sandbox_dir), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res_help.returncode != 0 or res_status.returncode != 0:
            print(f"[ERROR] CLI 調度失敗: help={res_help.returncode}, status={res_status.returncode}")
            return False
        print("[+] 'yscb_cli.py' 統一調度轉接器運作正常。")

        # 5. 測試 agents-workflow init (初始化專案路徑)
        print("\n[Step 2.4] 執行 'yscb_cli.py agents-workflow init --default'...")
        res_init = subprocess.run([sys.executable, "yscb_cli.py", "agents-workflow", "init", "--default"], cwd=str(sandbox_dir), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res_init.returncode != 0:
            print(f"[ERROR] 模組 init 失敗: {res_init.stderr}\n{res_init.stdout}")
            return False
        print("[+] 模組專案路徑初始化正常。")

        # 6. 測試 IDE 引用式指令生成與清理 (寫入 config.local.json)
        print("\n[Step 2.5] 測試 '--ide-antigravity' 指令生成與 '--ide-clear'...")
        res_ide_gen = subprocess.run([sys.executable, "yscb_cli.py", "agents-workflow", "--ide-antigravity", "-prefix", "sandbox_sop_"], cwd=str(sandbox_dir), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res_ide_gen.returncode != 0:
            print(f"[ERROR] IDE 指令生成失敗: {res_ide_gen.stderr}\n{res_ide_gen.stdout}")
            return False
        
        gen_sample = sandbox_dir / ".agents" / "workflows" / "sandbox_sop_NewPlan.md"
        if not gen_sample.is_file():
            print(f"[ERROR] 找不到生成的 IDE 指令檔案：{gen_sample}")
            return False
        
        local_cfg_file = sandbox_dir / "modules" / "agents-workflow" / "config.local.json"
        if not local_cfg_file.is_file():
            print(f"[ERROR] config.local.json 未成功寫入個人偏好！")
            return False
        print("[+] IDE 指令成功生成且正確記錄至 config.local.json。")

        res_ide_clr = subprocess.run([sys.executable, "yscb_cli.py", "agents-workflow", "--ide-clear"], cwd=str(sandbox_dir), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res_ide_clr.returncode != 0 or gen_sample.exists():
            print(f"[ERROR] IDE 指令清理失敗！")
            return False
        print("[+] IDE 指令成功清理。")

        # 7. 測試 remove
        print("\n[Step 2.6] 執行 'installer remove agents-workflow' 與 'installer remove core'...")
        res_rem_wf = subprocess.run([sys.executable, "yscb_installer.py", "remove", "agents-workflow"], cwd=str(sandbox_dir), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res_rem_wf.returncode != 0:
            print(f"[ERROR] 移除模組 agents-workflow 失敗: {res_rem_wf.stderr}\n{res_rem_wf.stdout}")
            return False
        
        res_rem_core = subprocess.run([sys.executable, "yscb_installer.py", "remove", "core"], cwd=str(sandbox_dir), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res_rem_core.returncode != 0:
            print(f"[ERROR] 移除模組 core 失敗: {res_rem_core.stderr}\n{res_rem_core.stdout}")
            return False
        print("[+] 模組卸載驗證成功。")

        print("\n[SUCCESS] 階段 2：下游沙盒 E2E 回歸測試全部順利通過！\n")
        return True
    finally:
        shutil.rmtree(sandbox_dir, ignore_errors=True)
        print(f"[INFO] 已清理沙盒環境: {sandbox_dir}")


def main() -> int:
    fast_mode = "--fast" in sys.argv
    print("\n" + "=" * 80)
    print("  🚀 YS-Codebase 全套自動化回歸測試 (Regression Suite)")
    print("=" * 80 + "\n")

    t1_ok = run_unit_tests()
    if not t1_ok:
        return 1

    if not fast_mode:
        t2_ok = run_e2e_downstream_simulation()
        if not t2_ok:
            return 1

    print("=" * 80)
    print("  🎉🎉🎉 全部回歸測試項目驗證完成 (ALL PASSED)！")
    print("=" * 80 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
