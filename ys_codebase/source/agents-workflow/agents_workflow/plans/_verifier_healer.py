"""
agents_workflow.plans._verifier_healer — PlanVerifier 確定性標頭自癒、伴隨檔初始化與變更日誌追加服務。
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ._common import parse_markdown_blockquote_headers
from ._verifier_specs import extract_requirement_ids


def infer_deterministic_header_values(file_path: Path, is_sub_plan: bool) -> Dict[str, str]:
    """推導檔案之 100% 確定性標頭欄位值 (功能名稱、建立日期、所屬主計畫)。"""
    target_dir = file_path.parent
    dir_date_m = re.match(r"^(\d{4})_(\d{2})_(\d{2})", target_dir.name) or re.match(
        r"^(\d{4})_(\d{2})_(\d{2})", target_dir.parent.name
    )
    today_str = (
        f"{dir_date_m.group(1)}-{dir_date_m.group(2)}-{dir_date_m.group(3)}"
        if dir_date_m
        else datetime.now().strftime("%Y-%m-%d")
    )
    parent_name = target_dir.parent.name if is_sub_plan else "N/A (Root Plan)"
    slug = re.sub(r"^(?:\d{4}_\d{2}_\d{2}_(?:\d{4}_)?|sub_\d+_)", "", target_dir.name)
    func_name = slug.replace("_", " ").title() if slug else target_dir.name
    try:
        for cand in sorted(target_dir.glob("P0[01]_*.md")):
            if cand.resolve() == file_path.resolve():
                continue
            cand_headers = parse_markdown_blockquote_headers(
                cand.read_text(encoding="utf-8", errors="ignore").splitlines()
            )
            for k in ("功能名稱", "計畫名稱", "調研主題", "name", "title"):
                val = cand_headers.get(k, "").strip()
                if val and not (val.startswith("[") and val.endswith("]")):
                    func_name = val
                    break
            if func_name != (slug.replace("_", " ").title() if slug else target_dir.name):
                break
    except Exception:
        pass
    return {
        "功能名稱": func_name,
        "建立日期": today_str,
        "所屬主計畫": parent_name,
    }


def auto_heal_deterministic_headers(
    md_file: Path,
    lines: List[str],
    headers: Dict[str, str],
    is_sub_plan: bool,
) -> Tuple[List[str], Dict[str, str], List[str]]:
    """
    若缺少 [功能名稱]、[建立日期] 或二級子計畫之 [所屬主計畫]，自動推導確定性值並寫回檔案。
    後置契約：絕不新增或修改 [狀態] 與 [模型]；回傳更新後之 (lines, headers, healed_keys)。
    """
    inferred = infer_deterministic_header_values(md_file, is_sub_plan)
    has_name = any(k in headers for k in [
        "功能名稱", "計畫名稱", "所屬計畫", "name", "title", "調研主題", "topic", "subject", "主題"
    ])
    has_date = any(k in headers for k in [
        "建立日期", "完成日期", "暫停時間", "歸檔日期", "更新日期",
        "date", "created_at", "updated_at", "archived_at", "日期", "time", "timestamp"
    ])
    has_parent = any(k in headers for k in ["所屬主計畫", "所屬計畫", "parent_plan", "主計畫", "parent"])

    missing_pairs: List[Tuple[str, str]] = []
    if not has_name:
        missing_pairs.append(("功能名稱", inferred["功能名稱"]))
    if not has_date:
        missing_pairs.append(("建立日期", inferred["建立日期"]))
    if is_sub_plan and not has_parent:
        missing_pairs.append(("所屬主計畫", inferred["所屬主計畫"]))

    if not missing_pairs:
        return lines, headers, []

    new_lines = list(lines)
    insert_idx = -1
    for idx, l in enumerate(new_lines[:35]):
        if l.strip().startswith(">"):
            insert_idx = idx
            break
    if insert_idx == -1:
        for idx, l in enumerate(new_lines[:15]):
            if l.strip().startswith("#"):
                insert_idx = idx + 1
                if insert_idx < len(new_lines) and new_lines[insert_idx].strip() != "":
                    new_lines.insert(insert_idx, "")
                    insert_idx += 1
                elif insert_idx == len(new_lines):
                    new_lines.append("")
                    insert_idx = len(new_lines)
                break
        if insert_idx == -1:
            insert_idx = 0

    for key, val in reversed(missing_pairs):
        new_lines.insert(insert_idx, f"> {key}：{val}  ")

    try:
        md_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except Exception:
        return lines, headers, []

    updated_headers = parse_markdown_blockquote_headers(new_lines)
    healed_keys = [k for k, _ in missing_pairs]
    return new_lines, updated_headers, healed_keys


def resolve_effective_phase(target_dir: Path, phase_norm: str) -> str:
    """當 phase_norm 為 'CURRENT' 時，依據目錄現有產物與狀態動態推導當前階段代號 (如 'P02', 'P04' 等)。"""
    p_up = (phase_norm or "ALL").strip().upper()
    if p_up != "CURRENT":
        return p_up
    from .status import PlanStatusResolver

    nav = PlanStatusResolver.resolve_next_action(target_dir)
    cur = str(nav.get("current_phase", "")).strip().upper()
    if cur in ("P00", "P01", "P02", "P03", "P04", "P05", "P06", "P07"):
        return cur
    return "ALL"


def resolve_companion_model(
    target_dir: Path,
    phase_norm: str,
    explicit_model: Optional[str] = None,
) -> str:
    """
    解析伴隨檔初始化時應填入之模型名稱（防呆 2：嚴禁跨階段回溯舊檔）。
    優先取用 CLI 顯式傳入之 --model；若未傳入，僅允許讀取當下同階段主體檔之標頭模型，否則回傳 'Unknown'。
    """
    if explicit_model and isinstance(explicit_model, str) and explicit_model.strip():
        val = explicit_model.strip()
        if not (val.startswith("[") and val.endswith("]")):
            return val

    from .status import PlanStatusResolver

    eff_phase = resolve_effective_phase(target_dir, phase_norm)
    if eff_phase in PlanStatusResolver.PHASE_CANONICAL_STEMS:
        primary_f = PlanStatusResolver.resolve_phase_file(target_dir, eff_phase)
        if primary_f.is_file():
            return PlanStatusResolver.get_doc_header_model(primary_f)

    for entry_name in ("umbrella_overview.md", "fast_track_plan.md", "revision_log.md"):
        if (target_dir / entry_name).is_file():
            return PlanStatusResolver.get_doc_header_model(target_dir / entry_name)

    return "Unknown"


def auto_heal_companions(
    target_dir: Path,
    phase_norm: str,
    explicit_model: Optional[str],
    report: Any,
) -> None:
    """
    Step 2: 自動初始化缺失之伴隨檔 (changelog.md 與 P02 階段伴隨之 P06_test_plan.md Draft)。
    僅於 Step 1 目標階段主體檔合規 (0 FAIL) 且啟用自癒時呼叫。
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    is_sub = target_dir.name.startswith("sub_")
    parent_name = target_dir.parent.name if is_sub else "N/A (Root Plan)"
    model_val = resolve_companion_model(target_dir, phase_norm, explicit_model)
    rel_prefix = f"{target_dir.name}/" if is_sub and target_dir.resolve() != Path(report.plan_path).resolve() else ""

    changelog_path = target_dir / "changelog.md"
    if not changelog_path.exists():
        now_min = datetime.now().strftime("%Y-%m-%d %H:%M")
        cl_content = (
            f"# 計畫變更紀錄 (Changelog)\n\n"
            f"> 功能名稱：{target_dir.name}  \n"
            f"> 建立日期：{today_str}  \n"
            f"> 所屬主計畫：{parent_name}  \n"
            f"> 狀態：In Progress  \n"
            f"> 模型：{model_val}  \n\n"
            f"> 模板版本：v1.1  \n\n"
            f"---\n\n"
            f"## 變更紀錄\n\n"
            f"| 日期時間 | 類型 | 模型 | 摘要 |\n"
            f"| :--- | :---: | :--- | :--- |\n"
            f"| {now_min} | `PHASE` | {model_val} | 自動初始化變更日誌 (changelog.md) |\n"
        )
        changelog_path.write_text(cl_content, encoding="utf-8")
        created_rel = f"{rel_prefix}changelog.md"
        if created_rel not in report.companion_created:
            report.companion_created.append(created_rel)

    from .status import PlanStatusResolver

    p02_path = PlanStatusResolver.resolve_phase_file(target_dir, "P02")
    p06_path = PlanStatusResolver.resolve_phase_file(target_dir, "P06")
    if phase_norm.upper() in ("P02", "ALL", "CURRENT") and p02_path.is_file() and not p06_path.exists():
        p02_model = resolve_companion_model(target_dir, "P02", explicit_model)
        p01_path = PlanStatusResolver.resolve_phase_file(target_dir, "P01")
        req_ids = (
            sorted(extract_requirement_ids(p01_path.read_text(encoding="utf-8", errors="ignore")))
            if p01_path.is_file()
            else ["FR-01"]
        )
        if not req_ids:
            req_ids = ["FR-01"]

        case_rows = []
        exec_rows = []
        for idx, rid in enumerate(req_ids, 1):
            prefix = "ET" if rid.startswith("EC-") else ("RT" if rid.startswith("NFR-") else "FT")
            tid = f"{prefix}-{idx:02d}"
            t_kind = "邊界測試" if prefix == "ET" else ("回歸測試" if prefix == "RT" else "單元測試")
            case_rows.append(
                f"| **{tid}** | {t_kind} | 待於 Phase 4 定稿補齊 ({rid}) | {rid} | 待定稿 |"
            )
            exec_rows.append(f"| **{tid}** | `Pending` | 待執行 | - |")

        p06_content = (
            f"# 測試計畫與驗證報告 (Test Plan & Verification)\n\n"
            f"> 功能名稱：{target_dir.name}  \n"
            f"> 建立日期：{today_str}  \n"
            f"> 所屬主計畫：{parent_name}  \n"
            f"> 狀態：Draft  \n"
            f"> 模型：{p02_model}  \n\n"
            f"> 模板版本：v1.4  \n\n"
            f"---\n\n"
            f"## 1. 自動化測試案例清單 (Automated Test Cases)\n\n"
            f"| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |\n"
            f"| :--- | :--- | :--- | :--- | :--- |\n"
            + "\n".join(case_rows)
            + "\n\n---\n\n"
            f"## 2. 測試執行紀錄表 (Test Execution Log)\n\n"
            f"| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |\n"
            f"| :--- | :---: | :--- | :---: |\n"
            + "\n".join(exec_rows)
            + "\n\n---\n\n"
            f"## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)\n\n"
            f"| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |\n"
            f"| :--- | :--- | :---: | :--- |\n"
            f"| **UX-01** | 待於 Phase 4 定稿確認 | `Pending` | 待驗收 |\n"
        )
        p06_path.write_text(p06_content, encoding="utf-8")
        created_rel = f"{rel_prefix}P06_test_plan.md"
        if created_rel not in report.companion_created:
            report.companion_created.append(created_rel)


