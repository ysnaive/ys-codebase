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
        """測試設定檔初始化"""
        cfg = self.config_mgr.create_default(repo="https://github.com/custom/repo.git", branch="dev")
        self.assertTrue(self.config_mgr.exists())
        self.assertEqual(cfg["remote"]["repo"], "https://github.com/custom/repo.git")
        self.assertEqual(cfg["remote"]["branch"], "dev")

        # 重複建立在無 --force 時應拋出 FileExistsError
        with self.assertRaises(FileExistsError):
            self.config_mgr.create_default()

        # 加上 force 應成功
        cfg_forced = self.config_mgr.create_default(repo="https://github.com/forced/repo.git", force=True)
        self.assertEqual(cfg_forced["remote"]["repo"], "https://github.com/forced/repo.git")

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
        """測試標準 Build 模式安裝"""
        self.config_mgr.create_default()
        success = self.module_mgr.install_module("module_workflow", mode="build")
        self.assertTrue(success)

        # 檢查 build/<module> 是否存在於專案中
        installed_file = self.test_dir / "build" / "module_workflow" / "sop_dist.md"
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
        """測試將 source 模組建置為 build 發布產物"""
        success = self.module_mgr.build_module("module_dependent")
        self.assertTrue(success)

        built_file = self.test_dir / "build" / "module_dependent" / "dep.txt"
        self.assertTrue(built_file.exists())

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


if __name__ == "__main__":
    unittest.main()
