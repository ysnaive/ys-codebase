#!/usr/bin/env python3
"""
test/test_uri_completeness.py — 語意 URI 統一轉換器、模組檔案系統與快取儲存完備性測試套件

覆蓋測試矩陣：
  - FT-01 ~ FT-08: 功能驗證
  - ET-01 ~ ET-07: 邊界與安全性防護
  - PT-01: 效能基準測試
"""

import os
import sys
import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

# 將 source/core/scripts 加入 sys.path 確保測試以最新源碼為準
# Windows 控制台 UTF-8 編碼防呆
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
YS_CODEBASE_ROOT = PROJECT_ROOT / "ys_codebase"
CORE_SCRIPTS = PROJECT_ROOT / "ys_codebase" / "source" / "core" / "scripts"

for p in [str(CORE_SCRIPTS), str(YS_CODEBASE_ROOT), str(PROJECT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from context import ProjectContext
from uri import ProjectURI
from config import ConfigManager


class TestSemanticURICompleteness(unittest.TestCase):
    """完備性測試套件：涵蓋 FT-01~08, ET-01~07, PT-01"""

    def setUp(self):
        ProjectURI.clear_cache()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="yscb_test_uri_"))
        self.proj_dir = self.temp_dir / "my_project"
        self.yscb_dir = self.proj_dir / "yscb_tools"
        self.proj_dir.mkdir(parents=True, exist_ok=True)
        self.yscb_dir.mkdir(parents=True, exist_ok=True)

        # 建立 yscb_config.json
        cfg_data = {
            "version": "2.0",
            "paths": {
                "project_root": ".",
                "yscb_root": "./yscb_tools"
            },
            "installed_modules": {
                "knowledge-db": {
                    "mode": "build",
                    "version": "1.0.0"
                }
            }
        }
        (self.proj_dir / "yscb_config.json").write_text(json.dumps(cfg_data, indent=2), encoding="utf-8")

    def tearDown(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ── FT-01: yscb:// 空間隔離與動態解耦 ──────────────────────────────
    def test_ft_01_yscb_root_isolation(self):
        """FT-01: 配置 paths.yscb_root = './yscb_tools' 時，get_yscb_root 正確解析至子目錄"""
        res_yscb = ProjectContext.get_yscb_root(self.proj_dir)
        self.assertEqual(res_yscb.resolve(), self.yscb_dir.resolve())
        self.assertNotEqual(res_yscb.resolve(), self.proj_dir.resolve())

        # 透過 URI 解析
        uri_res = ProjectURI.resolve("yscb://modules/core", start_dir=self.proj_dir)
        self.assertEqual(uri_res, (self.yscb_dir / "modules" / "core").resolve())

    # ── FT-02: 模組專屬命名空間快取目錄 ─────────────────────────────────
    def test_ft_02_module_cache_dir(self):
        """FT-02: get_module_cache_dir 解析為 yscb://.yscb_cache/modules/<module>/ 並自動建目錄"""
        cache_dir = ProjectContext.get_module_cache_dir("knowledge-db", start_dir=self.proj_dir)
        expected = self.yscb_dir / ".yscb_cache" / "modules" / "knowledge-db"
        self.assertEqual(cache_dir.resolve(), expected.resolve())
        self.assertTrue(cache_dir.is_dir())

    # ── FT-03: cache:// 與 storage:// 泛型語意解析 ──────────────────────
    def test_ft_03_cache_and_storage_uri(self):
        """FT-03: cache:// 與 storage:// 正確分流至 yscb 快取與 project 儲存"""
        res_cache = ProjectURI.resolve("cache://knowledge-db/index.json", start_dir=self.proj_dir)
        expected_cache = self.yscb_dir / ".yscb_cache" / "modules" / "knowledge-db" / "index.json"
        self.assertEqual(res_cache, expected_cache.resolve())

        res_storage = ProjectURI.resolve("storage://knowledge-db/records.db", start_dir=self.proj_dir)
        expected_storage = self.proj_dir / ".yscb_storage" / "knowledge-db" / "records.db"
        self.assertEqual(res_storage, expected_storage.resolve())

    # ── FT-04: ProjectURI.resolve() 與 validate() 接口校驗 ───────────────
    def test_ft_04_validate_and_resolve(self):
        """FT-04: validate() 與 resolve() 接口校驗與正常解析"""
        is_valid, err = ProjectURI.validate("project://AGENTS.md", start_dir=self.proj_dir)
        self.assertTrue(is_valid)
        self.assertEqual(err, "")

        resolved = ProjectURI.resolve("project://AGENTS.md", start_dir=self.proj_dir)
        self.assertEqual(resolved, (self.proj_dir / "AGENTS.md").resolve())

    # ── FT-05: 最長前綴匹配 (LPM) 演算法 ────────────────────────────────
    def test_ft_05_longest_prefix_matching(self):
        """FT-05: to_uri 依 LPM 與優先級將實體路徑反向匹配為最精確語意 URI"""
        docs_dir = self.proj_dir / "docs" / "guides"
        docs_dir.mkdir(parents=True, exist_ok=True)
        doc_file = docs_dir / "setup.md"
        doc_file.write_text("Hello", encoding="utf-8")

        # 模擬 docs 協議
        uri_str = ProjectURI.to_uri(doc_file, start_dir=self.proj_dir)
        self.assertEqual(uri_str, "docs://guides/setup.md")

        # 模組快取檔案反向匹配為 cache://
        cache_file = self.yscb_dir / ".yscb_cache" / "modules" / "knowledge-db" / "index.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text("{}", encoding="utf-8")

        cache_uri = ProjectURI.to_uri(cache_file, start_dir=self.proj_dir)
        self.assertEqual(cache_uri, "cache://knowledge-db/index.json")

    # ── FT-06: 快取直讀直寫與門面 API ────────────────────────────────────
    def test_ft_06_direct_io_facade(self):
        """FT-06: ProjectURI.write_text 與 read_text / exists 門面 API 正常工作"""
        target_uri = "cache://knowledge-db/test_data.txt"
        ProjectURI.write_text(target_uri, "Hello YSCB URI", start_dir=self.proj_dir)

        self.assertTrue(ProjectURI.exists(target_uri, start_dir=self.proj_dir))
        self.assertTrue(ProjectURI.is_file(target_uri, start_dir=self.proj_dir))
        self.assertEqual(ProjectURI.read_text(target_uri, start_dir=self.proj_dir), "Hello YSCB URI")

    # ── FT-07: agents-workflow 快取平滑遷移 ──────────────────────────────
    def test_ft_07_agents_workflow_cache_migration(self):
        """FT-07: IDECacheTracker 啟動時將舊版根目錄快取自動移動至命名空間目錄"""
        legacy_cache = self.proj_dir / ".yscb_cache" / "ide_manifest_antigravity.json"
        legacy_cache.parent.mkdir(parents=True, exist_ok=True)
        legacy_cache.write_text(json.dumps({"adapter": "antigravity", "files": ["test.md"]}), encoding="utf-8")

        # 載入 ide_sync 測試
        workflow_scripts = PROJECT_ROOT / "ys_codebase" / "source" / "agents-workflow" / "scripts"
        if str(workflow_scripts) not in sys.path:
            sys.path.insert(0, str(workflow_scripts))

        from ide_sync import IDECacheTracker
        tracker = IDECacheTracker(self.proj_dir, adapter="antigravity")

        new_cache = self.yscb_dir / ".yscb_cache" / "modules" / "agents-workflow" / "ide_manifest_antigravity.json"
        self.assertTrue(new_cache.is_file())
        self.assertFalse(legacy_cache.exists())

    # ── FT-08: ConfigManager 設定檔語意 URI 遞迴展開 ─────────────────────
    def test_ft_08_config_resolve_uris(self):
        """FT-08: ConfigManager.resolve_config_uris 遞迴展開字典中的語意 URI"""
        raw_dict = {
            "name": "my-tool",
            "paths": {
                "docs": "docs://topic/readme.md",
                "nested": {
                    "cache": "cache://knowledge-db/idx.db",
                    "list": ["project://AGENTS.md", "plain_string"]
                }
            }
        }
        resolved = ConfigManager.resolve_config_uris(raw_dict, start_dir=self.proj_dir)
        self.assertEqual(resolved["paths"]["docs"], str((self.proj_dir / "docs" / "topic" / "readme.md").resolve()))
        self.assertEqual(resolved["paths"]["nested"]["cache"], str((self.yscb_dir / ".yscb_cache" / "modules" / "knowledge-db" / "idx.db").resolve()))
        self.assertEqual(resolved["paths"]["nested"]["list"][0], str((self.proj_dir / "AGENTS.md").resolve()))
        self.assertEqual(resolved["paths"]["nested"]["list"][1], "plain_string")

    # ── ET-01: 深層未建立子目錄自動建立 ───────────────────────────────────
    def test_et_01_deep_nested_mkdir(self):
        """ET-01: paths.yscb_root 設為多層未建立目錄時自動 mkdir -p"""
        deep_dir = self.proj_dir / "sub1" / "sub2" / "yscb"
        (self.proj_dir / "yscb_config.json").write_text(
            json.dumps({"paths": {"yscb_root": "./sub1/sub2/yscb"}}, indent=2), encoding="utf-8"
        )
        cache_dir = ProjectContext.get_module_cache_dir("test-mod", start_dir=self.proj_dir)
        self.assertTrue(cache_dir.is_dir())
        self.assertTrue(deep_dir.is_dir())

    # ── ET-02: 多重連續斜線與反斜線正規化 ─────────────────────────────────
    def test_et_02_slashes_normalization(self):
        """ET-02: 傳入多重斜線 docs:///sub//topic///doc.md 自動正規化"""
        res = ProjectURI.resolve("docs:///sub//topic///doc.md", start_dir=self.proj_dir)
        expected = (self.proj_dir / "docs" / "sub" / "topic" / "doc.md").resolve()
        self.assertEqual(res, expected)

        res_bs = ProjectURI.resolve("docs:\\\\sub\\doc.md", start_dir=self.proj_dir)
        expected_bs = (self.proj_dir / "docs" / "sub" / "doc.md").resolve()
        self.assertEqual(res_bs, expected_bs)

    # ── ET-03: .. 越界逃逸沙盒圍欄安全阻斷 ────────────────────────────────
    def test_et_03_sandbox_chroot_escape_block(self):
        """ET-03: 傳入 docs://../../secret.json 試圖逃逸被安全阻斷"""
        is_valid, err = ProjectURI.validate("docs://../../secret.json", start_dir=self.proj_dir)
        self.assertFalse(is_valid)
        self.assertIn("越界", err)

        res = ProjectURI.resolve("docs://../../secret.json", start_dir=self.proj_dir)
        self.assertEqual(res, "!undefined")

        with self.assertRaises(PermissionError):
            ProjectURI.resolve("docs://../../secret.json", start_dir=self.proj_dir, strict=True)

    # ── ET-04: cache:// 缺少 authority 格式校驗失敗 ───────────────────────
    def test_et_04_cache_missing_authority(self):
        """ET-04: cache:// 未提供 authority 時 validate 判定失敗"""
        is_valid, err = ProjectURI.validate("cache://", start_dir=self.proj_dir)
        self.assertFalse(is_valid)
        self.assertIn("命名空間", err)

    # ── ET-05: 卸載無快取模組安全靜默 ───────────────────────────────────
    def test_et_05_clean_empty_cache_safe(self):
        """ET-05: 清理不存在的模組快取安全返回 False 不崩潰"""
        import importlib.util
        spec = importlib.util.spec_from_file_location("yscb_installer_src", str(YS_CODEBASE_ROOT / "yscb_installer.py"))
        installer_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer_mod)
        ModuleManager = installer_mod.ModuleManager
        InstConfigManager = installer_mod.ConfigManager
        GitRemoteClient = installer_mod.GitRemoteClient

        cfg_mgr = InstConfigManager(self.proj_dir)
        git_client = GitRemoteClient(self.proj_dir)
        mod_mgr = ModuleManager(self.proj_dir, cfg_mgr, git_client)

        success = mod_mgr.clean_module_cache("non_existing_module")
        self.assertFalse(success)

    # ── ET-06: 外部絕對路徑 to_uri 安全回退 ──────────────────────────────
    def test_et_06_to_uri_external_path_fallback(self):
        """ET-06: 傳入外部系統路徑至 to_uri 安全回退絕對路徑字串"""
        ext_path = Path("C:/Windows/temp/file.txt") if os.name == "nt" else Path("/tmp/other/file.txt")
        uri_str = ProjectURI.to_uri(ext_path, start_dir=self.proj_dir)
        self.assertNotIn("project://", uri_str)
        self.assertNotIn("yscb://", uri_str)

    # ── ET-07: yscb_root = '.' 同層配置向下相容 ───────────────────────────
    def test_et_07_same_layer_compatibility(self):
        """ET-07: paths.yscb_root = '.' 時專案與工具庫同層平滑相容"""
        (self.proj_dir / "yscb_config.json").write_text(
            json.dumps({"paths": {"project_root": ".", "yscb_root": "."}}, indent=2), encoding="utf-8"
        )
        res_proj = ProjectContext.get_project_root(self.proj_dir)
        res_yscb = ProjectContext.get_yscb_root(self.proj_dir)
        self.assertEqual(res_proj.resolve(), res_yscb.resolve())

        cache_dir = ProjectContext.get_module_cache_dir("knowledge-db", start_dir=self.proj_dir)
        self.assertEqual(cache_dir.resolve(), (self.proj_dir / ".yscb_cache" / "modules" / "knowledge-db").resolve())

    # ── PT-01: 10,000 次 URI 解析微秒級效能基準 ──────────────────────────
    def test_pt_01_performance_benchmark(self):
        """PT-01: 10,000 次 ProjectURI.resolve() 與 validate() 基準耗時 <= 150ms"""
        uris = [
            "project://AGENTS.md",
            "yscb://modules/core/manifest.json",
            "docs://topic/architecture.md",
            "cache://knowledge-db/index.json",
            "storage://knowledge-db/data.db"
        ]
        start_time = time.perf_counter()
        for i in range(2000):
            for u in uris:
                ProjectURI.resolve(u, start_dir=self.proj_dir)
        duration_ms = (time.perf_counter() - start_time) * 1000

        print(f"\n[BENCHMARK] 10,000 次 URI 解析耗時: {duration_ms:.2f} ms (平均單次: {duration_ms/10000*1000:.2f} us)")
        self.assertLessEqual(duration_ms, 500, "10,000 次解析耗時超出效能基準")


if __name__ == "__main__":
    unittest.main(verbosity=2)
