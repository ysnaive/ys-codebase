"""
agents_workflow.plans.state_machine — Single Source of Truth (SSOT) finite state machine
for plan track classification, header metadata normalization, attached revision detection,
and plan completion evaluation.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Dict, FrozenSet, List, Mapping, Optional, Tuple, Union

from ._common import parse_markdown_blockquote_headers

VALID_STATUSES: FrozenSet[str] = frozenset({
    "draft",
    "confirmed",
    "in progress",
    "in_progress",
    "implementing",
    "passed",
    "completed",
    "active",
    "archived",
    "pending",
    "review",
    "discussing",
    "planning",
    "executing",
    "concluded",
    "aborted",
    "cancelled",
    "backlog",
    "proposed",
    "ready",
    "deferred",
    "seeded",
    "phase 0",
})

COMPLETED_STATUS_SET: FrozenSet[str] = frozenset({"completed", "concluded", "passed"})
ORIGIN_SEED_FILES: FrozenSet[str] = frozenset({"roadmap.md", "todo.md"})

HEADER_NAME_KEYS: Tuple[str, ...] = (
    "功能名稱",
    "計畫名稱",
    "所屬計畫",
    "name",
    "title",
    "調研主題",
    "topic",
    "subject",
    "主題",
)
HEADER_DATE_KEYS: Tuple[str, ...] = (
    "建立日期",
    "完成日期",
    "暫停時間",
    "歸檔日期",
    "更新日期",
    "date",
    "created_at",
    "updated_at",
    "archived_at",
    "日期",
    "time",
    "timestamp",
)
HEADER_STATUS_KEYS: Tuple[str, ...] = (
    "狀態",
    "status",
    "計畫狀態",
    "plan_status",
    "調研狀態",
    "research_status",
    "進度",
    "當前所在階段",
)
HEADER_PARENT_KEYS: Tuple[str, ...] = (
    "所屬主計畫",
    "所屬計畫",
    "parent_plan",
    "主計畫",
    "parent",
)
HEADER_MODEL_KEYS: Tuple[str, ...] = (
    "模型",
    "model",
    "ai_model",
    "ai-model",
    "模型名稱",
    "model_name",
)

PHASE_PREFIX_MAP: Mapping[str, str] = MappingProxyType({
    "P00": "P00_",
    "P01": "P01_",
    "P02": "P02_",
    "P03": "P03_",
    "P04": "P04_",
    "P05": "P05_",
    "P06": "P06_",
    "P07": "P07_",
})

PHASE_CANONICAL_STEMS: Mapping[str, str] = MappingProxyType({
    "P00": "P00_discuss",
    "P01": "P01_requirements_spec",
    "P02": "P02_architecture_plan",
    "P03": "P03_api_spec",
    "P04": "P04_implementation_plan",
    "P05": "P05_task",
    "P06": "P06_test_plan",
    "P07": "P07_walkthrough",
})

PHASE_CANONICAL_FILES: Mapping[str, str] = MappingProxyType({
    code: f"{stem}.md" for code, stem in PHASE_CANONICAL_STEMS.items()
})

_RESEARCH_DOC_RE = re.compile(r"^R\d{2}_.+\.md$", re.IGNORECASE)


@dataclass(frozen=True)
class DirectoryStateEvaluation:
    """Unified state evaluation snapshot for a plan directory."""

    track_type: str
    status: str
    is_completed: bool
    attached_revision_active: bool
    blocking_reason: Optional[str] = None


def resolve_phase_file(plan_dir: Union[Path, str], phase_code: str) -> Path:
    """
    Resolve the physical file path for phase_code (P00~P07) under plan_dir,
    supporting standard filenames, legacy _auto.md suffixes, and P0X-05_auto.md range files.
    """
    p = Path(plan_dir)
    p_up = (phase_code or "").strip().upper()
    stem = PHASE_CANONICAL_STEMS.get(p_up, f"{p_up}_spec")
    std_path = p / f"{stem}.md"
    if std_path.is_file():
        return std_path
    auto_path = p / f"{stem}_auto.md"
    if auto_path.is_file():
        return auto_path
    if p.is_dir() and re.match(r"^P0[1-5]$", p_up):
        target_num = int(p_up[1:])
        for f in sorted(p.glob("P0*-05_auto.md")):
            m_range = re.match(r"^P0([1-5])-05_auto\.md$", f.name, re.IGNORECASE)
            if m_range and int(m_range.group(1)) <= target_num <= 5:
                return f
    if p.is_dir() and re.match(r"^P0[0-7]$", p_up):
        matches = sorted(p.glob(f"{p_up}_*.md"))
        if matches:
            return matches[0]
    return std_path


def read_doc_header_metadata(doc_target: Union[Path, str]) -> Optional[Dict[str, str]]:
    """Read the top 35 lines of a Markdown file or string and extract blockquote headers."""
    content = ""
    if isinstance(doc_target, Path) or (
        isinstance(doc_target, str) and "\n" not in doc_target and Path(doc_target).exists()
    ):
        p = Path(doc_target)
        if not p.is_file():
            return None
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None
    elif isinstance(doc_target, str):
        content = doc_target
    else:
        return None

    try:
        lines = content.splitlines()[:35]
        return parse_markdown_blockquote_headers(lines, max_lines=35)
    except Exception:
        return None


def get_doc_header_status(doc_target: Union[Path, str]) -> str:
    """Return normalized lowercase status from a Markdown file or content string ('unknown' if absent)."""
    headers = read_doc_header_metadata(doc_target)
    if not headers:
        return "unknown"

    for key in HEADER_STATUS_KEYS:
        if key in headers:
            val = headers[key].strip()
            if not val:
                continue
            if val.startswith("[") and val.endswith("]") and "|" in val:
                return "unknown"
            norm_val = val.lower()
            if norm_val in ("in_progress", "implementing", "executing", "active"):
                return "in progress"
            return norm_val

    return "unknown"


def is_doc_completed(doc_target: Union[Path, str]) -> bool:
    """Return True if the document header status is in COMPLETED_STATUS_SET."""
    return get_doc_header_status(doc_target) in COMPLETED_STATUS_SET


def is_research_completed(plan_dir_or_target: Union[Path, str]) -> bool:
    """Return True if all R{NN}_*.md files in a directory (or a single research doc) are completed."""
    if isinstance(plan_dir_or_target, Path) or (
        isinstance(plan_dir_or_target, str)
        and "\n" not in plan_dir_or_target
        and Path(plan_dir_or_target).exists()
    ):
        p = Path(plan_dir_or_target)
        if p.is_dir():
            r_files = [
                f
                for f in p.iterdir()
                if f.is_file() and _RESEARCH_DOC_RE.match(f.name)
            ]
            if not r_files:
                return False
            return all(is_doc_completed(rf) for rf in r_files)
        if p.is_file():
            return is_doc_completed(p)

    return is_doc_completed(plan_dir_or_target)


def get_doc_header_model(doc_target: Union[Path, str]) -> str:
    """Extract the model name from the top 35 lines blockquote header, or 'Unknown'."""
    headers = read_doc_header_metadata(doc_target)
    if not headers:
        return "Unknown"

    for key in HEADER_MODEL_KEYS:
        if key in headers:
            val = headers[key].strip()
            if not val:
                return "Unknown"
            if val.startswith("[") and val.endswith("]"):
                return "Unknown"
            return val
    return "Unknown"


def has_active_attached_revision(plan_dir: Union[Path, str]) -> bool:
    """Return True if plan_dir has an attached revision_log.md that is not yet completed."""
    p = Path(plan_dir)
    rev_log = p / "revision_log.md"
    if not rev_log.is_file():
        return False
    return not is_doc_completed(rev_log)


def is_revision_root_dir(plan_dir: Union[str, Path]) -> bool:
    """Return True if plan_dir is a standalone revision root directory."""
    p = Path(plan_dir)
    if not (p / "revision_log.md").is_file():
        return False
    if (p / "umbrella_overview.md").is_file() or (p / "fast_track_plan.md").is_file():
        return False
    if resolve_phase_file(p, "P01").is_file():
        return False
    if resolve_phase_file(p, "P07").is_file():
        return False
    return True


def evaluate_plan_completion(plan_dir: Union[str, Path]) -> Tuple[bool, Optional[str]]:
    """
    Evaluate whether a plan directory (including sub_XX sub-plans and attached revision_log.md)
    is fully completed and eligible for archiving.
    """
    p = Path(plan_dir)
    plan_name = p.name

    all_rev_logs: List[Path] = []
    root_rev = p / "revision_log.md"
    if root_rev.is_file():
        all_rev_logs.append(root_rev)

    sub_dirs = (
        sorted(
            [d for d in p.iterdir() if d.is_dir() and d.name.startswith("sub_")],
            key=lambda x: x.name,
        )
        if p.is_dir()
        else []
    )

    for sub_dir in sub_dirs:
        sub_rev = sub_dir / "revision_log.md"
        if sub_rev.is_file():
            all_rev_logs.append(sub_rev)

    for r_file in all_rev_logs:
        if not is_doc_completed(r_file):
            rel_r = r_file.relative_to(p)
            return (
                False,
                f"計畫 '{plan_name}' 內存在尚未完成之修訂紀錄 '{rel_r}'（標頭未標記 Completed），為確保結案無遺漏，無法歸檔。若確定要強制歸檔，請使用 --force 參數。",
            )

    umbrella_overview = p / "umbrella_overview.md"
    ft_plan = p / "fast_track_plan.md"
    p01_file = resolve_phase_file(p, "P01")
    p07_walkthrough = resolve_phase_file(p, "P07")

    if umbrella_overview.is_file():
        if not is_doc_completed(umbrella_overview):
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
        if is_doc_completed(ft_plan):
            return True, None
        return (
            False,
            f"計畫 '{plan_name}' 之 'fast_track_plan.md' 尚未完成（未找到標頭 Completed/Concluded 標記）。若確定要強制歸檔，請使用 --force 參數。",
        )

    if p01_file.is_file() or p07_walkthrough.is_file():
        if p07_walkthrough.is_file() and is_doc_completed(p07_walkthrough):
            return True, None
        return (
            False,
            f"計畫 '{plan_name}' 尚未完成（'P07_walkthrough.md' 未找到標頭 Completed/Concluded 標記）。若確定要強制歸檔，請使用 --force 參數。",
        )

    if root_rev.is_file():
        if is_doc_completed(root_rev):
            return True, None
        return (
            False,
            f"計畫 '{plan_name}' 之 'revision_log.md' 尚未完成（未找到標頭 Completed/Concluded 標記）。若確定要強制歸檔，請使用 --force 參數。",
        )

    if is_research_completed(p):
        return True, None

    return (
        False,
        f"計畫 '{plan_name}' 尚未完成（未找到標頭 Completed/Concluded 標記）。若確定要強制歸檔，請使用 --force 參數。",
    )
