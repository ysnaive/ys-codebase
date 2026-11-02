### 🔍 Knowledge-DB 混合語意知識庫 (`knowledge-db` — BM25 + 向量複合檢索)
<!-- yscb:ignore:begin -->
註：單檔結構大綱 `outline` 與呼叫拓撲 `callers` / `callees` / `impact` 已獨立收斂至 `module:ast`。
<!-- yscb:ignore:end -->
- **① 模組定位與適用時機**：
  - 直接消費 `module:ast` 產出之 `ASTSnapshot` 符號流，提供跨空間 BM25 倒排與 ONNX 向量混合語意檢索（RRF），具備 Pull-Based JIT 雙水位線 (`file-space` + `ast_generation`) 變更感知與背景兩階段微批次向量自癒。
  - 當你需要探索未知檔案座標、跨空間搜尋文檔或程式碼概念時使用（單檔大綱與呼叫拓撲請用 `ast` 模組）。
- **② 標準用法速查 (Golden Recipes)**：
  - **跨空間語意與關鍵字檢索 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ knowledge-db search "<query>" [--space=<name>] [--ftype=<ext>] [--limit=10] [-s]`
  - **索引健康度與水位檢查 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ knowledge-db status`
  - **全量索引建構與匯出 (`🟡 [CONDITIONAL]`)**：`python __${yscb.host://yscb.py}__ knowledge-db index [--space=<name>] [--force] [--export=<path>]`
  - **本地向量模型管理 (`🟡 [CONDITIONAL]`)**：`python __${yscb.host://yscb.py}__ knowledge-db model <status|download|clean>`
- **③ 隨包手冊語意連結**：
  - 深入探索混合檢索權重、同義詞擴充與兩階段背景服務請按需唯讀查閱 [`knowledge-db 隨包手冊`](`__#{module://knowledge-db/README.md}__`)。
