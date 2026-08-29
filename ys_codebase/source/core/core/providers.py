"""
YS-Codebase Core Computed Token Providers.
Provides dynamic AGENTS_CLI_GUILD and Phase-Aware JIT CLI Guild generation from declared contributes.core.commands.
100% Python Standard Library, Zero Third-Party Dependency.
100% SDK-Driven: powered by core.contributes.get().
"""

from typing import Dict, Any, Optional, List, Tuple
from core import contributes


def _normalize_tier(raw_tier: Any) -> str:
    tier = str(raw_tier).strip().lower() if raw_tier else "conditional"
    if tier in ("safe", "autonomous", "tier1", "tier_1"):
        return "safe"
    elif tier in ("gated", "strict", "tier3", "tier_3"):
        return "gated"
    return "conditional"


def _format_tier_badge(tier: str) -> str:
    if tier == "safe":
        return "🟢 自主安全"
    elif tier == "gated":
        return "🔴 授權守門"
    return "🟡 階段條件"


def get_agents_cli_guild(context: Optional[Any] = None, **kwargs: Any) -> str:
    """
    動態編譯全系統已宣告之 contributes.core.commands 為三級權限 Markdown 防呆對照表。

    過濾規則：
    - 若指令之 case_pros 與 case_cons 兩者皆無定義或皆為空（空字串/空陣列），自動排除於清單中。
    - 依權限分級（🟢 自主安全 ➔ 🟡 階段條件 ➔ 🔴 授權守門）與模組名稱排序輸出。

    :param context: 可選之編譯期上下文（由 agents-workflow compiler 提供）
    :return: 格式化完成之三級權限 Markdown 防呆手冊文字
    """
    # 1. 透過標準 SDK 取得全系統已合併之 core commands
    all_commands = contributes.get("core", "commands", default={})
    if not isinstance(all_commands, dict) or not all_commands:
        return "| 權限分級 | 指令名稱 | 推薦/適用情境 (Pros) | 🚨 絕對禁止/不適用情境 (Cons) |\n| :---: | :--- | :--- | :--- |\n| - | *(目前無已註冊之 CLI 防呆指令)* | - | - |"

    # 2. 依 __provider__ 分組搜集
    grouped_commands: Dict[str, List[Tuple[str, str, str, List[str], List[str]]]] = {}

    for cmd_name, cmd_body in sorted(all_commands.items()):
        if not isinstance(cmd_body, dict):
            continue

        donor = cmd_body.get("__provider__", "core")
        desc = str(cmd_body.get("description", "")).strip()
        tier = _normalize_tier(cmd_body.get("tier"))
        raw_pros = cmd_body.get("case_pros", [])
        raw_cons = cmd_body.get("case_cons", [])

        case_pros: List[str] = []
        if isinstance(raw_pros, str):
            case_pros = [raw_pros.strip()] if raw_pros.strip() else []
        elif isinstance(raw_pros, list):
            case_pros = [str(p).strip() for p in raw_pros if str(p).strip()]

        case_cons: List[str] = []
        if isinstance(raw_cons, str):
            case_cons = [raw_cons.strip()] if raw_cons.strip() else []
        elif isinstance(raw_cons, list):
            case_cons = [str(c).strip() for c in raw_cons if str(c).strip()]

        # 核心防呆過濾：若 pros 與 cons 皆無，自動排除
        if not case_pros and not case_cons:
            continue

        if donor not in grouped_commands:
            grouped_commands[donor] = []
        grouped_commands[donor].append((cmd_name, desc, tier, case_pros, case_cons))

    if not grouped_commands:
        return "| 權限分級 | 指令名稱 | 推薦/適用情境 (Pros) | 🚨 絕對禁止/不適用情境 (Cons) |\n| :---: | :--- | :--- | :--- |\n| - | *(目前無已註冊之 CLI 防呆指令)* | - | - |"

    # 3. 排序模組 (core 最先，其餘字母序)
    ordered_donors = (["core"] if "core" in grouped_commands else []) + sorted([d for d in grouped_commands if d != "core"])

    tier_order = {"safe": 0, "conditional": 1, "gated": 2}
    all_rows: List[Tuple[int, str, str, str, str]] = []

    for donor in ordered_donors:
        for cmd_name, desc, tier, pros, cons in grouped_commands[donor]:
            full_cmd = f"`python yscb.py {cmd_name}`" if donor == "core" else f"`python yscb.py {donor} {cmd_name}`"
            badge = _format_tier_badge(tier)

            # Pros 格式化
            if pros:
                pros_str = "<br/>".join([f"✅ {p}" if not p.startswith("✅") else p for p in pros])
            else:
                pros_str = f"✅ {desc}" if desc else "✅ 通用呼叫"

            # Cons 格式化
            if cons:
                cons_str = "<br/>".join([f"🚨 {c}" if not c.startswith("🚨") else c for c in cons])
            else:
                cons_str = "*(無特殊禁止事項)*"

            # Escape pipe characters in table cells
            pros_str = pros_str.replace("|", "\\|")
            cons_str = cons_str.replace("|", "\\|")

            all_rows.append((tier_order.get(tier, 1), badge, full_cmd, pros_str, cons_str))

    lines: List[str] = []
    lines.append("| 權限分級 | 指令名稱 | 推薦/適用情境 (Pros) | 🚨 絕對禁止/不適用情境 (Cons) |")
    lines.append("| :---: | :--- | :--- | :--- |")

    for _, badge, full_cmd, pros_str, cons_str in all_rows:
        lines.append(f"| {badge} | **{full_cmd}** | {pros_str} | {cons_str} |")

    return "\n".join(lines)


