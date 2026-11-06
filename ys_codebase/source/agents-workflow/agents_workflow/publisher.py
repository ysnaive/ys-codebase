"""
Release Publisher for agents-workflow.
Executes the 4-Step Atomic Release Transaction:
0. Pre-check source fingerprint for early short-circuit (Zero-I/O optimization)
1. Prune legacy published files recorded in storage.local://agents-workflow/project_release_manifest.json
2. Pre-compute deployment topology & rendered content for all active release_targets
3. Persist latest published file manifest and fingerprint to storage.local:// (host-local, git-ignored)
4. Materialize physical files (with in-memory diff check) & perform AGENTS.md soft-merge.
100% Python Standard Library, Zero Third-Party Dependency.
"""

import os
import sys
import re
import json
import hashlib
import datetime
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Set, Tuple, Union

try:
    from core import uri
    from core import vfs
except ImportError:
    uri = None
    vfs = None

from agents_workflow.compiler import ArtifactCompiler


PROJECT_MANIFEST_CACHE_URI = "storage.local://agents-workflow/project_release_manifest.json"
LOCAL_MANIFEST_CACHE_URI = "storage.local://agents-workflow/release_manifest.json"
SHA1_CACHE_URI = "storage.local://agents-workflow/source_sha1_cache.json"
AGENTS_MD_BEGIN = "<!-- YSCB_AGENTS_BEGIN -->"
AGENTS_MD_END = "<!-- YSCB_AGENTS_END -->"

_AGENTS_MANAGED_BLOCK_RE = re.compile(
    re.escape(AGENTS_MD_BEGIN) + r".*?" + re.escape(AGENTS_MD_END),
    re.DOTALL,
)
_EMPTY_AGENTS_BOILERPLATE_RE = re.compile(
    r"##\s*4\.\s*專案特化工程規範\s*\(Project\s*Specific\s*Standards\)\s*"
    r"\*\(專案特化工程規範填寫於此，不受中央標準庫覆蓋\)\*",
    re.DOTALL,
)
_HEADER_UNRESOLVED_MACRO_RE = re.compile(r"\{(?:export|target)\.[A-Za-z0-9_]+\}")


@dataclass
class _ReleaseTransactionContext:
    """封裝單次發布交易流水線之跨階段上下文狀態。"""
    force: bool
    proj_root: str
    active_target_names: List[str]
    proj_tier_targets: Set[str]
    proj_targets: List[str]
    local_targets: List[str]
    old_proj_manifest: Dict[str, Any]
    old_local_manifest: Dict[str, Any]
    all_registered_targets: Dict[str, Dict[str, Any]]
    proj_fingerprint: str
    local_fingerprint: str
    combined_fingerprint: str = ""


