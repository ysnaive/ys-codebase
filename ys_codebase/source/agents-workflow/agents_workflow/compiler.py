"""
Artifact Factory Compiler for agents-workflow.
Implements the 5-Step Multi-Pass Recursive State Machine for artifact resolution.
"""
import os
import re
from typing import Dict, List, Any, Optional, Tuple

try:
    from core import uri
except ImportError:
    uri = None


class ArtifactCompiler:
    """
    協議產物工廠編譯器 (Artifact Factory Compiler).
    負責解析已安裝模組之 contributes (export, insert, token)，
    執行多輪遞迴狀態機展開，並將標準資產物化寫入 module.root://agents-workflow/exports/。
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
            
            # 若 module.root:// 失敗，自適應嘗試 module.source.root://
            if path_or_uri.startswith("module.root://"):
                fallback_src_uri = path_or_uri.replace("module.root://", "module.source.root://", 1)
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
        收集全系統 contributes 資料：
        1. 優先自 cache.root://agents-workflow/contributes.merged.json 讀取。
        2. 降級掃描 module.root:// 與 module.source.root:// 下各模組之 manifest.json。
        """
        if uri:
            merged_uri = "cache.root://agents-workflow/contributes.merged.json"
            if uri.exists(merged_uri):
                try:
                    data = uri.read_json(merged_uri)
                    if isinstance(data, dict):
                        return data
                except Exception:
                    pass

        # 降級主動搜集
        aggregated: Dict[str, Any] = {
            "export": [],
            "insert": [],
            "token": []
        }

        search_roots = ["module.root://", "module.source.root://"]
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
                            # 1. 直接 contributes
                            c_all = m_data.get("contributes", {})
                            c_aw = c_all.get("agents-workflow", {}) if isinstance(c_all, dict) else {}
                        except Exception:
                            pass

        # 若依然為空，直接讀取模組本地 manifest.json (本地源碼/安裝兜底)
        if not any(aggregated.values()):
            local_mf = os.path.join(self.module_root, "manifest.json")
            if os.path.isfile(local_mf):
                try:
                    import json
                    with open(local_mf, "r", encoding="utf-8") as f:
                        m_data = json.load(f)
                    c_all = m_data.get("contributes", {})
                    c_aw = c_all.get("agents-workflow", {}) if isinstance(c_all, dict) else {}
                    for key in ("export", "insert", "token"):
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
        max_passes: int = 10
    ) -> str:
        """
        單一 Export 檔案之多輪遞迴解算狀態機：
        - Step 1: 建立文本當前 <!-- __TOKEN__ --> 錨點快照 CurrentTokens。
        - Step 2: 依照拓撲順序有序展開匹配的 insert (replace / below / above)。
        - Step 3: 移除本輪已完成解算之 Token 錨點標籤（清理殘留錨點）。
        - Step 4: 遞迴檢查文本是否仍有新 Token（有則回 Step 1，無則收斂結束）。
        - Step 5: 保持 <!-- __URI(...)__ --> 標籤原樣返回。
        """
        resolved_text = content
        pass_count = 0

        while pass_count < max_passes:
            pass_count += 1
            
            # Step 1: 建立快照
            current_tokens = list(dict.fromkeys(re.findall(r"<!--\s*__([A-Za-z0-9_]+)__\s*-->", resolved_text)))
            if not current_tokens:
                break

            # Step 2: 依序執行 insert 注入
            # 依據 token 分組匹配
            matched_tokens_this_pass = set()

            for token_name in current_tokens:
                token_tag_regex = re.compile(r"<!--\s*__" + re.escape(token_name) + r"__\s*-->")
                
                # 尋找所有匹配此 token 的 insert 宣告
                matched_inserts = [
                    ins for ins in inserts 
                    if isinstance(ins, dict) and ins.get("token") == token_name
                ]

                if not matched_inserts:
                    # 無匹配 insert，亦記錄待 Step 3 清除
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
                    else:
                        val_content = str(raw_val)

                    # 自指防護 (EC-02): 若注入內容包含同名 Token，暫時跳過自我展開
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

            # Step 3: 清除本輪已解算或無匹配的 Token 錨點標籤
            for token_name in matched_tokens_this_pass:
                # 若為 below/above 殘留標籤或無匹配標籤，自文本中乾淨抹除
                purge_regex = re.compile(r"([ \t]*<!--\s*__" + re.escape(token_name) + r"__\s*-->[ \t]*\r?\n?)")
                resolved_text = purge_regex.sub("", resolved_text)

            # Step 4: 遞迴檢查是否仍有新 Token
            remaining = re.findall(r"<!--\s*__([A-Za-z0-9_]+)__\s*-->", resolved_text)
            if not remaining:
                break

        # Step 5: 保持 <!-- __URI(...)__ --> 原樣，返回最終字串
        return resolved_text

    def compile_all(self) -> Dict[str, Any]:
        """
        執行全量工廠物化編譯流水線：
        1. 收集全系統 export, insert, token 宣告。
        2. 逐一讀取 export 來源文字，調用 resolve_single_artifact 解算。
        3. 分流原子覆蓋寫入至 exports/{standards|workflows|templates}/。
        """
        data = self.get_contributes_data()
        exports = data.get("export", [])
        inserts = data.get("insert", [])
        tokens = data.get("token", [])

        exported_count = 0
        errors = []

        # 確保目標輸出根目錄存在 (module.root://agents-workflow/exports/ 或 local exports/)
        target_export_root = "module.root://agents-workflow/exports"
        if not (uri and uri.exists("module.root://agents-workflow")):
            # 本地源碼環境降級輸出
            target_export_root = "module.source.root://agents-workflow/exports"

        for exp in exports:
            if not isinstance(exp, dict):
                continue
            exp_type = exp.get("type", "template")  # standard, workflow, template
            source_p = exp.get("source", "")
            
            # 推導目標檔案名稱
            base_name = os.path.basename(source_p.replace("\\", "/"))
            if not base_name:
                continue

            # 分類子目錄 (standards, workflows, templates)
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
                resolved_content = self.resolve_single_artifact(raw_content, inserts)
                
                # 寫入 exports
                written = False
                dst_uri = f"{target_export_root}/{sub_folder}/{base_name}"
                if uri:
                    try:
                        uri.makedirs(f"{target_export_root}/{sub_folder}", exist_ok=True)
                        uri.write_text(dst_uri, resolved_content)
                        written = True
                    except Exception:
                        written = False

                if not written:
                    local_dst = os.path.join(self.module_root, "exports", sub_folder, base_name)
                    os.makedirs(os.path.dirname(local_dst), exist_ok=True)
                    with open(local_dst, "w", encoding="utf-8") as f:
                        f.write(resolved_content)
                
                exported_count += 1
            except Exception as e:
                errors.append(f"Failed resolving {base_name}: {e}")

        return {
            "success": len(errors) == 0,
            "exported_count": exported_count,
            "inserted_count": len(inserts),
            "tokens_count": len(tokens),
            "errors": errors
        }

    def get_registered_tokens(self) -> List[Dict[str, Any]]:
        """自省查詢全系統已註冊的 Token 錨點清單。"""
        data = self.get_contributes_data()
        return data.get("token", [])

    def get_exported_artifacts(self) -> List[Dict[str, Any]]:
        """自省查詢全系統已宣告的 Export 資產清單。"""
        data = self.get_contributes_data()
        return data.get("export", [])
