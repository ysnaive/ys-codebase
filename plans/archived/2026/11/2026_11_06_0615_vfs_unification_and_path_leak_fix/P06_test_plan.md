# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：跨模組路徑洩漏根治、背景執行緒 URI 上下文固化與 VFS 原子寫入收口  
> 建立日期：2026-11-06  
> 所屬主計畫：N/A  
> 狀態：Passed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `file-space` 之 `FileSpaceWatcherServiceWorker`、`is_watcher_active`、`is_transaction_locked` 與 `FileSpaceManager.storage_root` 透過 `core.vfs` / `core.uri` 讀寫，且絕不在下游 `project_root` 產生 `.cache/file-space` 或 `ys_codebase/` | FR-01, FR-05 | `python yscb.py dev test file-space -q` |
| **FT-02** | 單元測試 | 驗證 `ast` 之 `_resolve_default_ast_storage_dir`、`ASTEngine._resolve_index_lock_path` 與 `_atomic_write_meta` 在 URI 退避時錨定 `yscb_root`，絕不在下游 `project_root` 建立 `.cache/ast` 或 `.storage.local/ast` | FR-02, FR-05 | `python yscb.py dev test ast -q` |
| **FT-03** | 單元測試 | 驗證 `knowledge-db` 之 `_resolve_default_knowledge_storage_dir`、`is_agents_workflow_installed` 與 `write_worker_state` 透過 `core.vfs` 運作且退避錨定 `yscb_root` | FR-02, FR-05 | `python yscb.py dev test knowledge-db -q` |
| **FT-04** | 單元測試 | 驗證 `agents-workflow` 之 `compiler`、`publisher`、`roadmap`、`verifier`、`_verifier_healer` 與 `session_trace` 統一走 `core.vfs` 原子寫入且無 `ys_codebase/` 硬編碼退避 | FR-03, FR-05 | `python yscb.py dev test agents-workflow -q` |
| **FT-05** | 單元測試 | 驗證 `server` 之 `WarmWorker.__init__` 於 `pre_warm()` 前將 `YSCB_ROOT_DIR` 與 `YSCB_HOST_DIR` 寫入 `os.environ` | FR-04 | `python yscb.py dev test server -q` |
| **ET-01** | 邊界測試 | 驗證下游獨立 `project_root`（目錄下無 `ys_codebase` 子目錄）且 `uri.resolve` 模擬失敗時，`file-space`、`ast`、`knowledge-db` 退避路徑仍 100% 指向 `yscb_root` 而非 `project_root` | EC-01, EC-02, EC-03 | `python yscb.py dev test file-space -q` & `python yscb.py dev test ast -q` |
| **RT-01** | 回歸測試 | 驗證 5 個修改模組之 `dev check` 靜態合規檢查與完整回歸測試套件 100% 通過 | NFR-01, NFR-02 | `python yscb.py dev check file-space server ast knowledge-db agents-workflow` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `file-space`: Pass: 28(100.0%), Fail: 0, Skip: 0 | 2026-11-06 |
| **FT-02** | `Passed` | `ast`: Pass: 37(100.0%), Fail: 0, Skip: 0 | 2026-11-06 |
| **FT-03** | `Passed` | `knowledge-db`: Pass: 109(100.0%), Fail: 0, Skip: 0 | 2026-11-06 |
| **FT-04** | `Passed` | `agents-workflow`: Pass: 145(100.0%), Fail: 0, Skip: 0 | 2026-11-06 |
| **FT-05** | `Passed` | `server`: Pass: 59(100.0%), Fail: 0, Skip: 0 | 2026-11-06 |
| **ET-01** | `Passed` | `TestASTEngineCore.test_storage_and_lock_fallback_anchors_to_yscb_root` 與 `TestFingerprintScannerSelfHealing.test_watcher_state_awareness_and_diff_all_spaces_aggregation` 驗證下游 `project_root` 零 `.cache` / `.storage.local` 洩漏 | 2026-11-06 |
| **RT-01** | `Passed` | `dev check` 於 `file-space`, `server`, `ast`, `knowledge-db`, `agents-workflow` 均 `PASSED`；總計 378 項測試 100% 通過 | 2026-11-06 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 於下游專案或本機執行 `yscb server restart/reload` 與 `file-space status`，確認業務 `project://` 目錄下不再生成 `.cache/file-space` | `[測試通過]` | 經獨立臨時兄弟目錄 (`tmp_downstream_sibling_sim`) 模擬驗證通過，目錄下僅保留 `['docs', 'src']`，零 `.cache` / `.storage.local` 洩漏 |
