# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_01_python_aci_toolchain  
> 建立日期：2026-10-23  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `PlanStatusResolver.resolve_next_action` 能針對 Phase 0、`P01`~`P07`、Fast Track、Revision、Research 與含活躍 `sub_XX` 之 Umbrella 計畫，精準推導 `mode`、`current_phase`、`next_phase` 與 `required_reference_path`。 | FR-01 | `python yscb.py dev test agents-workflow -k test_plans_aci_toolchain -q` |
| **FT-02** | 單元測試 | 驗證 `plan status --resume` 在存在 `handoff.md` 時完整輸出快照內容並立即呼叫 `os.unlink()` 物理刪除檔案；未傳 `--resume` 時維持純唯讀且保留 `handoff.md`。 | FR-02 | `python yscb.py dev test agents-workflow -k test_plans_aci_toolchain -q` |
| **FT-03** | 單元測試 | 驗證 `continue/SKILL.md` 已更新為優先呼叫 `plan status --resume` 並保留極簡沙盒唯讀 Fallback。 | FR-03 | `python yscb.py dev test agents-workflow -k test_plans_aci_toolchain -q` |
| **FT-04** | 單元測試 | 驗證 `PlanVerifier` 支援 `--phase` 左移與雙檔協同檢核：`P02` 存在但缺少 `P06_test_plan.md`（且未啟用 `--log` 自癒）時回報 `COMPANION` `FAIL`；`P04` 存在但 `P06_test_plan.md` 仍為 `Draft` 時回報 `COMPANION` `FAIL`。 | FR-04 | `python yscb.py dev test agents-workflow -k test_plans_aci_toolchain -q` |
| **FT-05** | 單元測試 | 驗證 `PlanVerifier` 之 `P01` $\leftrightarrow$ `P06` 追溯鏈集合差集比對：當 `P01` 定義之 `FR-01`、`EC-01`、`NFR-01` 在 `P06` 中有遺漏時，精準回報 `TRACEABILITY` `FAIL` 並列出孤兒需求 ID。 | FR-05 | `python yscb.py dev test agents-workflow -k test_plans_aci_toolchain -q` |
| **FT-06** | 單元測試 | 驗證 `PlanVerifier` 所有診斷錯誤訊息均包含具體可操作之修復建議 (`Actionable Fix Hint`)。 | FR-06 | `python yscb.py dev test agents-workflow -k test_plans_aci_toolchain -q` |
| **FT-07** | 單元測試 | 驗證 `plan verify --phase P02 --log "..."` 四步執行管線：當 `P02` 合規但缺少 `P06_test_plan.md` 與 `changelog.md` 時，自動從模板初始化 `P06_test_plan.md (Draft)` 與 `changelog.md`，通過雙檔檢核並以系統時間戳追加日誌列。 | FR-07 | `python yscb.py dev test agents-workflow -k test_plans_aci_toolchain -q` |
| **FT-08** | 單元測試 | 驗證伴隨檔模型紀錄防回溯與終端引號規範：傳入 `--model` 時優先採用，未傳時僅取同階段主體檔模型，且 `yscb-cli-guide` / `development-sop` 明確記載 `--log` 禁用雙引號與反引號規則。 | FR-08 | `python yscb.py dev test agents-workflow -k test_plans_aci_toolchain -q` |
| **ET-01** | 邊界測試 | 驗證當存在多個活躍進行中計畫且執行 `plan status --resume` 未指定 `--plan` 時，拒絕盲目挑選或刪除任何 `handoff.md` 並回傳明確提示。 | EC-01 | `python yscb.py dev test agents-workflow -k test_plans_aci_toolchain -q` |
| **ET-02** | 邊界測試 | 驗證 `P01` 含有刪除線 `~~FR-99~~`、Fenced Code Block 內 `FR-88` 與 HTML 註解內 `EC-77` 時，預過濾器成功排除，不誤報為孤兒需求 ID。 | EC-02 | `python yscb.py dev test agents-workflow -k test_plans_aci_toolchain -q` |
| **ET-03** | 邊界測試 | 驗證當 `P02_architecture_plan.md` 本體含有未替換佔位符 (`FAIL`) 時執行 `plan verify --phase P02 --log "..."`，拒絕生成伴隨 `P06` 且拒絕將 `--log` 寫入 `changelog.md`。 | EC-03 | `python yscb.py dev test agents-workflow -k test_plans_aci_toolchain -q` |
| **ET-04** | 邊界測試 | 驗證對同一階段重複執行相同之 `plan verify --log "<相同摘要>" --type PHASE` 時，冪等防重入保護跳過重複插入，表格僅保留單筆紀錄。 | EC-04 | `python yscb.py dev test agents-workflow -k test_plans_aci_toolchain -q` |
| **ET-05** | 邊界測試 | 驗證當 `P00_discuss.md` 標頭模型為 `OldModel-1.0`、而 `P02_architecture_plan.md` 標頭模型為 `Unknown` 且未傳 `--model` 時，自動生成的 `P06_test_plan.md (Draft)` 標頭模型為 `Unknown`（嚴禁跨階段回溯讀取 `P00`）。 | EC-05 | `python yscb.py dev test agents-workflow -k test_plans_aci_toolchain -q` |
| **ET-06** | 邊界測試 | 驗證針對 `Umbrella` 下之子計畫傳入 `<umbrella>/sub_01_xxx` 或唯一 `sub_01_xxx` 名稱時，`plan status --resume` 與 `plan verify --phase --log` 皆能精準定位並校驗 `> 所屬主計畫：` 標頭。 | EC-06 | `python yscb.py dev test agents-workflow -k test_plans_aci_toolchain -q` |
| **RT-01** | 回歸測試 | 執行 `agents-workflow` 全量單元測試套件與 `dev check agents-workflow` 靜態合規檢查，驗證 `NFR-01` 與 `NFR-02` 100% 通過。 | NFR-01, NFR-02 | `python yscb.py dev test agents-workflow -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01 ~ FT-08** | `Passed` | `TestPlansACIToolchain` 8 項功能測試 100% 通過（確定性領航、`--resume` 閱後即焚、`continue` 對接、`--phase` 雙檔檢核、`P01<->P06` 差集比對、Actionable Fix Hints、四步管線伴隨檔自癒與 `--log` 盲寫） | 2026-10-23 |
| **ET-01 ~ ET-06** | `Passed` | `TestPlansACIToolchain` 6 項邊界測試 100% 通過（多活躍計畫拒絕盲猜、`~~...~~` 刪除線與代碼塊/註解預剝除、主體檔 FAIL 阻斷自癒與日誌寫入、首筆冪等防重入、伴隨檔模型零跨階段回溯、`sub_XX` 直接定位） | 2026-10-23 |
| **RT-01** | `Passed` | `dev check agents-workflow` `[PASS]`；`dev test agents-workflow -q` 全模組 **123/123 (100.0%)** 測試通過（`Pass: 123, Fail: 0, Skip: 0`），並完成 `install agents-workflow@build --force` 自部署 | 2026-10-23 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 實機執行 `python yscb.py agents-workflow plan status --resume` 與 `python yscb.py agents-workflow plan verify --phase P04 --log "..."`，檢視終端輸出之確定性領航資訊與免讀日誌追加體驗。 | `[跳過/免測]` | 開發者指示從 P01 需求反查實作無誤後免測進入 P07（已逐條完成 FR-01~08、EC-01~06、NFR-01~02 反查並 100% 通過 123 項自動化測試） |

