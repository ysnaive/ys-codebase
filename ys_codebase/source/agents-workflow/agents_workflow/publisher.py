"""
Release Publisher for agents-workflow.
Executes the 4-Step Atomic Release Transaction:
0. Pre-check source fingerprint for early short-circuit (Zero-I/O optimization)
1. Prune legacy published files recorded in storage://agents-workflow/release_manifest.json
2. Pre-compute deployment topology & rendered content for all active release_targets
3. Persist latest published file manifest and fingerprint to storage://
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
    os.path.join(os.path.dirname(_mods_root_aw), "modules", "core")
]:
    if os.path.isdir(_cand) and _cand not in sys.path:
        sys.path.insert(0, _cand)

try:
    from core import uri
except ImportError:
    uri = None

from agents_workflow.compiler import ArtifactCompiler


PROJECT_MANIFEST_STORAGE_URI = "storage://agents-workflow/release_manifest.json"
LOCAL_MANIFEST_CACHE_URI = "cache://agents-workflow/release_manifest.json"
MANIFEST_STORAGE_URI = PROJECT_MANIFEST_STORAGE_URI
AGENTS_MD_BEGIN = "<!-- YSCB_AGENTS_BEGIN -->"
AGENTS_MD_END = "<!-- YSCB_AGENTS_END -->"
GITIGNORE_BEGIN_MARKER = "# === YSCB AGENTS_WORKFLOW IGNORE BEGIN ==="
GITIGNORE_END_MARKER = "# === YSCB AGENTS_WORKFLOW IGNORE END ==="


class ReleasePublisher:
    """發布引擎：負責 Target 拓撲映射、Header 巨集插值、雙軌 Diff 檢測與 4 步原子交易。"""

    def __init__(self, compiler: Optional[ArtifactCompiler] = None, host_dir: Optional[str] = None):
        self.compiler = compiler or ArtifactCompiler(host_dir=host_dir)
        self.host_dir = host_dir

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

        # 2. 模組自身版本與 Contributes 資料 (export, insert, token, release_target)
        try:
            manifest_p = os.path.join(self.compiler.module_root, "manifest.json")
            if os.path.isfile(manifest_p):
                with open(manifest_p, "r", encoding="utf-8") as f:
                    hasher.update(f.read().encode("utf-8"))
        except Exception:
            pass

        contrib = self.compiler.get_contributes_data()
        hasher.update(json.dumps(contrib, sort_keys=True).encode("utf-8"))

        # 3. 實體來源檔案特徵 (路徑與 SHA-1)
        for exp in contrib.get("export", []):
            src = exp.get("source", "")
            if src:
                content = self.compiler._read_file_content(src)
                hasher.update(src.encode("utf-8"))
                hasher.update(hashlib.sha1(content.encode("utf-8")).hexdigest().encode("utf-8"))

        for ins in contrib.get("insert", []):
            src = ins.get("source") or (ins.get("value") if ins.get("type") == "uri" else "")
            if src:
                content = self.compiler._read_file_content(str(src))
                hasher.update(str(src).encode("utf-8"))
                hasher.update(hashlib.sha1(content.encode("utf-8")).hexdigest().encode("utf-8"))

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
            exp_type = exp.get("type", "template")  # workflow, template, standard
            source_uri = exp.get("source", "")
            base_name = it.get("base_name", "")
            sub_folder = it.get("sub_folder", "templates")

            # 檢查 projections 是否有對應配置
            proj_rule = projections.get(exp_type, {})
            if not proj_rule:
                # 嘗試單複數容錯 (standards vs standard)
                for k, v in projections.items():
                    if k.rstrip("s") == exp_type.rstrip("s"):
                        proj_rule = v
                        break

            if not proj_rule:
                # 預設 fallback 輸出到 .agents/<sub_folder>/
                target_dir_uri = f"project://.agents/{sub_folder}"
                ext = ".md"
                header_tpl = None
            else:
                target_dir_uri = proj_rule.get("target_dir", f"project://.agents/{sub_folder}")
                ext = proj_rule.get("extension", ".md")
                header_tpl = proj_rule.get("header")

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

            # 計算目標檔案名稱 (替換副檔名)
            file_main_name = os.path.splitext(base_name)[0]
            target_filename = f"{file_main_name}{ext}"
            target_abs_path = os.path.normpath(os.path.join(target_dir_abs, target_filename))

            # 註冊完整來源 URI 與標準短名
            if source_uri:
                deployment_map[source_uri] = target_abs_path
            deployment_map[f"{sub_folder}/{base_name}"] = target_abs_path
            deployment_map[base_name] = target_abs_path

            target_items.append({
                "source_uri": source_uri,
                "base_name": base_name,
                "sub_folder": sub_folder,
                "target_abs_path": target_abs_path,
                "header_tpl": header_tpl,
                "content": it.get("content", ""),
                "export": exp
            })

        return deployment_map, target_items

    def render_header(
        self,
        export_item: Dict[str, Any],
        header_tpl: Any,
        target_name: str
    ) -> str:
        """解析純文字/陣列 header 模板，動態替換 {export.*} 巨集。"""
        if not header_tpl:
            return ""

        if isinstance(header_tpl, list):
            raw_template = "\n".join(str(x) for x in header_tpl)
        else:
            raw_template = str(header_tpl)

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

    def _soft_merge_agents_md(self, dev_standards_content: str, proj_root: str, force: bool = False) -> Tuple[bool, bool]:
        """
        執行 AGENTS.md 軟合併注入，保留自定義章節。
        Returns:
            (success: bool, written: bool)
        """
        target_file = os.path.join(proj_root, "AGENTS.md")
        injected_section = f"{AGENTS_MD_BEGIN}\n{dev_standards_content.strip()}\n{AGENTS_MD_END}"

        if not os.path.isfile(target_file):
            # 若不存在，建立全新 AGENTS.md
            full_content = (
                f"{injected_section}\n\n"
                f"## 4. 專案特化工程規範 (Project Specific Standards)\n"
                f"*(專案特化工程規範填寫於此，不受中央標準庫覆蓋)*\n"
            )
            with open(target_file, "w", encoding="utf-8", newline="\n") as f:
                f.write(full_content)
            return True, True

        # 若已存在，讀取並執行正則軟合併
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                existing = f.read()

            pattern = re.compile(
                re.escape(AGENTS_MD_BEGIN) + r".*?" + re.escape(AGENTS_MD_END),
                re.DOTALL
            )

            if pattern.search(existing):
                new_content = pattern.sub(lambda _: injected_section, existing)
            else:
                # 若無標籤，追加在最前或特定標題後
                new_content = injected_section + "\n\n" + existing

            if not force and new_content == existing:
                return True, False

            with open(target_file, "w", encoding="utf-8", newline="\n") as f:
                f.write(new_content)
            return True, True
        except Exception as e:
            print(f"[publisher:warning] Failed soft-merge AGENTS.md: {e}", file=sys.stderr)
            return False, False

    def release_all(self, force: bool = False, interactive: bool = False) -> Dict[str, Any]:
        """
        執行 4 步原子發布交易流水線（支援 Project/Local 雙軌獨立 Manifest 與 Diff 優化）：
        Stage 0: 來源指紋提前短路檢查 (雙軌獨立比對)
        Stage 1: 內容佔位符展開 (compile_stage1)
        Stage 2: 提前解算所有已啟用 Target 之檔案實體路徑與渲染內容 (分流 Project 與 Local 集合)
        Stage 3: 原子寫入 storage:// (Project 軌, project:// 格式) 與 cache:// (Local 軌, 絕對路徑格式)
        Stage 4: 落地端檔案內容比對與增量輸出（含 AGENTS.md 軟合併與純 LF 寫入）
        """
        cfg = self._get_project_config()
        active_target_names: List[str] = cfg.get("release_targets", ["antigravity"])
        enable_agents_md: bool = cfg.get("enable_agents_md", True)

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
        # Stage 0: 來源指紋提前短路檢查 (Source Fingerprint Gate)
        # -------------------------------------------------------------
        proj_fingerprint = self.compute_source_fingerprint(proj_targets) if proj_targets else ""
        local_fingerprint = self.compute_source_fingerprint(local_targets) if local_targets else ""
        combined_fingerprint = self.compute_source_fingerprint(active_target_names)

        old_proj_manifest = self._load_manifest(PROJECT_MANIFEST_STORAGE_URI)
        old_local_manifest = self._load_manifest(LOCAL_MANIFEST_CACHE_URI)

        # 檢查歷史 Manifest 遷移 (EC-05)
        if uri:
            try:
                legacy_wrong_uri = "storage://core/agents-workflow/release_manifest.json"
                if uri.exists(legacy_wrong_uri):
                    if not uri.exists(PROJECT_MANIFEST_STORAGE_URI):
                        legacy_data = uri.read_json(legacy_wrong_uri)
                        uri.write_json(PROJECT_MANIFEST_STORAGE_URI, legacy_data)
                    uri.remove(legacy_wrong_uri)
                    legacy_dir_uri = "storage://core/agents-workflow"
                    if uri.exists(legacy_dir_uri):
                        uri.rmtree(legacy_dir_uri)
            except Exception:
                pass

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

            if enable_agents_md:
                agents_md_file = os.path.join(proj_root, "AGENTS.md")
                if not os.path.isfile(agents_md_file):
                    can_short_circuit = False

            if not (proj_targets or local_targets):
                can_short_circuit = False

        if can_short_circuit and total_short_circuited_files:
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
        all_registered_targets = {t["name"]: t for t in self.get_registered_targets() if "name" in t}

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
                    os.remove(f_rem)
                except Exception as e:
                    print(f"[publisher:warning] Failed removing stale file {f_rem}: {e}", file=sys.stderr)

        # --- 步驟 3 (更新持久清單): 分流寫入 storage:// 與 cache:// ---
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. Project 軌 (寫入 storage://，使用 project:// 協議路徑)
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
                "updated_at": updated_at_proj
            }
            if new_proj_manifest != old_proj_manifest:
                self._save_manifest(PROJECT_MANIFEST_STORAGE_URI, new_proj_manifest)

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

        # 執行 AGENTS.md 軟合併 (若啟用 enable_agents_md)
        if enable_agents_md:
            if not agents_standards_content:
                for r_item in resolved_items:
                    if "AgentsStandards" in r_item.get("base_name", ""):
                        agents_standards_content = r_item.get("content", "")
                        break

            if agents_standards_content:
                target_agents_abs = os.path.join(proj_root, "AGENTS.md")
                rendered_agents_content = agents_standards_content
                if active_target_names:
                    main_target_cfg = all_registered_targets.get(active_target_names[0], {})
                    if main_target_cfg:
                        dep_map_main, _ = self.build_deployment_map(main_target_cfg, resolved_items)
                        rendered_agents_content = self.compiler.resolve_stage2_uri(
                            agents_standards_content, target_agents_abs, dep_map_main
                        )
                else:
                    rendered_agents_content = self.compiler.resolve_stage2_uri(
                        agents_standards_content, target_agents_abs, {}
                    )

                self._soft_merge_agents_md(rendered_agents_content, proj_root, force=force)

        # 執行 project://.gitignore 軟合併同步 (傳入本次發布之精確檔案清單)
        gitignore_res = self.sync_gitignore(
            active_targets=active_target_names,
            published_files=current_published_set,
            proj_root=proj_root
        )

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
            if uri and uri.exists(MANIFEST_STORAGE_URI):
                try:
                    m_data = uri.read_json(MANIFEST_STORAGE_URI)
                    file_list = m_data.get("published_files", [])
                except Exception:
                    pass

        # 2. 針對個別發布檔案轉換為相對路徑 (100% 精確檔案路徑，不濃縮任何目錄)
        for f_abs in file_list:
            if isinstance(f_abs, str) and f_abs.startswith("project://"):
                f_abs = self._resolve_project_uri(f_abs, proj_root)
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