def append_changelog_entry(
    target_dir: Path,
    summary: str,
    log_type: str = "PHASE",
    model: str = "Unknown",
) -> Tuple[bool, str]:
    """
    於 target_dir/changelog.md 表格頂部免讀盲寫插入新紀錄列 (含首筆 (類型, 摘要) 冪等防重入保護)。
    """
    changelog_path = target_dir / "changelog.md"
    clean_type = log_type.strip().upper().strip("`") or "PHASE"
    clean_summary = summary.strip().replace("\r", " ").replace("\n", " ")
    clean_model = model.strip() if model and model.strip() else "Unknown"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not changelog_path.exists():
        today_str = datetime.now().strftime("%Y-%m-%d")
        is_sub = target_dir.name.startswith("sub_")
        parent_name = target_dir.parent.name if is_sub else "N/A (Root Plan)"
        cl_content = (
            f"# 計畫變更紀錄 (Changelog)\n\n"
            f"> 功能名稱：{target_dir.name}  \n"
            f"> 建立日期：{today_str}  \n"
            f"> 所屬主計畫：{parent_name}  \n"
            f"> 狀態：In Progress  \n"
            f"> 模型：{clean_model}  \n\n"
            f"> 模板版本：v1.1  \n\n"
            f"---\n\n"
            f"## 變更紀錄\n\n"
            f"| 日期時間 | 類型 | 模型 | 摘要 |\n"
            f"| :--- | :---: | :--- | :--- |\n"
            f"| {now_str} | `{clean_type}` | {clean_model} | {clean_summary} |\n"
        )
        changelog_path.write_text(cl_content, encoding="utf-8")
        return True, "appended"

    content = changelog_path.read_text(encoding="utf-8", errors="ignore")
    lines = content.splitlines()

    sep_idx = -1
    for idx, line in enumerate(lines):
        if "|" in line and re.match(r"^\|?\s*[-:]+\s*\|", line.strip()):
            sep_idx = idx
            break

    if sep_idx == -1:
        new_row = f"| {now_str} | `{clean_type}` | {clean_model} | {clean_summary} |"
        lines.extend([
            "",
            "## 變更紀錄",
            "",
            "| 日期時間 | 類型 | 模型 | 摘要 |",
            "| :--- | :---: | :--- | :--- |",
            new_row,
        ])
        changelog_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True, "appended"

    first_data_idx = sep_idx + 1
    while first_data_idx < len(lines) and not lines[first_data_idx].strip():
        first_data_idx += 1

    if first_data_idx < len(lines) and "|" in lines[first_data_idx]:
        cells = [c.strip() for c in lines[first_data_idx].strip().strip("|").split("|")]
        if len(cells) >= 3:
            existing_type = cells[1].strip().strip("`").upper()
            existing_summary = cells[-1].strip()
            if existing_type == clean_type and existing_summary == clean_summary:
                return False, "idempotent_skipped"

    new_row = f"| {now_str} | `{clean_type}` | {clean_model} | {clean_summary} |"
    lines.insert(sep_idx + 1, new_row)
    changelog_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True, "appended"
