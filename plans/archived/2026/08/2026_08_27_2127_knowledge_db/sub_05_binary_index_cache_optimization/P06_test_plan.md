# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：knowledge-db 子計畫 05: 符號池去重與二進位 Gzip 倒排索引快取優化 (Symbol Pool Normalization & Binary Gzip Inverted Index Cache Optimization)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Passed  
> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 依據 P02：[P02_architecture_plan.md](./P02_architecture_plan.md)  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `InvertedIndex.symbols` 符號池去重且 `Posting` 僅包含 `doc_id` 引用 | FR-01, FR-02 | `test_retrieval.py:TestRetrieval.test_symbol_pool_normalization_and_binary_gzip_io` |
| **FT-02** | 單元測試 | 驗證 `InvertedIndex.save_binary()` 與 `load_binary()` 二進位 Gzip 正確序列化與還原 | FR-03 | `test_retrieval.py:TestRetrieval.test_symbol_pool_normalization_and_binary_gzip_io` |
| **FT-03** | 效能測試 | 驗證倒排索引體積縮減 $\ge 90\%$ (實測 55MB 降至 253KB，縮減 99.5%) 且載入反序列化耗時 $\le 50\text{ ms}$ | NFR-01, NFR-02 | 實機測試與 `benchmark_storage.py` 基準評測 |
| **FT-04** | 整合測試 | 驗證 `KnowledgeEngine` 建立、持久化與讀取 `.index.bin.gz` 快取 | FR-04 | `test_engine.py:TestEngine.test_engine_status_and_lifecycle` |
| **FT-05** | 整合測試 | 驗證 `KnowledgeEngine.status()` 正確偵測並回報 `.index.bin.gz` 狀態 | FR-05 | `test_engine.py:TestEngine.test_engine_status_and_lifecycle` |
| **FT-06** | 整合測試 | 驗證 `KnowledgeEngine.clean()` 正確清理 `.index.bin.gz` 與舊 `.index.json` | FR-05 | `test_engine.py:TestEngine.test_engine_status_and_lifecycle` |
| **ET-01** | 例外測試 | 驗證二進位快取檔案損毀時捕獲異常並透明自癒重建 (EC-01) | EC-01 | `test_retrieval.py:TestRetrieval.test_corrupted_binary_cache_fallback` |
| **RT-01** | 回歸測試 | 全模組單元測試回歸，執行 `python yscb.py dev test knowledge-db` 達成 100% Passed (40/40) | NFR-03, NFR-04 | `python yscb.py dev test knowledge-db` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_symbol_pool_normalization`: 符號池抽離去重，Posting 字典僅保留 doc_id 100% 通過 | 2026-08-28 16:13 |
| **FT-02** | `Passed` | `test_binary_gzip_io`: 二進位 Gzip 儲存與讀取還原，檢索一致性 100% 通過 | 2026-08-28 16:13 |
| **FT-03** | `Passed` | 實機索引體積從 55,350,859 bytes 暴降至 259,982 bytes (253.89 KB)，縮減率達 99.53% | 2026-08-28 16:13 |
| **FT-04** | `Passed` | `test_engine_status_and_lifecycle`: KnowledgeEngine 建置並讀取 `.index.bin.gz` 100% 通過 | 2026-08-28 16:13 |
| **FT-05** | `Passed` | `test_engine_status`: status 指令正確識別 `.index.bin.gz` 快取狀態 100% 通過 | 2026-08-28 16:13 |
| **FT-06** | `Passed` | `test_engine_clean`: clean 指令乾淨銷毀 `.index.bin.gz` 與舊 `.index.json` 100% 通過 | 2026-08-28 16:13 |
| **ET-01** | `Passed` | `test_corrupted_binary_cache_fallback`: 損毀二進位資料讀取拋錯並由引擎自癒重建 100% 通過 | 2026-08-28 16:13 |
| **RT-01** | `Passed` | 實機執行 `python yscb.py dev test knowledge-db` 達成 40/40 測試案例 100% Passed (9.045s) | 2026-08-28 16:13 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [ ] **UX-01**：Phase 6 實機測試 100% 通過，倒排索引檔案體積從 55.35 MB 暴降至 253.89 KB（縮減 99.53%），呈遞測試報告等待開發者 UX 驗證確認。
