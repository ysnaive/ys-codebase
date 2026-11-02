# 成果展示與結案報告 (Walkthrough)

> 功能名稱：`knowledge-db` 功能細節優化（常駐背景 Worker、向量模型自動下載、忙碌毫秒探針與容差降級、`status` 詳盡觀測）  
> 建立日期：2026-11-02  
> 所屬主計畫：`2026_11_02_0339_module_space_feasibility_research`  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **專屬常駐 `KnowledgeDBServiceWorker` (`knowledge-db-worker`) 兩階段背景管線 (`FR-01`, `EC-02`, `NFR-02`)**：於 `ys_codebase/source/knowledge-db/contributes/server.json` 宣告 `knowledge-db-worker`，檔案系統 `watchdog` 監聽 100% 維持由 `module:space` (`space-watcher`) 負責，`hook.space.py` 透過 O(1) `notify_space_changed()` 喚醒 Worker。Stage 1 以 `skip_vectors=True` 秒級更新 AST、BM25 與呼叫圖譜並推進游標；Stage 2 按 `vector_batch_size`（預設 `32`）微批次補齊缺失符號向量直至覆蓋率達 100%。
  2. **常駐 Worker 背景自動下載向量模型 (`FR-02`, `EC-05`)**：當 `knowledge-db-worker` 在線且 `enable_vector_search=True` 時，若本地快取缺少 FastEmbed ONNX 權重，Worker 自動於背景執行 `embedding_service.download_model()`（具備 60 秒失敗退避冷卻並抑制前台 `[GUARD]` 阻斷提示），下載完成後無縫銜接 Stage 2 微批次向量建置。無 Server 時則維持原本行為。
  3. **`is_worker_busy() -> int`（已運行 ms）探針與 `jit_vector_timeout_ms` 動態容差降級 (`FR-03`, `EC-01`, `EC-03`, `EC-04`, `EC-06`, `NFR-01`, `NFR-03`)**：於 `KnowledgeDBConfig` 新增 `jit_vector_timeout_ms: int = 3000`（支援於 `config.json` 設定，並向下相容舊鍵 `jit_vector_timeout_seconds`）。`engine.is_worker_busy() -> int` 回傳 `0`（空閒，含死進程 PID 自動清理）或已連續忙碌之毫秒數 `elapsed_ms > 0`。搜尋時若 `elapsed_ms >= timeout_ms` 則等待 `0ms` 瞬時降級純 BM25 並輸出 `[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]`；若 `0 < elapsed_ms < timeout_ms` 則最多等待剩餘時間 `timeout_ms - elapsed_ms`。
  4. **`knowledge-db status` 直白詳盡化觀測升級與嵌入文本優化 (`FR-04`, `FR-05`)**：全面升級 `engine.status()` 與 `scripts/cli.py:status()`（含終端機與 `--json`），展示後台服務與忙碌毫秒數、當前檢索模式與原因、BM25 / 圖譜 / 向量三大索引細部指標（含覆蓋率 `%` 與待補數量）、模型與組態參數及各空間游標水位（`acked / head`）；同步補齊 `pre_warm()` 組態守門與 `format_symbol_embedding_text()` `1000` 字元 Docstring 截斷保護。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/knowledge-db/contributes/server.json` | New | 註冊 `knowledge-db-worker` (`knowledge_db.service:KnowledgeDBServiceWorker`) 至 `module:server` |
| `ys_codebase/source/knowledge-db/knowledge_db/service.py` | New | 實作 `KnowledgeDBServiceWorker` 兩階段背景同步、自動下載模型、微批次向量自癒與 `get_worker_busy_ms` / `wait_until_worker_idle` 探針 |
| `ys_codebase/source/knowledge-db/knowledge_db/config.py` | Modify | 新增 `jit_vector_timeout_ms: int = 3000`、`vector_batch_size: int = 32` 與 `jit_vector_timeout_seconds` 向下相容屬性 |
| `ys_codebase/source/knowledge-db/configurable/config.project.json` | Modify | 更新預設組態模板為 `jit_vector_timeout_ms: 3000` 與 `vector_batch_size: 32` |
| `ys_codebase/config/knowledge-db/config.project.json` | Modify | 同步更新專案組態為 `jit_vector_timeout_ms: 3000` 與 `vector_batch_size: 32` |
| `ys_codebase/source/knowledge-db/knowledge_db/embedding.py` | Modify | 新增 `format_symbol_embedding_text(max_doc_chars=1000)`、`suppress_guard_prompt` 與背景下載完成後熱重載模型支援 |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | 新增 `skip_vectors`、`get_vector_deficit_info()`、`sync_vector_deficit_step()` 與 `_resolve_vector_availability_with_worker_tolerance()` |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | 新增 `is_worker_busy() -> int`、`wait_for_worker_idle()`、`sync_vector_deficit_step()`、`pre_warm()` 守門與詳盡化 `status()` |
| `ys_codebase/source/knowledge-db/knowledge_db/__init__.py` | Modify | 匯出 `KnowledgeDBServiceWorker`、`get_worker_busy_ms` 與 `is_worker_running` |
| `ys_codebase/source/knowledge-db/scripts/hook.space.py` | Modify | 當 `KnowledgeDBServiceWorker` 在線時透過 `notify_space_changed()` 非阻塞喚醒後台兩階段處理 |
| `ys_codebase/source/knowledge-db/scripts/cli.py` | Modify | 升級 `knowledge-db status` 終端機直白詳盡化分區排版與 `--json` 欄位 |
| `ys_codebase/source/knowledge-db/tests/test_engine.py` | Modify | 新增 `jit_vector_timeout_ms`、`status()` 詳盡指標與 Docstring 截斷測試 |
| `ys_codebase/source/knowledge-db/tests/test_service_worker.py` | Modify | 新增 `is_worker_busy()` 探針、動態容差等待 / 0ms 瞬時降級、兩階段微批次向量自癒與背景自動模型下載測試 |
| `ys_codebase/source/knowledge-db/tests/test_space.py` | Modify | 對齊 `jit_vector_timeout_ms: int = 3000` 預設契約斷言 |
| `ys_codebase/source/knowledge-db/README.md` | Modify | 更新 `knowledge-db-worker`、`jit_vector_timeout_ms` 與 `vector_batch_size` 說明 |
| `docs/knowledge-db/README.md` | Modify | 同步更新模組手冊之組態表與兩階段背景 Worker 說明 |
| `docs/knowledge-db/incremental_hot_reload.md` | Modify | 同步更新 `space-watcher` + `knowledge-db-worker` 兩階段微批次向量自癒與動態容差降級專題 |
| `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 登錄 `[DN-10]` 兩階段背景 Worker、`is_worker_busy() -> int` 探針與 `jit_vector_timeout_ms` 動態容差降級防坑筆記 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：
  - `python yscb.py dev check knowledge-db`：`[PASS]`
  - `python yscb.py dev test knowledge-db -q`：`Pass: 155(100.0%), Fail: 0, Skip: 0`
