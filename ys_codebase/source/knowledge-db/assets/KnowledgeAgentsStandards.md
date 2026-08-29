### 🧠 知識庫檢索與代碼搜尋規範 (Knowledge-DB Search Standards)

#### 1. 搜尋工具「目標產出導向」二分流決策矩陣 (Outcome-Driven Tool Routing Matrix)

| 搜尋後的下一步目標行為 | 唯一指定工具 (能力類型與別名) | 決策理由與守門規範 |
| :--- | :---: | :--- |
| **「閱讀代碼 / 理解邏輯 / 查簽名 / 查調用上下文 / 架構探索」** | **知識庫語意檢索**<br>`knowledge-db search -s` | 一步到位取得 AST 節點、Docstring 摘要、行號切片與 IDE 點擊連結。<br>🚨 **絕對禁止「文字搜尋 ➔ 檔案閱讀」兩段式翻讀**！ |
| **「執行代碼替換 / 精確行號定位 / 標點錨點 / 符號出現計數」** | **原生文字搜尋 (Text Grep)**<br>`grep_search` / `Grep` / `findTextInFiles` | 僅供已知代碼外觀且**不需閱讀上下文**，直接取得唯一行號以執行編輯工具，或比對分詞器忽略之純標點/語法常數（例：`__#{`、`<!--`、`TODO:`、`0x7FFF`）。 |

---

#### 2. 語意廣搜心法：拒絕狹隘關鍵字 (Semantic Breadth Formulation)

- **初始檢索目的**：在未掌握專案全貌前，優先用語意化詞組抓取宏觀架構廣度，嚴禁直接使用單一檔名或表面變數孤立搜尋。
- **三維語意查詢公式**：
  $$\text{Query} = \text{[領域概念]} + \text{[架構機制]} + \text{[核心動詞]}$$
  - 例：「排查 ContextInit 佔位符失效」 ➔ `search '佔位符 語意URI 拓撲映射 發布流水線' -s`
  - 例：「詞庫改為 contribute 提供」 ➔ `search '詞庫解耦 contributes 宣告式注入 跨模組聚合' -s`

---

#### 3. 簽名 + 情境複合檢索 (Signature + Context Co-Search)

- **通用簽名消歧義**：遇到通用名稱之函式或方法（如 `resolve`、`compile`、`update`、`create`、`validate`、`init`），強制採用 **「簽名詞 + 業務情境詞」** 複合檢索。
- **Docstring 交叉加權**：簽名詞命中函式標頭，情境詞命中 Docstring 註解，過濾同名無關簽章。
  - 例：尋找佔位符路徑解算 ➔ `search 'resolve 佔位符 拓撲 產物工廠' -s`（避免單搜 `resolve`）
  - 例：尋找模組升級與快照 ➔ `search 'update 模組升級 雙軌快照' -s`（避免單搜 `update`）

---

#### 4. 兩階段檢索流程 (`--ftype` Routing)

- **Phase A (宏觀脈絡 / 廣度)**：`python __${yscb.host://yscb.py}__ knowledge-db search '<語意化情境詞組>' --ftype=md -s`（或不加 `--ftype` 全空間檢索）。
- **Phase B (微觀實作 / 深度)**：`python __${yscb.host://yscb.py}__ knowledge-db search '<簽名詞 業務情境詞>' --ftype=c,cpp,py -s`。

---

#### 5. 執行紀律 (Guardrails)

1. **第一反射原則**：凡以「理解、閱讀、探索」為目的，強制以 `python __${yscb.host://yscb.py}__ knowledge-db search -s` 為第一反射，杜絕盲目使用原生文字搜尋 (Text Grep) 或檔案閱讀 (File Reader) 工具。
2. **🚨 阻斷「Grep ➔ ViewFile」鏈式翻讀反模式**：凡調用原生文字搜尋工具 (Text Grep: `grep_search` / `Grep` / `findTextInFiles` 等) 後緊接著對該檔案調用檔案閱讀工具 (File Reader: `view_file` / `View` / `read_file` / `readFile` 等) 進行閱讀者，視為嚴重複合工具浪費與決策違規！切片閱讀需求必須直接調用 `knowledge-db search -s` 一步到位。
3. **新詞主動補足鐵律**：在分析、修改或排查途中，凡遭遇當前上下文未曾具備之任何新名詞、新欄位、新協議或未知概念，嚴禁憑字面臆測，必須即刻將其轉化為語意化查詢（`python __${yscb.host://yscb.py}__ knowledge-db search '<新詞 業務情境>' -s`），主動補足對應知識上下文後方可繼續推進。
4. **禁止模糊探索**：嚴禁以原生文字搜尋工具 (Text Grep) 進行未指定精確符號之全專案正則遍歷或關鍵字廣蒐。
5. **禁止盲目翻讀**：嚴禁在未定位精確行位址前使用目錄列出 / 檔案閱讀工具 (`list_dir` / `view_file` / `read_file`) 盲目列出目錄或整檔閱讀。
6. **強制切片預覽**：檢索強制附加 `-s`（或 `--snippet`）直接獲取帶行號之上下文代碼切片與 Docstring。
7. **註解結構保護**：編寫或重構 Public API 時，嚴禁破壞標準 Docstring 註解結構。
