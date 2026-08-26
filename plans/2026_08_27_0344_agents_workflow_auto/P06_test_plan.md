# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Agents-Workflow 模組新增 Auto 工作流 (Add Auto Workflow to Agents-Workflow)  
> 建立日期：2026-08-27  
> 狀態：Passed  
> 依據 P01/P02/P03：[P01_requirements_spec.md](./P01_requirements_spec.md) / [P02_architecture_plan.md](./P02_architecture_plan.md) / [P03_api_spec.md](./P03_api_spec.md)  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `Auto.md` 檔案存在、包含 `__${yscb.host://yscb.py}__`、定義四大步驟與三大熔斷機制。 | FR-01, FR-03 | `python yscb.py dev test agents-workflow -k test_auto_workflow` |
| **FT-02** | 單元測試 | 驗證 `manifest.json` 中 `contributes["agents-workflow"]["export"]` 正確包含 `Auto.md` 條目與 `WORKFLOW_AUTO` token。 | FR-02 | `python yscb.py dev test agents-workflow -k test_auto_manifest` |
| **FT-03** | 單元測試 | 驗證 `compiler.py` 能夠成功編譯 `Auto.md` 並正確轉譯所有佔位符（無警告日誌）。 | FR-04, NFR-01 | `python yscb.py dev test agents-workflow -k test_auto_compilation` |
| **ET-01** | 單元/邏輯測試 | 驗證 `Auto.md` 規範中明確包含 Phase 0 觸發拒絕與引導至 P00 之邊界條款。 | EC-01 | `python yscb.py dev test agents-workflow -k test_auto_workflow_edge_cases` |
| **ET-02** | 單元/邏輯測試 | 驗證 `Auto.md` 規範中明確包含 Fast Track (Level 0) 不適用之邊界條款。 | EC-02 | `python yscb.py dev test agents-workflow -k test_auto_workflow_edge_cases` |
| **ET-03** | 單元/邏輯測試 | 驗證 `Auto.md` 規範中包含 P06 手動/UX 驗證絕對阻斷（強制停步）之邊界條款。 | EC-05 | `python yscb.py dev test agents-workflow -k test_auto_workflow_edge_cases` |
| **RT-01** | 全系統回歸測試 | 執行 `agents-workflow` 模組全量沙盒回歸測試，維持 100% Passed。 | NFR-02 | `python yscb.py dev test agents-workflow` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_ft_01_auto_workflow_asset_content`: 驗證 Auto.md 包含四大步驟、三大熔斷、專案路徑佔位符與尾部 token 通過 | 2026-08-27 04:00 |
| **FT-02** | `Passed` | `test_ft_02_manifest_export_and_token`: 驗證 manifest.json export 與 token WORKFLOW_AUTO 宣告通過 | 2026-08-27 04:00 |
| **FT-03** | `Passed` | `test_ft_03_compilation_and_placeholder_resolution`: 驗證 compiler.py Stage 1 解析 Auto.md 通過 | 2026-08-27 04:00 |
| **ET-01** | `Passed` | `test_et_01_et_02_et_03_edge_cases_in_specification`: 驗證 Phase 0 拒絕防禦條款存在 | 2026-08-27 04:00 |
| **ET-02** | `Passed` | `test_et_01_et_02_et_03_edge_cases_in_specification`: 驗證 Fast Track 不適用防禦條款存在 | 2026-08-27 04:00 |
| **ET-03** | `Passed` | `test_et_01_et_02_et_03_edge_cases_in_specification`: 驗證 P06 UX 阻斷條款存在 | 2026-08-27 04:00 |
| **RT-01** | `Passed` | `python yscb.py dev test agents-workflow`: 30 Total, 30 Passed, 0 Failed, 0 Skipped (100% Ready) | 2026-08-27 04:02 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01 (工作流資產與命令體驗驗證)**：
  - 發布後的 `.agents/workflows/Auto.md` 排版乾淨、包含 `__${yscb.host://yscb.py}__` 轉譯之指令路徑、三大熔斷守門明確。
  - `.agents/workflows/ContextInit.md` 明確強化 `DevelopmentStandards.md` 之讀取引導。
  - 完成 revision 遞增 (1.0.1.1) 正式 release 與 install。
