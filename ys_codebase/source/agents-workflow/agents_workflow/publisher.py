"""
Release Publisher for agents-workflow.
Executes the 4-Step Atomic Release Transaction:
1. Prune legacy published files recorded in storage://agents-workflow/release_manifest.json
2. Pre-compute deployment topology & rendered content for all active release_targets
3. Persist latest published file manifest to storage://
4. Materialize physical files & perform AGENTS.md soft-merge.
100% Python Standard Library, Zero Third-Party Dependency.
"""

import os
import sys
import re
import json
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


MANIFEST_STORAGE_URI = "storage://agents-workflow/release_manifest.json"
AGENTS_MD_BEGIN = "<!-- YSCB_AGENTS_BEGIN -->"
AGENTS_MD_END = "<!-- YSCB_AGENTS_END -->"


class ReleasePublisher:
    """發布引擎：負責 Target 拓撲映射、Header 巨集插值與 4 步原子交易。"""

    def __init__(self, compiler: Optional[ArtifactCompiler] = None, host_dir: Optional[str] = None):
        self.compiler = compiler or ArtifactCompiler(host_dir=host_dir)
        self.host_dir = host_dir

    def _get_project_config(self) -> Dict[str, Any]:
        """讀取 config://agents-workflow/config.project.json 設定檔。"""
        cfg_uri = "config://agents-workflow/config.project.json"
        if uri and uri.exists(cfg_uri):
            try:
                data = uri.read_json(cfg_uri)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        
        # 本地 fallback 尋找
        proj_dir = os.getcwd()
        cand = os.path.join(proj_dir, "config", "agents-workflow", "config.project.json")
        if os.path.isfile(cand):
            try:
                with open(cand, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "paths": {},
            "release_targets": ["antigravity"],
            "enable_agents_md": True,
            "enable_project_changelog": True
        }

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

    def _soft_merge_agents_md(self, dev_standards_content: str, proj_root: str) -> bool:
        """執行 AGENTS.md 軟合併注入，保留自定義章節。"""
        target_file = os.path.join(proj_root, "AGENTS.md")
        injected_section = f"{AGENTS_MD_BEGIN}\n{dev_standards_content.strip()}\n{AGENTS_MD_END}"

        if not os.path.isfile(target_file):
            # 若不存在，建立全新 AGENTS.md
            full_content = (
                f"# Agent 專案行為準則與工作流指南 (AGENTS.md)\n\n"
                f"{injected_section}\n\n"
                f"## 4. 專案特化工程規範 (Project Specific Standards)\n"
                f"*(專案特化工程規範填寫於此，不受中央標準庫覆蓋)*\n"
            )
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(full_content)
            return True

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

            with open(target_file, "w", encoding="utf-8") as f:
                f.write(new_content)
            return True
        except Exception as e:
            print(f"[publisher:warning] Failed soft-merge AGENTS.md: {e}", file=sys.stderr)
            return False

    def release_all(self, interactive: bool = False) -> Dict[str, Any]:
        """
        執行 4 步原子發布交易流水線：
        1. 檢查 storage:// 舊發布清單並安全清理舊檔案
        2. 提前解算所有已啟用 Target 之檔案實體路徑與渲染內容
        3. 原子寫入 storage:// 最新發布清單
        4. 建立目標實體目錄並覆蓋寫入檔案（含 AGENTS.md 軟合併）
        """
        cfg = self._get_project_config()
        active_target_names: List[str] = cfg.get("release_targets", ["antigravity"])
        enable_agents_md: bool = cfg.get("enable_agents_md", True)

        # 執行 Stage 1: 內容佔位符展開與快取
        stage1_res = self.compiler.compile_stage1()
        if not stage1_res.get("success", False):
            return {
                "success": False,
                "error": "Stage 1 content compilation failed",
                "details": stage1_res.get("errors", [])
            }

        resolved_items = stage1_res.get("resolved_items", [])
        all_registered_targets = {t["name"]: t for t in self.get_registered_targets() if "name" in t}

        # --- 步驟 2 (提前解算): 為所有已啟用 Target 解算檔案清單與內容 ---
        precomputed_files: Dict[str, str] = {}  # {target_abs_path: final_content}
        orphan_targets: List[str] = []
        dev_standards_content = ""

        for t_name in active_target_names:
            if t_name not in all_registered_targets:
                orphan_targets.append(t_name)
                print(f"[publisher:warning] Release target '{t_name}' not found in registered contributes.", file=sys.stderr)
                continue

            target_cfg = all_registered_targets[t_name]
            dep_map, target_items = self.build_deployment_map(target_cfg, resolved_items)

            for t_item in target_items:
                dst_abs = t_item["target_abs_path"]
                stage1_text = t_item["content"]
                exp_item = t_item["export"]

                # 提取 DevelopmentStandards 供 AGENTS.md 軟合併使用
                if "DevelopmentStandards" in t_item["base_name"]:
                    dev_standards_content = stage1_text

                # Stage 2 URI 佔位符轉譯 (Tier 1 -> Tier 2 -> Tier 3)
                stage2_text = self.compiler.resolve_stage2_uri(stage1_text, dst_abs, dep_map)

                # 注入 Header 巨集模板
                header_text = self.render_header(exp_item, t_item["header_tpl"], t_name)
                final_text = header_text + stage2_text

                precomputed_files[dst_abs] = final_text

        # --- 步驟 1 (過往清理): 讀取 storage:// release_manifest.json ---
        old_published_files: Set[str] = set()
        if uri and uri.exists(MANIFEST_STORAGE_URI):
            try:
                manifest_data = uri.read_json(MANIFEST_STORAGE_URI)
                if isinstance(manifest_data, dict):
                    old_published_files = set(manifest_data.get("published_files", []))
            except Exception:
                pass

        # 算出本次不再保留的過往孤立檔案
        current_published_set = set(precomputed_files.keys())
        files_to_remove = old_published_files - current_published_set

        for f_rem in files_to_remove:
            if os.path.isfile(f_rem):
                try:
                    os.remove(f_rem)
                except Exception as e:
                    print(f"[publisher:warning] Failed removing stale file {f_rem}: {e}", file=sys.stderr)

        # --- 步驟 3 (更新持久清單): 原子寫入 storage:// release_manifest.json ---
        new_manifest = {
            "active_targets": active_target_names,
            "published_files": sorted(list(current_published_set)),
            "updated_at": "2026-08-26"
        }

        if uri:
            try:
                uri.write_json(MANIFEST_STORAGE_URI, new_manifest)
            except Exception:
                pass

        # --- 步驟 4 (建立目錄並落地輸出檔案) ---
        written_count = 0
        for dst_abs, content in precomputed_files.items():
            os.makedirs(os.path.dirname(dst_abs), exist_ok=True)
            with open(dst_abs, "w", encoding="utf-8") as f:
                f.write(content)
            written_count += 1

        # 執行 AGENTS.md 軟合併
        proj_root = os.getcwd()
        if uri:
            try:
                proj_root = uri.resolve("project://", interactive=False)
            except Exception:
                pass

        if enable_agents_md and dev_standards_content:
            target_agents_abs = os.path.join(proj_root, "AGENTS.md")
            # 依主要 Target 之發布拓撲映射表轉譯 URI 標籤為相對於根目錄之路徑
            rendered_agents_content = dev_standards_content
            if active_target_names:
                main_target_cfg = all_registered_targets.get(active_target_names[0], {})
                if main_target_cfg:
                    dep_map_main, _ = self.build_deployment_map(main_target_cfg, resolved_items)
                    rendered_agents_content = self.compiler.resolve_stage2_uri(
                        dev_standards_content, target_agents_abs, dep_map_main
                    )

            self._soft_merge_agents_md(rendered_agents_content, proj_root)

        return {
            "success": True,
            "published_count": written_count,
            "active_targets": active_target_names,
            "orphan_targets": orphan_targets,
            "removed_count": len(files_to_remove)
        }
