# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_04 空間指紋、AST 解析與知識庫檢索深層審計收斂 (Knowledge Pipeline Remediation)  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_05_0104_codebase_deep_audit_remediation  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `FileSpaceManager` 單檔 `include` 解析走訪、符號連結邏輯相對路徑保留、`FingerprintScanner` `.watcher_dirty` 跨行程信標觸發 `auto_refresh=True`、以及 `ack(space_name=None)` 跨空間世代對齊 | FR-01, NFR-02 | `TestFileSpaceManager.test_ft06_single_file_include_and_symlink_logical_rel_path` / `TestFingerprintScannerSelfHealing.test_ft_06_watcher_dirty_beacon_and_atomic_write_retry` |
| **FT-02** | 單元測試 | 驗證 `ASTEngine` 根目錄單檔 `is_dirty_file_match` 絕對路徑匹配與多空間 `best_mtime_ns` 消歧、`CSharpDialect` 檔案級命名空間範圍延伸至 EOF、`ASTSnapshot.from_dict` 串列容錯與 `_LAST_LINKER_CACHE` 原地更新指紋失效 | FR-02, NFR-02 | `TestASTEngine.test_is_dirty_file_match_and_mtime_disambiguation` / `test_csharp_file_scoped_namespace_and_snapshot_list_symbols` / `test_linker_cache_invalidation_on_inplace_symbol_update` |
| **FT-03** | 單元測試 | 驗證 `KnowledgeDBServiceWorker` 冷啟動載入 `unified_index` 檢出 `[DN-30]` 雙水位線落差、`KnowledgeEngine.bundle(space=None, export_path=...)` 多空間匯出路徑隔離、以及 `InvertedIndex.build(..., pre_aggregated=True)` 免重複聚合快徑 | FR-03, NFR-01 | `TestKnowledgeEngine.test_worker_cold_start_watermark_and_multi_space_bundle_export` / `TestRetrieval.test_hybrid_dot_directory_extension_and_pre_aggregated_index` |
| **ET-01** | 邊界測試 | 驗證 `FileSpaceManager._apply_project_space_overrides` 於測試沙盒傳入 `project_root=tmp_dir` 時受 `_explicit_project_root is None` 守衛保護，不混入宿主 `contribute.json` | EC-01 | `TestFileSpaceManager.test_ft01_dual_track_aggregation_and_override` |
| **ET-02** | 邊界測試 | 驗證 `_atomic_write_bytes` 遭遇暫時性 `PermissionError` 時自動指數退避重試並寫入成功，以及 `_walk_root` 對 `st_ino != 0` 之防禦 | EC-02 | `TestFingerprintScannerSelfHealing.test_ft_06_watcher_dirty_beacon_and_atomic_write_retry` |
| **ET-03** | 邊界測試 | 驗證 `is_dirty_file_match` 在含 `/` 子目錄路徑下維持雙向後綴匹配且不誤匹配同名異目錄檔案 | EC-03 | `TestASTEngine.test_is_dirty_file_match_and_mtime_disambiguation` |
| **ET-04** | 邊界測試 | 驗證 `HybridSearchEngine.search` 對含 `.` 父目錄但無副檔名路徑（如 `.agents/skills/Makefile`）使用 `Path.suffix` 精確過濾 `file_types`，且不將 BM25 `min_score` 套用於 RRF 分數 | EC-04 | `TestRetrieval.test_hybrid_dot_directory_extension_and_pre_aggregated_index` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `dev check file-space` 與 `dev test file-space -q --sync` 100% 通過 (Pass: 24, Fail: 0, Skip: 0)，已同步 `file-space@1.0.1.build` | 2026-11-05 |
| **FT-02** | `Passed` | `dev check ast` 與 `dev test ast -q --sync` 100% 通過 (Pass: 30, Fail: 0, Skip: 0)，已同步 `ast@1.0.1.build` | 2026-11-05 |
| **FT-03** | `Passed` | `dev check knowledge-db` 與 `dev test knowledge-db -q --sync` 100% 通過 (Pass: 111, Fail: 0, Skip: 0)，已同步 `knowledge-db@1.2.1.build` | 2026-11-05 |
| **ET-01** | `Passed` | `dev test file-space -q --sync` 沙盒測試 100% 通過 (Pass: 24, Fail: 0, Skip: 0) | 2026-11-05 |
| **ET-02** | `Passed` | `dev test file-space -q --sync` 沙盒測試 100% 通過 (Pass: 24, Fail: 0, Skip: 0) | 2026-11-05 |
| **ET-03** | `Passed` | `dev test ast -q --sync` 沙盒測試 100% 通過 (Pass: 30, Fail: 0, Skip: 0) | 2026-11-05 |
| **ET-04** | `Passed` | `dev test knowledge-db -q --sync` 沙盒測試 100% 通過 (Pass: 111, Fail: 0, Skip: 0) | 2026-11-05 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 主代理於 4 個子計畫全數完成後統一執行 `python yscb.py dev test file-space`、`python yscb.py dev test ast` 與 `python yscb.py dev test knowledge-db` 驗收全量測試套件 | `[測試通過]` | 開發者確認推進統一沙盒測試驗收，`file-space` (24/24)、`ast` (30/30)、`knowledge-db` (111/111) 100% 通過並同步 `@build` |
