#!/usr/bin/env python3
"""
test/tests/test_installer.py — yscb_installer.py 與 yscb_core SDK 自動化整合與單元測試
"""

import os
import sys
import shutil
import tempfile
import unittest
import json
from pathlib import Path

# 取得專案根目錄與 ys_codebase 源碼目錄
TESTS_DIR = Path(__file__).resolve().parent
TEST_DIR = TESTS_DIR.parent
ROOT_DIR = TEST_DIR.parent
YS_CODEBASE_ROOT = ROOT_DIR / "ys_codebase"

if (YS_CODEBASE_ROOT / "yscb_installer.py").is_file():
    PROJECT_ROOT = YS_CODEBASE_ROOT
else:
    PROJECT_ROOT = ROOT_DIR

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "source" / "core"))

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
        
        # 1. 建立 core (有 source 與 build)
        core_dir = self.source_dir / "core"
        core_dir.mkdir(parents=True, exist_ok=True)
        with open(core_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump({"name": "core", "version": "2.0.0", "description": "Core Base SDK", "dependencies": []}, f)
        with open(core_dir / "core_file.txt", "w", encoding="utf-8") as f:
            f.write("core payload")

        core_bld = self.build_dir / "core"
        core_bld.mkdir(parents=True, exist_ok=True)
        with open(core_bld / "manifest.json", "w", encoding="utf-8") as f:
            json.dump({"name": "core", "version": "2.0.0", "description": "Core Base SDK Built", "dependencies": []}, f)
        with open(core_bld / "core_file.txt", "w", encoding="utf-8") as f:
            f.write("core built payload")

        # 2. 建立 module_workflow (有 source 與 build，相依於 core)
        wf_src = self.source_dir / "module_workflow"
        wf_src.mkdir(parents=True, exist_ok=True)
        with open(wf_src / "manifest.json", "w", encoding="utf-8") as f:
            json.dump({"name": "module_workflow", "version": "1.0.0", "description": "Workflow SOPs", "dependencies": ["core"]}, f)
        with open(wf_src / "sop.md", "w", encoding="utf-8") as f:
            f.write("# SOP Content")

        wf_bld = self.build_dir / "module_workflow"
        wf_bld.mkdir(parents=True, exist_ok=True)
        with open(wf_bld / "manifest.json", "w", encoding="utf-8") as f:
            json.dump({"name": "module_workflow", "version": "1.0.0", "description": "Workflow SOPs Built", "dependencies": ["core"]}, f)
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

        # 測試自訂 project_root（例如下游專案在外層 ../..）
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
        """測試模組掃描與發現 (包含 core)"""
        modules = self.module_mgr.discover_modules()
        self.assertIn("core", modules)
        self.assertIn("module_workflow", modules)
        self.assertIn("module_dependent", modules)

        self.assertTrue(modules["core"]["has_source"])
        self.assertTrue(modules["core"]["has_build"])

        self.assertTrue(modules["module_workflow"]["has_source"])
        self.assertTrue(modules["module_workflow"]["has_build"])

    def test_03_dependency_resolution(self):
        """測試相依性解析（自動補齊 core 且置於首位）"""
        res_build = self.module_mgr.resolve_dependencies(["module_dependent"], is_source_mode=False)
        self.assertEqual(res_build, ["core", "module_workflow", "module_dependent"])

        res_source = self.module_mgr.resolve_dependencies(["module_dependent"], is_source_mode=True)
        self.assertEqual(res_source[0], "core")
        self.assertIn("module_workflow", res_source)
        self.assertIn("module_dependent", res_source)

    def test_04_install_build_mode(self):
        """測試標準 Build 模式安裝（從 build/ 安裝至 modules/，包含 core）"""
        self.config_mgr.create_default()
        
        # 安裝 module_workflow (連帶相依 core)
        resolved = self.module_mgr.resolve_dependencies(["module_workflow"], is_source_mode=False)
        for mod in resolved:
            self.module_mgr.install_module(mod, mode="build")

        installed_wf = self.test_dir / "modules" / "module_workflow" / "sop_dist.md"
        installed_core = self.test_dir / "modules" / "core" / "core_file.txt"
        self.assertTrue(installed_wf.exists())
        self.assertTrue(installed_core.exists())

        cfg = self.config_mgr.load()
        self.assertIn("module_workflow", cfg["installed_modules"])
        self.assertIn("core", cfg["installed_modules"])
        self.assertEqual(cfg["installed_modules"]["module_workflow"]["mode"], "build")
        self.assertEqual(cfg["installed_modules"]["core"]["mode"], "build")

    def test_05_install_source_mode(self):
        """測試源碼模式安裝與 core 連帶安裝"""
        self.config_mgr.create_default()
        
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
        """測試將 source 模組建置為 build 發布產物（包含 core 與排除 2x2 local 設定）"""
        # 1. 測試建置相依解析
        build_deps = self.module_mgr.resolve_build_dependencies(["module_dependent"])
        self.assertEqual(build_deps, ["core", "module_workflow", "module_dependent"])

        # 在 source 放入本地運行期 config.local.json 與 config.project.json
        with open(self.source_dir / "module_dependent" / "config.local.json", "w", encoding="utf-8") as f:
            f.write('{"local_secret": "abc"}')
        with open(self.source_dir / "module_dependent" / "config.project.json", "w", encoding="utf-8") as f:
            f.write('{"project_data": "xyz"}')
        with open(self.source_dir / "module_dependent" / "config.project.template.json", "w", encoding="utf-8") as f:
            f.write('{"template_data": "default"}')

        # 2. 測試建置
        success = self.module_mgr.build_module("module_dependent")
        self.assertTrue(success)

        built_file = self.test_dir / "build" / "module_dependent" / "dep.txt"
        self.assertTrue(built_file.exists())
        # 確認 config.local.json 與 config.project.json 被排除，template 被保留
        self.assertFalse((self.test_dir / "build" / "module_dependent" / "config.local.json").exists())
        self.assertFalse((self.test_dir / "build" / "module_dependent" / "config.project.json").exists())
        self.assertTrue((self.test_dir / "build" / "module_dependent" / "config.project.template.json").exists())

        # 檢查 manifest 注入 built_at
        manifest_path = self.test_dir / "build" / "module_dependent" / "manifest.json"
        self.assertTrue(manifest_path.exists())
        with open(manifest_path, "r", encoding="utf-8") as f:
            b_manifest = json.load(f)
        self.assertIn("built_at", b_manifest)
        self.assertEqual(b_manifest["version"], "1.0.0")

    def test_07_remove_and_dependency_guard(self):
        """測試移除模組與 core 相依防護阻斷"""
        self.config_mgr.create_default()
        
        self.config_mgr.record_installed_module("core", mode="build")
        self.config_mgr.record_installed_module("module_workflow", mode="build")

        # 嘗試移除 core 應觸發保護例外
        with self.assertRaises(RuntimeError):
            self.module_mgr.remove_module("core", force=False)

        # 移除 module_workflow
        self.module_mgr.remove_module("module_workflow")
        cfg = self.config_mgr.load()
        self.assertNotIn("module_workflow", cfg["installed_modules"])

        # 此時再移除 core 應成功
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

        hook_mod = self.source_dir / "module_with_hooks"
        hook_mod.mkdir(parents=True, exist_ok=True)
        (hook_mod / "scripts").mkdir(parents=True, exist_ok=True)
        with open(hook_mod / "manifest.json", "w", encoding="utf-8") as f:
            json.dump({"name": "module_with_hooks", "version": "1.0.0", "dependencies": []}, f)
        
        with open(hook_mod / "scripts" / "_installed.py", "w", encoding="utf-8") as f:
            f.write("""import sys, pathlib
dest = pathlib.Path(sys.argv[1])
with open(dest / "installed_flag.txt", "w") as f: f.write("hook_ran")
""")
        with open(hook_mod / "scripts" / "_uninstall.py", "w", encoding="utf-8") as f:
            f.write("""import sys, pathlib
target = pathlib.Path(sys.argv[1])
with open(target.parent / "uninstalled_flag.txt", "w") as f: f.write("uninstalled_hook_ran")
""")

        self.module_mgr.install_module("module_with_hooks", mode="source")
        flag_file = self.test_dir / "source" / "module_with_hooks" / "installed_flag.txt"
        self.assertTrue(flag_file.exists())

        self.module_mgr.remove_module("module_with_hooks")
        uninst_flag = self.test_dir / "source" / "uninstalled_flag.txt"
        self.assertTrue(uninst_flag.exists())

    def test_10_yscb_cli_routing(self):
        """測試 yscb_cli.py 的轉發與查找能力"""
        from yscb_cli import find_module_cli, get_all_available_clis
        self.config_mgr.create_default()

        cli_mod = self.test_dir / "modules" / "module_with_cli"
        cli_mod.mkdir(parents=True, exist_ok=True)
        (cli_mod / "scripts").mkdir(parents=True, exist_ok=True)
        with open(cli_mod / "scripts" / "cli.py", "w", encoding="utf-8") as f:
            f.write("print('module cli')")

        self.config_mgr.record_installed_module("module_with_cli", mode="build")
        cfg = self.config_mgr.load()

        cli_path = find_module_cli(self.test_dir, "module_with_cli", cfg)
        self.assertIsNotNone(cli_path)
        self.assertTrue(cli_path.is_file())

        clis = get_all_available_clis(self.test_dir, cfg)
        self.assertIn("installer", clis)
        self.assertIn("module_with_cli", clis)

    def test_11_ide_gemini_generation(self):
        """測試 agents-workflow --ide-gemini 指令生成與 config.local.json 記錄"""
        import importlib.util
        src_path = PROJECT_ROOT / "source" / "agents-workflow" / "scripts" / "cli.py"
        if not src_path.is_file():
            src_path = YS_CODEBASE_ROOT / "source" / "agents-workflow" / "scripts" / "cli.py"

        cli_spec = importlib.util.spec_from_file_location("agents_wf_cli", str(src_path))
        wf_cli = importlib.util.module_from_spec(cli_spec)
        cli_spec.loader.exec_module(wf_cli)

        os.environ["YSCB_PROJECT_ROOT"] = str(self.test_dir)
        try:
            ret = wf_cli.generate_gemini_ide_commands(prefix="test_sop_", postfix="_v2")
            self.assertEqual(ret, 0)

            wf_target_dir = self.test_dir / ".agents" / "workflows"
            self.assertTrue(wf_target_dir.exists())

            sample_gen = wf_target_dir / "test_sop_NewPlan_v2.md"
            self.assertTrue(sample_gen.exists())

            ret2 = wf_cli.generate_gemini_ide_commands(prefix="new_sop_", postfix="")
            self.assertEqual(ret2, 0)
            self.assertFalse(sample_gen.exists(), "舊有前綴檔案應被自動清理")
            self.assertTrue((wf_target_dir / "new_sop_NewPlan.md").exists())

            ret_clear = wf_cli.clear_ide_commands()
            self.assertEqual(ret_clear, 0)
            self.assertFalse((wf_target_dir / "new_sop_NewPlan.md").exists(), "執行 clear 後檔案應被全部清理")
        finally:
            if "YSCB_PROJECT_ROOT" in os.environ:
                del os.environ["YSCB_PROJECT_ROOT"]
            local_cfg = (PROJECT_ROOT / "source" / "agents-workflow" / "config.local.json")
            if local_cfg.exists():
                local_cfg.unlink()

    def test_12_yscb_core_sdk_2x2_cascade(self):
        """測試 yscb_core 的 ProjectContext 與 ConfigManager 2×2 Cascade 合併"""
        from yscb_core import ProjectContext, ConfigManager, Console

        # 1. 測試 ProjectContext
        proj_root = ProjectContext.get_project_root(self.test_dir)
        self.assertEqual(proj_root, self.test_dir.resolve())
        resolved_p = ProjectContext.resolve("plans", self.test_dir)
        self.assertEqual(resolved_p, (self.test_dir / "plans").resolve())

        # 2. 測試 ConfigManager 2x2 Cascade
        mod_dir = self.test_dir / "modules" / "my_module"
        mod_dir.mkdir(parents=True, exist_ok=True)

        # 6. Template
        with open(mod_dir / "config.project.template.json", "w", encoding="utf-8") as f:
            json.dump({"plans_dir": "plans", "theme": "light", "opt": 1}, f)

        # 5. Codebase.ProjectLevel (yscb_config.json)
        with open(self.test_dir / "yscb_config.json", "w", encoding="utf-8") as f:
            json.dump({"version": "2.0", "custom_settings": {"theme": "dark"}}, f)

        # 4. Codebase.UserLevel (yscb_config.local.json)
        with open(self.test_dir / "yscb_config.local.json", "w", encoding="utf-8") as f:
            json.dump({"custom_settings": {"opt": 2}}, f)

        # 3. Module.ProjectLevel (config.project.json)
        with open(mod_dir / "config.project.json", "w", encoding="utf-8") as f:
            json.dump({"plans_dir": "custom_plans"}, f)

        # 2. Module.UserLevel (config.local.json)
        with open(mod_dir / "config.local.json", "w", encoding="utf-8") as f:
            json.dump({"user_ide": "gemini"}, f)

        merged = ConfigManager.load("my_module", start_dir=self.test_dir)
        self.assertEqual(merged.get("plans_dir"), "custom_plans")  # Module.Project 覆寫 Template
        self.assertEqual(merged.get("theme"), "dark")              # Codebase.Project 覆寫 Template
        self.assertEqual(merged.get("opt"), 2)                     # Codebase.User 覆寫 Codebase.Project
        self.assertEqual(merged.get("user_ide"), "gemini")         # Module.User 生效

    def test_13_missing_build_artifact_diagnostic(self):
        """測試當請求 build 模式但僅存在 source 時，提供友善診斷提示"""
        self.config_mgr.create_default()

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
        src_path = PROJECT_ROOT / "source" / "agents-workflow" / "scripts" / "verify_plan.py"
        if not src_path.is_file():
            src_path = YS_CODEBASE_ROOT / "source" / "agents-workflow" / "scripts" / "verify_plan.py"

        vp_spec = importlib.util.spec_from_file_location("verify_plan_mod", str(src_path))
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

    def test_15_mandatory_init_check(self):
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

    def test_16_installer_init_with_project_root_cli(self):
        """測試 CLI 執行 init -p / --project-root 能正確生成 paths.project_root 與 paths.yscb_root"""
        import subprocess
        test_workspace = Path(tempfile.mkdtemp(prefix="yscb_ws_"))
        yscb_sub = test_workspace / "tools" / "ys-codebase"
        yscb_sub.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(str(PROJECT_ROOT / "yscb_installer.py"), str(yscb_sub / "yscb_installer.py"))
            
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
