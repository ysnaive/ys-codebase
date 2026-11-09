### 🌳 AST 語法樹與呼叫拓撲引擎 (`ast` — 單檔結構大綱、部位切片與全倉語意圖譜)

- **① 模組定位與適用時機**：
  - Layer 2 零向量/零 BM25 依賴之確定性語法樹與語意圖譜核心引擎，內建 7 大官方方言隔離 (`dialects/<lang>`)、4-Pass 確定性跨檔連結器 (`WorkspaceGraphLinker`)、C# `partial class` 雙層分部符號聚合、同名異載群組定址與單次解析雙圖譜快照共享 (`ASTSnapshot` & `WorkspaceSymbolGraph`)。
  - 當你需要查閱已知檔案的結構大綱與行號區間 (`outline`)、無損切取符號特定部位 (`slice`)、發現跨分部姊妹檔 (`[Partial Siblings]`)，或追蹤誰呼叫/繼承了目標符號 (`callers`/`callees`/`impact`/`traverse`) 時使用。
- **② 標準用法速查 (Golden Recipes)**：
  - **單檔結構大綱與三維度正交過濾 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ ast outline <file_or_uri> [--public|--private|--static|--non-static|--methods|--fields|--types|--merged]`
  - **結構化部位無損切片 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ ast slice "<symbol>" [--part=outer|signature|doc|body|parameters|return_type|name] [--json]`（`<symbol>` 為 `[kind] [scope.]name[(params)]` 如 `"ASTEngine.slice_part"`，或雙冒號 `<rel_path>::<fqn>`；不支援單冒號 `<file>:<symbol>`）
  - **全倉語意圖譜有向遍歷 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ ast traverse "<symbol>" [--kind=calls,inherits,implements,imports,documents] [--direction=out|in|both] [--depth=1] [--json]`（`<symbol>` 同樣支援 `[kind] [scope.]name[(params)]` 或 `<rel_path>::<fqn>`）
  - **追蹤上游呼叫方與同名重載群組 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ ast callers "<symbol>" [-s] [--ftype=<ext>]`
  - **追蹤下游被呼叫方 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ ast callees "<symbol>" [-s] [--ftype=<ext>]`
  - **評估多階重構爆炸半徑 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ ast impact "<symbol>" [--depth=2] [--ftype=<ext>]`
  - **快照與圖譜狀態查詢 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ ast status`
- **③ 隨包手冊語意連結**：
  - 深入探索方言隔離架構、雙層分部模型與語言擴充請按需唯讀查閱 [`ast 隨包手冊`](`__#{module://ast/README.md}__`)。
