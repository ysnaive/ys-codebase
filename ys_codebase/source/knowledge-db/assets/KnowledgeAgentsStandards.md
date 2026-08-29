### 🧠 知識庫檢索與搜尋規範 (Knowledge-DB Standards)

#### 1. 目標導向工具二分流決策矩陣 (Outcome-Driven Tool Routing)

| 下一步目標行為 | 唯一指定工具 | 守門規範與授權邊界 |
| :--- | :---: | :--- |
| **閱讀代碼 / 理解邏輯 / 查簽名 / 架構探索** | **知識庫語意檢索**<br>`knowledge-db search -s` | • 一步到位取得 AST 切片與 Docstring。<br>• 🚨 **嚴禁「Grep ➔ ViewFile」鏈式翻讀**。<br>• 💡 **切片缺行補足授權**：上下文缺失時，允許用 `view_file` 定點補讀（**限原切片行數 + 最多 30 行**，嚴禁擴大為整檔翻讀）。 |
| **代碼替換 / 行號精確定位 / 標點與常數** | **原生文字搜尋**<br>`grep_search` | 僅供已知代碼外觀且**不需閱讀上下文**時定位行號，或比對分詞器忽略之標點/常數（如 `<!--`、`0x7FFF`）。 |

---

#### 2. 三維語意構詞與兩階段分流 (Query Formulation & Routing)

- **三維語意構詞**：
  $$\text{Query} = \text{[領域概念/簽名]} + \text{[架構機制/情境]} + \text{[核心動詞]}$$
  - 通用函式名（如 `resolve`、`update`）強制附加業務情境詞（例：`search 'resolve 佔位符 拓撲' -s`）以交叉過濾同名簽章。
- **兩階段 `--ftype` 分流**：
  - **Phase A (宏觀脈絡/廣度)**：`python __${yscb.host://yscb.py}__ knowledge-db search '<情境詞組>' --ftype=md -s` (或全域搜尋)。
  - **Phase B (微觀實作/深度)**：`python __${yscb.host://yscb.py}__ knowledge-db search '<簽名詞 業務詞>' --ftype=c,cpp,py -s`。

---

#### 3. 四大防呆阻斷鐵律 (Guardrails & Anti-Patterns)

1. **第一反射與鏈式翻讀阻斷**：探索閱讀強制以 `knowledge-db search -s` 為第一反射；嚴禁未定位行號即以 `list_dir` / `view_file` 盲目翻讀，嚴禁以 `grep_search` 進行未指定精確符號之模糊廣蒐。
2. **🚨 阻斷連續同義詞抖動重搜 (Anti-Query Thrashing)**：
   - 針對同一目標**嚴禁連續發起超過 2 次微調關鍵字的無效重搜**。
   - **嚴禁將 Search 當捲軸**：命中切片需相鄰上下文時，強制依授權以 `view_file`（原範圍+30行）定點補讀或進入邏輯推理。
3. **新概念主動補足**：遭遇上下文未具備之新名詞或新協議，嚴禁憑字面臆測，必須即刻以語意化查詢補足知識後再推進。
4. **註解結構保護**：編寫或重構 Public API 時，嚴禁破壞標準 Docstring 結構。
