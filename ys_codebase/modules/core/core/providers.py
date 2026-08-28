"""
YS-Codebase Core Computed Token Providers.
Provides dynamic AGENTS_CLI_GUILD generation from declared contributes.core.commands.
100% Python Standard Library, Zero Third-Party Dependency.
100% SDK-Driven: powered by core.contributes.get().
"""

from typing import Dict, Any, Optional, List, Tuple
from core import contributes


def get_agents_cli_guild(context: Optional[Any] = None, **kwargs: Any) -> str:
    """
    動態編譯全系統已宣告之 contributes.core.commands 為 Markdown 防呆對照表。

    過濾規則：
    - 若指令之 case_pros 與 case_cons 兩者皆無定義或皆為空（空字串/空陣列），自動排除於清單中。
    - 僅保留具備防呆語意宣告之指令，依模組名稱與指令名稱排序輸出。

    :param context: 可選之編譯期上下文（由 agents-workflow compiler 提供）
    :return: 格式化完成之 Markdown 防呆手冊文字
    """
    # 1. 透過標準 SDK 取得全系統已合併之 core commands
    all_commands = contributes.get("core", "commands", default={})
    if not isinstance(all_commands, dict) or not all_commands:
        return "| 指令名稱 | 推薦/適用情境 (Pros) | 🚨 絕對禁止/不適用情境 (Cons) |\n| :--- | :--- | :--- |\n| *(目前無已註冊之 CLI 防呆指令)* | - | - |"

    # 2. 依 __provider__ 分組搜集
    grouped_commands: Dict[str, List[Tuple[str, str, List[str], List[str]]]] = {}

    for cmd_name, cmd_body in sorted(all_commands.items()):
        if not isinstance(cmd_body, dict):
            continue

        donor = cmd_body.get("__provider__", "core")
        desc = str(cmd_body.get("description", "")).strip()
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
        grouped_commands[donor].append((cmd_name, desc, case_pros, case_cons))

    if not grouped_commands:
        return "| 指令名稱 | 推薦/適用情境 (Pros) | 🚨 絕對禁止/不適用情境 (Cons) |\n| :--- | :--- | :--- |\n| *(目前無已註冊之 CLI 防呆指令)* | - | - |"

    # 3. 排序模組 (core 最先，其餘字母序)
    ordered_donors = (["core"] if "core" in grouped_commands else []) + sorted([d for d in grouped_commands if d != "core"])

    lines: List[str] = []
    lines.append("| 指令名稱 | 推薦/適用情境 (Pros) | 🚨 絕對禁止/不適用情境 (Cons) |")
    lines.append("| :--- | :--- | :--- |")

    for donor in ordered_donors:
        for cmd_name, desc, pros, cons in grouped_commands[donor]:
            full_cmd = f"`python yscb.py {cmd_name}`" if donor == "core" else f"`python yscb.py {donor} {cmd_name}`"
            
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

            lines.append(f"| **{full_cmd}** | {pros_str} | {cons_str} |")

    return "\n".join(lines)