class ReleasePublisher:
    """發布引擎：負責 Target 拓撲映射、Header 巨集插值、雙軌 Diff 檢測與 4 步原子交易。"""

    def __init__(self, compiler: Optional[ArtifactCompiler] = None, host_dir: Optional[str] = None):
        self.host_dir = host_dir or os.getcwd()
        self.compiler = compiler or ArtifactCompiler(host_dir=self.host_dir)
        self._sha1_cache_dirty = False
        self._sha1_cache: Dict[str, List[Any]] = self._load_sha1_cache()
        self._sources_digest_cache: Optional[bytes] = None

    @staticmethod
    def _write_text_atomic(file_path: str, content: str) -> None:
        """透過 core.vfs 執行純 LF 原子文字寫入。"""
        if vfs is not None:
            vfs.write_text(file_path, content, encoding="utf-8", atomic=True)
            return
        parent_dir = os.path.dirname(os.path.abspath(file_path))
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(file_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

    def _load_sha1_cache(self) -> Dict[str, List[Any]]:
        """載入持久化之來源檔案 SHA-1 快取 (storage.local://)。"""
        if vfs and vfs.exists(SHA1_CACHE_URI):
            try:
                data = vfs.read_json(SHA1_CACHE_URI)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {}

    def _save_sha1_cache(self) -> None:
        """若有異動，將來源檔案 SHA-1 快取持久化至 storage.local://。"""
        if getattr(self, "_sha1_cache_dirty", False) and vfs:
            try:
                vfs.write_json(SHA1_CACHE_URI, self._sha1_cache)
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
        if vfs and vfs.exists(manifest_uri):
            try:
                data = vfs.read_json(manifest_uri)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {}

    def _save_manifest(self, manifest_uri: str, data: Dict[str, Any]) -> bool:
        """安全寫入 Manifest 至指定語意 URI，使用純 LF 換行。"""
        if vfs:
            try:
                vfs.write_json(manifest_uri, data)
                return True
            except Exception:
                pass
        return False

    def _get_project_config(self) -> Dict[str, Any]:
        """讀取 config://agents-workflow 設定檔（自動計算 Local 與 Project 之 release_targets 聯集）。"""
        cfg: Dict[str, Any] = {
            "paths": {},
            "release_targets": ["antigravity"],
            "enable_agents_md": True,
            "enable_project_changelog": True,
        }
        try:
            from core import config
            data = config.get_all("agents-workflow")
            if isinstance(data, dict) and data:
                cfg = dict(data)
        except Exception:
            pass

        try:
            from agents_workflow.targets import ReleaseTargetManager
            classified = ReleaseTargetManager.get_classified_targets()
            cfg["release_targets"] = list(classified.get("union", []))
        except Exception:
            try:
                from core import config
                raw_proj = config.get_raw("agents-workflow", "release_targets", local=False, default=None)
                proj_targets = (
                    ["antigravity"]
                    if raw_proj is None
                    else ([str(x).strip() for x in raw_proj if str(x).strip()] if isinstance(raw_proj, list) else ["antigravity"])
                )
                raw_local = config.get_raw("agents-workflow", "release_targets", local=True, default=None)
                local_targets = (
                    [str(x).strip() for x in raw_local if str(x).strip()]
                    if isinstance(raw_local, list)
                    else []
                )
                cfg["release_targets"] = list(dict.fromkeys(proj_targets + local_targets))
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
                        st = os.stat(fp)
                        cached = self._sha1_cache.get(fp)
                        if cached and len(cached) >= 3 and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
                            file_sha1 = str(cached[2])
                        else:
                            with open(fp, "rb") as rf:
                                raw = rf.read()
                            try:
                                text = raw.decode("utf-8")
                                norm_bytes = text.replace("\r\n", "\n").encode("utf-8")
                                file_sha1 = hashlib.sha1(norm_bytes).hexdigest()
                            except UnicodeDecodeError:
                                file_sha1 = hashlib.sha1(raw).hexdigest()
                            self._sha1_cache[fp] = [st.st_mtime_ns, st.st_size, file_sha1]
                            self._sha1_cache_dirty = True
                        hasher.update(file_sha1.encode("utf-8"))
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

        # 4. 模組自身 locales/*.json 專有名詞字典特徵
        locales_dir = os.path.join(self.compiler.module_root, "locales")
        if os.path.isdir(locales_dir):
            sha1_loc = self._get_source_file_sha1(locales_dir)
            hasher.update(b"locales:")
            hasher.update(sha1_loc.encode("utf-8"))

        self._sources_digest_cache = hasher.digest()
        return self._sources_digest_cache

    def compute_source_fingerprint(self, target_names: Optional[List[str]] = None) -> str:
        """
        計算來源端綜合特徵指紋 (SHA-256 Hex Digest)。
        涵蓋 assets 資源、contributes 宣告、專案組態、有效語系鏈與 target 投影規則。
        """
        hasher = hashlib.sha256()

        cfg = self._get_project_config()
        if target_names is not None:
            cfg = dict(cfg)
            cfg["release_targets"] = sorted(list(target_names))
        hasher.update(json.dumps(cfg, sort_keys=True).encode("utf-8"))

        try:
            from core import locale as core_locale
            active_chain = core_locale.get_active_chain()
            hasher.update(json.dumps(active_chain, sort_keys=True).encode("utf-8"))
        except Exception:
            pass

        try:
            from core import config
            core_cfg = config.get_all("core") or {}
            hasher.update(json.dumps(core_cfg, sort_keys=True, default=str).encode("utf-8"))
        except Exception:
            pass

        hasher.update(self._get_sources_digest())

        return hasher.hexdigest()

    def build_deployment_map(
        self,
        target_cfg: Dict[str, Any],
        resolved_items: List[Dict[str, Any]],
        proj_root: Optional[str] = None,
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

        explicit_proj_root = proj_root is not None
        if proj_root is None:
            proj_root = self.host_dir
            if uri:
                try:
                    proj_root = uri.resolve("project://", interactive=False)
                except Exception:
                    pass

        for it in resolved_items:
            exp = it.get("export", {})
            raw_type = str(exp.get("type", "template")).strip()
            exp_type = "skill" if raw_type.lower() in ("workflow", "workflows") else raw_type
            source_uri = exp.get("source", "")
            base_name = it.get("base_name", "")
            sub_folder = it.get("sub_folder", "templates")
            if sub_folder in ("workflow", "workflows"):
                sub_folder = "skills"
            is_skill = it.get("is_skill", False) or exp_type in ("skill", "skills")
            skill_name = it.get("skill_name", exp.get("name", os.path.splitext(base_name)[0]))
            rel_path = it.get("rel_path", base_name)

            proj_rule = projections.get(exp_type, {})
            if not proj_rule:
                for k, v in projections.items():
                    if k.rstrip("s") == exp_type.rstrip("s"):
                        proj_rule = v
                        break
            if not proj_rule and is_skill:
                proj_rule = projections.get("workflow") or projections.get("workflows") or {}

            if not proj_rule:
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

                target_dir_uri = (
                    raw_target_dir
                    .replace("{export.name}", skill_name)
                    .replace("{export.basename}", os.path.splitext(base_name)[0])
                    .replace("{target.name}", target_cfg.get("name", ""))
                )

            target_dir_abs = ""
            if explicit_proj_root and target_dir_uri.startswith("project://"):
                rel_part = target_dir_uri.replace("project://", "", 1).lstrip("/\\")
                target_dir_abs = os.path.join(proj_root, rel_part.replace("/", os.sep))
            elif uri and "://" in target_dir_uri:
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

            file_main_name = os.path.splitext(base_name)[0]
            if is_skill:
                target_abs_path = os.path.normpath(os.path.join(target_dir_abs, rel_path.replace("/", os.sep)))
            else:
                target_filename = f"{file_main_name}{ext}"
                target_abs_path = os.path.normpath(os.path.join(target_dir_abs, target_filename))

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
        """將 release_target 宣告之 header 模板進行動態巨集替換。"""
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
            "export.description": self.compiler.resolve_export_description(export_item),
            "export.name": export_item.get("name", main_name),
            "export.type": export_item.get("type", "template"),
            "export.source": source_p,
            "export.filename": base_name,
            "export.basename": main_name,
            "target.name": target_name
        }

        res = raw_template
        for k, v in macros.items():
            res = res.replace(f"{{{k}}}", str(v))

        res = _HEADER_UNRESOLVED_MACRO_RE.sub("", res)
        return res.strip() + "\n\n" if res.strip() else ""

    def _soft_merge_agents_text(self, existing_text: str, dev_standards_content: str) -> str:
        """
        純文字軟合併演算法 (Pure String Soft-Merge).
        將新標準內容單向注入至 YSCB 標記區塊，保留外部自定義章節。
        """
        injected_section = f"{AGENTS_MD_BEGIN}\n{dev_standards_content.strip()}\n{AGENTS_MD_END}"
        if not existing_text:
            return (
                f"{injected_section}\n\n"
                f"## 4. 專案特化工程規範 (Project Specific Standards)\n"
                f"*(專案特化工程規範填寫於此，不受中央標準庫覆蓋)*\n"
            )

        if _AGENTS_MANAGED_BLOCK_RE.search(existing_text):
            return _AGENTS_MANAGED_BLOCK_RE.sub(lambda _: injected_section, existing_text)
        return injected_section + "\n\n" + existing_text

    def _soft_unmerge_agents_text(self, existing_text: str) -> str:
        """
        純文字軟剝離演算法 (Pure String Soft-Unmerge).
        精準移除 YSCB 託管區塊與空自訂樣板，保留使用者自定義內容。
        """
        if not existing_text:
            return ""

        cleaned = _AGENTS_MANAGED_BLOCK_RE.sub("", existing_text).strip()
        without_boilerplate = _EMPTY_AGENTS_BOILERPLATE_RE.sub("", cleaned).strip()
        if not without_boilerplate:
            return ""

        return cleaned

    def _verify_agent_rule_injections(
        self,
        active_target_names: List[str],
        all_registered_targets: Dict[str, Dict[str, Any]],
        proj_root: str,
    ) -> bool:
        """檢查所有啟用 Target 之 agents_md 與 agent_rules 落地檔案及受管標記完整性。"""
        for t_name in active_target_names:
            t_cfg = all_registered_targets.get(t_name, {})
            a_md = t_cfg.get("agents_md")
            if a_md and str(a_md).strip():
                a_abs = self._resolve_project_uri(str(a_md).strip(), proj_root)
                if not os.path.isfile(a_abs):
                    return False
                try:
                    with open(a_abs, "r", encoding="utf-8") as f:
                        a_text = f.read()
                    if AGENTS_MD_BEGIN not in a_text or AGENTS_MD_END not in a_text:
                        return False
                except Exception:
                    return False

            agent_rules = t_cfg.get("agent_rules")
            if isinstance(agent_rules, list):
                for rule_item in agent_rules:
                    if not isinstance(rule_item, dict):
                        continue
                    r_target = str(rule_item.get("target") or "").strip()
                    if not r_target:
                        continue
                    r_abs = self._resolve_project_uri(r_target, proj_root)
                    if not os.path.isfile(r_abs):
                        return False
                    r_mode = str(rule_item.get("mode") or "inject").strip().lower()
                    if r_mode == "inject":
                        r_marker = str(rule_item.get("marker") or "").strip()
                        b_mark = f"<!-- {r_marker}_BEGIN -->" if r_marker else AGENTS_MD_BEGIN
                        e_mark = f"<!-- {r_marker}_END -->" if r_marker else AGENTS_MD_END
                        try:
                            with open(r_abs, "r", encoding="utf-8") as f:
                                r_text = f.read()
                            if b_mark not in r_text or e_mark not in r_text:
                                return False
                        except Exception:
                            return False
        return True

    def _check_short_circuit(
        self,
        force: Union[bool, _ReleaseTransactionContext] = False,
        proj_targets: Optional[List[str]] = None,
        local_targets: Optional[List[str]] = None,
        active_target_names: Optional[List[str]] = None,
        old_proj_manifest: Optional[Dict[str, Any]] = None,
        old_local_manifest: Optional[Dict[str, Any]] = None,
        proj_fingerprint: str = "",
        local_fingerprint: str = "",
        all_registered_targets: Optional[Dict[str, Dict[str, Any]]] = None,
        proj_root: str = "",
        *,
        tx_ctx: Optional[_ReleaseTransactionContext] = None,
    ) -> Tuple[bool, List[str]]:
        """Stage 0: 檢查是否滿足來源指紋與落地檔案完整性，以執行零 I/O 短路（相容 _ReleaseTransactionContext 與舊版參數）。"""
        if isinstance(force, _ReleaseTransactionContext):
            tx_ctx = force

        if tx_ctx is not None:
            eff_force = tx_ctx.force
            eff_proj_targets = tx_ctx.proj_targets
            eff_local_targets = tx_ctx.local_targets
            eff_active_names = tx_ctx.active_target_names
            eff_old_proj = tx_ctx.old_proj_manifest
            eff_old_local = tx_ctx.old_local_manifest
            eff_proj_fp = tx_ctx.proj_fingerprint
            eff_local_fp = tx_ctx.local_fingerprint
            eff_registered = tx_ctx.all_registered_targets
            eff_proj_root = tx_ctx.proj_root
        else:
            eff_force = bool(force)
            eff_proj_targets = proj_targets or []
            eff_local_targets = local_targets or []
            eff_active_names = active_target_names or []
            eff_old_proj = old_proj_manifest or {}
            eff_old_local = old_local_manifest or {}
            eff_proj_fp = proj_fingerprint
            eff_local_fp = local_fingerprint
            eff_registered = all_registered_targets or {}
            eff_proj_root = proj_root

        if eff_force or not (eff_proj_targets or eff_local_targets):
            return False, []

        total_short_circuited_files: List[str] = []

        if eff_proj_targets:
            if eff_old_proj.get("fingerprint") != eff_proj_fp:
                return False, []
            for p_item in eff_old_proj.get("published_files", []):
                p_abs = self._resolve_project_uri(p_item, eff_proj_root)
                if not os.path.isfile(p_abs):
                    return False, []
                total_short_circuited_files.append(p_abs)

        if eff_local_targets:
            if eff_old_local.get("fingerprint") != eff_local_fp:
                return False, []
            for l_item in eff_old_local.get("published_files", []):
                l_abs = self._resolve_project_uri(l_item, eff_proj_root)
                if not os.path.isfile(l_abs):
                    return False, []
                total_short_circuited_files.append(l_abs)

        if not self._verify_agent_rule_injections(eff_active_names, eff_registered, eff_proj_root):
            return False, []

        return bool(total_short_circuited_files), total_short_circuited_files

    def _prepare_target_compilations(
        self,
        active_target_names: List[str],
        all_registered_targets: Dict[str, Dict[str, Any]],
        proj_tier_targets: Set[str],
        resolved_items: List[Dict[str, Any]],
        proj_root: str,
    ) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str], List[str], List[str]]:
        """Stage 2: 為所有啟用之 Target 預先解算檔案實體路徑與最終渲染內容（支援共用實體路徑並聯去重與衝突告警）。"""
        precomputed_project_files: Dict[str, str] = {}
        precomputed_local_files: Dict[str, str] = {}
        precomputed_all_files: Dict[str, str] = {}
        orphan_targets: List[str] = []
        shared_path_warnings: List[str] = []
        agents_standards_content = ""

        # Step 1: 收集各 Target 之拓撲映射與候選落地項目（以 dst_abs 聚合）
        item_groups: Dict[str, List[Dict[str, Any]]] = {}
        agents_md_groups: Dict[str, List[Dict[str, Any]]] = {}

        for t_name in active_target_names:
            if t_name not in all_registered_targets:
                orphan_targets.append(t_name)
                print(f"[publisher:warning] Release target '{t_name}' not found in registered contributes.", file=sys.stderr)
                continue

            target_cfg = all_registered_targets[t_name]
            dep_map, target_items = self.build_deployment_map(target_cfg, resolved_items, proj_root=proj_root)
            is_proj_target = t_name in proj_tier_targets

            for t_item in target_items:
                dst_abs = t_item["target_abs_path"]
                stage1_text = t_item["content"]
                if "AgentsStandards" in t_item["base_name"]:
                    agents_standards_content = stage1_text

                item_groups.setdefault(dst_abs, []).append({
                    "target_name": t_name,
                    "is_proj_target": is_proj_target,
                    "dep_map": dep_map,
                    "item": t_item,
                })

            agents_md_uri = target_cfg.get("agents_md")
            if agents_md_uri and str(agents_md_uri).strip():
                target_agents_abs = self._resolve_project_uri(str(agents_md_uri).strip(), proj_root)
                agents_md_groups.setdefault(target_agents_abs, []).append({
                    "target_name": t_name,
                    "is_proj_target": is_proj_target,
                    "dep_map": dep_map,
                })

        if not agents_standards_content:
            for r_item in resolved_items:
                if "AgentsStandards" in r_item.get("base_name", ""):
                    agents_standards_content = r_item.get("content", "")
                    break

        # Step 2: 偵測多 Target 共用實體路徑並按共享組合聚合輸出告警
        shared_combos: Dict[Tuple[str, ...], List[str]] = {}
        for dst_abs, entries in item_groups.items():
            t_names = list(dict.fromkeys(e["target_name"] for e in entries))
            if len(t_names) > 1:
                shared_combos.setdefault(tuple(t_names), []).append(self._to_project_uri(dst_abs, proj_root))
        for target_agents_abs, entries in agents_md_groups.items():
            t_names = list(dict.fromkeys(e["target_name"] for e in entries))
            if len(t_names) > 1:
                shared_combos.setdefault(tuple(t_names), []).append(self._to_project_uri(target_agents_abs, proj_root))

        for t_tuple, shared_uris in shared_combos.items():
            t_joined = ", ".join(t_tuple)
            sample_paths = ", ".join(shared_uris[:3])
            if len(shared_uris) > 3:
                sample_paths += f" (+{len(shared_uris) - 3} more)"
            warn_msg = (
                f"[publisher:warning] Multiple active release_targets ({t_joined}) share destination path(s) "
                f"({sample_paths}). Merged union content materialized; consider overriding 'release_targets' "
                f"in config.local://agents-workflow/config.local.json if you want a single-target workspace."
            )
            shared_path_warnings.append(warn_msg)
            print(warn_msg, file=sys.stderr)

        # Step 3: 渲染各投影項目（單一或多重 Target 共用時傳入完整 target_names 與 extra_deployment_maps）
        for dst_abs, entries in item_groups.items():
            primary = entries[0]
            t_item = primary["item"]
            stage1_text = t_item["content"]
            exp_item = t_item["export"]
            sharing_targets = list(dict.fromkeys(e["target_name"] for e in entries))
            extra_maps = [(e["target_name"], e["dep_map"]) for e in entries[1:]]

            stage2_text = self.compiler.resolve_stage2_uri(
                stage1_text,
                dst_abs,
                primary["dep_map"],
                target_name=sharing_targets if len(sharing_targets) > 1 else sharing_targets[0],
                extra_deployment_maps=extra_maps if extra_maps else None,
            )
            header_text = self.render_header(exp_item, t_item["header_tpl"], primary["target_name"])
            final_text = header_text + stage2_text

            precomputed_all_files[dst_abs] = final_text
            if any(e["is_proj_target"] for e in entries):
                precomputed_project_files[dst_abs] = final_text
            if any(not e["is_proj_target"] for e in entries):
                precomputed_local_files[dst_abs] = final_text

        # Step 4: 渲染各 agents_md 入口檔（支援多重 Target 路徑並聯與軟合併）
        if agents_standards_content:
            for target_agents_abs, entries in agents_md_groups.items():
                primary = entries[0]
                sharing_targets = list(dict.fromkeys(e["target_name"] for e in entries))
                extra_maps = [(e["target_name"], e["dep_map"]) for e in entries[1:]]

                rendered_agents_content = self.compiler.resolve_stage2_uri(
                    agents_standards_content,
                    target_agents_abs,
                    primary["dep_map"],
                    target_name=sharing_targets if len(sharing_targets) > 1 else sharing_targets[0],
                    extra_deployment_maps=extra_maps if extra_maps else None,
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
                if any(e["is_proj_target"] for e in entries):
                    precomputed_project_files[target_agents_abs] = final_agents_text
                if any(not e["is_proj_target"] for e in entries):
                    precomputed_local_files[target_agents_abs] = final_agents_text

        return (
            precomputed_project_files,
            precomputed_local_files,
            precomputed_all_files,
            orphan_targets,
            shared_path_warnings,
        )

    def _prune_orphaned_managed_files(
        self,
        old_proj_manifest: Dict[str, Any],
        old_local_manifest: Dict[str, Any],
        current_published_set: Set[str],
        all_registered_targets: Dict[str, Dict[str, Any]],
        proj_root: str,
    ) -> Set[str]:
        """Stage 1: 比對雙軌舊清單並安全清理不再受管之過期檔案（含 AGENTS.md 軟剝離保護）。"""
        old_proj_files: Set[str] = {
            self._resolve_project_uri(f, proj_root) for f in old_proj_manifest.get("published_files", [])
        }
        old_local_files: Set[str] = {
            self._resolve_project_uri(f, proj_root) for f in old_local_manifest.get("published_files", [])
        }

        files_to_remove = (old_proj_files | old_local_files) - current_published_set

        for f_rem in files_to_remove:
            if os.path.isfile(f_rem):
                try:
                    base_name = os.path.basename(f_rem)
                    is_agents_md = base_name in ("AGENTS.md", "CLAUDE.md") or any(
                        t_cfg.get("agents_md") and f_rem.endswith(
                            os.path.normpath(str(t_cfg.get("agents_md")).replace("project://", "").replace("/", os.sep))
                        )
                        for t_cfg in all_registered_targets.values()
                    )
                    if is_agents_md:
                        with open(f_rem, "r", encoding="utf-8") as f:
                            curr_text = f.read()
                        remaining = self._soft_unmerge_agents_text(curr_text)
                        if remaining:
                            self._write_text_atomic(f_rem, remaining + "\n")
                            continue
                    os.remove(f_rem)
                    parent_d = os.path.dirname(f_rem)
                    while parent_d and parent_d != proj_root and os.path.isdir(parent_d) and not os.listdir(parent_d):
                        os.rmdir(parent_d)
                        parent_d = os.path.dirname(parent_d)
                except Exception as e:
                    print(f"[publisher:warning] Failed removing stale file {f_rem}: {e}", file=sys.stderr)

        if proj_root:
            for legacy_rel in ((".agents", "workflows"), (".claude", "commands")):
                legacy_dir = os.path.normpath(os.path.join(proj_root, *legacy_rel))
                if os.path.isdir(legacy_dir):
                    has_active_managed = any(
                        os.path.normpath(p).startswith(legacy_dir + os.sep)
                        for p in current_published_set
                    )
                    if not has_active_managed:
                        try:
                            for root_d, _, fnames in os.walk(legacy_dir):
                                for fn in fnames:
                                    files_to_remove.add(os.path.join(root_d, fn))
                            if vfs:
                                vfs.robust_rmtree(legacy_dir)
                            else:
                                import shutil
                                shutil.rmtree(legacy_dir, ignore_errors=True)
                            parent_d = os.path.dirname(legacy_dir)
                            while parent_d and parent_d != proj_root and os.path.isdir(parent_d) and not os.listdir(parent_d):
                                os.rmdir(parent_d)
                                parent_d = os.path.dirname(parent_d)
                        except Exception as e:
                            print(f"[publisher:warning] Failed removing legacy workflow directory {legacy_dir}: {e}", file=sys.stderr)

        return files_to_remove

    def _save_deployment_manifests(
        self,
        proj_targets: Union[List[str], _ReleaseTransactionContext, None] = None,
        local_targets: Union[List[str], Dict[str, str], None] = None,
        precomputed_project_files: Optional[Dict[str, str]] = None,
        precomputed_local_files: Optional[Dict[str, str]] = None,
        old_proj_manifest: Optional[Dict[str, Any]] = None,
        old_local_manifest: Optional[Dict[str, Any]] = None,
        proj_fingerprint: str = "",
        local_fingerprint: str = "",
        combined_fingerprint: str = "",
        proj_root: str = "",
        *,
        tx_ctx: Optional[_ReleaseTransactionContext] = None,
    ) -> None:
        """Stage 3: 原子寫入 storage.local:// 之 Project 軌與 Local 軌持久化發布清單（相容 _ReleaseTransactionContext 與舊版參數）。"""
        if isinstance(proj_targets, _ReleaseTransactionContext):
            tx_ctx = proj_targets
            if isinstance(local_targets, dict):
                precomputed_local_files = precomputed_project_files if isinstance(precomputed_project_files, dict) else precomputed_local_files
                precomputed_project_files = local_targets

        if tx_ctx is not None:
            eff_proj_targets = tx_ctx.proj_targets
            eff_local_targets = tx_ctx.local_targets
            eff_old_proj = tx_ctx.old_proj_manifest
            eff_old_local = tx_ctx.old_local_manifest
            eff_proj_fp = tx_ctx.proj_fingerprint
            eff_local_fp = tx_ctx.local_fingerprint
            eff_combined_fp = tx_ctx.combined_fingerprint
            eff_proj_root = tx_ctx.proj_root
        else:
            eff_proj_targets = proj_targets if isinstance(proj_targets, list) else []
            eff_local_targets = local_targets if isinstance(local_targets, list) else []
            eff_old_proj = old_proj_manifest or {}
            eff_old_local = old_local_manifest or {}
            eff_proj_fp = proj_fingerprint
            eff_local_fp = local_fingerprint
            eff_combined_fp = combined_fingerprint
            eff_proj_root = proj_root

        eff_pre_proj = precomputed_project_files or {}
        eff_pre_local = precomputed_local_files or {}

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if eff_proj_targets or eff_old_proj:
            proj_uris = [self._to_project_uri(f, eff_proj_root) for f in eff_pre_proj.keys()]
            sorted_proj_uris = sorted(proj_uris)
            if (
                eff_old_proj
                and eff_old_proj.get("fingerprint") == eff_proj_fp
                and eff_old_proj.get("active_targets") == eff_proj_targets
                and eff_old_proj.get("published_files") == sorted_proj_uris
                and "updated_at" in eff_old_proj
            ):
                updated_at_proj = eff_old_proj["updated_at"]
            else:
                updated_at_proj = now_str

            new_proj_manifest = {
                "fingerprint": eff_proj_fp,
                "active_targets": eff_proj_targets,
                "published_files": sorted_proj_uris,
                "combined_fingerprint": eff_combined_fp,
                "updated_at": updated_at_proj,
            }
            if new_proj_manifest != eff_old_proj:
                self._save_manifest(PROJECT_MANIFEST_CACHE_URI, new_proj_manifest)

        if eff_local_targets or eff_old_local:
            sorted_local_files = sorted(list(eff_pre_local.keys()))
            if (
                eff_old_local
                and eff_old_local.get("fingerprint") == eff_local_fp
                and eff_old_local.get("active_targets") == eff_local_targets
                and eff_old_local.get("published_files") == sorted_local_files
                and "updated_at" in eff_old_local
            ):
                updated_at_local = eff_old_local["updated_at"]
            else:
                updated_at_local = now_str

            new_local_manifest = {
                "fingerprint": eff_local_fp,
                "active_targets": eff_local_targets,
                "published_files": sorted_local_files,
                "combined_fingerprint": eff_combined_fp,
                "updated_at": updated_at_local,
            }
            if new_local_manifest != eff_old_local:
                self._save_manifest(LOCAL_MANIFEST_CACHE_URI, new_local_manifest)

    def _materialize_target_files(
        self,
        precomputed_all_files: Dict[str, str],
        force: bool,
    ) -> Tuple[int, int]:
        """Stage 4: 落地端檔案內容比對與增量輸出（純 LF 換行）。"""
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

            self._write_text_atomic(dst_abs, content)
            written_count += 1
        return written_count, skipped_count

    def release_all(self, force: bool = False) -> Dict[str, Any]:
        """
        執行 4 步原子發布交易流水線（支援 Project/Local 雙軌獨立 Manifest 與 Diff 優化）：
        Stage 0: 來源指紋提前短路檢查 (_check_short_circuit)
        Stage 1: 內容佔位符展開 (compile_stage1)
        Stage 2: 預先解算所有已啟用 Target 之檔案實體路徑與渲染內容 (_prepare_target_compilations)
        Stage 3: 清理過期檔案 (_prune_orphaned_managed_files) 並原子寫入 storage.local:// 清單 (_save_deployment_manifests)
        Stage 4: 落地端檔案內容比對與增量輸出 (_materialize_target_files) 與 .gitignore 軟合併
        """
        cfg = self._get_project_config()
        active_target_names: List[str] = cfg.get("release_targets", ["antigravity"])

        proj_root = self.host_dir
        if uri:
            try:
                proj_root = uri.resolve("project://", interactive=False)
            except Exception:
                pass

        try:
            from agents_workflow.targets import ReleaseTargetManager
            classified = ReleaseTargetManager.get_classified_targets()
            proj_tier_targets = set(classified.get("project", []))
        except Exception:
            proj_tier_targets = {"antigravity"}

        proj_targets = [t for t in active_target_names if t in proj_tier_targets]
        local_targets = [t for t in active_target_names if t not in proj_tier_targets]

        old_proj_manifest = self._load_manifest(PROJECT_MANIFEST_CACHE_URI)
        old_local_manifest = self._load_manifest(LOCAL_MANIFEST_CACHE_URI)
        all_registered_targets = {t["name"]: t for t in self.compiler.get_release_targets() if "name" in t}

        proj_fingerprint = self.compute_source_fingerprint(proj_targets) if proj_targets else ""
        if not local_targets:
            local_fingerprint = ""
        elif local_targets == proj_targets:
            local_fingerprint = proj_fingerprint
        else:
            local_fingerprint = self.compute_source_fingerprint(local_targets)

        if active_target_names == proj_targets:
            combined_fingerprint = proj_fingerprint
        elif active_target_names == local_targets:
            combined_fingerprint = local_fingerprint
        else:
            combined_fingerprint = self.compute_source_fingerprint(active_target_names)

        tx_ctx = _ReleaseTransactionContext(
            force=force,
            proj_root=proj_root,
            active_target_names=active_target_names,
            proj_tier_targets=proj_tier_targets,
            proj_targets=proj_targets,
            local_targets=local_targets,
            old_proj_manifest=old_proj_manifest,
            old_local_manifest=old_local_manifest,
            all_registered_targets=all_registered_targets,
            proj_fingerprint=proj_fingerprint,
            local_fingerprint=local_fingerprint,
            combined_fingerprint=combined_fingerprint,
        )

        can_short_circuit, short_circuited_files = self._check_short_circuit(tx_ctx)
        if can_short_circuit:
            self.sync_gitignore(
                active_targets=active_target_names,
                published_files=short_circuited_files,
                proj_root=proj_root,
            )
            self._save_sha1_cache()
            return {
                "success": True,
                "short_circuited": True,
                "published_count": len(short_circuited_files),
                "written_count": 0,
                "skipped_count": len(short_circuited_files),
                "removed_count": 0,
                "active_targets": active_target_names,
                "orphan_targets": [],
                "shared_path_warnings": [],
                "fingerprint": combined_fingerprint,
            }

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
                "orphan_targets": [],
                "shared_path_warnings": [],
            }

        resolved_items = stage1_res.get("resolved_items", [])
        (
            precomputed_project_files,
            precomputed_local_files,
            precomputed_all_files,
            orphan_targets,
            shared_path_warnings,
        ) = self._prepare_target_compilations(
            active_target_names=active_target_names,
            all_registered_targets=all_registered_targets,
            proj_tier_targets=proj_tier_targets,
            resolved_items=resolved_items,
            proj_root=proj_root,
        )

        current_published_set = set(precomputed_all_files.keys())
        files_to_remove = self._prune_orphaned_managed_files(
            old_proj_manifest=old_proj_manifest,
            old_local_manifest=old_local_manifest,
            current_published_set=current_published_set,
            all_registered_targets=all_registered_targets,
            proj_root=proj_root,
        )

        self._save_deployment_manifests(
            tx_ctx,
            precomputed_project_files=precomputed_project_files,
            precomputed_local_files=precomputed_local_files,
        )

        written_count, skipped_count = self._materialize_target_files(precomputed_all_files, force=force)

        gitignore_res = self.sync_gitignore(
            active_targets=active_target_names,
            published_files=current_published_set,
            proj_root=proj_root,
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
            "shared_path_warnings": shared_path_warnings,
            "removed_count": len(files_to_remove),
            "gitignore_synced": gitignore_res.get("updated", False) or gitignore_res.get("created", False),
            "fingerprint": combined_fingerprint,
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
            proj_root = self.host_dir
            if uri:
                try:
                    proj_root = uri.resolve("project://", interactive=False)
                except Exception:
                    pass

        if active_targets is None:
            cfg = self._get_project_config()
            active_targets = list(cfg.get("release_targets", []))

        all_registered = {t["name"]: t for t in self.compiler.get_release_targets() if "name" in t}
        ignore_patterns: Set[str] = set()

        file_list: List[str] = []
        if published_files is not None:
            file_list = list(published_files)
        else:
            seen_files: Set[str] = set()
            for manifest_uri in (PROJECT_MANIFEST_CACHE_URI, LOCAL_MANIFEST_CACHE_URI):
                m_data = self._load_manifest(manifest_uri)
                for f_item in m_data.get("published_files", []):
                    if isinstance(f_item, str) and f_item not in seen_files:
                        seen_files.add(f_item)
                        file_list.append(f_item)

        agents_md_abs_set: Set[str] = set()
        for t_cfg in all_registered.values():
            a_uri = t_cfg.get("agents_md")
            if a_uri and str(a_uri).strip():
                agents_md_abs_set.add(os.path.normpath(self._resolve_project_uri(str(a_uri).strip(), proj_root)))

        for f_abs in file_list:
            if isinstance(f_abs, str) and f_abs.startswith("project://"):
                f_abs = self._resolve_project_uri(f_abs, proj_root)
            f_norm = os.path.normpath(f_abs)
            if os.path.basename(f_norm) in ("AGENTS.md", "CLAUDE.md") or f_norm in agents_md_abs_set:
                continue
            try:
                rel = os.path.relpath(f_abs, proj_root).replace("\\", "/")
                if not rel.startswith("../") and not rel.startswith("/"):
                    ignore_patterns.add(f"/{rel}")
            except Exception:
                pass

        for t_name in active_targets:
            t_cfg = all_registered.get(t_name, {})
            for pat in t_cfg.get("ignore_patterns", []):
                p_clean = pat.strip()
                if not p_clean.startswith("/") and not p_clean.startswith("*"):
                    p_clean = f"/{p_clean}"
                ignore_patterns.add(p_clean)

        sorted_patterns = sorted(list(ignore_patterns))

        try:
            from core import gitignore as gi_mod
            res = gi_mod.register_dynamic(
                "agents-workflow",
                sorted_patterns,
                sync_now=True,
                proj_root=proj_root,
            )
            res["patterns"] = sorted_patterns
            return res
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
