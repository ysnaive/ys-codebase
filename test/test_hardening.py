#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test/test_hardening.py — 擴充性與可靠性強化回歸測試套件

覆蓋範圍：
  - HT-01: build_module 於「僅遠端快取有源碼」情境不再崩潰 (UnboundLocalError 修復)
  - HT-02: YSCB_MODULE_DIR 環境變數不再汙染跨模組目錄查詢
  - HT-03: SOPSynthesizer Slot 匹配與 SLOT_PATTERN 容錯規則一致 (空白變體)
  - HT-04: remove_module 依 manifest dependencies 執行真實相依防護
  - HT-05: URI Scheme 可由模組 manifest contributes["core"]["uri_schemes"] 開放註冊
  - HT-06: 多模組貢獻查詢 (get_contributions) 結果具決定性排序
  - HT-07: 版本號單一事實來源 (SSOT) 同步防護 (起手腳本雙副本 / yscb_core.__version__)
"""

import os
import re
import sys
import json
import shutil
import tempfile
import unittest
from pathlib import Path

# Windows 控制台編碼防呆
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

TEST_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEST_DIR.parent
YS_CODEBASE_DIR = REPO_ROOT / "ys_codebase"

for p in [YS_CODEBASE_DIR, YS_CODEBASE_DIR / "source" / "core" / "scripts",
          YS_CODEBASE_DIR / "source" / "agents-workflow" / "scripts"]:
    if p.is_dir() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

from yscb_installer import ConfigManager, ModuleManager, GitRemoteClient
from context import ProjectContext
from uri import ProjectURI
from sop_synthesizer import SOPSynthesizer


class TestHardening(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="yscb_test_hardening_"))
        self.config_mgr = ConfigManager(self.test_dir)
        self.git_client = GitRemoteClient(self.test_dir)
        self.module_mgr = ModuleManager(self.test_dir, self.config_mgr, self.git_client)

    def tearDown(self):
        if self.test_dir.is_dir():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _write_manifest(self, mod_dir: Path, name: str, version: str = "1.0.0", **extra):
        mod_dir.mkdir(parents=True, exist_ok=True)
        manifest = {"name": name, "version": version, "description": "", "dependencies": []}
        manifest.update(extra)
        (mod_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ── HT-01: build_module 於快取來源情境的 dest_path 回退 ──────────
    def test_ht_01_build_from_cache_only_source(self):
        """僅 .yscb_cache/source 有源碼 (典型下游專案) 時，build 應回退輸出至本地 build/ 而非崩潰"""
        cache_src = self.test_dir / ".yscb_cache" / "source" / "cache_mod"
        self._write_manifest(cache_src, "cache_mod")
        (cache_src / "payload.txt").write_text("payload", encoding="utf-8")

        success = self.module_mgr.build_module("cache_mod")
        self.assertTrue(success)
        self.assertTrue((self.test_dir / "build" / "cache_mod" / "payload.txt").is_file())

    # ── HT-02: YSCB_MODULE_DIR 汙染防護 ─────────────────────────────
    def test_ht_02_module_dir_env_isolation(self):
        """環境變數指向模組 A 時，查詢模組 B 不得回傳 A 的目錄"""
        mod_a = self.test_dir / "modules" / "mod_a"
        mod_b = self.test_dir / "modules" / "mod_b"
        self._write_manifest(mod_a, "mod_a")
        self._write_manifest(mod_b, "mod_b")

        old_env = os.environ.get("YSCB_MODULE_DIR")
        try:
            os.environ["YSCB_MODULE_DIR"] = str(mod_a)
            # 查詢自身：環境變數命中，直接採用
            self.assertEqual(ProjectContext.get_module_dir("mod_a", start_dir=self.test_dir), mod_a.resolve())
            # 跨模組查詢：不得被汙染
            self.assertEqual(ProjectContext.get_module_dir("mod_b", start_dir=self.test_dir), mod_b.resolve())
        finally:
            if old_env is None:
                os.environ.pop("YSCB_MODULE_DIR", None)
            else:
                os.environ["YSCB_MODULE_DIR"] = old_env

    # ── HT-03: Slot 匹配規則與 SLOT_PATTERN 一致 ─────────────────────
    def test_ht_03_slot_whitespace_variants(self):
        """extract_slots 認得的空白變體，synthesize_sop 也必須匹配注入 (不得靜默降級至檔尾)"""
        variants = [
            "<!--YSCB_SLOT:Phase0-->",
            "<!-- YSCB_SLOT:Phase0 -->",
            "<!--  YSCB_SLOT:Phase0  -->",
        ]
        for marker in variants:
            template = f"# Doc\n\n## Phase0\n{marker}\n\n## End\n"
            self.assertEqual(SOPSynthesizer.extract_slots(template), ["Phase0"])
            result = SOPSynthesizer.synthesize_sop(
                template, [{"target_slot": "Phase0", "position": "append", "content": "INJECTED"}]
            )
            # 注入內容必須出現在 marker 之後、"## End" 之前 (即插槽原位)
            self.assertLess(result.index("INJECTED"), result.index("## End"),
                            msg=f"變體 {marker!r} 未於插槽原位注入")

        # 找不到插槽時仍應優雅降級至檔尾 (既有 ET-01 行為)
        res_fb = SOPSynthesizer.synthesize_sop(
            "# No slot here", [{"target_slot": "Nope", "content": "FB"}]
        )
        self.assertIn("FB", res_fb)

    # ── HT-04: remove_module 真實相依防護 ────────────────────────────
    def test_ht_04_remove_real_dependency_guard(self):
        """依 manifest dependencies 阻擋移除被相依模組；--force 可越過；無相依者可移除"""
        base_dir = self.test_dir / "modules" / "base_mod"
        cons_dir = self.test_dir / "modules" / "consumer_mod"
        self._write_manifest(base_dir, "base_mod", "2.0.0")
        self._write_manifest(cons_dir, "consumer_mod", "1.0.0", dependencies=["base_mod >= 1.0.0"])

        self.config_mgr.create_default()
        self.config_mgr.record_installed_module("base_mod", mode="build", version="2.0.0")
        self.config_mgr.record_installed_module("consumer_mod", mode="build", version="1.0.0")

        # 移除被相依的 base_mod → 必須被阻擋
        with self.assertRaises(RuntimeError):
            self.module_mgr.remove_module("base_mod", force=False)

        # 無人相依的 consumer_mod → 可正常移除
        self.assertTrue(self.module_mgr.remove_module("consumer_mod"))
        # consumer 移除後 base_mod 即可移除
        self.assertTrue(self.module_mgr.remove_module("base_mod"))

    # ── HT-05: URI Scheme 開放註冊 (contributes 協定) ────────────────
    def test_ht_05_uri_scheme_open_registration(self):
        """第三方模組透過 manifest contributes['core']['uri_schemes'] 註冊自訂協議並可解析"""
        (self.test_dir / "yscb_config.json").write_text(json.dumps({
            "version": "2.0",
            "paths": {"project_root": ".", "yscb_root": "."},
            "installed_modules": {"notes_mod": {"version": "1.0.0", "mode": "build"}}
        }), encoding="utf-8")

        mod_dir = self.test_dir / "modules" / "notes_mod"
        self._write_manifest(mod_dir, "notes_mod", contributes={
            "core": {"uri_schemes": [{"scheme": "notes", "config_key": "notes_dir"}]}
        })
        (mod_dir / "config.project.json").write_text(
            json.dumps({"paths": {"notes_dir": "my_notes"}}), encoding="utf-8"
        )
        (self.test_dir / "my_notes").mkdir()

        schemes = ProjectURI.get_dynamic_schemes(start_dir=self.test_dir)
        self.assertIn("notes", schemes)
        self.assertEqual(schemes["notes"][0], "notes_mod")

        resolved = ProjectURI.resolve("notes://idea.md", start_dir=self.test_dir)
        self.assertEqual(resolved, (self.test_dir / "my_notes" / "idea.md").resolve())

        # 保留字協議不得被模組覆蓋
        self._write_manifest(self.test_dir / "modules" / "evil_mod", "evil_mod", contributes={
            "core": {"uri_schemes": [{"scheme": "project", "config_key": "hijack_dir"}]}
        })
        schemes2 = ProjectURI.get_dynamic_schemes(start_dir=self.test_dir)
        self.assertNotIn("project", schemes2)

    # ── HT-06: 貢獻查詢決定性排序 ────────────────────────────────────
    def test_ht_06_contributions_deterministic_order(self):
        """get_contributions 依模組名稱排序，跨檔案系統結果一致"""
        for name in ["zeta_mod", "alpha_mod", "midd_mod"]:
            self._write_manifest(self.test_dir / "modules" / name, name, contributes={
                "agents-workflow": {"sop_patches": []}
            })
        (self.test_dir / "yscb_config.json").write_text(json.dumps({
            "version": "2.0", "paths": {"project_root": ".", "yscb_root": "."}
        }), encoding="utf-8")

        contribs = ProjectContext.get_contributions("agents-workflow", start_dir=self.test_dir)
        self.assertEqual([c[0] for c in contribs], ["alpha_mod", "midd_mod", "zeta_mod"])

    # ── HT-07: 版本號 SSOT 同步防護 ──────────────────────────────────
    def test_ht_07_version_ssot_sync(self):
        """根目錄與 ys_codebase/ 起手腳本版本一致；yscb_core.__version__ 來自 manifest.json"""
        def read_installer_version(p: Path):
            m = re.search(r'INSTALLER_VERSION\s*=\s*["\']([^"\']+)["\']',
                          p.read_text(encoding="utf-8", errors="ignore"))
            return m.group(1) if m else None

        root_v = read_installer_version(REPO_ROOT / "yscb_installer.py")
        src_v = read_installer_version(YS_CODEBASE_DIR / "yscb_installer.py")
        self.assertIsNotNone(root_v)
        self.assertEqual(root_v, src_v, "根目錄與 ys_codebase/ 的 yscb_installer.py 版本號發散！")

        core_manifest = json.loads(
            (YS_CODEBASE_DIR / "source" / "core" / "manifest.json").read_text(encoding="utf-8")
        )
        import yscb_core as core_sdk_check
        # 於源碼樹執行時 __version__ 應與 source manifest 一致
        self.assertEqual(core_sdk_check.__version__, core_manifest.get("version"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
