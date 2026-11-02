### 🌳 AST 語法樹與呼叫拓撲引擎 (`ast` — 單檔結構大綱、分部符號與雙向呼叫圖譜)

- **① 模組定位與適用時機**：
  - Layer 2 零向量/零 BM25 依賴之確定性語法樹與呼叫拓撲核心引擎，內建 7 大官方方言隔離 (`dialects/<lang>`)、C# `partial class` 雙層分部符號聚合、同名異載群組定址與單次解析符號快照共享 (`ASTSnapshot`)。
  - 當你需要查閱已知檔案的結構大綱與行號區間 (`outline`)、發現跨分部姊妹檔 (`[Partial Siblings]`)，或追蹤誰呼叫了目標符號 (`callers`/`callees`/`impact`) 時使用。
- **② 標準用法速查 (Golden Recipes)**：
  - **單檔結構大綱與三維度正交過濾 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ ast outline <file_or_uri> [--public|--private|--static|--non-static|--methods|--fields|--types|--merged]`
  - **追蹤上游呼叫方与同名重載群組 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ ast callers "<symbol>" [-s] [--ftype=<ext>]`
  - **追蹤下游被呼叫方 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ ast callees "<symbol>" [-s] [--ftype=<ext>]`
  - **評估多階重構爆炸半徑 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ ast impact "<symbol>" [--depth=2] [--ftype=<ext>]`
  - **快照與圖譜狀態查詢 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ ast status`
- **③ 隨包手冊語意連結**：
  - 深入探索方言隔離架構、雙層分部模型與語言擴充請按需唯讀查閱 [`ast 隨包手冊`](`__#{module://ast/README.md}__`)。
