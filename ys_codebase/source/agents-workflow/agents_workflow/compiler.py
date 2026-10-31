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
    os.path.join(os.path.dirname(_mods_root_aw), ".modules", "core")
]:
    if os.path.isdir(_cand) and _cand not in sys.path:
        sys.path.insert(0, _cand)

try:
    from core import uri
    from core import vfs
    from core.context import ExecutionContext
except ImportError:
    uri = None
    vfs = None
    ExecutionContext = None

FENCED_CODE_BLOCK_REGEX = re.compile(r"```[\s\S]*?```")
LITERAL_FENCED_BLOCK_REGEX = re.compile(r"(```[^\r\n]*\r?\n)<!--\s*yscb:literal\s*-->[ \t]*\r?\n([\s\S]*?```)")
CODE_SPAN_REGEX = re.compile(r"(`[^`\r\n]+`)")
UNENCLOSED_TAG_REGEX = re.compile(r"__(?:[@#%]\s*\{\s*[^}]+\s*\}|\$(?:\([^)]*\))?\{\s*[^}]+\s*\})__")

TOKEN_ANCHOR_INNER_REGEX = re.compile(r"__@\{\s*([A-Za-z0-9_]+)\s*\}__")
LOCAL_URI_INNER_REGEX = re.compile(r"__#\{\s*([^}]+)\s*\}__")
PROJECT_URI_INNER_REGEX = re.compile(r"__\$(?:\(\s*([^)]*?)\s*\))?\{\s*([^}]+)\s*\}__")
LOCALE_NOUN_INNER_REGEX = re.compile(r"__%\{\s*([A-Za-z0-9_.:-]+)\s*\}__")

LOCAL_URI_EXACT_REGEX = re.compile(r"^__#\{\s*([^}]+)\s*\}__$")
PROJECT_URI_EXACT_REGEX = re.compile(r"^__\$(?:\(\s*([^)]*?)\s*\))?\{\s*([^}]+)\s*\}__$")


def check_unenclosed_tags(content: str, doc_name: str = "") -> None:
    """檢查並輸出未被反引號包裹的裸佔位符警示 (Unenclosed Placeholder Warning Gate)。"""
    if not content:
        return
    clean_text = FENCED_CODE_BLOCK_REGEX.sub("", content)
    clean_text = CODE_SPAN_REGEX.sub("", clean_text)
    matches = UNENCLOSED_TAG_REGEX.findall(clean_text)
    if matches:
        for m in dict.fromkeys(matches):
            target_str = f" in '{doc_name}'" if doc_name else ""
            print(f"[compiler:warning] Unenclosed placeholder tag '{m}' detected{target_str} (must be enclosed in backticks '`...`')", file=sys.stderr)


def make_token_tag_regex(token_name: str) -> re.Pattern:
    """構造匹配指定 Token 標籤之正則表達式，支援大括號內部微量空格。"""
    return re.compile(r"__@\{\s*" + re.escape(token_name) + r"\s*\}__")


def make_purge_regex(token_name: str) -> re.Pattern:
    """構造用於抹除殘留 Token 錨點行之正則表達式，自動吞噬行首縮排與行尾換行。"""
    return re.compile(r"([ \t]*`__@\{\s*" + re.escape(token_name) + r"\s*\}__`[ \t]*\r?\n?)")


def _lookup_deployed_abs_path(tag_uri: str, deployment_map: Dict[str, str]) -> Optional[str]:
    """
    於 deployment_map 中查找目標 URI 的絕對路徑：
    1. 精確鍵值匹配
    2. 短名後綴匹配（僅限 module://、config:// 或純短名，嚴禁攔截 project://、workflow.* 與 yscb.*）
    """
    if not deployment_map or not tag_uri:
        return None
    if tag_uri in deployment_map:
        return deployment_map[tag_uri]
    if not tag_uri.startswith(("project://", "workflow.", "yscb.")):
        for s_key, cand_abs in deployment_map.items():
            if tag_uri.endswith(s_key) or s_key.endswith(tag_uri):
                return cand_abs
    return None


