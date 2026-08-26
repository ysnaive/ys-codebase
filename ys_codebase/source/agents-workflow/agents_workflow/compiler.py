"""
Artifact Factory Compiler for agents-workflow.
Implements the 6-Stage Semantic Pipeline:
Stage 1: 5-Step Multi-Pass Recursive State Machine for Content Token Resolution -> cache.root://
Stage 2: 3-Tier Contextual Semantic URI Resolution -> Target Deployments.
100% Python Standard Library, Zero Third-Party Dependency.
"""

import os
import sys
import re
from typing import Dict, List, Any, Optional, Tuple

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
    from core.context import ExecutionContext
except ImportError:
    uri = None
    ExecutionContext = None

# Global Placeholder Pattern Constants (Strict Backtick Format)
TOKEN_ANCHOR_REGEX = re.compile(r"`__@\{\s*([A-Za-z0-9_]+)\s*\}__`")
URI_REF_REGEX = re.compile(r"`?__#\{\s*([^}]+)\s*\}__`?")


def make_token_tag_regex(token_name: str) -> re.Pattern:
    """構造匹配指定 Token 標籤之正則表達式，支援大括號內部微量空格。"""
    return re.compile(r"`__@\{\s*" + re.escape(token_name) + r"\s*\}__`")


def make_purge_regex(token_name: str) -> re.Pattern:
    """構造用於抹除殘留 Token 錨點行之正則表達式，自動吞噬行首縮排與行尾換行。"""
    return re.compile(r"([ \t]*`__@\{\s*" + re.escape(token_name) + r"\s*\}__`[ \t]*\r?\n?)")


