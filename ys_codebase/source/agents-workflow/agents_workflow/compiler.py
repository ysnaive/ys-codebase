"""
Artifact Factory Compiler for agents-workflow.
Implements the 6-Stage Semantic Pipeline:
Stage 1: 5-Step Multi-Pass Recursive State Machine for Content Token Resolution -> cache://
Stage 2: 3-Tier Contextual Semantic URI Resolution -> Target Deployments.
100% Python Standard Library, Zero Third-Party Dependency.
"""

import functools
import hashlib
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from core import uri
    from core import vfs
    from core.context import ExecutionContext, get_virtual_cwd
    from core.log import log_stream
except ImportError:
    uri = None
    vfs = None
    ExecutionContext = None
    get_virtual_cwd = None
    log_stream = None


def _warn_stderr(msg: str) -> None:
    if log_stream is not None:
        log_stream(msg + "\n", stream="stderr")


FENCED_CODE_BLOCK_REGEX = re.compile(r"```[\s\S]*?```")
LITERAL_BEGIN_LINE_REGEX = re.compile(r"^[ \t]*<!--\s*yscb:literal:begin\s*-->[ \t]*$")
LITERAL_END_LINE_REGEX = re.compile(r"^[ \t]*<!--\s*yscb:literal:end\s*-->[ \t]*$")
IGNORE_BEGIN_LINE_REGEX = re.compile(r"^[ \t]*<!--\s*yscb:ignore:begin\s*-->[ \t]*$")
IGNORE_END_LINE_REGEX = re.compile(r"^[ \t]*<!--\s*yscb:ignore:end\s*-->[ \t]*$")
CODE_SPAN_REGEX = re.compile(r"(`[^`\r\n]+`)")
UNENCLOSED_TAG_REGEX = re.compile(r"__(?:[@#%]\s*\{\s*[^}]+\s*\}|\$(?:\([^)]*\))?\{\s*[^}]+\s*\})__")

TOKEN_ANCHOR_INNER_REGEX = re.compile(r"__@\{\s*([A-Za-z0-9_]+)\s*\}__")
LOCAL_URI_INNER_REGEX = re.compile(r"__#\{\s*([^}]+)\s*\}__")
PROJECT_URI_INNER_REGEX = re.compile(r"__\$(?:\(\s*([^)]*?)\s*\))?\{\s*([^}]+)\s*\}__")
LOCAL_URI_BOUNDARY_REGEX = re.compile(r"(/*)__#\{\s*([^}]+)\s*\}__(/*)")
PROJECT_URI_BOUNDARY_REGEX = re.compile(r"(/*)__\$(?:\(\s*([^)]*?)\s*\))?\{\s*([^}]+)\s*\}__(/*)")
LOCALE_NOUN_INNER_REGEX = re.compile(r"__%\{\s*([A-Za-z0-9_.:-]+)\s*\}__")

LOCAL_URI_EXACT_REGEX = re.compile(r"^__#\{\s*([^}]+)\s*\}__$")
PROJECT_URI_EXACT_REGEX = re.compile(r"^__\$(?:\(\s*([^)]*?)\s*\))?\{\s*([^}]+)\s*\}__$")

URI_SCHEME_PREFIX_REGEX = re.compile(r"^[a-zA-Z0-9_\+\-]+://")
DOUBLE_SLASH_CLEAN_REGEX = re.compile(r"(?<![a-zA-Z0-9_\+\-]:)/{2,}")
MD_LINK_BACKTICK_CLEAN_REGEX = re.compile(r"\]\(`?([^`\r\n\)]+)`?\)")
FRONTMATTER_BLOCK_REGEX = re.compile(r"\A---\r?\n([\s\S]*?)\r?\n---")
FRONTMATTER_DESC_LINE_REGEX = re.compile(r"^\s*description\s*:\s*(.+?)\s*$")

_WORKFLOW_FALLBACK_REL_MAP: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("workflow.docs://", ("docs",)),
    ("workflow.plans://", ("plans",)),
    ("workflow.archived://", ("plans", "archived")),
    ("workflow.roadmap://", ("plans", "roadmap")),
)


def _resolve_workflow_uri_fallback(tag_uri: str, project_root: str) -> Optional[str]:
    """當 URI 引擎離線或未掛載時，針對內建 workflow.* 語意協定提供一致的專案相對退避解析。"""
    if not tag_uri or not project_root:
        return None
    for prefix, rel_parts in _WORKFLOW_FALLBACK_REL_MAP:
        if tag_uri.startswith(prefix):
            tail = tag_uri[len(prefix):]
            return os.path.join(project_root, *rel_parts, tail)
    return None


