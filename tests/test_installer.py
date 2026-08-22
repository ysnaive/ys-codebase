#!/usr/bin/env python3
"""
tests/test_installer.py — yscb_installer.py 自動化整合與單元測試
"""

import os
import sys
import shutil
import tempfile
import unittest
import json
from pathlib import Path

# 將專案根目錄加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from yscb_installer import ConfigManager, ModuleManager, GitRemoteClient, format_help_doc, CONFIG_FILENAME


class TestYSCBInstaller(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="yscb_test_"))
        self.config_mgr = ConfigManager(self.test_dir)
        self.git_client = GitRemoteClient(self.test_dir)
        self.module_mgr = ModuleManager(self.test_dir, self.config_mgr, self.git_client)

        # 建立測試用的 source 結構
        self.source_dir = self.test_dir / "source"
        self.build_dir = self.test_dir / "build"
        
        # 1. 建立 core
        core_dir = self.source_dir / "core"
        core_dir.mkdir(parents=True, exist_ok=True)
        with open(core_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump({"name": "core", "version": "2.0.0", "description": "Core Base", "dependencies": []}, f)
        with open(core_dir / "core_file.txt", "w", encoding="utf-8") as f:
            f.write("core payload")

        # 2. 建立 module_workflow (有 source 與 build)
        wf_src = self.source_dir / "module_workflow"
        wf_src.mkdir(parents=True, exist_ok=True)
        with open(wf_src / "manifest.json", "w", encoding="utf-8") as f:
            json.dump({"name": "module_workflow", "version": "1.0.0", "description": "Workflow SOPs", "dependencies": []}, f)
        with open(wf_src / "sop.md", "w", encoding="utf-8") as f:
            f.write("# SOP Content")

        wf_bld = self.build_dir / "module_workflow"
        wf_bld.mkdir(parents=True, exist_ok=True)
        with open(wf_bld / "manifest.json", "w", encoding="utf-8") as f:
            json.dump({"name": "module_workflow", "version": "1.0.0", "description": "Workflow SOPs Built", "dependencies": []}, f)
        with open(wf_bld / "sop_dist.md", "w", encoding="utf-8") as f:
            f.write("# Built SOP Distribution")

        # 3. 建立 module_dependent (相依於 module_workflow)
        dep_src = self.source_dir / "module_dependent"
        dep_src.mkdir(parents=True, exist_ok=True)
        with open(dep_src / "manifest.json", "w", encoding="utf-8") as f:
            json.dump({"name": "module_dependent", "version": "1.0.0", "description": "Dependent module", "dependencies": ["module_workflow"]}, f)
        with open(dep_src / "dep.txt", "w", encoding="utf-8") as f:
            f.write("dependent payload")

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_config_init(self):
        """測試設定檔初始化與 project_root / yscb_root 相對路徑計算"""
        # 1. 預設同層級目錄
        cfg = self.config_mgr.create_default(repo="https://github.com/custom/repo.git", branch="dev")
        self.assertTrue(self.config_mgr.exists())
        self.assertEqual(cfg["remote"]["repo"], "https://github.com/custom/repo.git")
        self.assertEqual(cfg["remote"]["branch"], "dev")
        self.assertIn("paths", cfg)
        self.assertEqual(cfg["paths"]["project_root"], ".")
        self.assertEqual(cfg["paths"]["yscb_root"], ".")
        self.assertEqual(self.config_mgr.get_project_root(), self.test_dir.resolve())
        self.assertEqual(self.config_mgr.get_yscb_root(), self.test_dir.resolve())

        # 重複建立在無 --force 時應拋出 FileExistsError
        with self.assertRaises(FileExistsError):
            self.config_mgr.create_default()

        # 2. 測試自訂 project_root（例如下游專案在外層 ../..）
        cfg_custom = self.config_mgr.create_default(
            repo="https://github.com/forced/repo.git",
            project_root="../..",
            force=True
        )
        self.assertEqual(cfg_custom["remote"]["repo"], "https://github.com/forced/repo.git")
        self.assertEqual(cfg_custom["paths"]["project_root"], "../..")
        expected_yscb_rel = os.path.relpath(self.test_dir.resolve(), (self.test_dir / "../..").resolve()).replace("\\", "/")
        self.assertEqual(cfg_custom["paths"]["yscb_root"], expected_yscb_rel)
        self.assertEqual(self.config_mgr.get_project_root(), (self.test_dir / "../..").resolve())

    def test_02_discover_modules(self):
        """測試模組掃描與發現"""
        modules = self.module_mgr.discover_modules()
        self.assertIn("core", modules)
        self.assertIn("module_workflow", modules)
        self.assertIn("module_dependent", modules)

        self.assertTrue(modules["core"]["has_source"])
        self.assertFalse(modules["core"]["has_build"])

        self.assertTrue(modules["module_workflow"]["has_source"])
        self.assertTrue(modules["module_workflow"]["has_build"])

    def test_03_dependency_resolution(self):
        """測試相依性解析（包含 --source 下自動補齊 core）"""
        # 標準 build 模式：安裝 module_dependent 應自動解析出 module_workflow -> module_dependent
        res_build = self.module_mgr.resolve_dependencies(["module_dependent"], is_source_mode=False)
        self.assertEqual(res_build, ["module_workflow", "module_dependent"])

        # source 模式：安裝 module_dependent 應強制補齊 core 且排在首位
        res_source = self.module_mgr.resolve_dependencies(["module_dependent"], is_source_mode=True)
        self.assertEqual(res_source[0], "core")
        self.assertIn("module_workflow", res_source)
        self.assertIn("module_dependent", res_source)

    def test_04_install_build_mode(self):
        """測試標準 Build 模式安裝（從 build/ 安裝至 modules/）"""
        self.config_mgr.create_default()
        success = self.module_mgr.install_module("module_workflow", mode="build")
        self.assertTrue(success)

        # 檢查 modules/<module> 是否存在於專案中
        installed_file = self.test_dir / "modules" / "module_workflow" / "sop_dist.md"
        self.assertTrue(installed_file.exists())

        # 檢查 config 紀錄
        cfg = self.config_mgr.load()
        self.assertIn("module_workflow", cfg["installed_modules"])
        self.assertEqual(cfg["installed_modules"]["module_workflow"]["mode"], "build")

    def test_05_install_source_mode(self):
        """測試源碼模式安裝與 core 連帶安裝"""
        self.config_mgr.create_default()
        
        # 模擬 CLI 安裝序列
        resolved = self.module_mgr.resolve_dependencies(["module_workflow"], is_source_mode=True)
        self.assertEqual(resolved, ["core", "module_workflow"])

        for mod in resolved:
            self.module_mgr.install_module(mod, mode="source")

        cfg = self.config_mgr.load()
        self.assertIn("core", cfg["installed_modules"])
        self.assertEqual(cfg["installed_modules"]["core"]["mode"], "source")
        self.assertIn("module_workflow", cfg["installed_modules"])
        self.assertEqual(cfg["installed_modules"]["module_workflow"]["mode"], "source")

    def test_06_build_module(self):
        """測試將 source 模組建置為 build 發布產物（含相依解析、自訂 build.py 與排除 config.json）"""
        # 1. 測試建置相依解析
        build_deps = self.module_mgr.resolve_build_dependencies(["module_dependent"])
        self.assertEqual(build_deps, ["module_workflow", "module_dependent"])
        self.assertNotIn("core", build_deps)

        # 在 source 放入本地運行期 config.json
        with open(self.source_dir / "module_dependent" / "config.json", "w", encoding="utf-8") as f:
            f.write('{"local_runtime": true}')

        # 2. 測試標準建置
        success = self.module_mgr.build_module("module_dependent")
        self.assertTrue(success)

        built_file = self.test_dir / "build" / "module_dependent" / "dep.txt"
        self.assertTrue(built_file.exists())
        # 確認 config.json 被排除
        self.assertFalse((self.test_dir / "build" / "module_dependent" / "config.json").exists())

        # 檢查 manifest 注入 built_at
        manifest_path = self.test_dir / "build" / "module_dependent" / "manifest.json"
        self.assertTrue(manifest_path.exists())
        with open(manifest_path, "r", encoding="utf-8") as f:
            b_manifest = json.load(f)
        self.assertIn("built_at", b_manifest)
        self.assertEqual(b_manifest["version"], "1.0.0")

        # 3. 測試自訂 build.py
        custom_mod = self.source_dir / "module_custom_build"
        custom_mod.mkdir(parents=True, exist_ok=True)
        with open(custom_mod / "manifest.json", "w", encoding="utf-8") as f:
            json.dump({"name": "module_custom_build", "version": "3.0.0", "dependencies": []}, f)
        with open(custom_mod / "build.py", "w", encoding="utf-8") as f:
            f.write("""import sys, os, pathlib
src, dest = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
dest.mkdir(parents=True, exist_ok=True)
with open(dest / "custom_output.txt", "w") as f: f.write("custom build worked")
""")

        self.module_mgr.build_module("module_custom_build")
        custom_out = self.test_dir / "build" / "module_custom_build" / "custom_output.txt"
        self.assertTrue(custom_out.exists())

    def test_07_remove_and_dependency_guard(self):
        """測試移除模組與相依防護阻斷"""
        self.config_mgr.create_default()
        
        # 註冊 core (source) 與 module_workflow (source)
        self.config_mgr.record_installed_module("core", mode="source")
        self.config_mgr.record_installed_module("module_workflow", mode="source")

        # 嘗試移除 core 應觸發保護例外
        with self.assertRaises(RuntimeError):
            self.module_mgr.remove_module("core", force=False)

        # 移除 module_workflow
        self.module_mgr.remove_module("module_workflow")
        cfg = self.config_mgr.load()
        self.assertNotIn("module_workflow", cfg["installed_modules"])

        # 此时再移除 core 应成功
        self.module_mgr.remove_module("core")
        cfg_after = self.config_mgr.load()
        self.assertNotIn("core", cfg_after["installed_modules"])

    def test_08_help_doc(self):
        """測試說明文檔格式"""
        help_text = format_help_doc()
        self.assertIn("YS-Codebase 管理工具庫", help_text)
        self.assertIn("init", help_text)
        self.assertIn("install", help_text)
        self.assertIn("build", help_text)
        self.assertIn("push", help_text)

    def test_09_lifecycle_hooks(self):
        """測試 _installed.py 與 _uninstall.py 生命週期 Hook 調用"""
        self.config_mgr.create_default()

        # 建立帶有 hook 的測試模組
        hook_mod = self.source_dir / "module_with_hooks"
        hook_mod.mkdir(parents=True, exist_ok=True)
        (hook_mod / "scripts").mkdir(parents=True, exist_ok=True)
        with open(hook_mod / "manifest.json", "w", encoding="utf-8") as f:
            json.dump({"name": "module_with_hooks", "version": "1.0.0", "dependencies": []}, f)
        
        # 寫入 _installed.py
        with open(hook_mod / "scripts" / "_installed.py", "w", encoding="utf-8") as f:
            f.write("""import sys, pathlib
dest = pathlib.Path(sys.argv[1])
with open(dest / "installed_flag.txt", "w") as f: f.write("hook_ran")
""")
        # 寫入 _uninstall.py
        with open(hook_mod / "scripts" / "_uninstall.py", "w", encoding="utf-8") as f:
            f.write("""import sys, pathlib
target = pathlib.Path(sys.argv[1])
with open(target.parent / "uninstalled_flag.txt", "w") as f: f.write("uninstalled_hook_ran")
""")

        # 測試安裝時觸發 _installed.py
        self.module_mgr.install_module("module_with_hooks", mode="source")
        flag_file = self.test_dir / "source" / "module_with_hooks" / "installed_flag.txt"
        self.assertTrue(flag_file.exists())

        # 測試卸載時觸發 _uninstall.py
        self.module_mgr.remove_module("module_with_hooks")
        uninst_flag = self.test_dir / "source" / "uninstalled_flag.txt"
        self.assertTrue(uninst_flag.exists())

    def test_10_yscb_cli_routing(self):
        """測試 yscb_cli.py 的轉發與查找能力 (支援 modules/)"""
        from yscb_cli import find_module_cli, get_all_available_clis
        self.config_mgr.create_default()

        # 建立 modules/ 帶有 cli.py 的模組
        cli_mod = self.test_dir / "modules" / "module_with_cli"
        cli_mod.mkdir(parents=True, exist_ok=True)
        (cli_mod / "scripts").mkdir(parents=True, exist_ok=True)
        with open(cli_mod / "scripts" / "cli.py", "w", encoding="utf-8") as f:
            f.write("print('module cli')")

        self.config_mgr.record_installed_module("module_with_cli", mode="build")
        cfg = self.config_mgr.load()

        # 測試 find_module_cli
        cli_path = find_module_cli(self.test_dir, "module_with_cli", cfg)
        self.assertIsNotNone(cli_path)
        self.assertTrue(cli_path.is_file())

        # 測試 get_all_available_clis
        clis = get_all_available_clis(self.test_dir, cfg)
        self.assertIn("installer", clis)
        self.assertIn("module_with_cli", clis)

    def test_11_ide_gemini_generation(self):
        """測試 agents-workflow --ide-gemini 指令生成、自動清理與 --ide-clear 邏輯"""
        import importlib.util
        cli_spec = importlib.util.spec_from_file_location("agents_wf_cli", str(PROJECT_ROOT / "source" / "agents-workflow" / "scripts" / "cli.py"))
        wf_cli = importlib.util.module_from_spec(cli_spec)
        cli_spec.loader.exec_module(wf_cli)

        # 設定測試環境變數
        os.environ["YSCB_PROJECT_ROOT"] = str(self.test_dir)
        try:
            # 1. 首次生成 test_sop_ 前綴
            ret = wf_cli.generate_gemini_ide_commands(prefix="test_sop_", postfix="_v2")
            self.assertEqual(ret, 0)

            wf_target_dir = self.test_dir / ".agents" / "workflows"
            self.assertTrue(wf_target_dir.exists())

            sample_gen = wf_target_dir / "test_sop_NewPlan_v2.md"
            self.assertTrue(sample_gen.exists())

            # 2. 再次生成不同前綴，測試自動清理舊檔案
            ret2 = wf_cli.generate_gemini_ide_commands(prefix="new_sop_", postfix="")
            self.assertEqual(ret2, 0)
            self.assertFalse(sample_gen.exists(), "舊有前綴檔案應被自動清理")
            self.assertTrue((wf_target_dir / "new_sop_NewPlan.md").exists())

            # 3. 測試 clear_ide_commands()
            ret_clear = wf_cli.clear_ide_commands()
            self.assertEqual(ret_clear, 0)
            self.assertFalse((wf_target_dir / "new_sop_NewPlan.md").exists(), "執行 clear 後檔案應被全部清理")
        finally:
            if "YSCB_PROJECT_ROOT" in os.environ:
                del os.environ["YSCB_PROJECT_ROOT"]
            src_cfg = PROJECT_ROOT / "source" / "agents-workflow" / "config.json"
            if src_cfg.exists():
                src_cfg.unlink()

    def test_12_config_template_fallback(self):
        """測試當 config.json 不存在時，自動讀取 config.template.json"""
        self.config_mgr.create_default()

        # 建立帶有 config.template.json 的模組
        cfg_mod = self.source_dir / "module_with_template"
        cfg_mod.mkdir(parents=True, exist_ok=True)
        with open(cfg_mod / "config.template.json", "w", encoding="utf-8") as f:
            json.dump({"default_key": "default_value"}, f)

        # 模擬讀取
        tpl_file = cfg_mod / "config.template.json"
        self.assertTrue(tpl_file.exists())
        with open(tpl_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    def test_13_missing_build_artifact_diagnostic(self):
        """測試當請求 build 模式但僅存在 source 時，提供友善診斷提示"""
        self.config_mgr.create_default()

        # 建立僅有 source 的模組
        src_only = self.source_dir / "module_src_only"
        src_only.mkdir(parents=True, exist_ok=True)
        with open(src_only / "manifest.json", "w", encoding="utf-8") as f:
            json.dump({"name": "module_src_only", "version": "1.0.0", "dependencies": []}, f)

        with self.assertRaises(FileNotFoundError) as ctx:
            self.module_mgr.install_module("module_src_only", mode="build")
        self.assertIn("已發現可用源碼", str(ctx.exception))

    def test_14_verify_plan_header_parsing(self):
        """測試 verify_plan.py 對全半形冒號與空白 Header 的結構化解析能力"""
        import importlib.util
        vp_spec = importlib.util.spec_from_file_location("verify_plan_mod", str(PROJECT_ROOT / "source" / "agents-workflow" / "scripts" / "verify_plan.py"))
        vp = importlib.util.module_from_spec(vp_spec)
        vp_spec.loader.exec_module(vp)

        lines = [
            ">　功能名稱：測試計畫",
            "> 建立日期: 2026-08-22",
            "> 狀態：Planning",
            "> 擴充項目: none",
        ]
        headers = vp.parse_plan_header(lines)
        self.assertEqual(headers.get("功能名稱"), "測試計畫")
        self.assertEqual(headers.get("建立日期"), "2026-08-22")
        self.assertEqual(headers.get("狀態"), "Planning")
        self.assertEqual(headers.get("擴充項目"), "none")

    def test_15_agents_workflow_config_and_global_config(self):
        """測試 agents-workflow 模組之 config_global 與 config 單一數據源、繼承與覆寫行為"""
        import importlib.util
        cu_spec = importlib.util.spec_from_file_location("config_utils_mod", str(PROJECT_ROOT / "source" / "agents-workflow" / "scripts" / "config_utils.py"))
        cu = importlib.util.module_from_spec(cu_spec)
        cu_spec.loader.exec_module(cu)

        temp_mod_dir = self.test_dir / "modules" / "agents-workflow"
        temp_mod_dir.mkdir(parents=True, exist_ok=True)

        # 1. 僅提供 config_global.template.json，config.template.json 保持純淨（無 plans_dir 重疊）
        with open(temp_mod_dir / "config_global.template.json", "w", encoding="utf-8") as f:
            json.dump({
                "plans_dir": "../../plans",
                "archive_dir": "../../archive_plans"
            }, f)

        with open(temp_mod_dir / "config.template.json", "w", encoding="utf-8") as f:
            json.dump({
                "ide_integrations": {},
                "custom_module_settings": {}
            }, f)

        # 驗證預設自動繼承 global
        g_cfg = cu.load_global_config(temp_mod_dir)
        self.assertEqual(g_cfg["plans_dir"], "../../plans")

        p_dir = cu.get_plans_dir(temp_mod_dir)
        a_dir = cu.get_archive_dir(temp_mod_dir)
        self.assertEqual(p_dir, (self.test_dir / "plans").resolve())
        self.assertEqual(a_dir, (self.test_dir / "archive_plans").resolve())

        # 2. 本地 config.json 設定 __inherit__ token，依然繼承 global
        l_cfg = cu.load_local_config(temp_mod_dir)
        l_cfg["plans_dir"] = "__inherit__"
        cu.save_local_config(l_cfg, temp_mod_dir)
        p_dir_inherited = cu.get_plans_dir(temp_mod_dir)
        self.assertEqual(p_dir_inherited, (self.test_dir / "plans").resolve())

        # 3. 本地 config.json 顯式自訂路徑，成功覆寫 global
        l_cfg["plans_dir"] = "../../local_custom_plans"
        cu.save_local_config(l_cfg, temp_mod_dir)
        p_dir_overridden = cu.get_plans_dir(temp_mod_dir)
        self.assertEqual(p_dir_overridden, (self.test_dir / "local_custom_plans").resolve())

    def test_16_module_migration_hook(self):
        """測試模組升級時自動呼叫 _migration.py (傳入 old_version, new_version) 並保留/遷移本地 config.json"""
        mod_src = self.source_dir / "module_upgradeable"
        mod_src.mkdir(parents=True, exist_ok=True)
        scripts_src = mod_src / "scripts"
        scripts_src.mkdir(parents=True, exist_ok=True)

        # 1. 建立 v1.0.0 模組
        with open(mod_src / "manifest.json", "w", encoding="utf-8") as f:
            json.dump({
                "name": "module_upgradeable",
                "version": "1.0.0",
                "description": "Upgradeable Test Module",
                "dependencies": []
            }, f)

        self.module_mgr.build_module("module_upgradeable")
        self.module_mgr.install_module("module_upgradeable", mode="build")

        # 寫入本地 config.json
        installed_dir = self.test_dir / "modules" / "module_upgradeable"
        with open(installed_dir / "config.json", "w", encoding="utf-8") as f:
            json.dump({"custom_data": "v1_state"}, f)

        # 2. 升級至 v2.0.0 並提供 _migration.py 遷移腳本
        with open(mod_src / "manifest.json", "w", encoding="utf-8") as f:
            json.dump({
                "name": "module_upgradeable",
                "version": "2.0.0",
                "description": "Upgradeable Test Module v2",
                "dependencies": []
            }, f)

        migration_code = """import sys, json, pathlib
if __name__ == '__main__':
    old_ver = sys.argv[1]
    new_ver = sys.argv[2]
    mod_dir = pathlib.Path(__file__).resolve().parent.parent
    cfg_file = mod_dir / 'config.json'
    with open(cfg_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    data['migrated_from'] = old_ver
    data['migrated_to'] = new_ver
    with open(cfg_file, 'w', encoding='utf-8') as f:
        json.dump(data, f)
"""
        with open(scripts_src / "_migration.py", "w", encoding="utf-8") as f:
            f.write(migration_code)

        self.module_mgr.build_module("module_upgradeable")
        self.module_mgr.install_module("module_upgradeable", mode="build", force=True)

        # 3. 驗證遷移結果與本地 config.json 保留
        with open(installed_dir / "config.json", "r", encoding="utf-8") as f:
            migrated_cfg = json.load(f)

        self.assertEqual(migrated_cfg.get("custom_data"), "v1_state")
        self.assertEqual(migrated_cfg.get("migrated_from"), "1.0.0")
        self.assertEqual(migrated_cfg.get("migrated_to"), "2.0.0")

    def test_17_mandatory_init_check(self):
        """測試未執行 init 時，調用其他指令 (如 status/install) 會強制攔截並報錯"""
        import subprocess
        empty_temp_dir = Path(tempfile.mkdtemp(prefix="yscb_empty_"))
        try:
            installer_path = PROJECT_ROOT / "yscb_installer.py"
            res = subprocess.run(
                [sys.executable, str(installer_path), "status"],
                cwd=str(empty_temp_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("尚未初始化專案設定檔", res.stderr + res.stdout)
        finally:
            shutil.rmtree(empty_temp_dir, ignore_errors=True)

    def test_18_installer_init_with_project_root_cli(self):
        """測試 CLI 執行 init -p / --project-root 能正確生成 paths.project_root 與 paths.yscb_root"""
        import subprocess
        test_workspace = Path(tempfile.mkdtemp(prefix="yscb_ws_"))
        yscb_sub = test_workspace / "tools" / "ys-codebase"
        yscb_sub.mkdir(parents=True, exist_ok=True)
        try:
            # 複製 installer 腳本到子目錄
            shutil.copy2(str(PROJECT_ROOT / "yscb_installer.py"), str(yscb_sub / "yscb_installer.py"))
            
            # 在子目錄執行 init -p ../..
            res = subprocess.run(
                [sys.executable, "yscb_installer.py", "init", "-p", "../.."],
                cwd=str(yscb_sub),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            self.assertEqual(res.returncode, 0)
            self.assertTrue((yscb_sub / CONFIG_FILENAME).exists())

            with open(yscb_sub / CONFIG_FILENAME, "r", encoding="utf-8") as f:
                saved_cfg = json.load(f)

            self.assertIn("paths", saved_cfg)
            self.assertEqual(saved_cfg["paths"]["project_root"], "../..")
            self.assertEqual(saved_cfg["paths"]["yscb_root"], "tools/ys-codebase")
        finally:
            shutil.rmtree(test_workspace, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

