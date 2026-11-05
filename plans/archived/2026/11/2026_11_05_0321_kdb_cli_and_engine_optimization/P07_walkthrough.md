# 成果展示與結案報告 (Walkthrough)

> 功能名稱：2026_11_05_0321_kdb_cli_and_engine_optimization  
> 建立日期：2026-11-05  
> 所屬主計畫：無  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Medium)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  - **CLI 與 JSON 輸出路徑去重瘦身與 `--file-uri` 顯式開關 (`FR-01` ~ `FR-03`, `EC-01`, `NFR-01`)**：將 `ResultFormatter` (`knowledge-db`) 與 `ASTResultFormatter` (`ast`) 之 `file_uri` 預設改為 `False`（預設輸出標準專案相對路徑 `rel/path.py:Lstart-end`），於 `search`/`outline`/`callers`/`callees`/`impact` 新增 `--file-uri` 獨立選項群組旗標；將 `kdb search` 無旗標預設顯示對齊 `detail_mode="auto"`（單命中折疊單行、多命中子項不重複印出檔名），並在 `simple`/`preview` JSON 階層預設省略冗餘 `"file_uri"` 與空字串選填欄位。
  - **`kdb` 頂層模組別名與軌跡審計對齊 (`FR-04`)**：於 `knowledge-db/contributes/core.json` 註冊 `"module_alias": ["kdb"]`，並更新 `agents_workflow/plans/_trace_parser.py` 支援辨識 `python yscb.py kdb ...` 且統一歸一化至 `"knowledge-db"`。
  - **`ASTEngine` 呼叫圖譜惰性載入、`unified.meta.json` 輕量探針、相對斷崖截斷與 `InvertedIndex` `0..n` 整數 `doc_idx` 駐留 (`FR-05` ~ `FR-08`, `EC-02` ~ `EC-04`, `NFR-02`)**：於 `ASTEngine` 拆分 `_ensure_symbols_loaded()` 與 `_ensure_graph_loaded()` 並持久化 `unified.meta.json`；於 `IndexingPipeline.search(adaptive_limit=True)` 實作文字模式動態分數斷崖截斷；於 `InvertedIndex` 實作 `_doc_id_table` / `_free_doc_indices` `0..n` 整數文檔碼映射與 `SparseFieldFreqs(dict)` 稀疏欄位詞頻；並將 `KnowledgeEngine.status()` 改為優先自 `snap_state.entries` 計算存活檔案數免除重複 `os.walk`。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/ast/contributes/core.json` | Modify | 新增 `"uri"` 群組之 `--file-uri` 選項定義 |
| `ys_codebase/source/ast/ast_engine/formatter.py` | Modify | `file_uri` 預設改為 `False` 並確保輸出完整相對路徑 |
| `ys_codebase/source/ast/ast_engine/engine.py` | Modify | 拆分 `_ensure_symbols_loaded()` / `_ensure_graph_loaded()` 與 `unified.meta.json` 指紋快取 |
| `ys_codebase/source/ast/scripts/cli.py` | Modify | 解析並傳遞 `--file-uri` 旗標 |
| `ys_codebase/source/ast/tests/test_ast_engine.py` | Modify | 新增 `OPT-01` 與 `OPT-05` 單元測試 |
| `ys_codebase/source/knowledge-db/contributes/core.json` | Modify | 新增 `"module_alias": ["kdb"]` 與 `--file-uri` 選項 |
| `ys_codebase/source/knowledge-db/knowledge_db/formatter.py` | Modify | 實作 `OPT-01` ~ `OPT-03` 輸出精簡與分級瘦身 |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | 支援 `adaptive_limit` 並於 `status()` 直接讀取快照計算存活檔案數 (`OPT-08`) |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | 串接 `get_persisted_meta()` (`OPT-05`) 與 `adaptive_limit` 相對斷崖截斷 (`OPT-06`) |
| `ys_codebase/source/knowledge-db/knowledge_db/retrieval.py` | Modify | 實作 `SparseFieldFreqs(dict)` 與 `InvertedIndex` `0..n` `doc_idx` 駐留表 (`OPT-07`) |
| `ys_codebase/source/knowledge-db/scripts/cli.py` | Modify | 對齊 `detail_mode="auto"`、傳遞 `--file-uri` 與 `adaptive_limit` |
| `ys_codebase/source/knowledge-db/tests/test_cli.py` | Modify | 擴充 CLI `auto` 模式、`--file-uri` 與 JSON 分級瘦身測試 |
| `ys_codebase/source/knowledge-db/tests/test_engine.py` | Modify | 擴充 `OPT-05` ~ `OPT-08` 單元測試 |
| `ys_codebase/source/knowledge-db/tests/test_retrieval.py` | Modify | 擴充 `doc_idx` 駐留、Free-List 回收與 `SparseFieldFreqs` 測試 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/_trace_parser.py` | Modify | 辨識 `kdb` 別名並歸一化至 `"knowledge-db"` (`OPT-04`) |
| `ys_codebase/source/agents-workflow/tests/test_plans_toolchain.py` | Modify | 新增 `kdb search` 軌跡解析測試 |
| `docs/knowledge-db/README.md` | Modify | 更新 `kdb` 短別名、`--file-uri` 與預設 `auto` 輸出文檔 |
| `docs/knowledge-db/retrieval.md` | Modify | 更新 `InvertedIndex` `doc_idx` 駐留、斷崖截斷與 `unified.meta.json` 機制說明 |
| `CHANGELOG.md` | Modify | 記錄 `2026_11_05_0321_kdb_cli_and_engine_optimization` 結案摘要 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：
  - `dev check {ast,knowledge-db,agents-workflow}`：100% `[PASS]`
  - `ast`：27 / 27 (100.0%) Passed
  - `knowledge-db`：109 / 109 (100.0%) Passed
  - `agents-workflow`：142 / 142 (100.0%) Passed
- **實機 UX / 人工驗證**：
  - `UX-01` `[測試通過]`：實機驗證 `python yscb.py kdb search`、`--file-uri`、`--json`、`--simple`、`kdb status` 與 `ast outline` 輸出完全符合規格。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已完成 | 頂部新增 `2026_11_05_0321_kdb_cli_and_engine_optimization (Completed)` 完整變更摘要 |
| **中觀 (Meso)** | `docs/knowledge-db/README.md` | 已完成 | 同步更新 `kdb` 短別名、`--file-uri` 與預設 `auto` 精簡模式說明 |
| **中觀 (Meso)** | `docs/knowledge-db/retrieval.md` | 已完成 | 同步更新 `InvertedIndex` `0..n` `doc_idx` 駐留、動態分數斷崖截斷與 `unified.meta.json` 機制 |
| **中觀 (Meso)** | `docs/knowledge-db/DESIGN_NOTES.md` | 免更 | 細節已完整收錄於專題手冊 `retrieval.md`，遵守 DN 防膨脹守門 |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已完成 | `ResultFormatter`、`ASTEngine`、`InvertedIndex`、`Posting`、`SparseFieldFreqs` Docstrings 均已同步維護 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
perf(knowledge-db,ast): slim CLI/JSON output, add kdb alias, lazy-load AST graph, and intern InvertedIndex doc_idx (OPT-01~OPT-08)
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

