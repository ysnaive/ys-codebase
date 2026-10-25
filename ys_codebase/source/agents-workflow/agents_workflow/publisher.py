"""
Release Publisher for agents-workflow.
Executes the 4-Step Atomic Release Transaction:
0. Pre-check source fingerprint for early short-circuit (Zero-I/O optimization)
1. Prune legacy published files recorded in cache://agents-workflow/project_release_manifest.json (auto-migrated from legacy storage://)
2. Pre-compute deployment topology & rendered content for all active release_targets
3. Persist latest published file manifest and fingerprint to cache:// (host-local, git-ignored)
4. Materialize physical files (with in-memory diff check) & perform AGENTS.md soft-merge.
100% Python Standard Library, Zero Third-Party Dependency.
"""

import os
import sys
import re
import json
import hashlib
import datetime
from typing import Dict, List, Any, Optional, Set, Tuple

# 自動探測掛載 core 模組
_this_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root_aw = os.path.dirname(_this_dir)
_mods_root_aw = os.path.dirname(_pkg_root_aw)
for _cand in [
    os.path.join(_mods_root_aw, "core"),
    os.path.join(os.path.dirname(_mods_root_aw), "source", "core"),
    os.path.join(os.path.dirname(_mods_root_aw), ".modules", "core")
]:
    if os.path.isdir(_cand) and _cand not in sys.path:
        sys.path.insert(0, _cand)

try:
    from core import uri
except ImportError:
    uri = None

from agents_workflow.compiler import ArtifactCompiler


PROJECT_MANIFEST_CACHE_URI = "cache://agents-workflow/project_release_manifest.json"
LOCAL_MANIFEST_CACHE_URI = "cache://agents-workflow/release_manifest.json"
# 舊版 Project 軌清單位置（位於 Git 追蹤之 storage://），僅供遷移讀取與清理，嚴禁再寫入
LEGACY_PROJECT_MANIFEST_STORAGE_URI = "storage://agents-workflow/release_manifest.json"
SHA1_CACHE_URI = "cache://agents-workflow/source_sha1_cache.json"
AGENTS_MD_BEGIN = "<!-- YSCB_AGENTS_BEGIN -->"
AGENTS_MD_END = "<!-- YSCB_AGENTS_END -->"
GITIGNORE_BEGIN_MARKER = "# === YSCB AGENTS_WORKFLOW IGNORE BEGIN ==="
GITIGNORE_END_MARKER = "# === YSCB AGENTS_WORKFLOW IGNORE END ==="


