### 🧠 知識庫檢索與註解防護規範 (Knowledge-DB Standards)

- **知識檢索優先紀律 (Knowledge-First Axiom)**：
  - Agent 在探索專案架構、查找類別/函式或尋找既有實現時，**必須優先調用 `python yscb.py knowledge-db search <query> [--snippet]` 或查閱 `workflow.docs://` 知識庫**。附加 `--snippet`（或 `-s`）可直接於搜尋結果中獲取目標程式碼切片與 Docstring 預覽，避免無效二次檔案讀取。
  - **絕對禁止**在未經定向索引前，盲目發起大範圍檔案正則遍歷、暴力 grep 或逐檔全文讀取。
- **Docstring 與符號結構防護鐵律 (Docstring Integrity Guardrail)**：
  - Agent 在編寫或重構 Public API 時，**嚴禁刪除或破壞已有的標準 Docstring 註解結構**，必須確保符號能被 `knowledge-db` AST 解析器無損提取。
