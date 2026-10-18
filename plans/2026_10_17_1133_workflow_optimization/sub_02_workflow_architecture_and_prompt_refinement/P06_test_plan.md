# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：工作流流程架構與提示詞設計調研與優化 (Workflow Process Architecture & Prompt Refinement)  
> 建立日期：2026-10-18  
> 所屬主計畫：2026_10_17_1133_workflow_optimization  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `context-init/SKILL.md` 已移除「首行強制輸出」舊指令並對齊模型紀錄規範與權限標籤；`yscb-cli-guild/SKILL.md` 含 `[SAFE]/[CONDITIONAL]/[GATED]` 三級權限定義 | FR-01, FR-08 | `python yscb.py dev test agents-workflow -k test_plans_model_record` |
| **FT-02** | 單元測試 | 驗證 `continue/SKILL.md` 包含 `handoff.md` 消費後即刻刪除規定與 Umbrella 主目錄選配讀取；`pause/SKILL.md` 包含 `sub_` 子計畫路徑指引 | FR-02, FR-03 | `python yscb.py dev test agents-workflow -k test_plans_model_record` |
| **FT-03** | 單元測試 | 驗證 `plan_modes.md`、`research/SKILL.md`、`roadmap/SKILL.md`、`templates/roadmap.md` 包含跨軌道升級舊檔清理/回滾 SOP、Umbrella 主從狀態連動與 `Completed` 狀態枚舉 | FR-03, FR-04 | `python yscb.py dev test agents-workflow -k test_plans_model_record` |
| **FT-04** | 單元測試 | 驗證 `phase_07_walkthrough.md`、`P07_walkthrough.md`、`fast_track_plan.md`、`revision_log.md` 之 `plan verify` 結案時序與 `discuss/SKILL.md` 三大範疇出口及回填鏈 | FR-05, FR-06 | `python yscb.py dev test agents-workflow -k test_plans_model_record` |
| **FT-05** | 單元測試 | 驗證 `P04_implementation_plan.md` §4 不含 `- [ ]` Checkbox，`P04 §2` 與 `P07 §4.1` 皆具備三層 5 列文檔結構與 `<Category>` 命名，且 `P00 §3` 不含預設空 `- [ ]` | FR-07, FR-08, EC-04 | `python yscb.py dev test agents-workflow -k test_plans_model_record` |
| **ET-01** | 邊界測試 | 驗證修改模板後，`PlanVerifier` 對既有已完成之活躍子計畫 `sub_01` 與當前 `sub_02` 執行動態章節檢核 (`verify_plan`) 100% 通過（0 FAIL） | EC-01, EC-02, EC-03 | `python yscb.py agents-workflow plan verify 2026_10_17_1133_workflow_optimization` |
| **RT-01** | 回歸測試 | 執行 `agents-workflow` 全模組單元測試套件與 `dev check` 靜態合規檢查，確認 100% 通過（0 Failed, 0 Warnings, 0 Errors） | NFR-01, NFR-02 | `python yscb.py dev test agents-workflow -q` & `python yscb.py dev check agents-workflow` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestModelRecordRule.test_ft_04_sub02_context_init_and_cli_guild_alignment` 通過：`context-init` 已移除首行模型錨點並對齊 `[SAFE]/[CONDITIONAL]/[GATED]` 權限標籤，`yscb-cli-guild` 三級權限定義完整 | 2026-10-18 11:00 |
| **FT-02** | `Passed` | `TestModelRecordRule.test_ft_05_sub02_handoff_and_umbrella_lifecycle` 通過：`continue` 含 `Consume & Delete` 即刻刪除規定與 Umbrella 主目錄選配讀取，`pause` 含 `sub_{編號}_{名稱}/handoff.md` 指引 | 2026-10-18 11:00 |
| **FT-03** | `Passed` | `TestModelRecordRule.test_ft_05_sub02_handoff_and_umbrella_lifecycle` 通過：`plan_modes.md` 含 Fast->Full 刪舊檔、附掛修訂熔斷回滾/結算與 Umbrella 主從狀態連動，`roadmap.md` 含 `Completed` 狀態並通用化 §1.2 | 2026-10-18 11:00 |
| **FT-04** | `Passed` | `TestModelRecordRule.test_ft_06_sub02_templates_and_verify_ordering` 通過：`phase_07_walkthrough.md` 與 `P07`/`fast_track_plan`/`revision_log` 之 `plan verify` 結案時序校正完成，`discuss/SKILL.md` 含三大範疇出口與完整回填鏈 | 2026-10-18 11:00 |
| **FT-05** | `Passed` | `TestModelRecordRule.test_ft_06_sub02_templates_and_verify_ordering` 通過：`P04 §4` 移除 `- [ ]` Checkbox 改為有序清單，`P04 §2` 與 `P07 §4.1` 對齊三層 5 列文檔表與 `<Category>`，`P00 §3` 移除預設 `- [ ]` | 2026-10-18 11:00 |
| **ET-01** | `Passed` | 實機執行 `python yscb.py agents-workflow plan verify 2026_10_17_1133_workflow_optimization`：1 Total, 1 Passed, 0 Warnings, 0 Failed（`sub_01` 與 `sub_02` 100% 通過動態章節與佔位符檢核） | 2026-10-18 11:00 |
| **RT-01** | `Passed` | 實機執行 `python yscb.py dev check agents-workflow` (`PASSED`) 與 `python yscb.py dev test agents-workflow -q` (`Pass: 103(100.0%), Fail: 0, Skip: 0`) | 2026-10-18 11:00 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視更新後之 `ys_codebase/source/agents-workflow/assets/` 技能手冊與標準模板（或執行 `python yscb.py agents-workflow plan verify 2026_10_17_1133_workflow_optimization`），確認流程閉環與提示詞表述符合預期 | `[跳過/免測]` | 2026-10-18 開發者指示免測 |

