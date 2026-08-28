### 🧠 知識庫檢索與註解防護規範 (Knowledge-DB Standards)

- **日常檢索與調研優先紀律 (Research & Knowledge-First Axiom)**：
  - **日常全時主動使用 (Daily & Universal Practice)**：Agent 在日常任何開發、除錯、排查、架構探索或概念搜尋時（非僅限於特定 SOP 環節提醒），**必須常態化優先調用 `python yscb.py knowledge-db search <query> [-s|--snippet]` 或查閱 `workflow.docs://` 知識庫**。
  - **代碼切片即時預覽**：附加 `-s`（或 `--snippet`）可直接獲取精確行號、Docstring 摘要與上下文程式碼片段，消除 80%+ 的無效二次檔案讀取。
  - **傳統 Grep 調度邊界**：除「已知精確且完整的類別/函式全名或完整簽名字串」可調用精準 grep 外，任何概念性、功能性、跨檔案或語意化探索，**絕對禁止**在未經知識庫定向檢索前盲目發起大範圍檔案正則遍歷、暴力 grep 或逐檔全文翻找。
- **Docstring 與符號結構防護鐵律 (Docstring Integrity Guardrail)**：
  - Agent 在編寫或重構 Public API 時，**嚴禁刪除或破壞已有的標準 Docstring 註解結構**，必須確保符號能被 `knowledge-db` AST 解析器無損提取。
