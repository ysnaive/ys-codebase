# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：YS-Codebase v1.2.1 二輪審計 5 項邊界條件與相容性隱患修復  
> 建立日期：2026-11-02  
> 所屬主計畫：2026_11_02_0315_v121_audit_boundary_fixes  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `yscb.py` 與 `core/engine.py` 將舊倉庫名 `ysnaive/agent.workflow`（含尾部 `/`）自動正規化並遷移回寫至 `DEFAULT_PROVIDER_URL` | FR-01 | `python yscb.py dev test --target=core:TestCoreInstaller.test_legacy_agent_workflow_provider_url_auto_migration` |
| **FT-02** | 單元/邊界測試 | 驗證 C# `partial class` 跨檔聚合不產生 $N^2$ 重複倒排 Posting（`NFR-01`），且 `patch_incremental` 增量更新單一分部檔時雙向保留主分部 `field_types`/`base_types` 與新成員（`FR-02`, `EC-01`） | FR-02, EC-01, NFR-01 | `python yscb.py dev test --target=knowledge-db:TestTopologyGraph.test_ft_14_csharp_partial_class_cross_file_aggregation_and_linking` |
| **FT-03** | 單元/邊界測試 | 驗證 `PlanScanner.build_recovery_capsule` 對 `P01-05_auto.md` 僅提取 `§2` 異動檔案，排除 `§4.2` 維度名稱；驗證單檔模式 `BACKPROP` 檢核能攔截未標註回寫之 `Major` 偏差並對標註「已回寫 §2」放行 | FR-03, FR-04, EC-02, EC-03 | `python yscb.py dev test --target=agents-workflow:TestPlansStatusAndBoundaries.test_v122_scanner_capsule_search_and_verifier_warnings` |
| **FT-04** | 單元測試 | 驗證 `ArtifactCompiler.resolve_stage2_uri` 對獨立行內代碼標籤 `` `__${project://}__` `` 渲染為 `` `./` `` 而非空雙反引號 `` `` `` | FR-05 | `python yscb.py dev test --target=agents-workflow:TestArtifactCompiler.test_ft_15_literal_and_ignore_block_directives` |
| **RT-01** | 全量回歸測試 | 驗證 `core`、`knowledge-db`、`agents-workflow` 三模組 `dev check` 與 `dev test` 100% 通過 | NFR-02 | `python yscb.py dev test core && python yscb.py dev test knowledge-db && python yscb.py dev test agents-workflow` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestCoreInstaller.test_legacy_agent_workflow_provider_url_auto_migration` 通過，舊倉庫名網址自動遷移至 `/releases` | 2026-11-02 |
| **FT-02** | `Passed` | `TestTopologyGraph.test_ft_14_csharp_partial_class_cross_file_aggregation_and_linking` 通過，倒排 Posting 為 1 筆且 `patch_incremental` 跨檔重聚合無損 | 2026-11-02 |
| **FT-03** | `Passed` | `TestPlansStatusAndBoundaries.test_v122_scanner_capsule_search_and_verifier_warnings` 通過，`impacted_files` 排除 `§4.2` 維度且單檔 `BACKPROP` 檢核生效 | 2026-11-02 |
| **FT-04** | `Passed` | `TestArtifactCompiler.test_ft_15_literal_and_ignore_block_directives` 通過，`` `__${project://}__` `` 展開為 `` `./` `` | 2026-11-02 |
| **RT-01** | `Passed` | `core`、`knowledge-db`、`agents-workflow` 全量合規與沙盒測試 100% PASS | 2026-11-02 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py agents-workflow plan status --resume`，確認當前計畫 `P01-05_auto.md` 之 `Impacted Files` 僅列出真實代碼路徑，未混入 `§4.2` 文檔維度名稱 | `[測試通過]` | 開發者授權實機復測驗證通過 |
| **UX-02** | 檢視 `core`、`knowledge-db`、`agents-workflow` 5 項邊界條件修復與測試覆蓋是否符合預期 | `[測試通過]` | 開發者授權實機復測驗證通過 |

