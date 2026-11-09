"""
agents_workflow.plans._common — Plans 工具鏈共用基礎設施（語意 URI 解析、Markdown 標頭提取、生命周期完成度判定、目標投影規則與變更日誌表格解析 SSOT）。
"""

import os
import re
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from core.context import get_virtual_cwd

DEFAULT_URI_FALLBACKS: Mapping[str, str] = MappingProxyType({
    "workflow.plans://": "plans",
    "workflow.archived://": "plans/archived",
    "workflow.roadmap://": "plans/roadmap",
    "workflow.docs://": "docs",
    "project://": ".",
})

_CHANGELOG_UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")
_CHANGELOG_SEP_LINE_RE = re.compile(r"^\|?\s*[-:]+\s*\|")
_CHANGELOG_HEADER_FIRST_CELLS = frozenset({"日期時間", "日期", "timestamp", "date", "time"})


def resolve_plan_uri(
    uri_str: str,
    default_fallback: Optional[str] = None,
    host_dir: Optional[Union[str, Path]] = None,
) -> Optional[Path]:
    """
    安全解析語意 URI；若無 core 上下文或解析失敗，則依 default_fallback 或 DEFAULT_URI_FALLBACKS 退避（支援帶子路徑之 workflow.*:// URI）。

    Args:
        uri_str: 語意 URI 字串（如 'workflow.plans://'、'workflow.archived://'、'project://' 或帶子路徑）
        default_fallback: 選填退避相對路徑；若未指定則查表 DEFAULT_URI_FALLBACKS
        host_dir: 選填宿主基準目錄；當 host_dir is None 時維持 Path(get_virtual_cwd()).resolve()

    Returns:
        Optional[Path]: 解析後之絕對路徑，若無對應退避則回傳 None
    """
    if not uri_str:
        return None
    try:
        from core.uri import resolve

        resolved = resolve(uri_str, interactive=False)
        if resolved and not str(resolved).startswith("!"):
            return Path(resolved).resolve()
    except Exception:
        pass

    base = (
        Path(host_dir).resolve()
        if host_dir is not None
        else Path(get_virtual_cwd()).resolve()
    )

    if default_fallback is not None:
        tail = ""
        if "://" in uri_str:
            tail = uri_str.split("://", 1)[1].lstrip("/\\")
        root_p = (base / default_fallback).resolve() if default_fallback else base
        return (root_p / tail).resolve() if tail else root_p

    for prefix, rel_dir in DEFAULT_URI_FALLBACKS.items():
        if uri_str == prefix or uri_str.startswith(prefix):
            tail = uri_str[len(prefix) :].lstrip("/\\")
            eff_rel = rel_dir
            if prefix == "workflow.roadmap://":
                if not (base / "plans" / "roadmap").exists() and (base / "roadmap").exists():
                    eff_rel = "roadmap"
            root_p = (base / eff_rel).resolve() if eff_rel and eff_rel != "." else base
            return (root_p / tail).resolve() if tail else root_p
    return None


def parse_markdown_blockquote_headers(
    lines_or_content: Union[str, List[str]],
    max_lines: int = 35,
) -> Dict[str, str]:
    """
    結構化解析 Markdown 開頭 Blockquote (> 欄位：值 或 > 欄位: 值) 中的 Header 元數據 (SSOT)。

    Args:
        lines_or_content: Markdown 全文字串或行清單
        max_lines: 最大掃描行數（預設 35 行）

    Returns:
        Dict[str, str]: 小寫欄位名對應修剪後欄位值之字典
    """
    if isinstance(lines_or_content, str):
        lines = lines_or_content.splitlines()
    else:
        lines = list(lines_or_content)

    headers: Dict[str, str] = {}
    for line in lines[:max_lines]:
        line_clean = line.strip().replace("\u3000", " ")
        if line_clean.startswith(">"):
            inner = line_clean.lstrip(">").strip()
            if "：" in inner:
                k, v = inner.split("：", 1)
                headers[k.strip().lower()] = v.strip()
            elif ":" in inner:
                k, v = inner.split(":", 1)
                headers[k.strip().lower()] = v.strip()
    return headers