class ArtifactCompiler:
    """
    協議產物工廠編譯器 (Artifact Factory Compiler).
    負責解析已安裝模組之 contributes (export, insert, token, release_target)，
    執行 Stage 1 內容展開快取與 Stage 2 URI 相對路徑轉譯。
    """

    def __init__(self, host_dir: Optional[str] = None):
        self.host_dir = host_dir
        # 定位模組根目錄 (source/agents-workflow 或 modules/agents-workflow)
        self.module_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _read_file_content(self, path_or_uri: str) -> str:
        """安全讀取語意 URI 或本機檔案文字，支援 module.root 與 module.source.root 自適應降級。"""
        if not path_or_uri:
            return ""

        # 1. 直接嘗試語意 URI
        if uri and "://" in path_or_uri:
            if uri.exists(path_or_uri):
                try:
                    return uri.read_text(path_or_uri)
                except Exception:
                    pass
            
            # 若 module:// 失敗，自適應嘗試 module.source://
            if path_or_uri.startswith("module://"):
                fallback_src_uri = path_or_uri.replace("module://", "module.source://", 1)
                if uri.exists(fallback_src_uri):
                    try:
                        return uri.read_text(fallback_src_uri)
                    except Exception:
                        pass

        # 2. 本地模組相對路徑嘗試 (自包含 fallback)
        sub_path = path_or_uri
        if "://" in path_or_uri:
            parts = path_or_uri.split("://", 1)[1]
            if "/" in parts:
                _, rel_p = parts.split("/", 1)
                sub_path = rel_p

        local_cand = os.path.join(self.module_root, sub_path.replace("/", os.sep))
        if os.path.isfile(local_cand):
            try:
                with open(local_cand, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                pass

        # 3. 實體路徑嘗試
        real_p = uri.resolve(path_or_uri) if (uri and "://" in path_or_uri) else path_or_uri
        if os.path.isfile(real_p):
            try:
                with open(real_p, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                pass

        return ""

    def get_contributes_data(self) -> Dict[str, Any]:
        """
        收集全系統 contributes 資料 (export, insert, token, release_target)：
        1. 優先自 cache.root://agents-workflow/contributes.merged.json 讀取。
        2. 若缺少 release_target 或為空，主動掃描 module.root:// 與 module.source.root:// 下各模組之 manifest.json 補充。
        """
        aggregated: Dict[str, Any] = {
            "export": [],
            "insert": [],
            "token": [],
            "release_target": []
        }

        if uri:
            merged_uri = "cache://agents-workflow/contributes.merged.json"
            if uri.exists(merged_uri):
                try:
                    data = uri.read_json(merged_uri)
                    if isinstance(data, dict):
                        for k in ("export", "insert", "token", "release_target"):
                            if k in data and isinstance(data[k], list):
                                aggregated[k].extend(data[k])
                except Exception:
                    pass

        # 若 release_target 或 export 依然為空，主動掃描模組根目錄
        if not aggregated["export"] or not aggregated["release_target"]:
            search_roots = ["module://", "module.source://"]
            seen_modules = set()

            for s_root in search_roots:
                if uri and uri.exists(s_root):
                    for mod in uri.listdir(s_root):
                        if mod in seen_modules:
                            continue
                        seen_modules.add(mod)
                        m_uri = f"{s_root}{mod}/manifest.json"
                        if uri.exists(m_uri):
                            try:
                                m_data = uri.read_json(m_uri)
                                c_all = m_data.get("contributes", {})
                                c_aw = c_all.get("agents-workflow", {}) if isinstance(c_all, dict) else {}
                                for key in ("export", "insert", "token", "release_target"):
                                    items = c_aw.get(key, [])
                                    if isinstance(items, list):
                                        for it in items:
                                            if isinstance(it, dict) and it not in aggregated[key]:
                                                aggregated[key].append(it)
                            except Exception:
                                pass

        # 若依然為空，直接讀取模組本地 manifest.json (本地源碼/安裝兜底)
        if not aggregated["export"] or not aggregated["release_target"]:
            local_mf = os.path.join(self.module_root, "manifest.json")
            if os.path.isfile(local_mf):
                try:
                    import json
                    with open(local_mf, "r", encoding="utf-8") as f:
                        m_data = json.load(f)
                    c_all = m_data.get("contributes", {})
                    c_aw = c_all.get("agents-workflow", {}) if isinstance(c_all, dict) else {}
                    for key in ("export", "insert", "token", "release_target"):
                        items = c_aw.get(key, []) or m_data.get(key, [])
                        if isinstance(items, list):
                            for it in items:
                                if isinstance(it, dict) and it not in aggregated[key]:
                                    aggregated[key].append(it)
                except Exception:
                    pass

        return aggregated

    def resolve_single_artifact(
        self,
        content: str,
        inserts: List[Dict[str, Any]],
        mod_order: Optional[List[str]] = None,
        max_passes: int = 10,
        context: Optional[Any] = None
    ) -> str:
        """
        Stage 1: 單一 Export 檔案之多輪遞迴解算狀態機 (resolve_stage1_content)：
        - Step 1: 建立文本當前 __@{token}__ 錨點快照 CurrentTokens。
        - Step 2: 依照拓撲順序有序展開匹配的 insert (replace / below / above)。
        - Step 3: 移除本輪已完成解算或無匹配之 Token 錨點標籤行。
        - Step 4: 遞迴檢查文本是否仍有新 Token（有則回 Step 1，無則收斂結束）。
        - Step 5: 保持 __#{uri}__ 標籤原樣返回。
        """
        resolved_text = content
        pass_count = 0

        while pass_count < max_passes:
            pass_count += 1
            
            # Step 1: 建立快照 (支援大括號內空白容錯)
            current_tokens = list(dict.fromkeys(TOKEN_ANCHOR_REGEX.findall(resolved_text)))
            if not current_tokens:
                break

            # Step 2: 依序執行 insert 注入
            matched_tokens_this_pass = set()

            for token_name in current_tokens:
                token_tag_regex = make_token_tag_regex(token_name)
                
                # 尋找所有匹配此 token 的 insert 宣告
                matched_inserts = [
                    ins for ins in inserts 
                    if isinstance(ins, dict) and ins.get("token") == token_name
                ]

                if not matched_inserts:
                    # 無匹配 insert，記錄待 Step 3 清除
                    matched_tokens_this_pass.add(token_name)
                    continue

                for ins in matched_inserts:
                    matched_tokens_this_pass.add(token_name)
                    ins_type = ins.get("type", "const")
                    mode = ins.get("mode", "replace")
                    raw_val = ins.get("value", "")

                    # 解算注入內容
                    if ins_type == "uri":
                        val_content = self._read_file_content(str(raw_val))
                    elif ins_type == "computed":
                        try:
                            from core.symbols import resolve_callable
                            target_fn = resolve_callable(str(raw_val), context=context)
                            comp_res = target_fn(context)
                            val_content = "" if comp_res is None else str(comp_res)
                        except Exception as e:
                            print(f"[compiler:warning] Failed to resolve computed token '{token_name}' ({raw_val}): {e}", file=sys.stderr)
                            val_content = ""
                    else:
                        val_content = str(raw_val)

                    # 自指防護 (EC-01): 若注入內容包含同名 Token，跳過自我展開
                    if mode == "replace":
                        resolved_text = token_tag_regex.sub(lambda _: val_content, resolved_text, count=1)
                    elif mode == "below":
                        resolved_text = token_tag_regex.sub(
                            lambda m: m.group(0) + "\n" + val_content, 
                            resolved_text, 
                            count=1
                        )
                    elif mode == "above":
                        resolved_text = token_tag_regex.sub(
                            lambda m: val_content + "\n" + m.group(0), 
                            resolved_text, 
                            count=1
                        )

            # Step 3: 清除本輪已解算或無匹配的 Token 錨點標籤行
            for token_name in matched_tokens_this_pass:
                purge_regex = make_purge_regex(token_name)
                resolved_text = purge_regex.sub("", resolved_text)

            # Step 4: 遞迴檢查是否仍有新 Token
            remaining = TOKEN_ANCHOR_REGEX.findall(resolved_text)
            if not remaining:
                break

        # Step 5: 保持 __#{uri}__ 語意標籤原樣，返回純淨中繼字串
        return resolved_text

    def resolve_stage1_content(self, content: str, inserts: List[Dict[str, Any]], context: Optional[Any] = None) -> str:
        """Stage 1: 解算內容佔位符別名。"""
        return self.resolve_single_artifact(content, inserts, context=context)

    def compile_stage1(self) -> Dict[str, Any]:
        """
        執行 Stage 1 全量段落佔位符解算：
        將所有 export 項目物化寫入 cache.root://agents-workflow/resolved_contents/。
        """
        data = self.get_contributes_data()
        exports = data.get("export", [])
        inserts = data.get("insert", [])
        tokens = data.get("token", [])

        resolved_items = []
        errors = []

        cache_target_root = "cache://@/resolved_contents"

        for exp in exports:
            if not isinstance(exp, dict):
                continue
            exp_type = exp.get("type", "template")
            source_p = exp.get("source", "")
            base_name = os.path.basename(source_p.replace("\\", "/"))
            if not base_name:
                continue

            folder_map = {
                "standard": "standards",
                "standards": "standards",
                "workflow": "workflows",
                "workflows": "workflows",
                "template": "templates",
                "templates": "templates"
            }
            sub_folder = folder_map.get(exp_type, "templates")

            raw_content = self._read_file_content(source_p)
            if not raw_content:
                errors.append(f"Cannot read export source: {source_p}")
                continue

            try:
                ctx = ExecutionContext("agents-workflow", "compile", []) if ExecutionContext else None
                stage1_content = self.resolve_single_artifact(raw_content, inserts, context=ctx)

                cache_uri = f"{cache_target_root}/{sub_folder}/{base_name}"
                written = False
                if uri:
                    try:
                        uri.makedirs(f"{cache_target_root}/{sub_folder}", exist_ok=True)
                        uri.write_text(cache_uri, stage1_content)
                        written = True
                    except Exception:
                        written = False

                if not written:
                    if uri:
                        try:
                            local_cache = uri.resolve(cache_uri)
                        except Exception:
                            local_cache = os.path.join(self.module_root, ".cache", "resolved_contents", sub_folder, base_name)
                    else:
                        local_cache = os.path.join(self.module_root, ".cache", "resolved_contents", sub_folder, base_name)
                    os.makedirs(os.path.dirname(local_cache), exist_ok=True)
                    with open(local_cache, "w", encoding="utf-8") as f:
                        f.write(stage1_content)
                    cache_uri = local_cache

                resolved_items.append({
                    "export": exp,
                    "sub_folder": sub_folder,
                    "base_name": base_name,
                    "cache_uri": cache_uri,
                    "content": stage1_content
                })
            except Exception as e:
                errors.append(f"Failed Stage 1 for {base_name}: {e}")

        return {
            "success": len(errors) == 0,
            "resolved_items": resolved_items,
            "inserted_count": len(inserts),
            "tokens_count": len(tokens),
            "errors": errors
        }

    def resolve_stage2_uri(
        self,
        content: str,
        current_dst_path: str,
        deployment_map: Dict[str, str]
    ) -> str:
        """
        Stage 2: 依三層重映射階層動態轉譯 `__#{uri}__` 為相對於 current_dst_path 之實體相對路徑。
        - Tier 1: 命中 deployment_map (本次發布拓撲映射表)
        - Tier 2: 專案級語意協議 (project://, docs://, plans://)
        - Tier 3: 未知/未決協議安全降級
        """
        if not content or "__#{" not in content:
            return content

        cur_dir = os.path.dirname(os.path.abspath(current_dst_path))

        def _replace_uri_tag(match: re.Match) -> str:
            tag_uri = match.group(1).strip()

            # --- Tier 1: 命中發布拓撲映射表 ---
            # 支援完整 URI 與標準短名匹配 (如 module.root://.../templates/P00.md 與 templates/P00.md)
            if tag_uri in deployment_map:
                target_abs = deployment_map[tag_uri]
                try:
                    rel_p = os.path.relpath(target_abs, cur_dir).replace("\\", "/")
                    return rel_p if rel_p.startswith(".") else f"./{rel_p}"
                except Exception:
                    return target_abs.replace("\\", "/")

            # 嘗試正規化短名匹配
            for s_key, t_abs in deployment_map.items():
                if tag_uri.endswith(s_key) or s_key.endswith(tag_uri):
                    try:
                        rel_p = os.path.relpath(t_abs, cur_dir).replace("\\", "/")
                        return rel_p if rel_p.startswith(".") else f"./{rel_p}"
                    except Exception:
                        return t_abs.replace("\\", "/")

            # --- Tier 2: 專案級語意協議 ---
            if uri and "://" in tag_uri:
                try:
                    real_p = uri.resolve(tag_uri, interactive=False)
                    rel_p = os.path.relpath(real_p, cur_dir).replace("\\", "/")
                    return rel_p if rel_p.startswith(".") else f"./{rel_p}"
                except Exception:
                    pass

            # --- Tier 3: 未知協議安全降級 ---
            print(f"[compiler:warning] Unresolved semantic URI tag: '{tag_uri}'", file=sys.stderr)
            return tag_uri

        return URI_REF_REGEX.sub(_replace_uri_tag, content)

    def compile_all(self) -> Dict[str, Any]:
        """相容性別名：執行 Stage 1 快取物化編譯。"""
        res = self.compile_stage1()
        return {
            "success": res.get("success", False),
            "exported_count": len(res.get("resolved_items", [])),
            "inserted_count": res.get("inserted_count", 0),
            "tokens_count": res.get("tokens_count", 0),
            "errors": res.get("errors", [])
        }

    def get_registered_tokens(self) -> List[Dict[str, Any]]:
        """自省查詢全系統已註冊的 Token 錨點清單。"""
        data = self.get_contributes_data()
        return data.get("token", [])

    def get_exported_artifacts(self) -> List[Dict[str, Any]]:
        """自省查詢全系統已宣告的 Export 資產清單。"""
        data = self.get_contributes_data()
        return data.get("export", [])

    def get_release_targets(self) -> List[Dict[str, Any]]:
        """自省查詢全系統已宣告的 Release Target 清單。"""
        data = self.get_contributes_data()
        return data.get("release_target", [])
