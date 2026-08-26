"""
Agents-Workflow Computed Token Providers.
Provides dynamic context map generation for JIT ContextInit workflow.
100% Python Standard Library, Zero Third-Party Dependency.
"""

import os
from typing import Optional, Any, List, Tuple
from core import uri


def get_dynamic_context_map(context: Optional[Any] = None) -> str:
    """
    動態生成當前專案已註冊之語意 URI 協議即時解析地圖 Markdown 表格。
    
    Args:
        context: 可選之編譯期/執行期上下文
    Returns:
        包含動態 JIT 解析地圖的 Markdown 區塊字串
    """
    # 核心優先展示的協議清單 (維持視覺與認知穩定)
    primary_schemes = ["project", "yscb", "plans", "archive", "docs"]
    
    # 探測專案根目錄以計算相對路徑
    proj_root = "./"
    try:
        if uri:
            proj_root = uri.resolve("project://", interactive=False)
    except Exception:
        proj_root = os.getcwd()

    rows: List[Tuple[str, str, str]] = []

    for scheme in primary_schemes:
        scheme_uri = f"{scheme}://"
        status = "[ACTIVE]"
        try:
            if uri:
                real_p = uri.resolve(scheme_uri, interactive=False)
                # 計算相對於專案根目錄的路徑
                try:
                    rel_p = os.path.relpath(real_p, proj_root).replace("\\", "/")
                    if rel_p == ".":
                        rel_display = "./"
                    elif not rel_p.startswith("."):
                        rel_display = f"./{rel_p}"
                    else:
                        rel_display = rel_p
                except Exception:
                    rel_display = real_p
            else:
                rel_display = f"./{scheme}"
        except Exception:
            rel_display = f"./{scheme}"
            status = "[!UNDEFINED]"

        rows.append((f"**`{scheme}://`**", rel_display, status))

    # 組裝 Markdown 表格
    lines = [
        "> [!NOTE]",
        "> ### 🧭 專案語意 URI 即時解析地圖 (JIT Dynamic Context)",
        "> 本專案已註冊之語意 URI 實體路徑如下：",
        "> ",
        "> | 語意 URI 協議 | 當前專案實體路徑 (相對於專案根目錄) | 狀態 |",
        "> | :--- | :--- | :--- |",
    ]

    for scheme_tag, rel_path, st in rows:
        lines.append(f"> | {scheme_tag} | `{rel_path}` | `{st}` |")

    lines.append("> ")
    lines.append("> 🛠️ **CLI 動態解析指令**：`python yscb.py uri resolve <uri>`（例：`python yscb.py uri resolve project://AGENTS.md`）")

    return "\n".join(lines)