def parse_changelog_table(
    lines_or_content: Union[str, List[str]],
) -> Tuple[int, int, List[Dict[str, Any]]]:
    """
    統一解析 changelog.md 中之 Markdown 表格結構（支援 `\\|` 跳脫直線字元與 3/4 欄相容）。

    Returns:
        Tuple[int, int, List[Dict[str, Any]]]:
            - table_line_count: 非 HTML 註解之表格行總數
            - sep_idx: 表格分隔線 (`| :--- |`) 在原行清單中之索引（若無則為 -1）
            - rows: 資料列字典清單，每筆包含 line_idx, timestamp, type, model, summary, raw_summary, cells
    """
    if isinstance(lines_or_content, str):
        lines = lines_or_content.splitlines()
    else:
        lines = list(lines_or_content)

    table_line_count = 0
    sep_idx = -1
    rows: List[Dict[str, Any]] = []

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if "|" not in stripped or stripped.startswith("<!--"):
            continue
        table_line_count += 1
        if _CHANGELOG_SEP_LINE_RE.match(stripped):
            if sep_idx == -1:
                sep_idx = idx
            continue

        cells = [
            c.strip()
            for c in _CHANGELOG_UNESCAPED_PIPE_RE.split(stripped.strip("|"))
        ]
        if not cells or not any(cells):
            continue
        first_cell_norm = cells[0].strip().lower()
        if first_cell_norm in _CHANGELOG_HEADER_FIRST_CELLS:
            continue
        if sep_idx != -1 and idx < sep_idx:
            continue

        ts_str = cells[0].strip()
        type_str = cells[1].strip().strip("`").upper() if len(cells) >= 2 else ""
        if len(cells) >= 4:
            model_str = cells[2].strip().replace(r"\|", "|")
            raw_summary = cells[3].strip()
        elif len(cells) == 3:
            model_str = "Unknown"
            raw_summary = cells[2].strip()
        else:
            model_str = "Unknown"
            raw_summary = cells[-1].strip()
        summary_str = raw_summary.replace(r"\|", "|").strip()

        rows.append({
            "line_idx": idx,
            "timestamp": ts_str,
            "type": type_str,
            "model": model_str,
            "summary": summary_str,
            "raw_summary": raw_summary,
            "cells": cells,
        })

    return table_line_count, sep_idx, rows


def is_revision_root_dir(plan_dir: Union[str, Path]) -> bool:
    """
    判定目錄是否為純獨立修訂根目錄（含 revision_log.md，且不含 umbrella_overview.md、fast_track_plan.md、P01 或 P07）。
    """
    from .state_machine import is_revision_root_dir as _is_rev_root

    return _is_rev_root(plan_dir)


def evaluate_plan_completion(plan_dir: Union[str, Path]) -> Tuple[bool, Optional[str]]:
    """
    統一評估計畫（含主計畫、所有 sub_XX 子計畫及附掛之 revision_log.md）是否已完整結案 (SSOT)。

    Returns:
        Tuple[bool, Optional[str]]: (is_completed, blocking_reason)
    """
    from .state_machine import evaluate_plan_completion as _eval_completion

    return _eval_completion(plan_dir)


