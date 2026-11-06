"""
agents_workflow.plans._common — Plans 工具鏈共用基礎設施（語意 URI 解析與 Markdown 標頭提取 SSOT）。
"""

from pathlib import Path
from typing import Dict, List, Optional, Union

DEFAULT_URI_FALLBACKS: Dict[str, str] = {
    "workflow.plans://": "plans",
    "workflow.archived://": "plans/archived",
    "project://": ".",
}


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
        base = Path(host_dir).resolve() if host_dir is not None else Path.cwd().resolve()
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
        from agents_workflow.targets import ReleaseTargetManager
        from agents_workflow.compiler import ArtifactCompiler

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
