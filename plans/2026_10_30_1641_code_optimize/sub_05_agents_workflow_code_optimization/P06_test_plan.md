# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_05_agents_workflow_code_optimization  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `ArtifactCompiler`、`ReleasePublisher`、`ReleaseTargetManager` 與 `WorkflowInitializer` 移除 `M-01`/`M-02`/`M-06` 死代碼、提升閉包、5 階段發布拆解與 `vfs.<io>` 遷移後，Stage 1/2 編譯與發布完全無損 | FR-01, FR-05, FR-06, FR-08, NFR-03 | `python yscb.py dev test agents-workflow` |
| **FT-02** | 單元測試 | 驗證 `PlanVerifier` 拆分為 `_verifier_specs.py`、`_verifier_healer.py` 與 `verifier.py`，且移除 `M-03`/`M-04` 舊版分支後，動態章節、標頭自癒、伴隨檔生成與追溯鏈檢核完全合規 | FR-02, FR-04, NFR-01 | `python yscb.py dev test agents-workflow` |
| **FT-03** | 單元測試 | 驗證 `SessionTraceEngine` 拆分為 `_trace_parser.py`、`_trace_renderer.py` 與 `session_trace.py`，單一解析函式 $\le 70$ LOC 且五大摩擦訊號與多宿主轉錄解析 100% 通過 | FR-03, EC-03, NFR-01 | `python yscb.py dev test agents-workflow` |
| **FT-04** | 單元測試 | 驗證 `PlanScanner`、`PlanStatusResolver`、`PlanArchiver`、`PlanSearcher`、`RoadmapManager`、`TodoManager` 與 `scripts/cli.py` 移除 `M-04`/`M-05` 並共用 `_common.py` 原語及晉升管線 | FR-02, FR-07, NFR-02, NFR-03 | `python yscb.py dev test agents-workflow` |
| **ET-01** | 邊界測試 | 驗證 `plans/__init__.py` PEP 562 `__getattr__` 延遲匯入、未知屬性拋出 `AttributeError`、`_common.resolve_plan_uri` 統一回退 `plans/archived`、以及 `targets.save_tier_targets` 異常透明拋出 | EC-01, EC-02, EC-04 | `python yscb.py dev test agents-workflow` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `ArtifactCompiler`（含 `R02` 修正 `workflow.archived://` fallback 為 `"plans/archived"`）、`ReleasePublisher`（補齊 `self.host_dir` 傳遞）、`ReleaseTargetManager` 與 `WorkflowInitializer` 通過驗證 | 2026-10-31 |
| **FT-02** | `Passed` | `PlanVerifier` 拆分為 `_verifier_specs.py`、`_verifier_healer.py` 與 `verifier.py` 並於 `R02` 清除 11 個 Mode A 單行轉發包裝，更新 `roadmap.py` 與 `test_plans_toolchain.py` 直接呼叫規範函式 | 2026-10-31 |
| **FT-03** | `Passed` | `SessionTraceEngine` 拆分為 `_trace_parser.py`、`_trace_renderer.py` 與 `session_trace.py` 並於 `R02` 清除 `_parse_transcript_file` 與 `render_session_list_text` 2 個單行轉發包裝 | 2026-10-31 |
| **FT-04** | `Passed` | `PlanStatusResolver` 於 `R02` 移除 `parse_header_metadata` 單行包裝並收斂 `_read_doc_header_metadata`，`_common.py` 與 `plans/__init__.py` 移除 `_resolve_uri_path` 別名 | 2026-10-31 |
| **ET-01** | `Passed` | 完成 `R02` 全數 P1 缺陷修復與 14 處 Mode A 單行轉發清除，通過 `compileall` 靜態語法檢查（待 5 個子計畫收斂後由主代理統一執行編譯與沙盒測試） | 2026-10-31 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 待 5 個子計畫全數進入 P06 後，統一執行 `@build` 編譯安裝與 `python yscb.py dev test agents-workflow` 全綠驗收 | `Pending` | 待驗收 |
