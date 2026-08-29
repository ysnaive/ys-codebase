### 🧠 知識庫檢索與註解防護規範 (Knowledge-DB Standards)

- **日常檢索決策樹與定向閱讀紀律 (Search Decision Tree & Targeted Reading Axiom)**：
  - **剛性檢索決策樹 (Search Decision Tree)**：
    Agent 在日常任何開發、除錯、排查、架構探索或概念搜尋時，**必須嚴格依據以下決策路徑選擇工具**：
    1. **已包含明確、獨一無二的符號/簽章？**（例：`foo.doSomething`、`class SnippetExtractor`、精確常數名）
       ➔ **直接調用原生精準工具**（如 `grep_search` 進行單一精確字串匹配）。
    2. **具備明確分類或模組功能概念？**（例："實體智能尋路模組"、"倒排索引快照"）
       ➔ **調用複合關鍵詞檢索**：`python __${yscb.host://yscb.py}__ knowledge-db search '<關鍵詞組合>' -s`（例：`"實體 A* 尋路 pathfinding entity"`）。
    3. **廣義需求、語意探索或跨模組關聯？**（例："修改角色尋路行為"、"快取失效機制"）
       ➔ **調用語意化敘述檢索**：`python __${yscb.host://yscb.py}__ knowledge-db search '<語意化需求>' -s`（例：`"修改角色尋路行為"`）。
  - **「定位 ➔ 定向閱讀」核心哲學**：
    - **非無條件暴力廣蒐**：不是不用 grep，而是用 `knowledge-db search -s` 快速定位需要的符號與行位址。**絕對禁止**在未知精確簽章前盲目發起全專案大範圍正則遍歷、暴力 grep 或逐檔翻找。
    - **代碼切片即時預覽**：檢索一律優先附加 `-s`（或 `--snippet`）直接獲取精確行號、Docstring 摘要與上下文代碼切片。
    - **極小範圍定向閱讀**：利用檢索定位之精確檔案與行號，進行極小範圍的定向閱讀（`view_file`）或單一目標確認，消除 80%+ 的無效二次檔案讀取。
- **Docstring 與符號結構防護鐵律 (Docstring Integrity Guardrail)**：
  - Agent 在編寫或重構 Public API 時，**嚴禁刪除或破壞已有的標準 Docstring 註解結構**，必須確保符號能被 `knowledge-db` AST 解析器無損提取。
