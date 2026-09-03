# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：dev test 輸出格式優化與節流模式 (Throttle Output)  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_03_1227_agents_workflow_plan_filter_and_session_analysis  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-06 在 P03 API 規格書中均具備對應之實體介面、檔案與實作拓撲。
- [x] **邊界防護**：EC-01 ~ EC-05 均有具體防禦處置（空測試防除零、崩潰兜底、多進程無交錯）。
- [x] **依賴純淨**：符合 NFR-02 約束，維持 100% Python 標準庫零第三方依賴。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **技能手冊** | `source/dev/assets/skills/yscb-module-dev/SKILL.md` | Modify | 雙軌開發流程圖與日常/發布流水線全面更新為 `--quiet`。 |
| **工作流程** | `source/agents-workflow/assets/workflows/Auto.md` | Modify | 自動推進工作流測試步驟命令更新為 `--quiet`。 |
| **工作流程** | `source/agents-workflow/assets/workflows/Review.md` | Modify | 品質驗收工作流全量測試指令更新為 `--quiet`。 |
| **工程手冊** | `source/agents-workflow/assets/skills/development-sop/references/phase_06_test.md` | Modify | Phase 6 測試手冊推薦執行指令更新為 `--quiet`。 |
| **工程手冊** | `source/agents-workflow/assets/skills/development-sop/references/plan_modes.md` | Modify | 迅捷/修訂模式中的測試命令更新為 `--quiet`。 |
| **發布日誌** | `CHANGELOG.md` | Modify | Phase 7 結案時追加本子計畫高階變更摘要。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若測試過程中發生嚴重未捕獲 Exception（如記憶體不足或沙盒崩潰），節流模式是否會吞掉錯誤導致「假綠燈」？  
> 💡 **防護解法**：絕對不會。`Tester` 調度器會嚴密校驗進程返回碼 `ret_code`；若 `ret_code != 0` 且無有效 JSON 報告，將強制判定為 `Fail: 1` 並顯示崩潰錯誤訊息及保留沙盒路徑，確保問題絕不漏報。

> ❓ **尖銳問題 2**：在 `--all -q` 多模組並行執行時，多個平行 worker 是否會發生輸出交錯破壞單行格式？  
> 💡 **防護解法**：平行 worker 在靜默模式下被徹底禁止直接寫入 stdout/stderr；全部資料透過獨立沙盒中的 `report_<mod>.json` 傳遞，最終由主進程統一計算並印出單行文字，物理上根除交錯可能。

> ❓ **尖銳問題 3**：AI 手冊全面對齊 `--quiet` 後，若開發者手動需要檢視完整 ASCII 診斷表格，體驗是否會受損？  
> 💡 **防護解法**：不會。未傳入 `-q / --quiet` 時完全維持既有完整 ASCII 報告行為；`--quiet` 是專為高頻回歸測試與 Agent Token 保護量身打造之高階開關。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：`runner.py` 擴充 — 於 `ASCIIReportFormatter` 實作 `format_throttled(report_data)`。
- [ ] **TASK-02**：`tester.py` 改造 — 支援 `--quiet` / `-q` 解析、深度靜默前置進度並整合節流報告。
- [ ] **TASK-03**：單元測試編寫 — 建立 `source/dev/tests/test_tester_throttle.py`，覆蓋 FT-01~04 與 EC-01~02。
- [ ] **TASK-04**：AI 指引與工作流更新 — 對齊 `yscb-module-dev`、`Auto.md`、`Review.md`、`development-sop` 為 `--quiet`。
- [ ] **TASK-05**：全模組沙盒測試驗證、本地 `@build` 直裝與實機回歸。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 剛性定稿實作規劃**：確認依序執行 TASK-01 ~ TASK-05，並同步將 `P06_test_plan.md` 定稿為 `Confirmed`。