def _clean_expanded_uri_boundary(
    segment: str,
    match_start: int,
    leading_slashes: str,
    resolved: str,
    trailing_slashes: str,
) -> str:
    """僅於展開後之 URI 字串及其緊鄰斜線接合邊界正規化重複斜線，保護區段內其他註解或運算子。"""
    if leading_slashes and match_start > 0 and segment[match_start - 1] == ":":
        if not URI_SCHEME_PREFIX_REGEX.match(resolved):
            resolved = DOUBLE_SLASH_CLEAN_REGEX.sub("/", resolved)
        combined_tail = f"{resolved}{trailing_slashes}"
        if not URI_SCHEME_PREFIX_REGEX.match(combined_tail):
            combined_tail = DOUBLE_SLASH_CLEAN_REGEX.sub("/", combined_tail)
        return f"{leading_slashes}{combined_tail}"

    combined = f"{leading_slashes}{resolved}{trailing_slashes}"
    if not URI_SCHEME_PREFIX_REGEX.match(combined):
        combined = DOUBLE_SLASH_CLEAN_REGEX.sub("/", combined)
    return combined


def _preprocess_directives(
    content: str,
    strip_literal_markers: bool,
    literal_blocks: Optional[List[str]] = None,
    doc_name: str = "",
    emit_warnings: bool = True,
) -> Tuple[str, List[str]]:
    """
    解析並處理 `yscb:ignore:begin/end` 與 `yscb:literal:begin/end` 區塊指令。
    - `ignore` 區塊（非位於 `literal` 保護區內時）直接整段抹除。
    - `literal` 區塊以深度計數支援巢狀自舉，替換為遮罩佔位符並存入 `literal_blocks`。
    """
    if literal_blocks is None:
        literal_blocks = []
    if not content:
        return "", literal_blocks
    if "yscb:literal:" not in content and "yscb:ignore:" not in content:
        return content, literal_blocks

    target_str = f" in '{doc_name}'" if doc_name else ""
    lines = content.splitlines(keepends=True)
    out_chunks: List[str] = []
    cur_literal_lines: List[str] = []
    literal_depth = 0
    ignore_depth = 0

    for line in lines:
        stripped = line.rstrip("\r\n")
        if ignore_depth > 0:
            if IGNORE_BEGIN_LINE_REGEX.match(stripped):
                ignore_depth += 1
            elif IGNORE_END_LINE_REGEX.match(stripped):
                ignore_depth -= 1
            continue

        if literal_depth > 0:
            if LITERAL_BEGIN_LINE_REGEX.match(stripped):
                literal_depth += 1
                cur_literal_lines.append(line)
            elif LITERAL_END_LINE_REGEX.match(stripped):
                literal_depth -= 1
                if literal_depth == 0:
                    if not strip_literal_markers:
                        cur_literal_lines.append(line)
                    idx = len(literal_blocks)
                    literal_blocks.append("".join(cur_literal_lines))
                    cur_literal_lines = []
                    out_chunks.append(f"\x00YSCB_LITERAL_BLOCK_{idx}\x00")
                else:
                    cur_literal_lines.append(line)
            else:
                cur_literal_lines.append(line)
            continue

        if IGNORE_BEGIN_LINE_REGEX.match(stripped):
            ignore_depth = 1
        elif IGNORE_END_LINE_REGEX.match(stripped):
            if emit_warnings:
                _warn_stderr(f"[compiler:warning] Unmatched '<!-- yscb:ignore:end -->' detected{target_str}")
        elif LITERAL_BEGIN_LINE_REGEX.match(stripped):
            literal_depth = 1
            cur_literal_lines = []
            if not strip_literal_markers:
                cur_literal_lines.append(line)
        elif LITERAL_END_LINE_REGEX.match(stripped):
            if emit_warnings:
                _warn_stderr(f"[compiler:warning] Unmatched '<!-- yscb:literal:end -->' detected{target_str}")
        else:
            out_chunks.append(line)

    if ignore_depth > 0 and emit_warnings:
        _warn_stderr(f"[compiler:warning] Unclosed '<!-- yscb:ignore:begin -->' detected{target_str}")
    if literal_depth > 0:
        if emit_warnings:
            _warn_stderr(f"[compiler:warning] Unclosed '<!-- yscb:literal:begin -->' detected{target_str}")
        idx = len(literal_blocks)
        literal_blocks.append("".join(cur_literal_lines))
        out_chunks.append(f"\x00YSCB_LITERAL_BLOCK_{idx}\x00")

    return "".join(out_chunks), literal_blocks