def _format_relative_local_path(target_abs: str, cur_dir: str, trailing_slash: bool) -> str:
    """計算 target_abs 相對於 cur_dir 之 POSIX 相對路徑（以 ./ 或 ../ 開頭）。"""
    try:
        rel_p = os.path.relpath(target_abs, cur_dir).replace("\\", "/")
        res = rel_p if rel_p.startswith(".") else f"./{rel_p}"
    except Exception:
        res = target_abs.replace("\\", "/")
    if trailing_slash and not res.endswith("/"):
        res = res + "/"
    return res


def _resolve_local_uri_tag(
    tag_uri: str,
    cur_dir: str,
    deployment_map: Dict[str, str],
    doc_basename: str,
) -> str:
    """解算 Stage 2 自身相對路徑標籤 `__#{uri}__`。"""
    trailing_slash = tag_uri.endswith("/")

    # Tier 1: 命中發布拓撲映射表
    mapped_abs = _lookup_deployed_abs_path(tag_uri, deployment_map)
    if mapped_abs:
        return _format_relative_local_path(mapped_abs, cur_dir, trailing_slash)

    # Tier 2: 專案級語意協議
    if uri and "://" in tag_uri:
        try:
            real_p = uri.resolve(tag_uri, interactive=False)
            return _format_relative_local_path(real_p, cur_dir, trailing_slash)
        except Exception:
            pass

    # Tier 3: 未知協議安全降級
    print(f"[compiler:warning] Unresolved semantic URI tag: '{tag_uri}' in '{doc_basename}'", file=sys.stderr)
    return tag_uri


def _resolve_anchor_base_dir(
    anchor_str: Optional[str],
    project_root: str,
    deployment_map: Dict[str, str],
) -> str:
    """解析起始錨點為實體基底目錄。預設為 project_root。"""
    if not anchor_str:
        return project_root

    anchor_abs = _lookup_deployed_abs_path(anchor_str, deployment_map)
    if not anchor_abs and uri and "://" in anchor_str:
        try:
            anchor_abs = uri.resolve(anchor_str, interactive=False)
        except Exception:
            pass

    if not anchor_abs:
        anchor_abs = os.path.normpath(os.path.join(project_root, anchor_str))

    anchor_abs = os.path.normpath(os.path.abspath(anchor_abs))
    if os.path.isdir(anchor_abs):
        return anchor_abs
    if os.path.isfile(anchor_abs):
        return os.path.dirname(anchor_abs)
    _, ext = os.path.splitext(anchor_abs)
    return os.path.dirname(anchor_abs) if ext else anchor_abs


def _resolve_project_uri_tag(
    tag_uri: str,
    anchor: Optional[str],
    project_root: str,
    deployment_map: Dict[str, str],
    doc_basename: str,
) -> str:
    """解算 Stage 2 專案/錨點相對路徑標籤 `__${uri}__` 或 `__$(anchor){uri}__`。"""
    t_abs = _lookup_deployed_abs_path(tag_uri, deployment_map)

    if not t_abs and uri and "://" in tag_uri:
        try:
            t_abs = uri.resolve(tag_uri, interactive=False)
        except Exception as e:
            if tag_uri.startswith("workflow.docs://"):
                t_abs = os.path.join(project_root, "docs", tag_uri[len("workflow.docs://"):])
            elif tag_uri.startswith("workflow.plans://"):
                t_abs = os.path.join(project_root, "plans", tag_uri[len("workflow.plans://"):])
            elif tag_uri.startswith("workflow.archived://"):
                t_abs = os.path.join(project_root, "plans", "archived", tag_uri[len("workflow.archived://"):])
            else:
                print(f"[compiler:warning] Failed to resolve project URI '{tag_uri}' in '{doc_basename}': {e}", file=sys.stderr)

    if t_abs:
        try:
            base_dir = _resolve_anchor_base_dir(anchor, project_root, deployment_map)
            rel_p = os.path.relpath(t_abs, base_dir).replace("\\", "/")
            if not anchor and (rel_p == "." or rel_p == "./"):
                return ""
            if rel_p.startswith("./"):
                rel_p = rel_p[2:]
            if tag_uri.endswith("/") and not rel_p.endswith("/") and rel_p != "":
                rel_p = rel_p + "/"
            return rel_p
        except Exception:
            res = t_abs.replace("\\", "/")
            if tag_uri.endswith("/") and not res.endswith("/"):
                res = res + "/"
            return res

    return tag_uri


