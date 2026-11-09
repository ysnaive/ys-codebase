"""
agents_workflow.plans._common — Plans 工具鏈共用基礎設施（語意 URI 解析、Markdown 標頭提取、生命周期完成度判定與變更日誌表格解析 SSOT）。
"""

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
    安全解析語意 URI；若無 core 上下文或解析失敗，則依 default_fallback 或 DEFAULT_URI_FALLBACKS 退避。

    Args:
        uri_str: 語意 URI 字串（如 'workflow.plans://'、'workflow.archived://'、'project://'）
        default_fallback: 選填退避相對路徑；若未指定則查表 DEFAULT_URI_FALLBACKS
        host_dir: 選填宿主基準目錄；當 host_dir is None 時維持 Path.cwd().resolve()

    Returns:
        Optional[Path]: 解析後之絕對路徑，若無對應退避則回傳 None
    """
    try:
        from core.uri import resolve
        resolved = resolve(uri_str, interactive=False)
        if resolved and not str(resolved).startswith("!"):
            return Path(resolved).resolve()
    except Exception:
        pass

    fallback = default_fallback if default_fallback is not None else DEFAULT_URI_FALLBACKS.get(uri_str)
    if fallback is not None:
        base = Path(host_dir).resolve() if host_dir is not None else Path(get_virtual_cwd()).resolve()
        return (base / fallback).resolve() if fallback else base
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
    from .status import PlanStatusResolver

    p = Path(plan_dir)
    if not (p / "revision_log.md").is_file():
        return False
    if (p / "umbrella_overview.md").is_file() or (p / "fast_track_plan.md").is_file():
        return False
    if PlanStatusResolver.resolve_phase_file(p, "P01").is_file():
        return False
    if PlanStatusResolver.resolve_phase_file(p, "P07").is_file():
        return False
    return True


def evaluate_plan_completion(plan_dir: Union[str, Path]) -> Tuple[bool, Optional[str]]:
    """
    統一評估計畫（含主計畫、所有 sub_XX 子計畫及附掛之 revision_log.md）是否已完整結案 (SSOT)。

    Returns:
        Tuple[bool, Optional[str]]: (is_completed, blocking_reason)
    """
    from .status import PlanStatusResolver

    p = Path(plan_dir)
    plan_name = p.name

    all_rev_logs: List[Path] = []
    root_rev = p / "revision_log.md"
    if root_rev.is_file():
        all_rev_logs.append(root_rev)

    sub_dirs = sorted(
        [d for d in p.iterdir() if d.is_dir() and d.name.startswith("sub_")],
        key=lambda x: x.name,
    ) if p.is_dir() else []

    for sub_dir in sub_dirs:
        sub_rev = sub_dir / "revision_log.md"
        if sub_rev.is_file():
            all_rev_logs.append(sub_rev)

    for r_file in all_rev_logs:
        if not PlanStatusResolver.is_doc_completed(r_file):
            rel_r = r_file.relative_to(p)
            return (
                False,
                f"計畫 '{plan_name}' 內存在尚未完成之修訂紀錄 '{rel_r}'（標頭未標記 Completed），為確保結案無遺漏，無法歸檔。若確定要強制歸檔，請使用 --force 參數。",
            )

    umbrella_overview = p / "umbrella_overview.md"
    ft_plan = p / "fast_track_plan.md"
    p01_file = PlanStatusResolver.resolve_phase_file(p, "P01")
    p07_walkthrough = PlanStatusResolver.resolve_phase_file(p, "P07")

    if umbrella_overview.is_file():
        if not PlanStatusResolver.is_doc_completed(umbrella_overview):
            return (
                False,
                f"計畫 '{plan_name}' 之 'umbrella_overview.md' 尚未完成（未找到標頭 Completed/Concluded 標記）。若確定要強制歸檔，請使用 --force 參數。",
            )
        for sub_dir in sub_dirs:
            sub_ok, sub_reason = evaluate_plan_completion(sub_dir)
            if not sub_ok:
                return (
                    False,
                    f"計畫 '{plan_name}' 之子計畫 '{sub_dir.name}' 尚未完成（{sub_reason or '未標記 Completed'}），無法歸檔。若確定要強制歸檔，請使用 --force 參數。",
                )
        return True, None

    if ft_plan.is_file():
        if PlanStatusResolver.is_doc_completed(ft_plan):
            return True, None
        return (
            False,
            f"計畫 '{plan_name}' 之 'fast_track_plan.md' 尚未完成（未找到標頭 Completed/Concluded 標記）。若確定要強制歸檔，請使用 --force 參數。",
        )

    if p01_file.is_file() or p07_walkthrough.is_file():
        if p07_walkthrough.is_file() and PlanStatusResolver.is_doc_completed(p07_walkthrough):
            return True, None
        return (
            False,
            f"計畫 '{plan_name}' 尚未完成（'P07_walkthrough.md' 未找到標頭 Completed/Concluded 標記）。若確定要強制歸檔，請使用 --force 參數。",
        )

    if root_rev.is_file():
        if PlanStatusResolver.is_doc_completed(root_rev):
            return True, None
        return (
            False,
            f"計畫 '{plan_name}' 之 'revision_log.md' 尚未完成（未找到標頭 Completed/Concluded 標記）。若確定要強制歸檔，請使用 --force 參數。",
        )

    if PlanStatusResolver.is_research_completed(p):
        return True, None

    return (
        False,
        f"計畫 '{plan_name}' 尚未完成（未找到標頭 Completed/Concluded 標記）。若確定要強制歸檔，請使用 --force 參數。",
    )


def resolve_active_target_projected_path(
    artifact_type: str,
    artifact_name: str = "",
    subpath: str = "",
) -> str:
    """
    依據當前啟用之 release_targets (local ∪ project) 動態解析 template / standard / skill 的專案相對路徑。
    若無啟用 Target 或讀取失敗，安全退回 .agents/... 預設路徑。
    """
    norm_type = (artifact_type or "").strip()
    singular_type = norm_type.rstrip("s")
    default_base = (
        f".agents/skills/{artifact_name}"
        if singular_type in ("skill", "workflow")
        else f".agents/.yscb/{singular_type}s"
    )
    fallback = f"{default_base}/{subpath}".strip("/") if subpath else default_base

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
                    cand_t = dialect[len("nouns-"):]
                    if cand_t in active_targets:
                        selected_target = cand_t
            except Exception:
                pass

        compiler = ArtifactCompiler()
        target_defs = {t["name"]: t for t in compiler.get_release_targets() if isinstance(t, dict) and "name" in t}
        t_obj = target_defs.get(selected_target)
        if not t_obj:
            return fallback

        projections = t_obj.get("projections", {})
        if not isinstance(projections, dict):
            return fallback

        proj_cfg = projections.get(norm_type)
        if not isinstance(proj_cfg, dict):
            for k, v in projections.items():
                if isinstance(v, dict) and k.rstrip("s") == singular_type:
                    proj_cfg = v
                    break
        if not isinstance(proj_cfg, dict) and singular_type in ("skill", "workflow"):
            proj_cfg = projections.get("workflow") or projections.get("workflows")

        if not isinstance(proj_cfg, dict) or "target_dir" not in proj_cfg:
            return fallback

        raw_dir = str(proj_cfg["target_dir"]).strip()
        if raw_dir.startswith("project://"):
            rel_dir = raw_dir[len("project://"):].lstrip("/")
        else:
            rel_dir = raw_dir.lstrip("/")

        export_basename = Path(subpath or artifact_name).stem if (subpath or artifact_name) else ""
        rel_dir = (
            rel_dir
            .replace("{export.name}", artifact_name)
            .replace("{export.basename}", export_basename)
            .replace("{target.name}", str(selected_target))
        )

        rel_dir = rel_dir.rstrip("/")
        return f"{rel_dir}/{subpath.lstrip('/')}" if subpath else rel_dir
    except Exception:
        return fallback