class ReleasePublisher:
    """發布引擎：負責 Target 拓撲映射、Header 巨集插值、雙軌 Diff 檢測與 4 步原子交易。"""

    def __init__(self, compiler: Optional[ArtifactCompiler] = None, host_dir: Optional[str] = None):
        self.compiler = compiler or ArtifactCompiler(host_dir=host_dir)
        self.host_dir = host_dir
        self._sha1_cache_dirty = False
        self._sha1_cache: Dict[str, List[Any]] = self._load_sha1_cache()
        self._sources_digest_cache: Optional[bytes] = None

    def _load_sha1_cache(self) -> Dict[str, List[Any]]:
        """載入持久化之來源檔案 SHA-1 快取 (cache://)。"""
        if uri and uri.exists(SHA1_CACHE_URI):
            try:
                data = uri.read_json(SHA1_CACHE_URI)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {}

    def _save_sha1_cache(self) -> None:
        """若有異動，將來源檔案 SHA-1 快取持久化至 cache://。"""
        if getattr(self, "_sha1_cache_dirty", False) and uri:
            try:
                uri.write_json(SHA1_CACHE_URI, self._sha1_cache)
                self._sha1_cache_dirty = False
            except Exception:
                pass

    def _to_project_uri(self, abs_path: str, proj_root: str) -> str:
        """將本機實體絕對路徑轉換為 project:// 語意協議路徑。"""
        if not abs_path:
            return ""
        if "://" in abs_path:
            return abs_path
        norm_abs = os.path.normpath(os.path.abspath(abs_path))
        norm_proj = os.path.normpath(os.path.abspath(proj_root))
        try:
            rel = os.path.relpath(norm_abs, norm_proj)
            if not rel.startswith("..") and not rel.startswith(os.sep):
                return f"project://{rel.replace(os.sep, '/')}"
        except Exception:
            pass
        return norm_abs

    def _resolve_project_uri(self, uri_str: str, proj_root: str) -> str:
        """將 project:// 協議路徑或歷史絕對路徑轉換為本機實體絕對路徑。"""
        if not uri_str:
            return ""
        if uri_str.startswith("project://"):
            rel_part = uri_str[len("project://"):].lstrip("/\\")
            return os.path.normpath(os.path.join(proj_root, rel_part.replace("/", os.sep)))
        return os.path.normpath(uri_str)

    def _load_manifest(self, manifest_uri: str) -> Dict[str, Any]:
        """安全讀取指定語意 URI 之 Manifest。"""
        if uri and uri.exists(manifest_uri):
            try:
                data = uri.read_json(manifest_uri)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        if uri and manifest_uri == PROJECT_MANIFEST_CACHE_URI and uri.exists(LEGACY_PROJECT_MANIFEST_STORAGE_URI):
            try:
                data = uri.read_json(LEGACY_PROJECT_MANIFEST_STORAGE_URI)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {}

    def _save_manifest(self, manifest_uri: str, data: Dict[str, Any]) -> bool:
        """安全寫入 Manifest 至指定語意 URI，使用純 LF 換行。"""
        if uri:
            try:
                uri.write_json(manifest_uri, data)
                return True
            except Exception:
                pass
        return False

    def _migrate_legacy_storage_manifest(self) -> None:
        """舊版 storage:// 物化清單平滑遷移至 cache:// 並物理清理舊檔與空目錄。"""
        if not uri:
            return
        try:
            if uri.exists(LEGACY_PROJECT_MANIFEST_STORAGE_URI):
                if not uri.exists(PROJECT_MANIFEST_CACHE_URI):
                    legacy_data = uri.read_json(LEGACY_PROJECT_MANIFEST_STORAGE_URI)
                    if isinstance(legacy_data, dict):
                        uri.write_json(PROJECT_MANIFEST_CACHE_URI, legacy_data)
                uri.remove(LEGACY_PROJECT_MANIFEST_STORAGE_URI)
                legacy_dir = "storage://agents-workflow"
                if uri.exists(legacy_dir):
                    abs_dir = uri.resolve(legacy_dir, interactive=False)
                    if os.path.isdir(abs_dir) and not os.listdir(abs_dir):
                        os.rmdir(abs_dir)
        except Exception:
            pass

    def _get_project_config(self) -> Dict[str, Any]:
        """讀取 config://agents-workflow 設定檔（自動計算 Local 與 Project 之 release_targets 聯集）。"""
        cfg = {
            "paths": {},
            "release_targets": ["antigravity"],
            "enable_agents_md": True,
            "enable_project_changelog": True
        }
        try:
            from core import config
            data = config.get_all("agents-workflow")
            if data:
                cfg = dict(data)
            
            # 計算 release_targets 聯集 (Local | Project)
            proj_targets = config.get_raw("agents-workflow", "release_targets", local=False, default=["antigravity"]) or ["antigravity"]
            local_targets = config.get_raw("agents-workflow", "release_targets", local=True, default=[]) or []
            union_targets = list(dict.fromkeys(list(proj_targets) + list(local_targets)))
            if union_targets:
                cfg["release_targets"] = union_targets
        except Exception:
            pass

        return cfg

    def _get_source_file_sha1(self, path_or_uri: str) -> str:
        """計算來源檔案或目錄 SHA-1，支援 (mtime_ns, size) Stat-First 快取加速、目錄遞迴雜湊與文字 CRLF->LF 正規化。"""
        real_p = self.compiler._resolve_source_path(path_or_uri)
        if real_p and os.path.isdir(real_p):
            hasher = hashlib.sha1()
            for root, _, files in sorted(os.walk(real_p)):
                for f in sorted(files):
                    fp = os.path.join(root, f)
                    rel = os.path.relpath(fp, real_p).replace("\\", "/")
                    hasher.update(rel.encode("utf-8"))
                    try:
                        with open(fp, "rb") as rf:
                            raw = rf.read()
                        try:
                            # 嘗試以 UTF-8 解碼並正規化 CRLF -> LF
                            text = raw.decode("utf-8")
                            norm_bytes = text.replace("\r\n", "\n").encode("utf-8")
                            hasher.update(norm_bytes)
                        except UnicodeDecodeError:
                            # 二進位檔案安全降級：維持原始 bytes
                            hasher.update(raw)
                    except Exception:
                        pass
            return hasher.hexdigest()

        if real_p and os.path.isfile(real_p):
            try:
                st = os.stat(real_p)
                cached = self._sha1_cache.get(real_p)
                if cached and len(cached) >= 3 and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
                    return str(cached[2])
                content = self.compiler._read_file_content(path_or_uri)
                norm_content = content.replace("\r\n", "\n")
                sha1_val = hashlib.sha1(norm_content.encode("utf-8")).hexdigest()
                self._sha1_cache[real_p] = [st.st_mtime_ns, st.st_size, sha1_val]
                self._sha1_cache_dirty = True
                return sha1_val
            except Exception:
                pass
        content = self.compiler._read_file_content(path_or_uri)
        norm_content = content.replace("\r\n", "\n")
        return hashlib.sha1(norm_content.encode("utf-8")).hexdigest()

    def _get_sources_digest(self) -> bytes:
        """計算來源端所有靜態資源與宣告（manifest, contributes, export, insert）之綜合 SHA-256 摘要。"""
        if self._sources_digest_cache is not None:
            return self._sources_digest_cache

        hasher = hashlib.sha256()

        # 1. 模組自身 manifest.json 與編譯/發布引擎代碼 (compiler.py, publisher.py)
        try:
            for code_rel in (
                "manifest.json",
                os.path.join("agents_workflow", "compiler.py"),
                os.path.join("agents_workflow", "publisher.py"),
            ):
                code_p = os.path.join(self.compiler.module_root, code_rel)
                if os.path.isfile(code_p):
                    sha1_val = self._get_source_file_sha1(code_p)
                    hasher.update(f"{code_rel}:".encode("utf-8"))
                    hasher.update(sha1_val.encode("utf-8"))
        except Exception:
            pass

        # 2. Contributes 資料 (export, insert, token, release_target)
        contrib = self.compiler.get_contributes_data()
        hasher.update(json.dumps(contrib, sort_keys=True).encode("utf-8"))

        # 3. 實體來源檔案特徵 (路徑與 SHA-1 快取)
        for exp in contrib.get("export", []):
            src = exp.get("source", "")
            if src:
                sha1_val = self._get_source_file_sha1(src)
                hasher.update(src.encode("utf-8"))
                hasher.update(sha1_val.encode("utf-8"))

        for ins in contrib.get("insert", []):
            src = ins.get("source") or (ins.get("value") if ins.get("type") == "uri" else "")
            if src:
                sha1_val = self._get_source_file_sha1(str(src))
                hasher.update(str(src).encode("utf-8"))
                hasher.update(sha1_val.encode("utf-8"))

        self._sources_digest_cache = hasher.digest()
        return self._sources_digest_cache

    def compute_source_fingerprint(self, target_names: Optional[List[str]] = None) -> str:
        """
        計算來源端綜合特徵指紋 (SHA-256 Hex Digest)。
        涵蓋 assets 資源、contributes 宣告、專案組態與 target 投影規則。
        """
        hasher = hashlib.sha256()

        # 1. 專案組態
        cfg = self._get_project_config()
        if target_names is not None:
            cfg = dict(cfg)
            cfg["release_targets"] = sorted(list(target_names))
        hasher.update(json.dumps(cfg, sort_keys=True).encode("utf-8"))

        # 2. 來源資產綜合摘要 (具備 stat 快照與單次調用快取)
        hasher.update(self._get_sources_digest())

        return hasher.hexdigest()

    def get_registered_targets(self) -> List[Dict[str, Any]]:
        """自 contributes 獲取所有已宣告之 release_target。"""
        return self.compiler.get_release_targets()

    def build_deployment_map(
        self,
        target_cfg: Dict[str, Any],
        resolved_items: List[Dict[str, Any]]
    ) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
        """
        為單一 Release Target 建立發布拓撲映射表。
        Returns:
            (deployment_map, target_items)
            - deployment_map: {source_uri: target_abs_path}
            - target_items: 帶目標實體路徑與投影設定的項目清單
        """
        projections = target_cfg.get("projections", {})
        deployment_map: Dict[str, str] = {}
        target_items: List[Dict[str, Any]] = []

        proj_root = os.getcwd()
        if uri:
            try:
                proj_root = uri.resolve("project://", interactive=False)
            except Exception:
                pass

        for it in resolved_items:
            exp = it.get("export", {})
            exp_type = exp.get("type", "template")  # workflow, template, standard, skill
            source_uri = exp.get("source", "")
            base_name = it.get("base_name", "")
            sub_folder = it.get("sub_folder", "templates")
            is_skill = it.get("is_skill", False) or exp_type in ("skill", "skills")
            skill_name = it.get("skill_name", exp.get("name", os.path.splitext(base_name)[0]))
            rel_path = it.get("rel_path", base_name)

            # 檢查 projections 是否有對應配置
            proj_rule = projections.get(exp_type, {})
            if not proj_rule:
                # 嘗試單複數容錯 (standards vs standard, skills vs skill)
                for k, v in projections.items():
                    if k.rstrip("s") == exp_type.rstrip("s"):
                        proj_rule = v
                        break

            if not proj_rule:
                # 預設 fallback 輸出到 .agents/<sub_folder>/ 或 .agents/skills/{export.name}
                if is_skill:
                    target_dir_uri = f"project://.agents/skills/{skill_name}"
                else:
                    target_dir_uri = f"project://.agents/{sub_folder}"
                ext = ".md"
                header_tpl = None
            else:
                raw_target_dir = proj_rule.get("target_dir", f"project://.agents/{sub_folder}")
                ext = proj_rule.get("extension", ".md")
                header_tpl = proj_rule.get("header")

                # 支援 target_dir 巨集插值 ({export.name}, {export.basename}, {target.name})
                target_dir_uri = (
                    raw_target_dir
                    .replace("{export.name}", skill_name)
                    .replace("{export.basename}", os.path.splitext(base_name)[0])
                    .replace("{target.name}", target_cfg.get("name", ""))
                )

            # 解析目標絕對目錄
            target_dir_abs = ""
            if uri and "://" in target_dir_uri:
                try:
                    target_dir_abs = uri.resolve(target_dir_uri, interactive=False)
                except Exception:
                    target_dir_abs = ""

            if not target_dir_abs:
                if target_dir_uri.startswith("project://"):
                    rel_part = target_dir_uri.replace("project://", "", 1).lstrip("/\\")
                    target_dir_abs = os.path.join(proj_root, rel_part.replace("/", os.sep))
                elif os.path.isabs(target_dir_uri):
                    target_dir_abs = target_dir_uri
                else:
                    target_dir_abs = os.path.join(proj_root, target_dir_uri.replace("/", os.sep))

            # 計算目標檔案名稱與路徑
            file_main_name = os.path.splitext(base_name)[0]
            if is_skill:
                # 保留 Skill 內部相對路徑 (如 SKILL.md 或 references/sub.md)
                target_abs_path = os.path.normpath(os.path.join(target_dir_abs, rel_path.replace("/", os.sep)))
            else:
                target_filename = f"{file_main_name}{ext}"
                target_abs_path = os.path.normpath(os.path.join(target_dir_abs, target_filename))

            # 註冊完整來源 URI 與標準別名
            if is_skill:
                if source_uri:
                    deployment_map[f"{source_uri.rstrip('/')}/{rel_path}"] = target_abs_path
                    if rel_path in ("SKILL.md", base_name):
                        deployment_map[source_uri] = target_abs_path
                deployment_map[f"skills/{skill_name}/{rel_path}"] = target_abs_path
                if rel_path in ("SKILL.md", base_name):
                    deployment_map[f"skills/{skill_name}"] = target_abs_path
                    deployment_map[skill_name] = target_abs_path
            else:
                if source_uri:
                    deployment_map[source_uri] = target_abs_path
                deployment_map[f"{sub_folder}/{base_name}"] = target_abs_path
                deployment_map[base_name] = target_abs_path

            target_items.append({
                "source_uri": source_uri,
                "base_name": base_name,
                "rel_path": rel_path,
                "sub_folder": sub_folder,
                "target_abs_path": target_abs_path,
                "header_tpl": header_tpl if (not is_skill or rel_path in ("SKILL.md", base_name)) else None,
                "content": it.get("content", ""),
                "export": exp,
                "is_skill": is_skill
            })

        return deployment_map, target_items

    def render_header(self, export_item: Dict[str, Any], header_template: Optional[Any], target_name: str) -> str:
        """
        將 release_target 宣告之 header 模板進行動態巨集替換。
        """
        if not header_template:
            return ""

        if isinstance(header_template, list):
            raw_template = "\n".join(str(x) for x in header_template)
        elif isinstance(header_template, str):
            raw_template = header_template
        else:
            return ""

        source_p = export_item.get("source", "")
        base_name = os.path.basename(source_p.replace("\\", "/"))
        main_name = os.path.splitext(base_name)[0]

        macros = {
            "export.description": export_item.get("description", ""),
            "export.name": export_item.get("name", main_name),
            "export.type": export_item.get("type", "template"),
            "export.source": source_p,
            "export.filename": base_name,
            "export.basename": main_name,
            "target.name": target_name
        }

        # 替換 {key}
        res = raw_template
        for k, v in macros.items():
            res = res.replace(f"{{{k}}}", str(v))

        # 安全清理殘留未匹配的 {export.*} 或 {target.*}
        res = re.sub(r"\{(?:export|target)\.[A-Za-z0-9_]+\}", "", res)
        return res.strip() + "\n\n" if res.strip() else ""

    def _soft_merge_agents_text(self, existing_text: str, dev_standards_content: str) -> str:
        """
        純文字軟合併演算法 (Pure String Soft-Merge).
        將新標準內容單向注入至 YSCB 標記區塊，保留外部自定義章節。
        專案特化技能擴充請透過 config/agents-workflow/contribute.json 宣告式注入。
        """
        injected_section = f"{AGENTS_MD_BEGIN}\n{dev_standards_content.strip()}\n{AGENTS_MD_END}"
        if not existing_text:
            return (
                f"{injected_section}\n\n"
                f"## 4. 專案特化工程規範 (Project Specific Standards)\n"
                f"*(專案特化工程規範填寫於此，不受中央標準庫覆蓋)*\n"
            )

        pattern = re.compile(
            re.escape(AGENTS_MD_BEGIN) + r".*?" + re.escape(AGENTS_MD_END),
            re.DOTALL
        )

        if pattern.search(existing_text):
            return pattern.sub(lambda _: injected_section, existing_text)
        else:
            return injected_section + "\n\n" + existing_text

    def _soft_unmerge_agents_text(self, existing_text: str) -> str:
        """
        純文字軟剝離演算法 (Pure String Soft-Unmerge).
        精準移除 YSCB 託管區塊與空自訂樣板，保留使用者自定義內容。
        """
        if not existing_text:
            return ""

        # 1. 剝離 <!-- YSCB_AGENTS_BEGIN --> ... <!-- YSCB_AGENTS_END -->
        pattern = re.compile(
            re.escape(AGENTS_MD_BEGIN) + r".*?" + re.escape(AGENTS_MD_END),
            re.DOTALL
        )
        cleaned = pattern.sub("", existing_text).strip()

        # 2. 剝離空樣板「## 4. 專案特化工程規範...」
        empty_boilerplate = (
            r"##\s*4\.\s*專案特化工程規範\s*\(Project\s*Specific\s*Standards\)\s*"
            r"\*\(專案特化工程規範填寫於此，不受中央標準庫覆蓋\)\*"
        )
        without_boilerplate = re.sub(empty_boilerplate, "", cleaned, flags=re.DOTALL).strip()
        if not without_boilerplate:
            return ""

        return cleaned

    def _soft_merge_agents_md(self, dev_standards_content: str, proj_root_or_file: str, force: bool = False) -> Tuple[bool, bool]:
        """
        執行 AGENTS.md 軟合併注入，保留自定義章節。
        Returns:
            (success: bool, written: bool)
        """
        if os.path.isdir(proj_root_or_file) or not proj_root_or_file.endswith(".md"):
            target_file = os.path.join(proj_root_or_file, "AGENTS.md")
        else:
            target_file = proj_root_or_file

        existing = ""
        if os.path.isfile(target_file):
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    existing = f.read()
            except Exception:
                existing = ""

        new_content = self._soft_merge_agents_text(existing, dev_standards_content)

        if not force and os.path.isfile(target_file) and new_content == existing:
            return True, False

        try:
            os.makedirs(os.path.dirname(target_file), exist_ok=True)
            with open(target_file, "w", encoding="utf-8", newline="\n") as f:
                f.write(new_content)
            return True, True
        except Exception as e:
            print(f"[publisher:warning] Failed soft-merge {target_file}: {e}", file=sys.stderr)
            return False, False

    def release_all(self, force: bool = False, interactive: bool = False) -> Dict[str, Any]:
        """
        執行 4 步原子發布交易流水線（支援 Project/Local 雙軌獨立 Manifest 與 Diff 優化）：
        Stage 0: 來源指紋提前短路檢查 (雙軌獨立比對)
        Stage 1: 內容佔位符展開 (compile_stage1)
        Stage 2: 提前解算所有已啟用 Target 之檔案實體路徑與渲染內容 (分流 Project 與 Local 集合)
        Stage 3: 原子寫入 cache:// (Project 軌 project_release_manifest.json, project:// 格式；Local 軌 release_manifest.json, 絕對路徑格式)
        Stage 4: 落地端檔案內容比對與增量輸出（含 agents_md 軟合併與純 LF 寫入）
        """
        cfg = self._get_project_config()
        active_target_names: List[str] = cfg.get("release_targets", ["antigravity"])

        # 取得專案根目錄
        proj_root = os.getcwd()
        if uri:
            try:
                proj_root = uri.resolve("project://", interactive=False)
            except Exception:
                pass

        # 分流 Project Targets (Tier 2) 與 Local Targets (Tier 1)
        try:
            from agents_workflow.targets import ReleaseTargetManager
            classified = ReleaseTargetManager.get_classified_targets()
            proj_tier_targets = set(classified.get("project", []))
        except Exception:
            proj_tier_targets = {"antigravity"}

        proj_targets = [t for t in active_target_names if t in proj_tier_targets]
        local_targets = [t for t in active_target_names if t not in proj_tier_targets]

        # -------------------------------------------------------------
        # Stage 0: 來源指紋提前短路檢查 (Source Fingerprint Gate & Stat-First)
        # -------------------------------------------------------------
        old_proj_manifest = self._load_manifest(PROJECT_MANIFEST_CACHE_URI)
        old_local_manifest = self._load_manifest(LOCAL_MANIFEST_CACHE_URI)

        # 檢查歷史 Manifest 遷移 (EC-05 及跨平台 Working Tree 隔離遷移)
        if uri:
            self._migrate_legacy_storage_manifest()
            try:
                legacy_wrong_uri = "storage://core/agents-workflow/release_manifest.json"
                if uri.exists(legacy_wrong_uri):
                    if not uri.exists(PROJECT_MANIFEST_CACHE_URI):
                        legacy_data = uri.read_json(legacy_wrong_uri)
                        uri.write_json(PROJECT_MANIFEST_CACHE_URI, legacy_data)
                    uri.remove(legacy_wrong_uri)
                    legacy_dir_uri = "storage://core/agents-workflow"
                    if uri.exists(legacy_dir_uri):
                        uri.rmtree(legacy_dir_uri)
            except Exception:
                pass

        all_registered_targets = {t["name"]: t for t in self.get_registered_targets() if "name" in t}

        # Stage 0.1: 極速來源指紋計算 (Stat-First 快取初篩與 sources_digest 共享)
        proj_fingerprint = self.compute_source_fingerprint(proj_targets) if proj_targets else ""
        local_fingerprint = self.compute_source_fingerprint(local_targets) if local_targets else ""
        combined_fingerprint = self.compute_source_fingerprint(active_target_names)

        # 評估是否可全短路 (Stage 0 Short-Circuit)
        can_short_circuit = True
        total_short_circuited_files: List[str] = []

        if force:
            can_short_circuit = False
        else:
            if proj_targets:
                if old_proj_manifest.get("fingerprint") != proj_fingerprint:
                    can_short_circuit = False
                else:
                    for p_item in old_proj_manifest.get("published_files", []):
                        p_abs = self._resolve_project_uri(p_item, proj_root)
                        if not os.path.isfile(p_abs):
                            can_short_circuit = False
                            break
                        total_short_circuited_files.append(p_abs)
            if local_targets:
                if old_local_manifest.get("fingerprint") != local_fingerprint:
                    can_short_circuit = False
                else:
                    for l_item in old_local_manifest.get("published_files", []):
                        l_abs = self._resolve_project_uri(l_item, proj_root)
                        if not os.path.isfile(l_abs):
                            can_short_circuit = False
                            break
                        total_short_circuited_files.append(l_abs)

            for t_name in active_target_names:
                t_cfg = all_registered_targets.get(t_name, {})
                a_md = t_cfg.get("agents_md")
                if a_md and str(a_md).strip():
                    a_abs = self._resolve_project_uri(str(a_md).strip(), proj_root)
                    if not os.path.isfile(a_abs):
                        can_short_circuit = False
                        break

            if not (proj_targets or local_targets):
                can_short_circuit = False

        if can_short_circuit and total_short_circuited_files:
            self._save_sha1_cache()
            return {
                "success": True,
                "short_circuited": True,
                "published_count": len(total_short_circuited_files),
                "written_count": 0,
                "skipped_count": len(total_short_circuited_files),
                "removed_count": 0,
                "active_targets": active_target_names,
                "orphan_targets": [],
                "fingerprint": combined_fingerprint
            }

        # 執行 Stage 1: 內容佔位符展開與快取
        stage1_res = self.compiler.compile_stage1()
        if not stage1_res.get("success", False):
            return {
                "success": False,
                "short_circuited": False,
                "error": "Stage 1 content compilation failed",
                "details": stage1_res.get("errors", []),
                "published_count": 0,
                "written_count": 0,
                "skipped_count": 0,
                "removed_count": 0,
                "active_targets": active_target_names,
                "orphan_targets": []
            }

        resolved_items = stage1_res.get("resolved_items", [])

        # --- 步驟 2 (提前解算): 為所有已啟用 Target 解算檔案清單與內容 ---
        precomputed_project_files: Dict[str, str] = {}
        precomputed_local_files: Dict[str, str] = {}
        precomputed_all_files: Dict[str, str] = {}
        orphan_targets: List[str] = []
        agents_standards_content = ""

        for t_name in active_target_names:
            if t_name not in all_registered_targets:
                orphan_targets.append(t_name)
                print(f"[publisher:warning] Release target '{t_name}' not found in registered contributes.", file=sys.stderr)
                continue

            target_cfg = all_registered_targets[t_name]
            dep_map, target_items = self.build_deployment_map(target_cfg, resolved_items)
            is_proj_target = t_name in proj_tier_targets

            for t_item in target_items:
                dst_abs = t_item["target_abs_path"]
                stage1_text = t_item["content"]
                exp_item = t_item["export"]

                if "AgentsStandards" in t_item["base_name"]:
                    agents_standards_content = stage1_text

                stage2_text = self.compiler.resolve_stage2_uri(stage1_text, dst_abs, dep_map)
                header_text = self.render_header(exp_item, t_item["header_tpl"], t_name)
                final_text = header_text + stage2_text

                precomputed_all_files[dst_abs] = final_text
                if is_proj_target:
                    precomputed_project_files[dst_abs] = final_text
                else:
                    precomputed_local_files[dst_abs] = final_text

            # 處理該 Target 的 agents_md 規範投影 (若有設定且非空)
            agents_md_uri = target_cfg.get("agents_md")
            if agents_md_uri and str(agents_md_uri).strip():
                if not agents_standards_content:
                    for r_item in resolved_items:
                        if "AgentsStandards" in r_item.get("base_name", ""):
                            agents_standards_content = r_item.get("content", "")
                            break

                if agents_standards_content:
                    target_agents_abs = self._resolve_project_uri(str(agents_md_uri).strip(), proj_root)
                    rendered_agents_content = self.compiler.resolve_stage2_uri(
                        agents_standards_content, target_agents_abs, dep_map
                    )
                    existing_agents_text = ""
                    if os.path.isfile(target_agents_abs):
                        try:
                            with open(target_agents_abs, "r", encoding="utf-8") as f:
                                existing_agents_text = f.read()
                        except Exception:
                            existing_agents_text = ""

                    final_agents_text = self._soft_merge_agents_text(existing_agents_text, rendered_agents_content)
                    precomputed_all_files[target_agents_abs] = final_agents_text
                    if is_proj_target:
                        precomputed_project_files[target_agents_abs] = final_agents_text
                    else:
                        precomputed_local_files[target_agents_abs] = final_agents_text

        # --- 步驟 1 (過往清理): 雙軌舊檔案比對 ---
        old_proj_files: Set[str] = {
            self._resolve_project_uri(f, proj_root) for f in old_proj_manifest.get("published_files", [])
        }
        old_local_files: Set[str] = {
            self._resolve_project_uri(f, proj_root) for f in old_local_manifest.get("published_files", [])
        }

        # 算出各軌不再需要的檔案（必須同時不在當前全體產出中）
        current_published_set = set(precomputed_all_files.keys())
        stale_proj_files = old_proj_files - current_published_set
        stale_local_files = old_local_files - current_published_set
        files_to_remove = stale_proj_files | stale_local_files

        for f_rem in files_to_remove:
            if os.path.isfile(f_rem):
                try:
                    base_name = os.path.basename(f_rem)
                    is_agents_md = base_name in ("AGENTS.md", "CLAUDE.md") or any(
                        t_cfg.get("agents_md") and f_rem.endswith(os.path.normpath(str(t_cfg.get("agents_md")).replace("project://", "").replace("/", os.sep)))
                        for t_cfg in all_registered_targets.values()
                    )
                    if is_agents_md:
                        with open(f_rem, "r", encoding="utf-8") as f:
                            curr_text = f.read()
                        remaining = self._soft_unmerge_agents_text(curr_text)
                        if remaining:
                            with open(f_rem, "w", encoding="utf-8", newline="\n") as f:
                                f.write(remaining + "\n")
                            continue
                    os.remove(f_rem)
                    parent_d = os.path.dirname(f_rem)
                    while parent_d and parent_d != proj_root and os.path.isdir(parent_d) and not os.listdir(parent_d):
                        os.rmdir(parent_d)
                        parent_d = os.path.dirname(parent_d)
                except Exception as e:
                    print(f"[publisher:warning] Failed removing stale file {f_rem}: {e}", file=sys.stderr)

        # 自動清理已除役之 legacy workflows 目錄 (.agents/workflows 與 .claude/commands)
        for legacy_rel in [".agents/workflows", ".claude/commands"]:
            legacy_dir = os.path.normpath(os.path.join(proj_root, legacy_rel))
            if os.path.isdir(legacy_dir):
                try:
                    for root, dirs, files in os.walk(legacy_dir, topdown=False):
                        for f in files:
                            fp = os.path.join(root, f)
                            if fp not in current_published_set:
                                try:
                                    os.remove(fp)
                                    files_to_remove.add(fp)
                                except Exception:
                                    pass
                        for d in dirs:
                            dp = os.path.join(root, d)
                            try:
                                os.rmdir(dp)
                            except Exception:
                                pass
                    if os.path.isdir(legacy_dir) and not os.listdir(legacy_dir):
                        os.rmdir(legacy_dir)
                except Exception:
                    pass

        # --- 步驟 3 (更新持久清單): 分流寫入 cache:// 之 Project 軌與 Local 軌清單 ---
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. Project 軌 (寫入 cache://，使用 project:// 協議路徑；不入 Git 追蹤區)
        if proj_targets or old_proj_manifest:
            proj_uris = [self._to_project_uri(f, proj_root) for f in precomputed_project_files.keys()]
            sorted_proj_uris = sorted(proj_uris)
            if (
                old_proj_manifest
                and old_proj_manifest.get("fingerprint") == proj_fingerprint
                and old_proj_manifest.get("active_targets") == proj_targets
                and old_proj_manifest.get("published_files") == sorted_proj_uris
                and "updated_at" in old_proj_manifest
            ):
                updated_at_proj = old_proj_manifest["updated_at"]
            else:
                updated_at_proj = now_str

            new_proj_manifest = {
                "fingerprint": proj_fingerprint,
                "active_targets": proj_targets,
                "published_files": sorted_proj_uris,
                "combined_fingerprint": combined_fingerprint,
                "updated_at": updated_at_proj
            }
            if new_proj_manifest != old_proj_manifest:
                self._save_manifest(PROJECT_MANIFEST_CACHE_URI, new_proj_manifest)

        # 2. Local 軌 (寫入 cache://，使用實體絕對路徑)
        if local_targets or old_local_manifest:
            sorted_local_files = sorted(list(precomputed_local_files.keys()))
            if (
                old_local_manifest
                and old_local_manifest.get("fingerprint") == local_fingerprint
                and old_local_manifest.get("active_targets") == local_targets
                and old_local_manifest.get("published_files") == sorted_local_files
                and "updated_at" in old_local_manifest
            ):
                updated_at_local = old_local_manifest["updated_at"]
            else:
                updated_at_local = now_str

            new_local_manifest = {
                "fingerprint": local_fingerprint,
                "active_targets": local_targets,
                "published_files": sorted_local_files,
                "combined_fingerprint": combined_fingerprint,
                "updated_at": updated_at_local
            }
            if new_local_manifest != old_local_manifest:
                self._save_manifest(LOCAL_MANIFEST_CACHE_URI, new_local_manifest)

        # --- 步驟 4 (建立目錄並落地輸出檔案，含 Diff 檢測與純 LF 換行) ---
        written_count = 0
        skipped_count = 0
        for dst_abs, content in precomputed_all_files.items():
            if not force and os.path.isfile(dst_abs):
                try:
                    with open(dst_abs, "r", encoding="utf-8") as f:
                        existing_content = f.read()
                    if existing_content == content:
                        skipped_count += 1
                        continue
                except Exception:
                    pass

            os.makedirs(os.path.dirname(dst_abs), exist_ok=True)
            with open(dst_abs, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            written_count += 1

        # 執行 project://.gitignore 軟合併同步 (傳入本次發布之精確檔案清單)
        gitignore_res = self.sync_gitignore(
            active_targets=active_target_names,
            published_files=current_published_set,
            proj_root=proj_root
        )

        self._save_sha1_cache()
        return {
            "success": True,
            "short_circuited": False,
            "published_count": len(current_published_set),
            "written_count": written_count,
            "skipped_count": skipped_count,
            "active_targets": active_target_names,
            "orphan_targets": orphan_targets,
            "removed_count": len(files_to_remove),
            "gitignore_synced": gitignore_res.get("updated", False) or gitignore_res.get("created", False),
            "fingerprint": combined_fingerprint
        }

    def sync_gitignore(
        self,
        active_targets: Optional[List[str]] = None,
        published_files: Optional[Any] = None,
        proj_root: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        非破壞性軟合併 project://.gitignore 中的 YSCB 管理區塊。
        精準針對 agents-workflow 發布之個別檔案與 .yscb 私有目錄進行忽略，
        避免整目錄忽略 (.agents/) 干擾使用者存放於該目錄下的自訂 skills/rules/檔案。
        """
        if proj_root is None:
            proj_root = os.getcwd()
            if uri:
                try:
                    proj_root = uri.resolve("project://", interactive=False)
                except Exception:
                    pass

        if active_targets is None:
            cfg = self._get_project_config()
            active_targets = list(cfg.get("release_targets", []))

        all_registered = {t["name"]: t for t in self.get_registered_targets() if "name" in t}
        ignore_patterns: Set[str] = set()

        # 1. 取得發布檔案清單 (優先使用傳入的 published_files，否則讀取 storage manifest)
        file_list = []
        if published_files is not None:
            file_list = list(published_files)
        else:
            if uri and uri.exists(PROJECT_MANIFEST_CACHE_URI):
                try:
                    m_data = uri.read_json(PROJECT_MANIFEST_CACHE_URI)
                    file_list = m_data.get("published_files", [])
                except Exception:
                    pass

        # 2. 針對個別發布檔案轉換為相對路徑 (100% 精確檔案路徑，不濃縮任何目錄，略過常駐規則檔)
        for f_abs in file_list:
            if isinstance(f_abs, str) and f_abs.startswith("project://"):
                f_abs = self._resolve_project_uri(f_abs, proj_root)
            if os.path.basename(f_abs) in ("AGENTS.md", "CLAUDE.md"):
                continue
            try:
                rel = os.path.relpath(f_abs, proj_root).replace("\\", "/")
                if not rel.startswith("../") and not rel.startswith("/"):
                    ignore_patterns.add(f"/{rel}")
            except Exception:
                pass

        # 3. 補充各 Target 宣告之自訂 ignore patterns (若有的話)
        for t_name in active_targets:
            t_cfg = all_registered.get(t_name, {})
            for pat in t_cfg.get("ignore_patterns", []):
                p_clean = pat.strip()
                if not p_clean.startswith("/") and not p_clean.startswith("*"):
                    p_clean = f"/{p_clean}"
                ignore_patterns.add(p_clean)

        # 排序 patterns
        sorted_patterns = sorted(list(ignore_patterns))

        block_lines = [
            GITIGNORE_BEGIN_MARKER,
            "# Auto-managed by agents-workflow. Do not edit this block manually.",
        ]
        block_lines.extend(sorted_patterns)
        block_lines.append(GITIGNORE_END_MARKER)
        new_block_text = "\n".join(block_lines)

        gitignore_path = os.path.join(proj_root, ".gitignore")
        existing_content = ""
        has_existing = os.path.isfile(gitignore_path)

        if has_existing:
            try:
                with open(gitignore_path, "r", encoding="utf-8") as f:
                    existing_content = f.read()
            except Exception:
                existing_content = ""

        # 檢測現有標記
        pattern = re.compile(
            rf"{re.escape(GITIGNORE_BEGIN_MARKER)}[\s\S]*?{re.escape(GITIGNORE_END_MARKER)}",
            re.MULTILINE,
        )

        if pattern.search(existing_content):
            merged_content = pattern.sub(new_block_text, existing_content)
        else:
            if existing_content and not existing_content.endswith("\n"):
                merged_content = existing_content + "\n\n" + new_block_text + "\n"
            elif existing_content:
                merged_content = existing_content + "\n" + new_block_text + "\n"
            else:
                merged_content = new_block_text + "\n"

        # 若無變更則跳過
        if has_existing and existing_content == merged_content:
            return {"updated": False, "created": False, "patterns": sorted_patterns}

        try:
            with open(gitignore_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(merged_content)
            return {"updated": True, "created": not has_existing, "patterns": sorted_patterns}
        except Exception as e:
            print(f"[publisher:warning] Failed to sync .gitignore: {e}", file=sys.stderr)
            return {"updated": False, "created": False, "error": str(e), "patterns": sorted_patterns}


def ensure_jit_release(force: bool = False) -> bool:
    """
    JIT 變更感知自愈管線：
    自動檢驗來源資產新鮮度。若來源特徵指紋變更，調用 ReleasePublisher.release_all() 自動同步物化至 Target 目錄。
    返回 True 表示有實質物化寫入，False 表示 Clean 或短路跳過。
    """
    try:
        pub = ReleasePublisher()
        res = pub.release_all(force=force)
        return bool(res.get("success", False) and not res.get("short_circuited", False))
    except Exception:
        return False



