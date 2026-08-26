"""
YS-Codebase Core Computed Token Providers.
Provides dynamic AGENTS_CLI_GUILD generation from declared contributes.core.commands.
100% Python Standard Library, Zero Third-Party Dependency.
"""

from typing import Dict, Any, Optional, List, Tuple
import os
from core import uri
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
    module_commands: List[Tuple[str, str, str, List[str], List[str]]] = []

    # 1. 搜集所有已安裝或源碼模組
    installed_modules: List[str] = []
    try:
        if uri.exists("module://"):
            installed_modules = uri.listdir("module://")
    except Exception:
        installed_modules = []

    if not installed_modules:
        # Fallback 探測 source/ (開發環境跑測支援)
        try:
            if uri.exists("module.source://"):
                installed_modules = uri.listdir("module.source://")
        except Exception:
            pass

    # 排序模組 (core 第一，其餘字母序)
    ordered_mods = (["core"] if "core" in installed_modules else []) + sorted([m for m in installed_modules if m != "core"])

    for mod_name in ordered_mods:
        mf_data: Dict[str, Any] = {}
        for base_scheme in ["module://", "module.source://"]:
            mf_uri = f"{base_scheme}{mod_name}/manifest.json"
            if uri.exists(mf_uri):
                try:
                    mf_data = uri.read_json(mf_uri)
                    if mf_data:
                        break
                except Exception:
                    pass

        if not mf_data:
            continue

        c_core = mf_data.get("contributes", {}).get("core", {})
        cmds = c_core.get("commands", {})
        if not isinstance(cmds, dict):
            continue

        for cmd_name, cmd_body in sorted(cmds.items()):
            desc = ""
            case_pros: List[str] = []
            case_cons: List[str] = []

            if isinstance(cmd_body, dict):
                desc = str(cmd_body.get("description", "")).strip()
                raw_pros = cmd_body.get("case_pros", [])
                raw_cons = cmd_body.get("case_cons", [])

                if isinstance(raw_pros, str):
                    case_pros = [raw_pros.strip()] if raw_pros.strip() else []
                elif isinstance(raw_pros, list):
                    case_pros = [str(p).strip() for p in raw_pros if str(p).strip()]

                if isinstance(raw_cons, str):
                    case_cons = [raw_cons.strip()] if raw_cons.strip() else []
                elif isinstance(raw_cons, list):
                    case_cons = [str(c).strip() for c in raw_cons if str(c).strip()]
            elif isinstance(cmd_body, str):
                desc = cmd_body.strip()
                case_pros = []
                case_cons = []

            # 🚨 關鍵過濾規則：若 case_pros 與 case_cons 兩者皆無定義或皆為空，排除於生成清單
            if not case_pros and not case_cons:
                continue

            module_commands.append((mod_name, cmd_name, desc, case_pros, case_cons))

    if not module_commands:
        return "> *(目前全系統模組尚未定義具備防呆情境之 CLI 指令)*\n"

    # 組裝 Markdown 表格
    lines = [
        "| 模組 | 指令 (Command) | 說明 (Description) | ✅ 推薦/適用情境 (case_pros) | 🚨 絕對禁止/不適用情境 (case_cons) |",
        "| :---: | :--- | :--- | :--- | :--- |"
    ]

    for mod_name, cmd_name, desc, pros, cons in module_commands:
        cmd_display = f"`{cmd_name}`" if mod_name == "core" else f"`{mod_name} {cmd_name}`"
        pros_str = "<br/>".join([f"• {p}" for p in pros]) if pros else "—"
        cons_str = "<br/>".join([f"• {c}" for c in cons]) if cons else "—"
        
        desc_clean = desc.replace("\n", " ").replace("|", "\\|")
        pros_clean = pros_str.replace("\n", " ").replace("|", "\\|")
        cons_clean = cons_str.replace("\n", " ").replace("|", "\\|")

        lines.append(f"| `{mod_name}` | {cmd_display} | {desc_clean} | {pros_clean} | {cons_clean} |")

    return "\n".join(lines)
