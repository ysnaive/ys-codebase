# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_03_knowledge_db_and_workflow_engine_remediation  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Passed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證同名跨目錄檔案增量修補不會誤刪同名兄弟檔案符號 | FR-01 | `python yscb.py dev test knowledge-db -k test_hot_reload` |
| **FT-02** | 單元測試 | 驗證 `HybridSearchEngine` 支援 `spaces`/`kinds`/`languages` 前置精確過濾 | FR-02 | `python yscb.py dev test knowledge-db -k test_retrieval` |
| **FT-03** | 單元測試 | 驗證非 Mock 模式下向量推論失敗回傳空陣列且不注入偽向量 | FR-03 | `python yscb.py dev test knowledge-db -k test_retrieval` |
| **FT-04** | 單元測試 | 驗證 `pipeline.clean()` 完整清除 `unified.vectors.bin.gz` 與快取池 | FR-04 | `python yscb.py dev test knowledge-db -k test_retrieval` |
| **FT-05** | 單元測試 | 驗證 `act_callers` / `callees` / `impact` 執行時不觸發向量推論 | FR-05 | `python yscb.py dev test knowledge-db -k test_graph` |
| **FT-06** | 單元測試 | 驗證 `callees -d` 切片無重複輸出 | FR-06 | `python yscb.py dev test knowledge-db -k test_cli_ux` |
| **FT-07** | 單元測試 | 驗證 Skill 目錄檔案內容變更時 Stage 0 SHA-1 精確改變 | FR-07 | `python yscb.py dev test agents-workflow -k test_publisher` |
| **FT-08** | 單元測試 | 驗證 Stage 2 連結反引號剝除與路徑尾斜線保留 | FR-08 | `python yscb.py dev test agents-workflow -k test_compiler` |
| **FT-09** | 單元測試 | 驗證 `PlanVerifier` 成功接受 `Discussing` / `Planning` / `Executing` / `Concluded` 等狀態 | FR-09 | `python yscb.py dev test agents-workflow -k test_verifier` |
| **RT-01** | 全量回歸 | 驗證 `knowledge-db` 模組全量單元測試 100% 通過 | NFR-02 | `python yscb.py dev test knowledge-db` |
| **RT-02** | 全量回歸 | 驗證 `agents-workflow` 模組全量單元測試 100% 通過 | NFR-02 | `python yscb.py dev test agents-workflow` |
| **RT-03** | 生態系回歸 | 驗證全生態系 550+ 測試 100% 通過，0 失敗 0 警告 | NFR-02 | `python yscb.py dev test --all --quiet` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** ~ **FT-06** | `Pass` | `knowledge-db` 增量修補、前置過濾、向量解耦單元測試全數通過 | 2026-10-14 13:53 |
| **FT-07** ~ **FT-09** | `Pass` | `agents-workflow` 目錄雜湊、編譯器與驗證器測試全數通過 | 2026-10-14 13:54 |
| **RT-01** | `Pass` | `knowledge-db`: 157 Total, 157 Passed, 0 Failed (100% Ready) | 2026-10-14 13:53 |
| **RT-02** | `Pass` | `agents-workflow`: 79 Total, 79 Passed, 0 Failed (100% Ready) | 2026-10-14 13:54 |
| **RT-03** | `Pass` | 全生態系回歸: Pass: 550(100.0%), Fail: 0, Skip: 0 | 2026-10-14 13:55 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py agents-workflow list`，確認 documentation 描述不再包含未展開的 `__${workflow.docs://}__` | `Pass` | 實機驗證輸出為 clean `docs/` 路徑 |
| **UX-02** | 執行 `python yscb.py knowledge-db callees 'InvertedIndex.patch_incremental' -d`，確認切片僅輸出一次且無重疊 | `Pass` | 實機驗證切片輸出乾淨單次呈現 |


