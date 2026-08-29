### 🧠 知識庫檢索與代碼搜尋規範 (Knowledge-DB Search Standards)

#### 1. 搜尋工具二分流決策矩陣 (Tool Routing Matrix)

| 查詢特徵與情境 | 推薦工具 | 適用說明 |
| :--- | :---: | :--- |
| **純標點 / 語法錨點 / 字串常數**（例：`__#{`、`__@{`、`<!--`、`[x]`、`TODO:`、`0x7FFF`） | `grep_search` | 標點會被分詞器過濾；直接逐字節精確匹配行號。 |
| **精確符號定位**（已知唯一全名，僅需取得單檔行號） | `grep_search` | 單檔行位址定點。 |
| **代碼標識符 / 類別 / 函式**（例：`PIDController`、`ThesaurusEngine`） | `knowledge-db search -s` | 取得駝峰/底線拆解、Docstring 摘要與上下文代碼切片。 |
| **業務概念 / 架構邏輯 / 多詞組合**（例：`三階加權展開`、`尋路演算法`、`佔位符解析`） | `knowledge-db search -s` | 享有同義詞擴展、多跳鏈式傳播與 BM25 加權排序。 |

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

1. **第一反射原則**：凡標識符、概念、功能探索與架構查詢，強制調用 `python __${yscb.host://yscb.py}__ knowledge-db search`。
2. **新詞主動補足鐵律**：在分析、修改或排查途中，凡遭遇當前上下文未曾具備之任何新名詞、新欄位、新協議或未知概念，嚴禁憑字面臆測，必須即刻將其轉化為語意化查詢（`python __${yscb.host://yscb.py}__ knowledge-db search '<新詞 業務情境>' -s`），主動補足對應知識上下文後方可繼續推進。
3. **禁止模糊探索**：嚴禁以 `grep_search` 進行未指定精確符號之全專案正則遍歷或關鍵字廣蒐。
4. **禁止盲目翻讀**：嚴禁在未定位精確行位址前使用 `list_dir` / `view_file` 盲目列出目錄或整檔閱讀。
5. **強制切片預覽**：檢索強制附加 `-s`（或 `--snippet`）直接獲取帶行號之上下文代碼切片與 Docstring。
6. **註解結構保護**：編寫或重構 Public API 時，嚴禁破壞標準 Docstring 註解結構。
