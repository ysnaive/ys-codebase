# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：`sub_01_cli_guidance_and_privilege_optimization`  
> 建立日期：2026-08-29  
> 所屬主計畫：`workflow_and_agents_guidance_optimization` (Umbrella Level 2)  
> 狀態：Passed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `get_agents_cli_guild` 正確依據 `tier` 屬性分組渲染 🟢/🟡/🔴 三級權限標籤與防呆手冊表格。 | FR-02 | `python yscb.py dev test core -k test_cli_guild` |
| **FT-02** | 單元測試 | 驗證 `get_phase_cli_guild` 能根據傳入之 `phase`（如 `P05`, `P06`, `P07`）精準過濾該階段之推薦指令與防呆紅線清單。 | FR-03, FR-04 | `python yscb.py dev test core -k test_cli_guild` |
| **FT-03** | 單元測試 | 驗證 `KnowledgeAgentsStandards.md` 包含「🚨 執行紀律：日常代碼搜尋強制工具替代」條款與 `--ftype` 決策樹。 | FR-05 | `python yscb.py dev test knowledge-db` |
| **FT-04** | 靜態檢核 | 驗證 `ContextInit.md` 聚焦於 `AgentsStandards`，且 `AgentsStandards.md` 剛性純化後無失真。 | FR-06, FR-07 | `python yscb.py dev test agents-workflow` |
| **FT-05** | 契約測試 | 驗證 `core`, `dev`, `knowledge-db`, `agents-workflow` 所有指令均合法宣告 `tier` 與 `phases`。 | FR-01, FR-08 | `python yscb.py dev test core` |
| **ET-01** | 邊界測試 | 驗證 `commands` 缺失 `tier` 或未知 `tier` 時，自動安全 fallback 為 `"conditional"` (🟡)。 | EC-01, EC-02 | `python yscb.py dev test core -k test_cli_guild` |
| **ET-02** | 邊界測試 | 驗證 `phases` 為字串或空列表時，自動安全轉換容錯。 | EC-03, EC-04 | `python yscb.py dev test core -k test_cli_guild` |
| **RT-01** | 全域回歸 | 全生態系 4 大模組既有測試 100% Passed。 | NFR-03 | `python yscb.py dev test <core\|dev\|knowledge-db\|agents-workflow>` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_filter_and_formatting`: 🟢/🟡/🔴 三級權限標籤與 Markdown 表格渲染正確 | 2026-08-29 15:30 |
| **FT-02** | `Passed` | `test_phase_aware_jit_filtering`: Phase 5/6/7 JIT 指令與紅線過濾斷言 100% 通過 | 2026-08-29 15:30 |
| **FT-03** | `Passed` | `knowledge-db` 59/59 測試全數通過 (1.671s)，合規檢查 Passed | 2026-08-29 15:31 |
| **FT-04** | `Passed` | `agents-workflow` 40/40 測試全數通過 (6.074s)，合規檢查 Passed | 2026-08-29 15:31 |
| **FT-05** | `Passed` | `core` 59/59 測試全數通過 (1.071s)，全模組 commands 元資料合規 | 2026-08-29 15:30 |
| **ET-01** | `Passed` | `test_defensive_string_coercion`: tier 缺失自動 fallback 為 conditional 驗證通過 | 2026-08-29 15:30 |
| **ET-02** | `Passed` | `test_empty_fallback`: 空 commands 安全 fallback 驗證通過 | 2026-08-29 15:30 |
| **RT-01** | `Passed` | 全生態系 4 大模組 208/208 測試 100% Passed (core 59/59, dev 50/50, knowledge-db 59/59, agents-workflow 40/40) | 2026-08-29 15:31 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01 (CLI 指令手冊排版與清晰度驗收)**：檢視 `AgentsCliGuild.md` 三級權限標籤清晰醒目，守門邊界一目了然 (`Passed`)。
- [x] **UX-02 (ContextInit 認知減負效果)**：檢視 `ContextInit.md` 聚焦於 `AgentsStandards` 核心防呆反射，SOP 0~7 成功遞延 (`Passed`)。
- [x] **UX-03 (Knowledge-DB 搜尋鐵律感知驗收)**：檢視 `KnowledgeAgentsStandards.md` 工具替代與 `--ftype` 決策樹高約束力 (`Passed`)。
- [x] **UX-04 (AgentsStandards 剛性純化驗收)**：剝除 SOP 階段操作敘事，純化為全域防呆四重奏 (`Passed`)。
