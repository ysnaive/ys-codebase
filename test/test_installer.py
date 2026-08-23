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
TEST_DIR = Path(__file__).resolve().parent
ROOT_DIR = TEST_DIR.parent
YS_CODEBASE_ROOT = ROOT_DIR / "ys_codebase"

if (YS_CODEBASE_ROOT / "yscb_installer.py").is_file():
    PROJECT_ROOT = YS_CODEBASE_ROOT
else:
    PROJECT_ROOT = ROOT_DIR

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "source" / "core" / "scripts"))
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

        with self.assertRaises(FileExistsError):
            self.config_mgr.create_default()

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
        build_deps = self.module_mgr.resolve_build_dependencies(["module_dependent"])
        self.assertEqual(build_deps, ["core", "module_workflow", "module_dependent"])

        with open(self.source_dir / "module_dependent" / "config.local.json", "w", encoding="utf-8") as f:
            f.write('{"local_secret": "abc"}')
        with open(self.source_dir / "module_dependent" / "config.project.json", "w", encoding="utf-8") as f:
            f.write('{"project_data": "xyz"}')
        with open(self.source_dir / "module_dependent" / "config.project.template.json", "w", encoding="utf-8") as f:
            f.write('{"paths": {"plans_dir": "!undefined"}}')

        success = self.module_mgr.build_module("module_dependent")
        self.assertTrue(success)

        built_file = self.test_dir / "build" / "module_dependent" / "dep.txt"
        self.assertTrue(built_file.exists())
        self.assertFalse((self.test_dir / "build" / "module_dependent" / "config.local.json").exists())
        self.assertFalse((self.test_dir / "build" / "module_dependent" / "config.project.json").exists())
        self.assertTrue((self.test_dir / "build" / "module_dependent" / "config.project.template.json").exists())

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

        with self.assertRaises(RuntimeError):
            self.module_mgr.remove_module("core", force=False)

        self.module_mgr.remove_module("module_workflow")
        cfg = self.config_mgr.load()
        self.assertNotIn("module_workflow", cfg["installed_modules"])

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

    def test_11_ide_antigravity_and_init(self):
        """測試 agents-workflow --ide-antigravity 指令生成與 init 初始化指令"""
        import importlib.util
        src_path = PROJECT_ROOT / "source" / "agents-workflow" / "scripts" / "cli.py"
        if not src_path.is_file():
            src_path = YS_CODEBASE_ROOT / "source" / "agents-workflow" / "scripts" / "cli.py"

        cli_spec = importlib.util.spec_from_file_location("agents_wf_cli", str(src_path))
        wf_cli = importlib.util.module_from_spec(cli_spec)
        cli_spec.loader.exec_module(wf_cli)

        os.environ["YSCB_PROJECT_ROOT"] = str(self.test_dir)
        try:
            # 1. 測試 init 指令
            ret_init = wf_cli.init_project_paths(plans_dir="my_plans", archive_dir="my_archives", docs_dir="my_docs", is_default=False)
            self.assertEqual(ret_init, 0)

            # 2. 首次生成 test_sop_ 前綴
            ret = wf_cli.generate_antigravity_ide_commands(prefix="test_sop_", postfix="_v2")
            self.assertEqual(ret, 0)

            wf_target_dir = self.test_dir / ".agents" / "workflows"
            self.assertTrue(wf_target_dir.exists())

            sample_gen = wf_target_dir / "test_sop_NewPlan_v2.md"
            self.assertTrue(sample_gen.exists())

            # 3. 再次生成不同前綴，測試自動清理舊檔案
            ret2 = wf_cli.generate_antigravity_ide_commands(prefix="new_sop_", postfix="")
            self.assertEqual(ret2, 0)
            self.assertFalse(sample_gen.exists(), "舊有前綴檔案應被自動清理")
            self.assertTrue((wf_target_dir / "new_sop_NewPlan.md").exists())

            # 4. 測試 clear_ide_commands()
            ret_clear = wf_cli.clear_ide_commands()
            self.assertEqual(ret_clear, 0)
            self.assertFalse((wf_target_dir / "new_sop_NewPlan.md").exists(), "執行 clear 後檔案應被全部清理")
        finally:
            if "YSCB_PROJECT_ROOT" in os.environ:
                del os.environ["YSCB_PROJECT_ROOT"]
            local_cfg = (PROJECT_ROOT / "source" / "agents-workflow" / "config.local.json")
            if local_cfg.exists():
                local_cfg.unlink()
            proj_cfg = (PROJECT_ROOT / "source" / "agents-workflow" / "config.project.json")
            with open(proj_cfg, "w", encoding="utf-8") as f:
                json.dump({"version": "1.0", "paths": {"plans_dir": "plans", "archive_dir": "archive_plans", "docs_dir": "docs", "extensions_dir": "extensions"}}, f, indent=2)

    def test_12_yscb_core_sdk_2x2_cascade_and_undefined(self):
        """測試 yscb_core 的 ProjectContext 與 ConfigManager 2×2 Cascade 合併與 !undefined 檢查"""
        from yscb_core import ProjectContext, ConfigManager, Console

        # 1. 測試 !undefined 檢查
        self.assertTrue(ProjectContext.is_undefined("!undefined"))
        self.assertTrue(ProjectContext.is_undefined("!REQUIRED"))
        self.assertTrue(ProjectContext.is_undefined(""))
        self.assertFalse(ProjectContext.is_undefined("."))
        self.assertFalse(ProjectContext.is_undefined("plans"))

        with self.assertRaises(ValueError):
            ProjectContext.resolve("!undefined")

        # 2. 測試 ProjectContext 正常解析
        proj_root = ProjectContext.get_project_root(self.test_dir)
        self.assertEqual(proj_root, self.test_dir.resolve())
        resolved_p = ProjectContext.resolve("plans", self.test_dir)
        self.assertEqual(resolved_p, (self.test_dir / "plans").resolve())

        # 3. 測試 ConfigManager 2x2 Cascade
        mod_dir = self.test_dir / "modules" / "my_module"
        mod_dir.mkdir(parents=True, exist_ok=True)

        with open(mod_dir / "config.project.template.json", "w", encoding="utf-8") as f:
            json.dump({"paths": {"plans_dir": "plans"}, "theme": "light", "opt": 1}, f)

        with open(self.test_dir / "yscb_config.json", "w", encoding="utf-8") as f:
            json.dump({"version": "2.0", "custom_settings": {"theme": "dark"}}, f)

        with open(self.test_dir / "yscb_config.local.json", "w", encoding="utf-8") as f:
            json.dump({"custom_settings": {"opt": 2}}, f)

        with open(mod_dir / "config.project.json", "w", encoding="utf-8") as f:
            json.dump({"paths": {"plans_dir": "custom_plans"}}, f)

        with open(mod_dir / "config.local.json", "w", encoding="utf-8") as f:
            json.dump({"user_ide": "antigravity"}, f)

        merged = ConfigManager.load("my_module", start_dir=self.test_dir)
        self.assertEqual(merged.get("paths", {}).get("plans_dir"), "custom_plans")
        self.assertEqual(merged.get("theme"), "dark")
        self.assertEqual(merged.get("opt"), 2)
        self.assertEqual(merged.get("user_ide"), "antigravity")

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

    def test_17_project_uri_protocol(self):
        """測試 ProjectURI 語意協議解析 (project://, yscb://, plans://, archive://, docs://) 與 !undefined"""
        from yscb_core import ProjectURI

        # 1. 核心協議
        res_proj = ProjectURI.resolve("project://AGENTS.md", start_dir=self.test_dir)
        self.assertEqual(res_proj, (self.test_dir / "AGENTS.md").resolve())

        res_yscb = ProjectURI.resolve("yscb://source/core", start_dir=self.test_dir)
        self.assertEqual(res_yscb, (self.test_dir / "source" / "core").resolve())

        # 2. 未安裝模組時 plans:// 應回傳 !undefined
        res_uninst = ProjectURI.resolve("plans://2026_08_22/P00.md", start_dir=self.test_dir)
        self.assertEqual(res_uninst, "!undefined")

        # 3. 安裝 agents-workflow 並配置 paths.plans_dir
        mod_dir = self.test_dir / "modules" / "agents-workflow"
        mod_dir.mkdir(parents=True, exist_ok=True)
        with open(mod_dir / "config.project.json", "w", encoding="utf-8") as f:
            json.dump({"paths": {"plans_dir": "custom_plans", "archive_dir": "!undefined", "docs_dir": "docs"}}, f)

        res_plans = ProjectURI.resolve("plans://2026_08_22/P00.md", start_dir=self.test_dir)
        self.assertEqual(res_plans, (self.test_dir / "custom_plans" / "2026_08_22" / "P00.md").resolve())

        res_arch_undef = ProjectURI.resolve("archive://2026/08", start_dir=self.test_dir)
        self.assertEqual(res_arch_undef, "!undefined")

        # 4. 反向 to_uri
        sample_doc = self.test_dir / "docs" / "_project" / "STANDARDS.md"
        sample_doc.parent.mkdir(parents=True, exist_ok=True)
        sample_doc.touch()
        uri_str = ProjectURI.to_uri(sample_doc, start_dir=self.test_dir)
        self.assertEqual(uri_str, "docs://_project/STANDARDS.md")

        # 5. list_schemes
        schemes = ProjectURI.list_schemes(start_dir=self.test_dir)
        scheme_map = {s["scheme"]: s for s in schemes}
        self.assertIn("project://", scheme_map)
        self.assertIn("plans://", scheme_map)
        self.assertEqual(scheme_map["plans://"]["status"], "ACTIVE")
        self.assertEqual(scheme_map["archive://"]["status"], "UNINITIALIZED")

    def test_18_cli_uri_command(self):
        """測試 yscb_cli.py uri (resolve, list, to-uri) CLI 調度"""
        import subprocess
        self.config_mgr.create_default()

        cli_script = PROJECT_ROOT / "yscb_cli.py"

        # 1. 測試 uri resolve project://AGENTS.md
        res = subprocess.run(
            [sys.executable, str(cli_script), "uri", "resolve", "project://AGENTS.md"],
            cwd=str(self.test_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn(str(self.test_dir.resolve()), res.stdout)

        # 2. 測試 uri list
        res_list = subprocess.run(
            [sys.executable, str(cli_script), "uri", "list"],
            cwd=str(self.test_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        self.assertEqual(res_list.returncode, 0)
        self.assertIn("project://", res_list.stdout)
        self.assertIn("plans://", res_list.stdout)
        self.assertIn("sop_ext://", res_list.stdout)

    def test_19_sop_ext_and_ext_cli(self):
        """測試 sop_ext:// 協議解析與 agents-workflow ext list / show 指令"""
        from yscb_core import ProjectURI
        import subprocess

        self.config_mgr.create_default()

        mod_dir = self.test_dir / "modules" / "agents-workflow"
        mod_dir.mkdir(parents=True, exist_ok=True)
        ext_dir = self.test_dir / "custom_extensions"
        ext_dir.mkdir(parents=True, exist_ok=True)

        sample_ext = ext_dir / "ext_auth.md"
        with open(sample_ext, "w", encoding="utf-8") as f:
            f.write("---\nname: ext_auth\nphase: P01\ntrigger: on_demand\ndescription: 身份驗證安全檢查清單\n---\n# Auth Checklist\n- [ ] Check token\n")

        with open(mod_dir / "config.project.json", "w", encoding="utf-8") as f:
            json.dump({"paths": {"plans_dir": "plans", "archive_dir": "archive_plans", "docs_dir": "docs", "extensions_dir": "custom_extensions"}}, f)

        # 1. 測試 ProjectURI 解析 sop_ext://
        res_ext = ProjectURI.resolve("sop_ext://ext_auth.md", start_dir=self.test_dir)
        self.assertEqual(res_ext, sample_ext.resolve())

        # 2. 測試 agents-workflow init --extensions-dir
        from config_utils import get_extensions_dir
        resolved_ext_dir = get_extensions_dir(mod_dir)
        self.assertEqual(resolved_ext_dir, ext_dir.resolve())

    def test_20_core_module_scripts_cli(self):
        """測試 Core 模組遵照規範具備 core/scripts/cli.py 與 _installed.py"""
        src_core = PROJECT_ROOT / "source" / "core"
        if not src_core.exists():
            src_core = YS_CODEBASE_ROOT / "source" / "core"

        self.assertTrue((src_core / "scripts" / "cli.py").is_file())
        self.assertTrue((src_core / "scripts" / "_installed.py").is_file())
        self.assertTrue((src_core / "scripts" / "context.py").is_file())
        self.assertTrue((src_core / "scripts" / "config.py").is_file())
        self.assertTrue((src_core / "scripts" / "console.py").is_file())
        self.assertTrue((src_core / "scripts" / "uri.py").is_file())
        self.assertTrue((src_core / "scripts" / "yscb_core.py").is_file())
        self.assertFalse((src_core / "yscb_core").exists(), "source/core/yscb_core 不應存在")
        self.assertFalse((src_core / "scripts" / "yscb_core").exists(), "source/core/scripts/yscb_core 應已完全扁平化集成於 scripts/")
        self.assertFalse((src_core / "__init__.py").exists(), "source/core/__init__.py 不應存在，模組代碼應全數收斂至 scripts/")

        import subprocess
        res = subprocess.run(
            [sys.executable, str(src_core / "scripts" / "cli.py"), "info"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("YS-Codebase Core Runtime SDK", res.stdout)

    def test_21_plan_storage_scan_search_archive(self):
        """測試計畫儲存、狀態掃描、DR 檢索與安全歸檔工具鏈"""
        import subprocess
        import shutil

        self.config_mgr.create_default()

        mod_dir = self.test_dir / "modules" / "agents-workflow"
        (mod_dir / "scripts").mkdir(parents=True, exist_ok=True)

        src_scripts = PROJECT_ROOT / "source" / "agents-workflow" / "scripts"
        if not src_scripts.exists():
            src_scripts = YS_CODEBASE_ROOT / "source" / "agents-workflow" / "scripts"
        for sf in src_scripts.glob("*.py"):
            shutil.copy2(sf, mod_dir / "scripts" / sf.name)

        plans_dir = self.test_dir / "my_plans"
        archive_dir = self.test_dir / "my_archive"
        plans_dir.mkdir(parents=True, exist_ok=True)
        archive_dir.mkdir(parents=True, exist_ok=True)

        with open(mod_dir / "config.project.json", "w", encoding="utf-8") as f:
            json.dump({"paths": {"plans_dir": "my_plans", "archive_dir": "my_archive", "docs_dir": "docs", "extensions_dir": "extensions"}}, f)

        # 1. 建立 Umbrella 測試計畫與子計畫
        plan_name = "2026_08_22_1000_sample_umbrella"
        plan_path = plans_dir / plan_name
        sub_path = plan_path / "sub_01_core"
        sub_path.mkdir(parents=True, exist_ok=True)

        (plan_path / "umbrella_overview.md").write_text("# 總覽\n> 狀態：In Progress\n### DR-01: 架構分層\n- **結論**：採用微核心", encoding="utf-8")
        (plan_path / "handoff.md").write_text("# Handoff\n- [ ] Task 1", encoding="utf-8")
        (sub_path / "FT_plan.md").write_text("# 子計畫\n> 狀態：Planning", encoding="utf-8")

        scripts_dir = mod_dir / "scripts"

        # 2. 測試 scan 指令
        res_scan = subprocess.run([sys.executable, str(scripts_dir / "scan_plan_status.py")], capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res_scan.returncode, 0)
        self.assertIn(plan_name, res_scan.stdout)
        self.assertIn("sub_01_core", res_scan.stdout)
        self.assertIn("Paused", res_scan.stdout)

        # 3. 測試 search 指令 (DR 模式與全文模式)
        res_search_dr = subprocess.run([sys.executable, str(scripts_dir / "search_dev_plans.py"), "--dr"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res_search_dr.returncode, 0)
        self.assertIn("DR-01", res_search_dr.stdout)
        self.assertIn("微核心", res_search_dr.stdout)

        # 4. 測試 archive 指令：子計畫未完成時應攔截
        res_arch_fail = subprocess.run([sys.executable, str(scripts_dir / "archive_plan.py"), plan_name], capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertNotEqual(res_arch_fail.returncode, 0)
        self.assertIn("尚有未完成的子計畫", res_arch_fail.stdout)

        # 5. 完成子計畫與主計畫後，順利歸檔並清理 handoff.md
        (sub_path / "FT_plan.md").write_text("# 子計畫\n> 狀態：Completed", encoding="utf-8")
        (plan_path / "umbrella_overview.md").write_text("# 總覽\n> 狀態：Completed\n", encoding="utf-8")
        (self.test_dir / "CHANGELOG.md").write_text(f"## Changelog\n- {plan_name}\n", encoding="utf-8")

        res_arch_success = subprocess.run([sys.executable, str(scripts_dir / "archive_plan.py"), plan_name], capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res_arch_success.returncode, 0)
        self.assertIn("已成功將計畫歸檔至", res_arch_success.stdout)

        # 驗證目標路徑存在且 handoff.md 已被清理
        archived_target = archive_dir / "2026" / "08" / plan_name
        self.assertTrue(archived_target.is_dir())
        self.assertTrue((archived_target / "sub_01_core" / "FT_plan.md").is_file())
        self.assertFalse((archived_target / "handoff.md").exists())
        self.assertFalse(plan_path.exists())

    def test_22_docs_tooling_init_check_links_and_scaffold(self):
        """測試知識庫 docs init, new-topic 與 check-links/audit 工具鏈"""
        import subprocess
        import shutil

        self.config_mgr.create_default()

        mod_dir = self.test_dir / "modules" / "agents-workflow"
        (mod_dir / "scripts").mkdir(parents=True, exist_ok=True)

        src_scripts = PROJECT_ROOT / "source" / "agents-workflow" / "scripts"
        if not src_scripts.exists():
            src_scripts = YS_CODEBASE_ROOT / "source" / "agents-workflow" / "scripts"
        for sf in src_scripts.glob("*.py"):
            shutil.copy2(sf, mod_dir / "scripts" / sf.name)

        docs_dir = self.test_dir / "my_docs"
        scripts_dir = mod_dir / "scripts"

        # 1. 測試 docs init
        res_init = subprocess.run([sys.executable, str(scripts_dir / "docs_tool.py"), "init", "--docs-dir", str(docs_dir)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res_init.returncode, 0)
        self.assertTrue((docs_dir / "README.md").is_file())
        self.assertTrue((docs_dir / "_project" / "ARCHITECTURE.md").is_file())

        # 2. 測試 docs new-topic
        res_topic = subprocess.run([sys.executable, str(scripts_dir / "docs_tool.py"), "new-topic", "App", "lifecycle", "--docs-dir", str(docs_dir)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res_topic.returncode, 0)
        topic_file = docs_dir / "App" / "lifecycle.md"
        self.assertTrue(topic_file.is_file())
        self.assertIn("target: \"App/lifecycle\"", topic_file.read_text(encoding="utf-8"))

        # 3. 測試 docs audit (健康狀態)
        res_audit_ok = subprocess.run([sys.executable, str(scripts_dir / "docs_tool.py"), "audit", "--docs-dir", str(docs_dir)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res_audit_ok.returncode, 0)
        self.assertIn("100% 正常", res_audit_ok.stdout)

        # 4. 注入死鏈測試 audit 攔截
        topic_file.write_text("---\ntarget: \"App/lifecycle\"\nstatus: \"active\"\n---\n# Test\n[無效連結](./non_existent.md)\n", encoding="utf-8")
        res_audit_broken = subprocess.run([sys.executable, str(scripts_dir / "docs_tool.py"), "audit", "--docs-dir", str(docs_dir)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertNotEqual(res_audit_broken.returncode, 0)
        self.assertIn("Broken Link", res_audit_broken.stdout)

    def test_23_agents_md_soft_merge_three_states(self):
        """測試 AGENTS.md 軟合併三態處理 (無檔案新建、具備標記局部更新、無標記警告不覆寫)"""
        import shutil

        self.config_mgr.create_default()

        mod_dir = self.test_dir / "modules" / "agents-workflow"
        (mod_dir / "scripts").mkdir(parents=True, exist_ok=True)
        (mod_dir / "workflows" / "templates").mkdir(parents=True, exist_ok=True)

        src_scripts = PROJECT_ROOT / "source" / "agents-workflow" / "scripts"
        if not src_scripts.exists():
            src_scripts = YS_CODEBASE_ROOT / "source" / "agents-workflow" / "scripts"
        for sf in src_scripts.glob("*.py"):
            shutil.copy2(sf, mod_dir / "scripts" / sf.name)

        tpl_src = PROJECT_ROOT / "source" / "agents-workflow" / "workflows" / "templates" / "AGENTS.template.md"
        if not tpl_src.exists():
            tpl_src = YS_CODEBASE_ROOT / "source" / "agents-workflow" / "workflows" / "templates" / "AGENTS.template.md"
        shutil.copy2(tpl_src, mod_dir / "workflows" / "templates" / "AGENTS.template.md")

        if str(mod_dir / "scripts") not in sys.path:
            sys.path.insert(0, str(mod_dir / "scripts"))

        from config_utils import sync_agents_md, AGENTS_BEGIN_MARKER, AGENTS_END_MARKER

        os.environ["YSCB_PROJECT_ROOT"] = str(self.test_dir)
        try:
            target_agents = self.test_dir / "AGENTS.md"

            # 狀態 1：無檔案 ➔ 建立新檔案
            self.assertFalse(target_agents.exists())
            ret1 = sync_agents_md(mod_dir, target_path_override="AGENTS.md")
            self.assertTrue(ret1)
            self.assertTrue(target_agents.is_file())
            content1 = target_agents.read_text(encoding="utf-8")
            self.assertIn(AGENTS_BEGIN_MARKER, content1)
            self.assertIn(AGENTS_END_MARKER, content1)

            # 狀態 2：具備標記 ➔ 局部替換，保留自訂前後綴
            custom_prefix = "# My Custom Project Header\n\n"
            custom_suffix = "\n\n## Custom Rules\n- Rule A\n- Rule B\n"
            target_agents.write_text(f"{custom_prefix}{AGENTS_BEGIN_MARKER}\nOld Content\n{AGENTS_END_MARKER}{custom_suffix}", encoding="utf-8")

            ret2 = sync_agents_md(mod_dir, target_path_override="AGENTS.md")
            self.assertTrue(ret2)
            content2 = target_agents.read_text(encoding="utf-8")
            self.assertTrue(content2.startswith(custom_prefix))
            self.assertTrue(content2.endswith(custom_suffix))
            self.assertNotIn("Old Content", content2)
            self.assertIn("零臆測 (Zero Speculation)", content2)

            # 狀態 3：不具備標記 ➔ 輸出警告，不覆寫
            user_manual_content = "# Pure Manual Document Without Markers\nDo not touch!"
            target_agents.write_text(user_manual_content, encoding="utf-8")

            ret3 = sync_agents_md(mod_dir, target_path_override="AGENTS.md")
            self.assertFalse(ret3)
            self.assertEqual(target_agents.read_text(encoding="utf-8"), user_manual_content)
        finally:
            if "YSCB_PROJECT_ROOT" in os.environ:
                del os.environ["YSCB_PROJECT_ROOT"]

    def test_24_installer_self_update(self):
        """測試 Installer 自舉升級 (self-update) 與起手腳本原子安全替換"""
        self.config_mgr.create_default()
        
        # 在 test_dir 建立舊版起手腳本 (v2.0.0)
        root_inst = self.test_dir / "yscb_installer.py"
        root_inst.write_text('#!/usr/bin/env python3\nINSTALLER_VERSION = "2.0.0"\nprint("Old")', encoding="utf-8")
        
        # 在快取目錄建立新版起手腳本 (v2.1.0)
        cache_dir = self.git_client.cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        new_inst = cache_dir / "yscb_installer.py"
        new_inst.write_text('#!/usr/bin/env python3\nINSTALLER_VERSION = "2.1.0"\nprint("New")', encoding="utf-8")
        
        # 阻斷網路同步，聚焦於檔案替換邏輯
        self.git_client.sync_cache = lambda force_refresh=False: None

        # 執行 self-update
        success = self.module_mgr.self_update(force=False)
        self.assertTrue(success)
        
        # 驗證 root_inst 內容已更新為 v2.1.0
        updated_content = root_inst.read_text(encoding="utf-8")
        self.assertIn('INSTALLER_VERSION = "2.1.0"', updated_content)
        self.assertIn('print("New")', updated_content)
        self.assertFalse((self.test_dir / "yscb_installer.tmp").exists())
        self.assertFalse((self.test_dir / "yscb_installer.py.tmp").exists())


if __name__ == "__main__":
    unittest.main()