def resolve_target_projection_rule(
    target_cfg: Dict[str, Any],
    artifact_type: str,
    artifact_name: str = "",
    subpath: str = "",
) -> Tuple[str, str, Optional[str], str]:
    """
    解析單一 Target 對指定資產類型之投影規則 (SSOT)。

    Returns:
        Tuple[str, str, Optional[str], str]:
            - target_dir_uri: 展開巨集後之目標目錄 URI（如 'project://.agents/.yscb/templates'）
            - rel_subpath: 套用副檔名替換後之相對子路徑（如 'P01_requirements_spec.md'）
            - header_tpl: 投影標頭模板（若無則為 None）
            - ext: 目標副檔名（預設 '.md'）
    """
    norm_type = (artifact_type or "template").strip()
    singular_type = norm_type.rstrip("s").lower()
    is_skill = singular_type in ("skill", "workflow")
    sub_folder = "skills" if is_skill else f"{singular_type}s"
    default_target_dir_uri = (
        f"project://.agents/skills/{artifact_name}"
        if is_skill
        else f"project://.agents/.yscb/{sub_folder}"
    )

    projections = target_cfg.get("projections", {}) if isinstance(target_cfg, dict) else {}
    proj_cfg: Optional[Dict[str, Any]] = None
    if isinstance(projections, dict):
        cand = projections.get(norm_type)
        if isinstance(cand, dict):
            proj_cfg = cand
        else:
            for k, v in projections.items():
                if isinstance(v, dict) and k.rstrip("s").lower() == singular_type:
                    proj_cfg = v
                    break
        if proj_cfg is None and is_skill:
            wf_cand = projections.get("workflow") or projections.get("workflows")
            if isinstance(wf_cand, dict):
                proj_cfg = wf_cand

    if isinstance(proj_cfg, dict) and proj_cfg:
        raw_target_dir = str(proj_cfg.get("target_dir") or default_target_dir_uri).strip()
        ext = str(proj_cfg.get("extension", ".md"))
        header_tpl = proj_cfg.get("header")
    else:
        raw_target_dir = default_target_dir_uri
        ext = ".md"
        header_tpl = None

    base_ref = os.path.basename((subpath or artifact_name).replace("\\", "/"))
    export_basename = os.path.splitext(base_ref)[0] if base_ref else ""
    target_name_str = str(target_cfg.get("name", "")) if isinstance(target_cfg, dict) else ""

    target_dir_uri = (
        raw_target_dir
        .replace("{export.name}", artifact_name)
        .replace("{export.basename}", export_basename)
        .replace("{target.name}", target_name_str)
    )

    clean_sub = subpath.replace("\\", "/").lstrip("/")
    if not clean_sub:
        rel_subpath = ""
    elif is_skill:
        rel_subpath = clean_sub
    else:
        sub_dir_part = os.path.dirname(clean_sub)
        file_stem = os.path.splitext(os.path.basename(clean_sub))[0]
        target_filename = f"{file_stem}{ext}"
        rel_subpath = f"{sub_dir_part}/{target_filename}" if sub_dir_part else target_filename

    return target_dir_uri, rel_subpath, header_tpl, ext


def resolve_active_target_projected_path(
    artifact_type: str,
    artifact_name: str = "",
    subpath: str = "",
) -> str:
    """
    依據當前啟用之 release_targets (local ∪ project) 動態解析 template / standard / skill 的專案相對路徑。
    若無啟用 Target 或讀取失敗，安全退回 .agents/... 預設路徑。
    """
    default_dir_uri, default_subpath, _, _ = resolve_target_projection_rule(
        {}, artifact_type, artifact_name=artifact_name, subpath=subpath
    )
    default_base = (
        default_dir_uri[len("project://") :].lstrip("/")
        if default_dir_uri.startswith("project://")
        else default_dir_uri.lstrip("/")
    ).rstrip("/")
    fallback = f"{default_base}/{default_subpath}".strip("/") if default_subpath else default_base

    try:
        from agents_workflow.compiler import ArtifactCompiler
        from agents_workflow.targets import ReleaseTargetManager

        classified = ReleaseTargetManager.get_classified_targets()
        active_targets = classified.get("union", [])
        if not active_targets:
            return fallback

        selected_target = active_targets[0]
        if len(active_targets) > 1:
            try:
                from core.locale import detect_active_host_dialect

                dialect = detect_active_host_dialect()
                if dialect and dialect.startswith("nouns-"):
                    cand_t = dialect[len("nouns-") :]
                    if cand_t in active_targets:
                        selected_target = cand_t
            except Exception:
                pass

        compiler = ArtifactCompiler()
        target_defs = {
            t["name"]: t
            for t in compiler.get_release_targets()
            if isinstance(t, dict) and "name" in t
        }
        t_obj = target_defs.get(selected_target)
        if not t_obj:
            return fallback

        target_dir_uri, rel_subpath, _, _ = resolve_target_projection_rule(
            t_obj, artifact_type, artifact_name=artifact_name, subpath=subpath
        )
        if target_dir_uri.startswith("project://"):
            rel_dir = target_dir_uri[len("project://") :].lstrip("/")
        else:
            rel_dir = target_dir_uri.lstrip("/")
        rel_dir = rel_dir.rstrip("/")
        return f"{rel_dir}/{rel_subpath}" if rel_subpath else rel_dir
    except Exception:
        return fallback