def check_unenclosed_tags(
    content: str,
    doc_name: str = "",
    *,
    _preprocessed_text: Optional[str] = None,
) -> None:
    """檢查並輸出未被反引號包裹的裸佔位符警示 (Unenclosed Placeholder Warning Gate)。"""
    if not content and not _preprocessed_text:
        return
    if _preprocessed_text is not None:
        masked_text = _preprocessed_text
    else:
        masked_text, _ = _preprocess_directives(
            content, strip_literal_markers=True, doc_name=doc_name, emit_warnings=False
        )
    if "__" not in masked_text:
        return
    clean_text = FENCED_CODE_BLOCK_REGEX.sub("", masked_text)
    clean_text = CODE_SPAN_REGEX.sub("", clean_text)
    if "__" not in clean_text:
        return
    matches = UNENCLOSED_TAG_REGEX.findall(clean_text)
    if matches:
        for m in dict.fromkeys(matches):
            target_str = f" in '{doc_name}'" if doc_name else ""
            _warn_stderr(
                f"[compiler:warning] Unenclosed placeholder tag '{m}' detected{target_str} (must be enclosed in backticks '`...`')"
            )


@functools.lru_cache(maxsize=128)
def make_token_tag_regex(token_name: str) -> re.Pattern:
    """構造匹配指定 Token 標籤之正則表達式，支援大括號內部微量空格。"""
    return re.compile(r"__@\{\s*" + re.escape(token_name) + r"\s*\}__")


@functools.lru_cache(maxsize=128)
def make_standalone_tag_regex(token_name: str) -> re.Pattern:
    """構造匹配單行獨立 Token 錨點之正則表達式（嚴格要求整行僅含該錨點與空白）。"""
    return re.compile(
        r"(?:^|(?<=\x00))[ \t]*`__@\{\s*" + re.escape(token_name) + r"\s*\}__`(?:[ \t]*\r?\n|[ \t]*$)",
        re.MULTILINE,
    )


def _is_uri_suffix_match(longer: str, shorter: str) -> bool:
    """檢查 shorter 是否在路徑分隔邊界上後綴匹配 longer。"""
    if not longer or not shorter:
        return False
    return longer == shorter or longer.endswith("/" + shorter) or longer.endswith("://" + shorter)


def _lookup_deployed_abs_path(tag_uri: str, deployment_map: Dict[str, str]) -> Optional[str]:
    """
    於 deployment_map 中查找目標 URI 的絕對路徑：
    1. 精確鍵值匹配（含移除尾端斜線之正規化匹配）
    2. 短名後綴邊界匹配（僅限 module://、config:// 或純短名，嚴禁攔截 project://、workflow.* 與 yscb.*）
    """
    if not deployment_map or not tag_uri:
        return None
    if tag_uri in deployment_map:
        return deployment_map[tag_uri]
    norm_uri = tag_uri.rstrip("/")
    if norm_uri in deployment_map:
        return deployment_map[norm_uri]
    if not norm_uri.startswith(("project://", "workflow.", "yscb.")):
        for s_key, cand_abs in deployment_map.items():
            norm_key = s_key.rstrip("/")
            if _is_uri_suffix_match(norm_uri, norm_key) or _is_uri_suffix_match(norm_key, norm_uri):
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
    extra_deployment_maps: Optional[List[Tuple[str, Dict[str, str]]]] = None,
    project_root: Optional[str] = None,
) -> str:
    """解算 Stage 2 自身相對路徑標籤 `__#{uri}__`（支援多重 Target 拓撲映射並聯去重）。"""
    trailing_slash = tag_uri.endswith("/")

    # Tier 1: 命中發布拓撲映射表（支援單一或多重 Target 映射去重並聯）
    mapped_paths: List[str] = []
    mapped_abs = _lookup_deployed_abs_path(tag_uri, deployment_map)
    if mapped_abs:
        mapped_paths.append(_format_relative_local_path(mapped_abs, cur_dir, trailing_slash))

    if extra_deployment_maps:
        for _, extra_map in extra_deployment_maps:
            ext_abs = _lookup_deployed_abs_path(tag_uri, extra_map)
            if ext_abs:
                ext_rel = _format_relative_local_path(ext_abs, cur_dir, trailing_slash)
                if ext_rel not in mapped_paths:
                    mapped_paths.append(ext_rel)

    if mapped_paths:
        return " / ".join(mapped_paths)

    # Tier 2: 專案級語意協議與內建 workflow.* 退避
    if "://" in tag_uri:
        real_p = None
        if uri:
            try:
                real_p = uri.resolve(tag_uri, interactive=False)
            except Exception:
                real_p = None
        if not real_p and project_root:
            real_p = _resolve_workflow_uri_fallback(tag_uri, project_root)
        if real_p:
            return _format_relative_local_path(real_p, cur_dir, trailing_slash)

    # Tier 3: 未知協議安全降級
    _warn_stderr(f"[compiler:warning] Unresolved semantic URI tag: '{tag_uri}' in '{doc_basename}'")
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
            anchor_abs = _resolve_workflow_uri_fallback(anchor_str, project_root)

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

    if not t_abs and "://" in tag_uri:
        if uri:
            try:
                t_abs = uri.resolve(tag_uri, interactive=False)
            except Exception as e:
                t_abs = _resolve_workflow_uri_fallback(tag_uri, project_root)
                if not t_abs:
                    _warn_stderr(f"[compiler:warning] Failed to resolve project URI '{tag_uri}' in '{doc_basename}': {e}")
        else:
            t_abs = _resolve_workflow_uri_fallback(tag_uri, project_root)

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