def get_phase_cli_guild(context: Optional[Any] = None, phase: Optional[str] = None, **kwargs: Any) -> str:
    """
    依據給定之 Phase 標籤動態過濾 commands，產出適用於該階段之極簡 JIT 指令引導。

    :param context: 可選之編譯期上下文（可自 context.token 或 context.phase 提取 Phase 名稱）
    :param phase: 明確指定之 Phase 字串（例："P00", "P05", "P06", "P07", "FT", "RESEARCH"）
    :return: 適用於模板頂部 HTML 註解之 JIT 指令導引文字
    """
    target_phase = str(phase or "").strip().upper()
    if not target_phase and context:
        if isinstance(context, str):
            target_phase = context.upper()
        elif isinstance(context, dict):
            target_phase = str(context.get("phase") or context.get("token") or "").upper()

    all_commands = contributes.get("core", "commands", default={})
    if not isinstance(all_commands, dict) or not all_commands:
        return ""

    recommended_cmds: List[str] = []
    gated_warnings: List[str] = []

    for cmd_name, cmd_body in sorted(all_commands.items()):
        if not isinstance(cmd_body, dict):
            continue

        donor = cmd_body.get("__provider__", "core")
        full_cmd = f"python yscb.py {cmd_name}" if donor == "core" else f"python yscb.py {donor} {cmd_name}"
        desc = str(cmd_body.get("description", "")).strip()
        tier = _normalize_tier(cmd_body.get("tier"))

        raw_phases = cmd_body.get("phases", [])
        phases: List[str] = []
        if isinstance(raw_phases, str):
            phases = [p.strip().upper() for p in raw_phases.split(",") if p.strip()]
        elif isinstance(raw_phases, list):
            phases = [str(p).strip().upper() for p in raw_phases if str(p).strip()]

        is_match = False
        if target_phase and (target_phase in phases or any(target_phase == p or p.startswith(target_phase) for p in phases)):
            is_match = True

        if is_match:
            badge = _format_tier_badge(tier)
            raw_pros = cmd_body.get("case_pros", [])
            pros_summary = ""
            if isinstance(raw_pros, list) and raw_pros:
                pros_summary = f"（{raw_pros[0]}）"
            elif isinstance(raw_pros, str) and raw_pros:
                pros_summary = f"（{raw_pros}）"
            elif desc:
                pros_summary = f"（{desc}）"

            recommended_cmds.append(f"- `{full_cmd}` {badge}{pros_summary}")
        elif tier == "gated":
            raw_cons = cmd_body.get("case_cons", [])
            con_summary = "嚴禁未經開發者明確指示擅自執行"
            if isinstance(raw_cons, list) and raw_cons:
                con_summary = raw_cons[0]
            elif isinstance(raw_cons, str) and raw_cons:
                con_summary = raw_cons

            gated_warnings.append(f"- 🚨 嚴禁執行 `{full_cmd}`（{con_summary}）")

    if not recommended_cmds and not gated_warnings:
        return ""

    out_lines: List[str] = []
    if recommended_cmds:
        out_lines.append("- **🛠️ 當前階段推薦 CLI 指令 (Recommended CLI)**：")
        out_lines.extend([f"  {rc}" for rc in recommended_cmds])
    if gated_warnings:
        out_lines.append("- **🚨 授權守門與紅線禁忌 (Gated & Prohibited)**：")
        out_lines.extend([f"  {gw}" for gw in gated_warnings[:3]])

    return "\n".join(out_lines)


def get_phase00_cli_guild(context: Optional[Any] = None, **kwargs: Any) -> str:
    return get_phase_cli_guild(context, phase="P00", **kwargs)


def get_phase01_cli_guild(context: Optional[Any] = None, **kwargs: Any) -> str:
    return get_phase_cli_guild(context, phase="P01", **kwargs)


def get_phase02_cli_guild(context: Optional[Any] = None, **kwargs: Any) -> str:
    return get_phase_cli_guild(context, phase="P02", **kwargs)


def get_phase03_cli_guild(context: Optional[Any] = None, **kwargs: Any) -> str:
    return get_phase_cli_guild(context, phase="P03", **kwargs)


def get_phase04_cli_guild(context: Optional[Any] = None, **kwargs: Any) -> str:
    return get_phase_cli_guild(context, phase="P04", **kwargs)


def get_phase05_cli_guild(context: Optional[Any] = None, **kwargs: Any) -> str:
    return get_phase_cli_guild(context, phase="P05", **kwargs)


def get_phase06_cli_guild(context: Optional[Any] = None, **kwargs: Any) -> str:
    return get_phase_cli_guild(context, phase="P06", **kwargs)


def get_phase07_cli_guild(context: Optional[Any] = None, **kwargs: Any) -> str:
    return get_phase_cli_guild(context, phase="P07", **kwargs)


def get_fast_track_cli_guild(context: Optional[Any] = None, **kwargs: Any) -> str:
    return get_phase_cli_guild(context, phase="FT", **kwargs)


def get_research_cli_guild(context: Optional[Any] = None, **kwargs: Any) -> str:
    return get_phase_cli_guild(context, phase="RESEARCH", **kwargs)
