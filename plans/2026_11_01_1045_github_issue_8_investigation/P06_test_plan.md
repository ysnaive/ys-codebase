# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：GitHub Issue #8 四大跨模組缺陷與架構完善修復 (server / knowledge-db / agents-workflow)  
> 建立日期：2026-11-01  
> 所屬主計畫：N/A (Root Plan)  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `server.master.read_daemon_state` 正確透過 `vfs.read_json` 讀取 `daemon.json` 並反序列化為 `ServerDaemonState` | FR-01 | `python yscb.py dev test --target=server:TestServerModule.test_daemon_state_roundtrip_and_stop_lock_protection -q` |
| **FT-02** | 單元測試 | 驗證 `ParserRegistry` 支援從 `project://` / `yscb.host://` 載入專案自訂解析器，並將 `LanguageConfig.extensions` 動態綁定至內建 `HtmlParser` 與自訂解析器實例（不污染類別靜態集合） | FR-02, EC-03 | `python yscb.py dev test --target=knowledge-db:TestWebParsers.test_custom_parser_loading_extension_binding_and_error_diagnostics -q` |
| **FT-03** | 單元測試 | 驗證 `ParserRegistry.load_errors` 記錄解析器載入異常，且 `engine.status()` 與 CLI `index` / `status` 暴露警告並支援自癒重試 | FR-03, EC-02 | `python yscb.py dev test --target=knowledge-db:TestWebParsers.test_custom_parser_loading_extension_binding_and_error_diagnostics -q` |
| **FT-04** | 單元測試 | 驗證 `resolve_active_target_projected_path`、`PlanVerifier._build_next_phase_hint` 與 `PlanStatusResolver.resolve_next_action` 在僅啟用 `claude` Target 時動態輸出 `.claude/...` 路徑，無活躍 Target 時安全退回 `.agents/...` | FR-04, EC-04 | `python yscb.py dev test --target=agents-workflow:TestPlansModelRecord.test_ft_16_pxx_05_auto_consolidated_search_capsule_and_portability -q` |
| **ET-01** | 邊界測試 | 驗證當 `daemon.json` 損毀但 `daemon.lock` 仍被持有時，`cli.stop()` 拒絕刪除 `daemon.json`；當鎖釋放且進程結束時方清理殘留狀態檔 | FR-01, EC-01 | `python yscb.py dev test --target=server:TestServerModule.test_daemon_state_roundtrip_and_stop_lock_protection -q` |
| **RT-01** | 回歸測試 | 驗證 `server`（含 `Zero Source Path Injection` 護欄）、`knowledge-db` 與 `agents-workflow` 全量測試套件與 `dev check` 100% 通過 | NFR-01, NFR-02 | `python yscb.py dev test server -q && python yscb.py dev test knowledge-db -q && python yscb.py dev test agents-workflow -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `Pass: 1(100.0%), Fail: 0, Skip: 0` — `read_daemon_state` 讀寫往返斷言通過 | 2026-11-01 |
| **FT-02** | `Passed` | `Pass: 1(100.0%), Fail: 0, Skip: 0` — 專案自訂 `CustomAstroParser` 與 `HtmlParser` 實例級副檔名擴充通過 | 2026-11-01 |
| **FT-03** | `Passed` | `Pass: 1(100.0%), Fail: 0, Skip: 0` — 無效 `parser_entry` 準確記入 `reg.load_errors["broken_lang"]` | 2026-11-01 |
| **FT-04** | `Passed` | `Pass: 1(100.0%), Fail: 0, Skip: 0` — `claude` 單一 Target 下模板與技能路徑均映射至 `.claude/...` | 2026-11-01 |
| **ET-01** | `Passed` | `Pass: 1(100.0%), Fail: 0, Skip: 0` — `daemon.lock` 持有期間保護 `daemon.json` 不被誤刪 | 2026-11-01 |
| **RT-01** | `Passed` | `server`: 40 passed; `knowledge-db`: 158 passed; `agents-workflow`: 138 passed; `dev check`: 3/3 PASSED | 2026-11-01 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 確認 `server`、`knowledge-db` 與 `agents-workflow` 針對 GitHub Issue #8 四大問題之修復、單元測試與文檔更新符合預期 | `[跳過/免測]` | 開發者指示免測直接推進 P07 收尾結案 |

