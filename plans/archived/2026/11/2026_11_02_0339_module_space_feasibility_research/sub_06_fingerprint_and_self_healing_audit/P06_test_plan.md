# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：全生態系指紋快取與熱自癒機制完善度審視與修復  
> 建立日期：2026-11-02  
> 所屬主計畫：[2026_11_02_0339_module_space_feasibility_research](../umbrella_overview.md)  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `knowledge-db` 當符號起始行號未變但內容/Docstring 修改時，`hot_patch_unified_index(skip_vectors=True)` 主動從 `VectorIndex` 剔除舊符號 ID（且 `UnifiedSymbol.compute_id` 保持穩定），隨後 Stage 2 `sync_vector_deficit_step` 能偵測差集並重算新向量 | FR-01, NFR-02 | `python yscb.py dev test --target=knowledge-db:TestKnowledgeDBSelfHealing.test_ft_01_stage1_skip_vectors_evicts_old_vectors_for_same_line_edits` |
| **FT-02** | 單元測試 | 驗證 `knowledge-db` 修改或刪除某空間頂層無 `/` 檔案（如 `README.md`、`__init__.py`）時，經空間 `include` 根目錄正規化與 `is_dirty_file_match` 收斂後，不會誤判或剔除其他空間之同名頂層檔案 | FR-02, EC-04 | `python yscb.py dev test --target=knowledge-db:TestKnowledgeDBSelfHealing.test_ft_02_cross_space_same_filename_isolation` |
| **FT-03** | 單元測試 | 驗證 `file-space` `ScanDiffResult.space_generations` 與 `ack(None)` 在跨世代併發寫入時僅將各子空間推進至當次讀取世代（防止 Lost Update），且對 `watch=False` 空間在 Watcher 啟動時維持 `auto_refresh=True`，以及 `CursorStore` 多執行緒併發 RMW 零遺失 | FR-03, FR-04, EC-02 | `python yscb.py dev test file-space -q` |
| **FT-04** | 單元測試 | 驗證 `core.uri._get_merged_uri_schemes` 具 Thread-Local 重入保護（絕不發生 `RecursionError`）且於 `config://core/contribute.json` 變更時自動觸發 JIT 自癒，並驗證 `_scan_contributes_inputs` 追蹤專案語系實體檔與 `module.source://` `_format.json` | FR-05, EC-01 | `python yscb.py dev test --target=core:TestContributesJIT` |
| **FT-05** | 單元測試 | 驗證 `agents-workflow` `ReleasePublisher._get_source_file_sha1` 目錄走訪複用 `_sha1_cache`（快取命中 0 檔案內容重讀 I/O）、語系鏈與 `config://core` 變更觸發指紋更新、以及 `AGENTS.md` 託管區塊標記損壞時跳出短路自癒 | FR-06, EC-03, NFR-01 | `python yscb.py dev test --target=agents-workflow:TestPublisherSelfHealing` |
| **FT-06** | 回歸測試 | 驗證 `core`、`file-space`、`knowledge-db`、`agents-workflow` 四大模組 `dev check` 合規檢查與全量單元測試套件 100% 通過 | NFR-01, NFR-02 | `python yscb.py dev test core -q && python yscb.py dev test file-space -q && python yscb.py dev test knowledge-db -q && python yscb.py dev test agents-workflow -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestKnowledgeDBSelfHealing.test_ft_01_stage1_skip_vectors_evicts_old_vectors_for_same_line_edits` 通過 (`sym.id` 維持不變、Stage 1 成功剔除舊向量、Stage 2 `sync_vector_deficit_step` 補齊更新後向量) | 2026-11-02 09:31 |
| **FT-02** | `Passed` | `TestKnowledgeDBSelfHealing.test_ft_02_cross_space_same_filename_isolation` 通過 (`space_a/__init__.py` 修改與刪除不影響 `space_b/__init__.py` 快取與符號) | 2026-11-02 09:31 |
| **FT-03** | `Passed` | `file-space` 測試套件 `15/15 (100.0%)` 全數通過（含 `space_generations` 防 Lost Update、`watch=False` 自動刷新與 `CursorStore` 16 執行緒併發 RMW 驗證） | 2026-11-02 09:28 |
| **FT-04** | `Passed` | `core:TestContributesJIT` `5/5 (100.0%)` 全數通過（含 `custom.jittest://` JIT 自癒、Thread-Local 重入保護與專案語系檔髒檢查） | 2026-11-02 09:28 |
| **FT-05** | `Passed` | `agents-workflow:TestPublisherSelfHealing` `3/3 (100.0%)` 全數通過（目錄 SHA-1 快取命中 0 讀取、語系變更指紋更新、`AGENTS.md` 託管標記缺失自癒） | 2026-11-02 09:31 |
| **FT-06** | `Passed` | 四大模組 `dev check` 100% `PASSED`；全量測試套件總計 **534/534 (100.0%)** 通過（`core`: 221/221、`file-space`: 15/15、`knowledge-db`: 157/157、`agents-workflow`: 141/141），並完成 `@build` 安裝與 `agents-workflow release` 驗證 | 2026-11-02 09:34 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視 `R01` Devil's Advocate 反向查驗結論及四大模組（`core`、`file-space`、`knowledge-db`、`agents-workflow`）自癒邊界修復與 534 項自動化測試結果，確認無誤 | `[跳過/免測]` | 開發者指示免測 |

