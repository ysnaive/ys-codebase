# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_01_knowledge_db_embedding_and_diagnostics  
> 建立日期：2026-09-13  
> 所屬主計畫：2026_09_13_1648_downstream_feedback_remediation  
> 狀態：Passed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 既有向量快取儲存、載入與語意搜尋斷言（改以 service.dimension 校驗） | FR-01 | `dev test knowledge-db -k test_embedding` |
| **FT-02** | 單元測試 | 長文本切片推論輸出形狀匹配動態維度 | FR-01 | `dev test knowledge-db -k test_long_content` |
| **FT-03** | 單元測試 | 批次向量推論切片形狀匹配動態維度 | FR-01 | `dev test knowledge-db -k test_batching` |
| **FT-10** | 單元測試 | 驗證 DEFAULT_EMBEDDING_DIM 徹底移除，dimension 正確讀取自模型實例屬性 | FR-01 | `dev test knowledge-db -k test_dynamic_dimension_without_constant` |
| **FT-11** | 單元測試 | 驗證 FastEmbed 載入失敗時 last_error 結構化封裝與安全降級 | FR-03 | `dev test knowledge-db -k test_embedding_last_error_capture` |
| **FT-12** | 單元測試 | 驗證 normalize_model_name 補齊省略前綴與相容性 | FR-05 | `dev test knowledge-db -k test_model_name_normalization` |
| **FT-13** | 整合測試 | 驗證 VectorIndex.is_compatible_with 對齊 512 維度與不匹配拒絕 | FR-02 | `dev test knowledge-db -k test_vector_index_dimension_compatibility` |
| **RT-01** | 回歸測試 | knowledge-db 全套既有單元測試全數通過 | NFR-02 | `python yscb.py dev test knowledge-db` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | 向量生成、餘弦相似度與二進位快取持久化驗證通過 (dim=512) | 2026-09-13 17:03 |
| **FT-02** | `Passed` | 512+ tokens 長文本切片推論輸出形狀 (512,) 斷言通過 | 2026-09-13 17:03 |
| **FT-03** | `Passed` | 批次向量推論切片形狀 (70, 512) 斷言通過 | 2026-09-13 17:03 |
| **FT-10** | `Passed` | DEFAULT_EMBEDDING_DIM 徹底淘汰驗證通過，bge-small 512，minilm 384 | 2026-09-13 17:03 |
| **FT-11** | `Passed` | 載入失敗 last_error 結構化封裝與 is_available 降級驗證通過 | 2026-09-13 17:03 |
| **FT-12** | `Passed` | normalize_model_name 自動補齊 BAAI/ 與 sentence-transformers/ 驗證通過 | 2026-09-13 17:03 |
| **FT-13** | `Passed` | VectorIndex.is_compatible_with 512 通過，384 拒絕，模型不符拒絕 | 2026-09-13 17:03 |
| **RT-01** | `Passed` | knowledge-db 測試套件全量 148/148 100% 通過 (Pass: 148, Fail: 0) | 2026-09-13 17:03 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py knowledge-db search "test"` 不再出現 `(維度要求: 384) 不相容已降級` 告警 | `[跳過/免測]` | 開發者指示免測（自動化測試與實機背景查詢已覆蓋驗證） |
| **UX-02** | 執行 `python yscb.py knowledge-db index --help` 正確輸出說明卡而非建索引 | `[跳過/免測]` | 開發者指示免測（Core 派發攔截合約已實機確認） |