- **實機 UX / 人工驗證**：
  - `UX-01`（`[測試通過]`）：實機刪除 `.cache/knowledge-db/models/*` 與 `unified.vectors.bin.gz` 後，驗證 `knowledge-db status` 與 `search` 零 `[GUARD]` 阻斷、瞬時降級純 BM25 並印出 `[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]`，且常駐 `knowledge-db-worker` 自動於背景下載 ONNX 模型並以微批次（每批 32 符號）逐步補齊向量。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已交付 | 追加 `sub_03_knowledge_db_feature_refinement` 變更摘要 |
| **中觀 (Meso)** | `docs/knowledge-db/README.md` | 已交付 | 更新 `jit_vector_timeout_ms`、`vector_batch_size` 與兩階段背景 Worker 說明 |
| **中觀 (Meso)** | `docs/knowledge-db/incremental_hot_reload.md` | 已交付 | 更新 `KnowledgeDBServiceWorker` 兩階段同步、背景自動下載模型與 `is_worker_busy()` 動態容差機制 |
| **中觀 (Meso)** | `docs/knowledge-db/DESIGN_NOTES.md` | 已交付 | 登錄 `[DN-10]` 記錄兩階段背景 Worker 與 `elapsed_ms >= timeout_ms` 0ms 瞬時降級防坑邊界 |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已交付 | 完整維護 `service.py`、`config.py`、`embedding.py`、`pipeline.py`、`engine.py`、`cli.py` Docstring |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(knowledge-db): add two-stage background worker, auto model download, busy ms probe, and detailed status
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify 2026_11_02_0339_module_space_feasibility_research/sub_03_knowledge_db_feature_refinement` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