def _resolve_locale_noun_tag(
    noun_key: str,
    target_name: Optional[Union[str, List[str]]],
    doc_basename: str,
) -> str:
    """解算 Stage 2 目標宿主專有名詞標籤 `__%{key}__`（支援單一或多重 Target 並聯去重）。"""
    try:
        from core import locale as core_locale
        base_chain = core_locale.get_active_chain()
        clean_base = [c for c in base_chain if not c.startswith("nouns-")]

        if isinstance(target_name, (list, tuple)):
            t_list = [str(t).strip() for t in target_name if str(t).strip()]
        elif isinstance(target_name, str) and target_name.strip():
            t_list = [target_name.strip()]
        else:
            t_list = []

        if not t_list:
            hit = core_locale.resolve_raw(noun_key, module="agents-workflow", chain=base_chain)
            if hit is not None:
                return core_locale.t(noun_key, module="agents-workflow", chain=base_chain)
        else:
            rendered_values: List[str] = []
            for t_item in t_list:
                t_dialect = f"nouns-{t_item}"
                target_chain = [t_dialect, "nouns-antigravity"] + clean_base
                hit = core_locale.resolve_raw(noun_key, module="agents-workflow", chain=target_chain)
                if hit is not None:
                    val = core_locale.t(noun_key, module="agents-workflow", chain=target_chain)
                    if val and val not in rendered_values:
                        rendered_values.append(val)
            if rendered_values:
                return " / ".join(rendered_values)
    except Exception:
        pass
    _warn_stderr(f"[compiler:warning] Unresolved locale noun tag: '{noun_key}' in '{doc_basename}'")
    return f"__%{{{noun_key}}}__"


def _clean_md_link_match(match: re.Match) -> str:
    """清理 Markdown 超連結括號內殘留的多餘反引號與連續斜線: [text](`path`) -> [text](path)。"""
    path = match.group(1)
    if not URI_SCHEME_PREFIX_REGEX.match(path):
        path = DOUBLE_SLASH_CLEAN_REGEX.sub("/", path)
    return f"]({path})"


def _substitute_stage2_tags_in_segment(
    segment: str,
    cur_dir: str,
    project_root: str,
    deployment_map: Dict[str, str],
    doc_basename: str,
    target_name: Optional[Union[str, List[str]]],
    extra_deployment_maps: Optional[List[Tuple[str, Dict[str, str]]]] = None,
) -> str:
    """於單一文字區段（fenced code block 或 inline code span）內展開 Stage 2 標籤，僅對展開路徑邊界清理重複斜線。"""
    has_local = "__#{" in segment
    has_proj = "__${" in segment or "__$(" in segment
    has_noun = "__%{" in segment
    if not has_local and not has_proj and not has_noun:
        return segment
    if has_local:
        def _sub_local(m: re.Match) -> str:
            resolved = _resolve_local_uri_tag(
                m.group(2).strip(),
                cur_dir,
                deployment_map,
                doc_basename,
                extra_deployment_maps,
                project_root=project_root,
            )
            return _clean_expanded_uri_boundary(segment, m.start(), m.group(1), resolved, m.group(3))

        segment = LOCAL_URI_BOUNDARY_REGEX.sub(_sub_local, segment)
    if has_proj:
        def _sub_proj(m: re.Match) -> str:
            resolved = _resolve_project_uri_tag(
                m.group(3).strip(),
                anchor=m.group(2).strip() if m.group(2) else None,
                project_root=project_root,
                deployment_map=deployment_map,
                doc_basename=doc_basename,
            )
            return _clean_expanded_uri_boundary(segment, m.start(), m.group(1), resolved, m.group(4))

        segment = PROJECT_URI_BOUNDARY_REGEX.sub(_sub_proj, segment)
    if has_noun:
        segment = LOCALE_NOUN_INNER_REGEX.sub(
            lambda m: _resolve_locale_noun_tag(m.group(1).strip(), target_name, doc_basename),
            segment,
        )
    return segment


