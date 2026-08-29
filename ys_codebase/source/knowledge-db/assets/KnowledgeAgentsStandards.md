### 🧠 知識庫檢索與日常代碼搜尋強制鐵律 (Knowledge-DB Mandatory Search Standards)

#### 🚨 執行紀律：日常代碼搜尋強制工具替代 (Search Tool Substitution & Prohibitions)
- **預設第一反射工具 (Default First Search Tool)**：
  在日常任何任務、問題排查、符號定位、功能探索或架構查詢時，**Agent 的第一搜尋動作 100% 必須強制調用 `python __${yscb.host://yscb.py}__ knowledge-db search`**，嚴禁以內建工具走捷徑。
- **🚨 絕對禁止條款 (Absolute Prohibitions)**：
  1. **嚴禁以 `grep_search` 進行模糊探索**：絕對禁止在未知精確符號/常數全名前，使用 `grep_search` 發起全專案正則遍歷、模糊搜尋或關鍵字廣蒐。
  2. **嚴禁以 `list_dir` / `view_file` 盲目翻找**：絕對禁止在未透過 `knowledge-db search` 定位精確行位址前，盲目列出目錄或整檔逐篇閱讀。
- **唯一允許調用 `grep_search` 的例外條件 (Strict Exception)**：
  僅在「已獲取 100% 精確且唯一的符號名/常數名（如 `foo.doSomethingExact`），且僅需在單一已知檔案內精準定位行號」時，方可使用 `grep_search`。其餘 90%+ 的日常代碼探索與檢索情境，一律強制由 `knowledge-db search -s` 承接。

- **日常檢索決策樹與 `--ftype` 分流指引 (Search Decision Tree & FType Routing)**：
  1. **確定搜索程式碼 (Code Search)**：
     ➔ 附加 `--ftype=c,cpp,py`（或 `--ftype=py`, `--ftype=c,cpp` 等）：  
     `python __${yscb.host://yscb.py}__ knowledge-db search '<關鍵詞組合>' --ftype=c,cpp,py -s`
  2. **確定搜索規範、文檔或 SOP (Documentation Search)**：
     ➔ 附加 `--ftype=md`：  
     `python __${yscb.host://yscb.py}__ knowledge-db search '<關鍵詞組合>' --ftype=md -s`
  3. **廣義探索、語意探索或跨來源關聯 (Hybrid / Concept Search)**：
     ➔ 不加 `--ftype` 進行全空間加權檢索：  
     `python __${yscb.host://yscb.py}__ knowledge-db search '<語意化描述>' -s`

- **「定位 ➔ 切片即時理解」核心哲學 (Targeted Reading & Snippet Axiom)**：
  - **切片即時預覽**：檢索一律強制附加 `-s`（或 `--snippet`）直接獲取帶行號之上下文代碼切片與 Docstring 摘要。
  - **極小範圍定向閱讀**：利用檢索定位之精確檔案與行號進行極小範圍定向確認，消滅 80%+ 的無效二次檔案讀取。

- **Docstring 與符號結構防護鐵律 (Docstring Integrity Guardrail)**：
  - Agent 在編寫或重構 Public API 時，**嚴禁刪除或破壞已有的標準 Docstring 註解結構**，必須確保符號能被 `knowledge-db` AST 解析器無損提取。