def _resolve_locale_noun_tag(noun_key: str, target_name: Optional[str], doc_basename: str) -> str:
    """解算 Stage 2 目標宿主專有名詞標籤 `__%{key}__`。"""
    try:
        from core import locale as core_locale
        base_chain = core_locale.get_active_chain()
        if target_name and target_name.strip():
            t_dialect = f"nouns-{target_name.strip()}"
            target_chain = [t_dialect] + [c for c in base_chain if not c.startswith("nouns-")]
        else:
            target_chain = base_chain
        hit = core_locale.resolve_raw(noun_key, module="agents-workflow", chain=target_chain)
        if hit is not None:
            return core_locale.t(noun_key, module="agents-workflow", chain=target_chain)
    except Exception:
        pass
    print(f"[compiler:warning] Unresolved locale noun tag: '{noun_key}' in '{doc_basename}'", file=sys.stderr)
    return f"__%{{{noun_key}}}__"


def _clean_md_link_match(match: re.Match) -> str:
    """清理 Markdown 超連結括號內殘留的多餘反引號與連續斜線: [text](`path`) -> [text](path)。"""
    path = match.group(1)
    if not re.match(r"^[a-zA-Z0-9_\+\-]+://", path):
        path = re.sub(r"/{2,}", "/", path)
    return f"]({path})"


