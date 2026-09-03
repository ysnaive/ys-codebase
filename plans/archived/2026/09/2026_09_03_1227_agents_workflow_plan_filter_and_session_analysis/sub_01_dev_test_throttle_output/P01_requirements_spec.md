# 需求規格說明書 (Requirements Specification)

> 功能名稱：dev test 輸出格式優化與節流模式 (Throttle Output)  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_03_1227_agents_workflow_plan_filter_and_session_analysis  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | CLI 節流參數支援 | `dev test` 與 `dev op-test` 新增 `--quiet` 與 `-q` 命令列參數，未指定時維持既有預設完整 ASCII 診斷報告。 | P0 | [P00:DR-02] |
| **FR-02** | 深度靜默前置日誌 | 在 `--quiet` / `-q` 啟用時，徹底抑制前置之沙盒建置、進度訊息與清理日誌（包含 `[dev:test] Pre-building...`、`Create sandbox...`、`Cleaned up sandbox...` 等）。 | P0 | [P00:DR-03] |
| **FR-03** | 全數通過單行壓縮輸出 | 在 `--quiet` / `-q` 啟用且所有測試通過時，僅輸出單行文字：`Pass: {passed}({pass_pct:.1f}%), Fail: 0, Skip: {skipped}`，無任何多餘邊框或表格，最大化壓縮 Token I/O。 | P0 | [P00:DR-04] |
| **FR-04** | 失敗測試精確詳情保留 | 在 `--quiet` / `-q` 啟用且存在失敗/錯誤時，輸出首行統計後，接續輸出 `FAILED / ERROR TEST CASES LIST:` 詳情區塊（包含模組名、測試名、錯誤訊息、位置與 Quick Re-run 提示）。 | P0 | [P00:DR-04] |
| **FR-05** | 單模組與全庫並行支援 | 節流輸出模式同時支援單模組測試（`python yscb.py dev test <mod> -q`）、特定目標（`--target=... -q`）與多模組並行測試（`python yscb.py dev test --all -q`）。 | P0 | [P00:DR-05] |
| **FR-06** | AI 調用手冊全面對齊 --quiet | 修改專案內所有向 AI 推薦調用 `dev test` 的技能手冊、工作流與指引，全面一律改為使用 `--quiet`（包含 `yscb-module-dev`、`Auto.md`、`Review.md`、`development-sop` 等）。 | P0 | [P00:DR-05] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 0 測試案例或空模組 | 當目標模組無測試案例或 total = 0 時，避免除以零異常，精確輸出 `Pass: 0(0.0%), Fail: 0, Skip: 0`。 |
| **EC-02** | 所有測試均被 Skip | 當所有測試均被跳過時（`passed=0, failed=0, skipped>0`），輸出 `Pass: 0(0.0%), Fail: 0, Skip: {skipped}`，退出碼為 0。 |
| **EC-03** | 多模組並行平行聚合 | 在 `--all -q` 時各平行 worker 保持絕對靜默，聚合層於測試全數結束後一次性輸出合併之統計行與跨模組失敗清單。 |
| **EC-04** | 參數組合與互斥定義 | 當 `--quiet` 與 `-v / --verbose` 同時傳入時，定義 `--quiet` 優先（或最後指定者優先），確保節流指令具備最高優先權。 |
| **EC-05** | 沙盒執行崩潰防護 | 若子程序或沙盒執行異常崩潰（returncode != 0 且無 report.json），節流模式仍須輸出統計為 `Fail: 1` 並顯示崩潰錯誤訊息，避免除錯線索丟失。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | Token 壓縮率 | 在回歸測試 100% 通過之情境下，終端文字吞吐量由原本 ~500~1500 Tokens 降低至 10~15 Tokens，壓縮比 $\ge 95\%$。 |
| **NFR-02** | 純淨零依賴 | 全功能 100% 使用 Python 標準庫實作，零第三方套件依賴。 |
| **NFR-03** | 生態系向後相容 | 預設未傳入 `--quiet` / `-q` 時，輸出與現有完整 ASCII 報告 100% 相容，既有自動化契約測試無破壞。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`**：`dev test` 內部有兩層調度：外層 `Tester._run_test`（負責 sandbox provision 與日誌列印）與內層 `Tester._run_op_test`（在 sandbox 內被叫起）。因此 `--quiet` 必須由外層解析並向下傳遞給 `op-test`（或置入環境變數 `YSCB_TEST_QUIET=1`），使內外層皆達成深度靜默。
- **`[!NOTE]`**：AI 調用模式對齊 (FR-06) 涵蓋 source 空間中的 `source/dev/assets/skills/yscb-module-dev/`、`source/agents-workflow/assets/` 與對應 contributes，修改後需透過 `@build` 重新編譯物化。