class ArtifactCompiler:
    """
    協議產物工廠編譯器 (Artifact Factory Compiler).
    負責解析已安裝模組之 contributes (export, insert, token, release_target)，
    執行 Stage 1 內容展開快取與 Stage 2 URI 相對路徑轉譯。
    """

    def __init__(self, host_dir: Optional[str] = None):
        self.host_dir = host_dir
        self.module_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._stage1_insert_cache: Optional[Dict[str, str]] = None
        self._source_file_cache: Dict[str, Tuple[int, int, str, str, str]] = {}
        self._resolved_source_path_cache: Dict[Tuple[str, str], str] = {}

    def _resolve_source_path(self, path_or_uri: str) -> str:
        """解析語意 URI 或相對路徑至本機實體檔案/目錄路徑。"""
        if not path_or_uri:
            return ""

        cache_key = (self.module_root, path_or_uri)
        cached_path = self._resolved_source_path_cache.get(cache_key)
        if cached_path and os.path.exists(cached_path):
            return cached_path

        sub_path = path_or_uri
        target_root = self.module_root
        scheme = ""
        if "://" in path_or_uri:
            scheme, parts = path_or_uri.split("://", 1)
            if "/" in parts:
                mod_name, rel_p = parts.split("/", 1)
                sub_path = rel_p
                if scheme == "module" and mod_name and mod_name != os.path.basename(self.module_root):
                    sibling_root = os.path.join(os.path.dirname(self.module_root), mod_name)
                    if os.path.isdir(sibling_root):
                        target_root = sibling_root

        if scheme in ("", "module"):
            local_cand = os.path.join(target_root, sub_path.replace("/", os.sep))
            if os.path.exists(local_cand):
                self._resolved_source_path_cache[cache_key] = local_cand
                return local_cand

        if uri and "://" in path_or_uri:
            try:
                real_p = uri.resolve(path_or_uri, interactive=False)
                if os.path.exists(real_p):
                    self._resolved_source_path_cache[cache_key] = real_p
                    return real_p
            except Exception:
                pass

        if scheme not in ("", "module"):
            local_cand = os.path.join(target_root, sub_path.replace("/", os.sep))
            if os.path.exists(local_cand):
                self._resolved_source_path_cache[cache_key] = local_cand
                return local_cand

        if os.path.exists(path_or_uri):
            self._resolved_source_path_cache[cache_key] = path_or_uri
            return path_or_uri

        return ""

    def _read_and_cache_physical_file(self, abs_path: str) -> Tuple[str, str, str]:
        """單次讀取實體檔案並快取 (mtime_ns, size, content, sha1_hex, sha256_hex)。"""
        try:
            st = os.stat(abs_path)
            cached = self._source_file_cache.get(abs_path)
            if cached and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
                return cached[2], cached[3], cached[4]
        except Exception:
            st = None

        content = ""
        raw_bytes: Optional[bytes] = None
        try:
            with open(abs_path, "rb") as bf:
                raw_bytes = bf.read()
            content = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            if raw_bytes is not None:
                content = raw_bytes.decode("utf-8", errors="replace")
        except Exception:
            try:
                if vfs:
                    content = vfs.read_text(abs_path)
            except Exception:
                content = ""

        if st is not None:
            norm_bytes = content.replace("\r\n", "\n").encode("utf-8")
            sha1_hex = hashlib.sha1(norm_bytes).hexdigest()
            sha256_hex = hashlib.sha256(norm_bytes).hexdigest()
            self._source_file_cache[abs_path] = (st.st_mtime_ns, st.st_size, content, sha1_hex, sha256_hex)
            return content, sha1_hex, sha256_hex

        norm_bytes = content.replace("\r\n", "\n").encode("utf-8")
        return content, hashlib.sha1(norm_bytes).hexdigest(), hashlib.sha256(norm_bytes).hexdigest()

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
                content, _, _ = self._read_and_cache_physical_file(abs_f)
                results.append((rel_f, abs_f, content))
        return results

    def _read_file_content(self, path_or_uri: str) -> str:
        """安全讀取語意 URI 或本機檔案文字，支援 module.root 與 module.source.root 自適應降級。"""
        real_p = self._resolve_source_path(path_or_uri)
        if real_p and (vfs.is_file(real_p) if vfs else os.path.isfile(real_p)):
            content, _, _ = self._read_and_cache_physical_file(real_p)
            return content

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
            "release_target": [],
        }

        try:
            from core import contributes
            data = contributes.get("agents-workflow")
            if isinstance(data, dict):
                for k in ("export", "insert", "token", "release_target"):
                    if k in data and isinstance(data[k], list):
                        if k == "export":
                            for item in data[k]:
                                if isinstance(item, dict):
                                    norm_item = dict(item)
                                    if str(norm_item.get("type", "")).strip().lower() in ("workflow", "workflows"):
                                        norm_item["type"] = "skill"
                                    aggregated[k].append(norm_item)
                                else:
                                    aggregated[k].append(item)
                        else:
                            aggregated[k].extend(data[k])
        except Exception:
            pass

        return aggregated

    def _resolve_insert_value(
        self,
        ins: Dict[str, Any],
        token_name: str,
        context: Optional[Any] = None,
        active_cache: Optional[Dict[str, str]] = None,
    ) -> str:
        """解析單一 insert 規則之原始字串內容（嚴格確保 active_cache 快取 _preprocess_directives 之前的原始字串）。"""
        ins_type = ins.get("type", "const")
        raw_val = ins.get("value", "")
        cache_key = f"{ins_type}:{token_name}:{raw_val}"

        if active_cache is not None and ins_type in ("uri", "computed") and cache_key in active_cache:
            val_content = active_cache[cache_key]
        elif ins_type == "uri":
            val_content = self._read_file_content(str(raw_val))
            if active_cache is not None:
                active_cache[cache_key] = val_content
        elif ins_type == "computed":
            try:
                from core.symbols import resolve_callable
                target_fn = resolve_callable(str(raw_val), context=context)
                comp_res = target_fn(context)
                val_content = "" if comp_res is None else str(comp_res)
                if active_cache is not None:
                    active_cache[cache_key] = val_content
            except Exception as e:
                _warn_stderr(f"[compiler:warning] Failed to resolve computed token '{token_name}' ({raw_val}): {e}")
                val_content = ""
        else:
            val_content = str(raw_val)

        return "" if val_content is None else val_content

    def resolve_single_artifact(
        self,
        content: str,
        inserts: List[Dict[str, Any]],
        max_passes: int = 10,
        context: Optional[Any] = None,
        _insert_cache: Optional[Dict[str, str]] = None,
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

        active_cache = _insert_cache if _insert_cache is not None else self._stage1_insert_cache

        resolved_text, literal_blocks = _preprocess_directives(
            content, strip_literal_markers=False, emit_warnings=True
        )
        check_unenclosed_tags(content, _preprocessed_text=resolved_text)
        if "__@{" not in resolved_text:
            for idx, raw_block in enumerate(literal_blocks):
                resolved_text = resolved_text.replace(f"\x00YSCB_LITERAL_BLOCK_{idx}\x00", raw_block)
            return resolved_text

        pass_count = 0

        while pass_count < max_passes:
            pass_count += 1

            # Step 1: 建立快照（僅自代碼塊中提取）
            code_spans = CODE_SPAN_REGEX.findall(resolved_text)
            current_tokens = []
            for cs in code_spans:
                if "__@{" in cs:
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
                    mode = ins.get("mode", "replace")
                    raw_val = ins.get("value", "")

                    val_content = self._resolve_insert_value(
                        ins, token_name, context=context, active_cache=active_cache
                    )
                    if val_content:
                        val_content, literal_blocks = _preprocess_directives(
                            val_content,
                            strip_literal_markers=False,
                            literal_blocks=literal_blocks,
                            doc_name=str(raw_val),
                            emit_warnings=True,
                        )

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

                standalone_tag_regex = make_standalone_tag_regex(token_name)
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

                    resolved_text = standalone_tag_regex.sub(lambda _: combined_str, resolved_text)

                if token_tag_regex.search(resolved_text):
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
                purge_regex = make_standalone_tag_regex(token_name)
                resolved_text = purge_regex.sub("", resolved_text)
                token_tag_regex = make_token_tag_regex(token_name)

                if token_tag_regex.search(resolved_text):
                    def _purge_span_tag(match: re.Match) -> str:
                        span = match.group(0)
                        inner = span[1:-1]
                        if token_tag_regex.search(inner):
                            return f"`{token_tag_regex.sub('', inner)}`"
                        return span

                    resolved_text = CODE_SPAN_REGEX.sub(_purge_span_tag, resolved_text)

            # Step 4: 遞迴檢查是否仍有新 Token
            if "__@{" not in resolved_text:
                break
            code_spans = CODE_SPAN_REGEX.findall(resolved_text)
            has_remaining = any(TOKEN_ANCHOR_INNER_REGEX.search(cs) for cs in code_spans)
            if not has_remaining:
                break

        for idx, raw_block in enumerate(literal_blocks):
            resolved_text = resolved_text.replace(f"\x00YSCB_LITERAL_BLOCK_{idx}\x00", raw_block)
        return resolved_text

    def _write_cache_file(self, cache_uri: str, content: str) -> str:
        """寫入中繼快取檔案 (支援 vfs/cache URI 與本地原子寫入 fallback)。"""
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
                yscb_root = uri.resolve_yscb_root()
                sub_rel = cache_uri.replace("cache://agents-workflow/resolved_contents/", "")
                local_cache = os.path.join(
                    yscb_root,
                    ".cache",
                    "agents-workflow",
                    "resolved_contents",
                    sub_rel.replace("/", os.sep),
                )
        else:
            sub_rel = cache_uri.replace("cache://agents-workflow/resolved_contents/", "")
            local_cache = os.path.join(
                os.path.dirname(os.path.dirname(self.module_root)),
                ".cache",
                "agents-workflow",
                "resolved_contents",
                sub_rel.replace("/", os.sep),
            )

        if vfs:
            vfs.write_text(local_cache, content, atomic=True)
            return local_cache

        os.makedirs(os.path.dirname(local_cache), exist_ok=True)
        with open(local_cache, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        return local_cache

    def compile_stage1(self) -> Dict[str, Any]:
        """
        執行 Stage 1 全量段落佔位符解算：
        將所有 export 項目物化寫入 cache://agents-workflow/resolved_contents/。
        支援單檔與目錄級 (Skill Package) 遞迴掃描與 Stage 1 展開，並附帶單通計算之 SHA-256 摘要。
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
            "skills": "skills",
            "workflow": "skills",
            "workflows": "skills",
        }

        stage1_insert_cache: Dict[str, str] = {}
        self._stage1_insert_cache = stage1_insert_cache
        ctx = ExecutionContext("agents-workflow", "compile", []) if ExecutionContext else None
        try:
            for exp in exports:
                if not isinstance(exp, dict):
                    continue
                raw_type = str(exp.get("type", "template")).strip()
                exp_type = "skill" if raw_type.lower() in ("workflow", "workflows") else raw_type
                if exp.get("type") != exp_type:
                    exp = dict(exp)
                    exp["type"] = exp_type
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
                            if rel_f.endswith((".md", ".txt", ".json", ".yaml", ".yml", ".sh")):
                                stage1_content = self.resolve_single_artifact(
                                    raw_text, inserts, context=ctx, _insert_cache=stage1_insert_cache
                                )
                            else:
                                stage1_content = raw_text

                            cache_uri = f"{cache_target_root}/{sub_folder}/{skill_pkg_name}/{rel_f}"
                            actual_cache = self._write_cache_file(cache_uri, stage1_content)
                            content_sha256 = hashlib.sha256(stage1_content.encode("utf-8")).hexdigest()

                            resolved_items.append({
                                "export": exp,
                                "sub_folder": sub_folder,
                                "base_name": os.path.basename(rel_f),
                                "rel_path": rel_f,
                                "cache_uri": actual_cache,
                                "content": stage1_content,
                                "sha256": content_sha256,
                                "is_skill": True,
                                "skill_name": skill_pkg_name,
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
                        stage1_content = self.resolve_single_artifact(
                            raw_content, inserts, context=ctx, _insert_cache=stage1_insert_cache
                        )

                        cache_uri = f"{cache_target_root}/{sub_folder}/{base_name}"
                        actual_cache = self._write_cache_file(cache_uri, stage1_content)
                        content_sha256 = hashlib.sha256(stage1_content.encode("utf-8")).hexdigest()

                        resolved_items.append({
                            "export": exp,
                            "sub_folder": sub_folder,
                            "base_name": base_name,
                            "rel_path": base_name,
                            "cache_uri": actual_cache,
                            "content": stage1_content,
                            "sha256": content_sha256,
                            "is_skill": (exp_type in ("skill", "skills")),
                            "skill_name": exp_name or os.path.splitext(base_name)[0],
                        })
                    except Exception as e:
                        errors.append(f"Failed Stage 1 for {base_name}: {e}")
        finally:
            self._stage1_insert_cache = None

        return {
            "success": len(errors) == 0,
            "resolved_items": resolved_items,
            "inserted_count": len(inserts),
            "tokens_count": len(tokens),
            "errors": errors,
        }

    def _resolve_project_root(self) -> str:
        """取得正規化之 project_root 絕對路徑。"""
        if self.host_dir:
            return os.path.normpath(os.path.abspath(self.host_dir))
        if uri:
            try:
                return os.path.normpath(os.path.abspath(uri.resolve("project://", interactive=False)))
            except Exception:
                pass
        cwd_p = str(get_virtual_cwd()) if get_virtual_cwd is not None else "."
        return os.path.normpath(os.path.abspath(cwd_p))

    def resolve_stage2_uri(
        self,
        content: str,
        current_dst_path: str,
        deployment_map: Dict[str, str],
        target_name: Optional[Union[str, List[str]]] = None,
        extra_deployment_maps: Optional[List[Tuple[str, Dict[str, str]]]] = None,
    ) -> str:
        """
        Stage 2: 依三層重映射階層動態轉譯 `__#{uri}__` (自身相對路徑)、`__${uri}__` / `__$(anchor){uri}__` (錨點/專案相對路徑)
        與 `__%{key}__` (依 target_name 綁定之宿主專有名詞，支援多重 Target 並聯去重)。
        """
        if not content:
            return ""

        cur_dir = os.path.dirname(os.path.abspath(current_dst_path))
        doc_basename = os.path.basename(current_dst_path)
        project_root = self._resolve_project_root()

        content, literal_blocks = _preprocess_directives(
            content, strip_literal_markers=True, doc_name=doc_basename, emit_warnings=False
        )
        check_unenclosed_tags(content, doc_name=doc_basename, _preprocessed_text=content)

        if "__#{" not in content and "__${" not in content and "__$(" not in content and "__%{" not in content:
            for idx, clean_block in enumerate(literal_blocks):
                content = content.replace(f"\x00YSCB_LITERAL_BLOCK_{idx}\x00", clean_block)
            return content

        fenced_blocks: List[str] = []

        def _replace_and_mask_fenced_block(match: re.Match) -> str:
            expanded = _substitute_stage2_tags_in_segment(
                match.group(0),
                cur_dir=cur_dir,
                project_root=project_root,
                deployment_map=deployment_map,
                doc_basename=doc_basename,
                target_name=target_name,
                extra_deployment_maps=extra_deployment_maps,
            )
            idx = len(fenced_blocks)
            fenced_blocks.append(expanded)
            return f"\x00YSCB_FENCED_BLOCK_{idx}\x00"

        def _replace_in_code_span(match: re.Match) -> str:
            span_text = match.group(0)
            inner = span_text[1:-1]
            if "__#{" not in inner and "__${" not in inner and "__$(" not in inner and "__%{" not in inner:
                return span_text

            m_local_exact = LOCAL_URI_EXACT_REGEX.fullmatch(inner.strip())
            if m_local_exact:
                return _resolve_local_uri_tag(
                    m_local_exact.group(1).strip(),
                    cur_dir,
                    deployment_map,
                    doc_basename,
                    extra_deployment_maps,
                    project_root=project_root,
                )

            m_proj_exact = PROJECT_URI_EXACT_REGEX.fullmatch(inner.strip())
            if m_proj_exact:
                anchor = m_proj_exact.group(1).strip() if m_proj_exact.group(1) else None
                resolved = _resolve_project_uri_tag(
                    m_proj_exact.group(2).strip(),
                    anchor=anchor,
                    project_root=project_root,
                    deployment_map=deployment_map,
                    doc_basename=doc_basename,
                )
                return resolved if anchor else f"`{resolved or './'}`"

            new_inner = _substitute_stage2_tags_in_segment(
                inner,
                cur_dir=cur_dir,
                project_root=project_root,
                deployment_map=deployment_map,
                doc_basename=doc_basename,
                target_name=target_name,
                extra_deployment_maps=extra_deployment_maps,
            )
            return f"`{new_inner}`"

        res_fenced = FENCED_CODE_BLOCK_REGEX.sub(_replace_and_mask_fenced_block, content)
        res_spans = CODE_SPAN_REGEX.sub(_replace_in_code_span, res_fenced)
        res_clean = MD_LINK_BACKTICK_CLEAN_REGEX.sub(_clean_md_link_match, res_spans)
        for idx, fenced_block in enumerate(fenced_blocks):
            res_clean = res_clean.replace(f"\x00YSCB_FENCED_BLOCK_{idx}\x00", fenced_block)
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
        if exp_type.lower() in ("workflow", "workflows"):
            exp_type = "skill"
        source_p = str(export_item.get("source", "")).strip()
        if exp_type not in ("skill", "skills") or not source_p:
            return ""

        real_src = self._resolve_source_path(source_p)
        if not real_src:
            return ""
        skill_md_path = os.path.join(real_src, "SKILL.md") if os.path.isdir(real_src) else real_src
        if not os.path.isfile(skill_md_path):
            return ""

        raw_md, _, _ = self._read_and_cache_physical_file(skill_md_path)
        m_fm = FRONTMATTER_BLOCK_REGEX.match(raw_md)
        if not m_fm:
            return ""
        for line in m_fm.group(1).splitlines():
            m_desc = FRONTMATTER_DESC_LINE_REGEX.match(line)
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
