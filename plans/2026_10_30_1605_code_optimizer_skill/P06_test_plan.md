# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：2026_10_30_1605_code_optimizer_skill  
> 建立日期：2026-10-30  
> 所屬主計畫：N/A  
> 狀態：Passed  
> 模型：Gemini 4 Argon (High)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `code-optimizer` 技能與 `CODE_OPTIMIZER_STANDARDS` 錨點註冊、100% 純手動觸發（不注入 `AgentsStandards.md`）、包含式三層範圍（`全專案 ⊃ 單一模組 ⊃ 單一檔案`）、開發者指定 `Mode A / Mode B`（含 `Mode B` 經嚴格查驗 0 外部跨模組調用之純內部工具函式直接破壞性收斂）、`R01` 調研診斷與三大流轉出口、三大單層 `references/` 及四大紅線 | FR-01, FR-02, FR-03, FR-04, EC-01, EC-02, EC-03, EC-04, NFR-01 | `python yscb.py dev test agents-workflow -k test_ft_14_code_optimizer_skill_and_standards_anchor` |
| **ET-01** | 邊界測試 | 驗證 `code-optimizer/SKILL.md` 與三份 `references/*.md` 無任何未加單反引號之動態標籤，且實機通過 Stage 1 `resolve_single_artifact` 與 Stage 2 `resolve_stage2_uri`（跨 `antigravity`、`claude`、`codex` 三平台專有名詞投影）0 Error / 0 `[compiler:warning]`，並支援 `CODE_OPTIMIZER_STANDARDS` 自訂規則注入與未注入時乾淨抹除 | FR-04, FR-05, EC-05, NFR-02 | `python yscb.py dev test agents-workflow -k test_ft_14_code_optimizer_skill_and_standards_anchor` |
| **RT-01** | 回歸測試 | 驗證全系統 19 個內建純 Skill 雙軌邊界（`test_ft_08`）、24 個標準 Stage 1 Token 錨點地圖（`test_ft_11`）、`contributes check`、`dev check agents-workflow` 與 `agents-workflow` 全量 136 項沙盒回歸測試 100% 通過 | FR-05, NFR-01, NFR-02 | `python yscb.py contributes check && python yscb.py dev check agents-workflow && python yscb.py dev test agents-workflow -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_ft_14_code_optimizer_skill_and_standards_anchor` 100% 通過（`SKILL.md` 128 行 $\le 180$ 行上限、雙維度定錨與三出口完整對齊） | 2026-10-30 16:17 |
| **ET-01** | `Passed` | Stage 1 與 Stage 2 跨 `antigravity` / `claude` / `codex` 編譯 `0 Error / 0 Warning`，`CODE_OPTIMIZER_STANDARDS` 注入與抹除符合契約 | 2026-10-30 16:17 |
| **RT-01** | `Passed` | `contributes check` (15 files Valid)、`dev check agents-workflow` (PASSED)、`dev test agents-workflow -q` (136/136, 100.0% Passed) | 2026-10-30 16:17 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視物化後之 `.agents/skills/code-optimizer/SKILL.md` 與 `references/{exploration-and-delegation,diagnostic-matrix,refactoring-playbook}.md`，或於對話中實測輸入 `/code-optimizer`，確認步驟 1 主動詢問「包含式檢視範圍（全專案/模組/檔案）」與「`Mode A / Mode B` 生命週期模式」後建立 `R01` 調研計畫並詢問三大流轉出口 | `[測試通過]` | 針對 `core` 模組 (`Mode A`) 派遣雙子代理 (Auditor A / B) 執行獨立盲測，審閱品質與收斂度 >90%，成果已收錄至 `2026_10_30_1641_code_optimize/sub_01_core_code_optimization/R01_code_optimization_audit.md` |