class ArtifactCompiler:
    """
    協議產物工廠編譯器 (Artifact Factory Compiler).
    負責解析已安裝模組之 contributes (export, insert, token, release_target)，
    執行 Stage 1 內容展開快取與 Stage 2 URI 相對路徑轉譯。
    """

    def __init__(self, host_dir: Optional[str] = None):
        self.host_dir = host_dir
        self.module_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _resolve_source_path(self, path_or_uri: str) -> str:
        """解析語意 URI 或相對路徑至本機實體檔案/目錄路徑。"""
        if not path_or_uri:
            return ""

        if uri and "://" in path_or_uri:
            try:
                real_p = uri.resolve(path_or_uri, interactive=False)
                if os.path.exists(real_p):
                    return real_p
            except Exception:
                pass

        sub_path = path_or_uri
        target_root = self.module_root
        if "://" in path_or_uri:
            scheme, parts = path_or_uri.split("://", 1)
            if "/" in parts:
                mod_name, rel_p = parts.split("/", 1)
                sub_path = rel_p
                if scheme == "module" and mod_name and mod_name != os.path.basename(self.module_root):
                    sibling_root = os.path.join(os.path.dirname(self.module_root), mod_name)
                    if os.path.isdir(sibling_root):
                        target_root = sibling_root

        local_cand = os.path.join(target_root, sub_path.replace("/", os.sep))
        if os.path.exists(local_cand):
            return local_cand

        if os.path.exists(path_or_uri):
            return path_or_uri

        return ""

    def _scan_directory_files(self, dir_path_or_uri: str) -> List[Tuple[str, str, str]]:
        """
        遞迴掃描指定目錄路徑（支援語意 URI 或實體路徑）下的所有檔案。

        Returns:
            List of (rel_path, abs_path, content_str)
        """
        real_dir = self._resolve_source_path(dir_path_or_uri)
        if not real_dir or not os.path.isdir(real_dir):
            return []

        results: List[Tuple[str, str, str]] = []
        for root, _, files in os.walk(real_dir):
            for fname in sorted(files):
                abs_f = os.path.join(root, fname)
                rel_f = os.path.relpath(abs_f, real_dir).replace("\\", "/")
                content = ""
                try:
                    if vfs:
                        content = vfs.read_text(abs_f)
                    else:
                        with open(abs_f, "r", encoding="utf-8") as f:
                            content = f.read()
                except Exception:
                    try:
                        with open(abs_f, "rb") as f:
                            content = f.read().decode("utf-8", errors="replace")
                    except Exception:
                        content = ""
                results.append((rel_f, abs_f, content))
        return results

    def _read_file_content(self, path_or_uri: str) -> str:
        """安全讀取語意 URI 或本機檔案文字，支援 module.root 與 module.source.root 自適應降級。"""
        real_p = self._resolve_source_path(path_or_uri)
        if real_p and (vfs.is_file(real_p) if vfs else os.path.isfile(real_p)):
            try:
                if vfs:
                    return vfs.read_text(real_p)
                with open(real_p, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                try:
                    with open(real_p, "rb") as f:
                        return f.read().decode("utf-8", errors="replace")
                except Exception:
                    pass

        if vfs and "://" in path_or_uri:
            try:
                if vfs.exists(path_or_uri):
                    return vfs.read_text(path_or_uri)
            except Exception:
                pass

        return ""

    def get_contributes_data(self) -> Dict[str, Any]:
        """
        收集全系統 contributes 資料 (export, insert, token, release_target)：
        100% 透過 core.contributes SDK 查詢已合併快取或觸發自愈。
        """
        aggregated: Dict[str, Any] = {
            "export": [],
            "insert": [],
            "token": [],
            "release_target": []
        }

        try:
            from core import contributes
            data = contributes.get("agents-workflow")
            if isinstance(data, dict):
                for k in ("export", "insert", "token", "release_target"):
                    if k in data and isinstance(data[k], list):
                        aggregated[k].extend(data[k])
        except Exception:
            pass

        return aggregated

    def resolve_single_artifact(
        self,
        content: str,
        inserts: List[Dict[str, Any]],
        max_passes: int = 10,
        context: Optional[Any] = None
    ) -> str:
        """
        Stage 1: 單一 Export 檔案之多輪遞迴解算狀態機：
        - Step 1: 建立文本當前 `...` 代碼塊內部的 __@{token}__ 錨點快照 CurrentTokens。
        - Step 2: 依照拓撲順序有序展開匹配的 insert (replace / below / above)。
        - Step 3: 移除本輪已完成解算或無匹配之 Token 錨點標籤行/標籤。
        - Step 4: 遞迴檢查文本是否仍有新 Token（有則回 Step 1，無則收斂結束）。
        - Step 5: 保持 `__#{uri}__` 與 `__${uri}__` 標籤原樣返回。
        """
        if not content:
            return ""

        check_unenclosed_tags(content)
        literal_blocks: List[str] = []

        def _mask_stage1_literal(m: re.Match) -> str:
            idx = len(literal_blocks)
            literal_blocks.append(m.group(0))
            return f"\x00YSCB_LITERAL_BLOCK_{idx}\x00"

        resolved_text = LITERAL_FENCED_BLOCK_REGEX.sub(_mask_stage1_literal, content)
        pass_count = 0

        while pass_count < max_passes:
            pass_count += 1

            # Step 1: 建立快照（僅自代碼塊中提取）
            code_spans = CODE_SPAN_REGEX.findall(resolved_text)
            current_tokens = []
            for cs in code_spans:
                for t in TOKEN_ANCHOR_INNER_REGEX.findall(cs):
                    if t not in current_tokens:
                        current_tokens.append(t)
            if not current_tokens:
                break

            # Step 2: 依序執行 insert 注入
            matched_tokens_this_pass = set()

            for token_name in current_tokens:
                token_tag_regex = make_token_tag_regex(token_name)

                matched_inserts = [
                    ins for ins in inserts
                    if isinstance(ins, dict) and ins.get("token") == token_name
                ]

                if not matched_inserts:
                    matched_tokens_this_pass.add(token_name)
                    continue

                above_blocks = []
                replace_blocks = []
                below_blocks = []
                last_inline_val = ""

                for ins in matched_inserts:
                    matched_tokens_this_pass.add(token_name)
                    ins_type = ins.get("type", "const")
                    mode = ins.get("mode", "replace")
                    raw_val = ins.get("value", "")

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

                    if val_content is None:
                        val_content = ""

                    last_inline_val = val_content

                    if mode == "above":
                        if val_content.strip():
                            above_blocks.append(val_content.rstrip("\r\n"))
                    elif mode == "below":
                        if val_content.strip():
                            below_blocks.append(val_content.rstrip("\r\n"))
                    else:
                        if val_content.strip():
                            replace_blocks.append(val_content.rstrip("\r\n"))

                standalone_tag_regex = re.compile(r"[ \t]*`__@\{\s*" + re.escape(token_name) + r"\s*\}__`[ \t]*\r?\n?")
                if standalone_tag_regex.search(resolved_text):
                    combined_pieces = []
                    if above_blocks:
                        combined_pieces.extend(above_blocks)
                    if replace_blocks:
                        combined_pieces.extend(replace_blocks)
                    if below_blocks:
                        combined_pieces.extend(below_blocks)

                    if combined_pieces:
                        if all(p.lstrip().startswith("|") for p in combined_pieces):
                            combined_str = "\n".join(combined_pieces).rstrip("\r\n") + "\n"
                        else:
                            combined_str = "\n\n".join(combined_pieces).rstrip("\r\n") + "\n"
                    else:
                        combined_str = ""

                    resolved_text = standalone_tag_regex.sub(lambda _: combined_str, resolved_text, count=1)
                else:
                    def _replace_inline(match: re.Match) -> str:
                        span = match.group(0)
                        inner = span[1:-1]
                        if token_tag_regex.search(inner):
                            inner = token_tag_regex.sub(lambda _: last_inline_val, inner)
                            return f"`{inner}`"
                        return span

                    resolved_text = CODE_SPAN_REGEX.sub(_replace_inline, resolved_text)

            # Step 3: 清除本輪已解算或無匹配的 Token 錨點標籤行/殘留
            for token_name in matched_tokens_this_pass:
                purge_regex = make_purge_regex(token_name)
                resolved_text = purge_regex.sub("", resolved_text)
                token_tag_regex = make_token_tag_regex(token_name)

                def _purge_span_tag(match: re.Match) -> str:
                    span = match.group(0)
                    inner = span[1:-1]
                    if token_tag_regex.search(inner):
                        return f"`{token_tag_regex.sub('', inner)}`"
                    return span

                resolved_text = CODE_SPAN_REGEX.sub(_purge_span_tag, resolved_text)

            # Step 4: 遞迴檢查是否仍有新 Token
            code_spans = CODE_SPAN_REGEX.findall(resolved_text)
            has_remaining = any(TOKEN_ANCHOR_INNER_REGEX.search(cs) for cs in code_spans)
            if not has_remaining:
                break

        for idx, raw_block in enumerate(literal_blocks):
            resolved_text = resolved_text.replace(f"\x00YSCB_LITERAL_BLOCK_{idx}\x00", raw_block)
        return resolved_text

    def _write_cache_file(self, cache_uri: str, content: str) -> str:
        """寫入中繼快取檔案 (支援 vfs/cache URI 與本地 fallback)。"""
        if vfs:
            try:
                vfs.write_text(cache_uri, content, atomic=True)
                return cache_uri
            except Exception:
                pass

        if uri:
            try:
                local_cache = uri.resolve(cache_uri)
            except Exception:
                yscb_root = uri._get_yscb_root()
                sub_rel = cache_uri.replace("cache://agents-workflow/resolved_contents/", "")
                local_cache = os.path.join(yscb_root, ".cache", "agents-workflow", "resolved_contents", sub_rel.replace("/", os.sep))
        else:
            sub_rel = cache_uri.replace("cache://agents-workflow/resolved_contents/", "")
            local_cache = os.path.join(os.path.dirname(os.path.dirname(self.module_root)), ".cache", "agents-workflow", "resolved_contents", sub_rel.replace("/", os.sep))

        os.makedirs(os.path.dirname(local_cache), exist_ok=True)
        with open(local_cache, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        return local_cache

    def compile_stage1(self) -> Dict[str, Any]:
        """
        執行 Stage 1 全量段落佔位符解算：
        將所有 export 項目物化寫入 cache.root://agents-workflow/resolved_contents/。
        支援單檔與目錄級 (Skill Package) 遞迴掃描與 Stage 1 展開。
        """
        data = self.get_contributes_data()
        exports = data.get("export", [])
        inserts = data.get("insert", [])
        tokens = data.get("token", [])

        resolved_items = []
        errors = []

        cache_target_root = "cache://agents-workflow/resolved_contents"
        folder_map = {
            "standard": "standards",
            "standards": "standards",
            "template": "templates",
            "templates": "templates",
            "skill": "skills",
            "skills": "skills"
        }

        for exp in exports:
            if not isinstance(exp, dict):
                continue
            exp_type = exp.get("type", "template")
            source_p = exp.get("source", "")
            exp_name = exp.get("name", "")
            sub_folder = folder_map.get(exp_type, "templates")

            real_src_path = self._resolve_source_path(source_p)
            if not real_src_path or not os.path.exists(real_src_path):
                errors.append(f"Cannot read export source: {source_p}")
                continue

            if os.path.isdir(real_src_path):
                skill_files = self._scan_directory_files(source_p)
                if not skill_files:
                    errors.append(f"Skill directory is empty: {source_p}")
                    continue

                skill_pkg_name = exp_name or os.path.basename(source_p.rstrip("/\\"))
                for rel_f, _, raw_text in skill_files:
                    try:
                        ctx = ExecutionContext("agents-workflow", "compile", []) if ExecutionContext else None
                        if rel_f.endswith((".md", ".txt", ".json", ".yaml", ".yml", ".sh")):
                            stage1_content = self.resolve_single_artifact(raw_text, inserts, context=ctx)
                        else:
                            stage1_content = raw_text

                        cache_uri = f"{cache_target_root}/{sub_folder}/{skill_pkg_name}/{rel_f}"
                        actual_cache = self._write_cache_file(cache_uri, stage1_content)

                        resolved_items.append({
                            "export": exp,
                            "sub_folder": sub_folder,
                            "base_name": os.path.basename(rel_f),
                            "rel_path": rel_f,
                            "cache_uri": actual_cache,
                            "content": stage1_content,
                            "is_skill": True,
                            "skill_name": skill_pkg_name
                        })
                    except Exception as e:
                        errors.append(f"Failed Stage 1 for {skill_pkg_name}/{rel_f}: {e}")
            else:
                base_name = os.path.basename(source_p.replace("\\", "/"))
                raw_content = self._read_file_content(source_p)
                if not raw_content:
                    errors.append(f"Cannot read export source: {source_p}")
                    continue

                try:
                    ctx = ExecutionContext("agents-workflow", "compile", []) if ExecutionContext else None
                    stage1_content = self.resolve_single_artifact(raw_content, inserts, context=ctx)

                    cache_uri = f"{cache_target_root}/{sub_folder}/{base_name}"
                    actual_cache = self._write_cache_file(cache_uri, stage1_content)

                    resolved_items.append({
                        "export": exp,
                        "sub_folder": sub_folder,
                        "base_name": base_name,
                        "rel_path": base_name,
                        "cache_uri": actual_cache,
                        "content": stage1_content,
                        "is_skill": (exp_type in ("skill", "skills")),
                        "skill_name": exp_name or os.path.splitext(base_name)[0]
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

    def _resolve_project_root(self) -> str:
        """取得 정규化之 project_root 絕對路徑。"""
        if self.host_dir:
            return os.path.normpath(os.path.abspath(self.host_dir))
        if uri:
            try:
                return os.path.normpath(os.path.abspath(uri.resolve("project://", interactive=False)))
            except Exception:
                pass
        return os.path.normpath(os.path.abspath(os.getcwd()))

    def resolve_stage2_uri(
        self,
        content: str,
        current_dst_path: str,
        deployment_map: Dict[str, str],
        target_name: Optional[str] = None,
    ) -> str:
        """
        Stage 2: 依三層重映射階層動態轉譯 `__#{uri}__` (自身相對路徑)、`__${uri}__` / `__$(anchor){uri}__` (錨點/專案相對路徑)
        與 `__%{key}__` (依 target_name 綁定之宿主專有名詞)。
        """
        if not content:
            return ""

        cur_dir = os.path.dirname(os.path.abspath(current_dst_path))
        doc_basename = os.path.basename(current_dst_path)
        project_root = self._resolve_project_root()

        check_unenclosed_tags(content, doc_name=doc_basename)

        literal_blocks: List[str] = []

        def _mask_stage2_literal(m: re.Match) -> str:
            idx = len(literal_blocks)
            literal_blocks.append(m.group(1) + m.group(2))
            return f"\x00YSCB_LITERAL_BLOCK_{idx}\x00"

        content = LITERAL_FENCED_BLOCK_REGEX.sub(_mask_stage2_literal, content)

        def _replace_in_fenced_block(match: re.Match) -> str:
            block_text = match.group(0)
            has_local = "__#{" in block_text
            has_proj = "__${" in block_text or "__$(" in block_text
            has_noun = "__%{" in block_text
            if not has_local and not has_proj and not has_noun:
                return block_text
            if has_local:
                block_text = LOCAL_URI_INNER_REGEX.sub(
                    lambda m: _resolve_local_uri_tag(m.group(1).strip(), cur_dir, deployment_map, doc_basename),
                    block_text,
                )
            if has_proj:
                block_text = PROJECT_URI_INNER_REGEX.sub(
                    lambda m: _resolve_project_uri_tag(
                        m.group(2).strip(),
                        anchor=m.group(1).strip() if m.group(1) else None,
                        project_root=project_root,
                        deployment_map=deployment_map,
                        doc_basename=doc_basename,
                    ),
                    block_text,
                )
            if has_noun:
                block_text = LOCALE_NOUN_INNER_REGEX.sub(
                    lambda m: _resolve_locale_noun_tag(m.group(1).strip(), target_name, doc_basename),
                    block_text,
                )
            block_text = re.sub(r"(?<![a-zA-Z0-9_\+\-]:)/{2,}", "/", block_text)
            return block_text

        def _replace_in_code_span(match: re.Match) -> str:
            span_text = match.group(0)
            inner = span_text[1:-1]
            has_local = "__#{" in inner
            has_proj = "__${" in inner or "__$(" in inner
            has_noun = "__%{" in inner
            if not has_local and not has_proj and not has_noun:
                return span_text

            m_local_exact = LOCAL_URI_EXACT_REGEX.fullmatch(inner.strip())
            if m_local_exact:
                return _resolve_local_uri_tag(m_local_exact.group(1).strip(), cur_dir, deployment_map, doc_basename)

            m_proj_exact = PROJECT_URI_EXACT_REGEX.fullmatch(inner.strip())
            if m_proj_exact:
                anchor = m_proj_exact.group(1).strip() if m_proj_exact.group(1) else None
                return _resolve_project_uri_tag(
                    m_proj_exact.group(2).strip(),
                    anchor=anchor,
                    project_root=project_root,
                    deployment_map=deployment_map,
                    doc_basename=doc_basename,
                )

            if has_local:
                inner = LOCAL_URI_INNER_REGEX.sub(
                    lambda m: _resolve_local_uri_tag(m.group(1).strip(), cur_dir, deployment_map, doc_basename),
                    inner,
                )
            if has_proj:
                inner = PROJECT_URI_INNER_REGEX.sub(
                    lambda m: _resolve_project_uri_tag(
                        m.group(2).strip(),
                        anchor=m.group(1).strip() if m.group(1) else None,
                        project_root=project_root,
                        deployment_map=deployment_map,
                        doc_basename=doc_basename,
                    ),
                    inner,
                )
            if has_noun:
                inner = LOCALE_NOUN_INNER_REGEX.sub(
                    lambda m: _resolve_locale_noun_tag(m.group(1).strip(), target_name, doc_basename),
                    inner,
                )
            inner = re.sub(r"(?<![a-zA-Z0-9_\+\-]:)/{2,}", "/", inner)
            return f"`{inner}`"

        res_fenced = FENCED_CODE_BLOCK_REGEX.sub(_replace_in_fenced_block, content)
        res_spans = CODE_SPAN_REGEX.sub(_replace_in_code_span, res_fenced)
        res_clean = re.sub(r"\]\(`?([^`\r\n\)]+)`?\)", _clean_md_link_match, res_spans)
        for idx, clean_block in enumerate(literal_blocks):
            res_clean = res_clean.replace(f"\x00YSCB_LITERAL_BLOCK_{idx}\x00", clean_block)
        return res_clean

    def get_registered_tokens(self) -> List[Dict[str, Any]]:
        """自省查詢全系統已註冊的 Token 錨點清單。"""
        data = self.get_contributes_data()
        return data.get("token", [])

    def get_exported_artifacts(self) -> List[Dict[str, Any]]:
        """自省查詢全系統已宣告的 Export 資產清單。"""
        data = self.get_contributes_data()
        return data.get("export", [])

    def resolve_export_description(self, export_item: Dict[str, Any]) -> str:
        """
        解析 Export 資產之說明文字列（SSOT）：
        1. 若 export_item 已顯式提供非空 description（如 standard / template），直接返回。
        2. 若為 skill 且未於 contribute.json 重複定義 description，自動自 SKILL.md YAML Frontmatter 提取單一真理來源。
        """
        if not isinstance(export_item, dict):
            return ""
        explicit_desc = str(export_item.get("description") or "").strip()
        if explicit_desc:
            return explicit_desc

        exp_type = str(export_item.get("type", "")).strip()
        source_p = str(export_item.get("source", "")).strip()
        if exp_type not in ("skill", "skills") or not source_p:
            return ""

        real_src = self._resolve_source_path(source_p)
        if not real_src:
            return ""
        skill_md_path = os.path.join(real_src, "SKILL.md") if os.path.isdir(real_src) else real_src
        if not os.path.isfile(skill_md_path):
            return ""

        raw_md = self._read_file_content(skill_md_path)
        m_fm = re.match(r"\A---\r?\n([\s\S]*?)\r?\n---", raw_md)
        if not m_fm:
            return ""
        for line in m_fm.group(1).splitlines():
            m_desc = re.match(r"^\s*description\s*:\s*(.+?)\s*$", line)
            if m_desc:
                val = m_desc.group(1).strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                    val = val[1:-1]
                return val
        return ""

    def get_release_targets(self) -> List[Dict[str, Any]]:
        """自省查詢全系統已宣告的 Release Target 清單。"""
        data = self.get_contributes_data()
        return data.get("release_target", [])
