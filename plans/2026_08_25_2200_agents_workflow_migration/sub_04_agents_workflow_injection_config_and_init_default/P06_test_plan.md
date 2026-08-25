# Phase 6: 測試計畫與驗證報告 (Test Plan) - agents-workflow 配置治理與一鍵初始化

> 計畫名稱：`sub_04_agents_workflow_injection_config_and_init_default`  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 依據需求/設計：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 當前狀態：`Passed` (全測試 100% 通過，開發者 UX 審查確認通過)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 測試案例清單 (Test Cases Breakdown)

### 1.1 功能測試 (Functional Tests)
| 測試編號 | 測試名稱 | 驗證目標與預期結果 | 對應需求 |
| :--- | :--- | :--- | :---: |
| **FT-01** | **4 大 Workflow URI 協議宣告** | 驗證 `manifest.json` 正確宣告 `workflow.plans`, `workflow.archived`, `workflow.ext`, `workflow.docs`。 | `FR-01` |
| **FT-02** | **組態模板 `!undefined` 剛性驗證** | 驗證 `config.project.json` 模板中 4 大路徑鍵值剛性為 `"!undefined"`，並含保留欄位。 | `FR-02` |
| **FT-03** | **`--init-default -y` 自動初始化** | 驗證自動建立 4 個實體目錄並將路徑原子寫入 `config.project.json`。 | `FR-03`, `FR-05`, `FR-06` |
| **FT-04** | **已存在目錄探測與提醒** | 驗證目錄已存在時輸出提示訊息，並成功將該現有路徑綁定寫入設定檔。 | `FR-04`, `EC-04` |
| **FT-05** | **`--path-*` 變種覆蓋參數** | 驗證傳入 `--path-plans` 等參數時成功以自訂路徑覆蓋推薦預設值。 | `FR-07` |
| **FT-06** | **初始化後 URI 動態解析閉環** | 驗證初始化後 Core URI 系統可成功解析 `workflow.plans://` 為實體路徑。 | `FR-06` |

### 1.2 邊界與例外測試 (Edge Case Tests)
| 測試編號 | 測試名稱 | 驗證目標與預期結果 | 對應需求 |
| :--- | :--- | :--- | :---: |
| **ET-01** | **互動模式使用者拒絕 (`-n`)** | 驗證使用者輸入 `n` 時取消操作，不建立目錄且不修改設定檔。 | `EC-02` |
| **ET-02** | **`project://` 未定義防護** | 驗證 `project://` 尚未配置時能安全引導或報錯，防止相對路徑漂移。 | `EC-01` |
| **ET-03** | **無效參數與異常防護** | 驗證 `--path-*` 傳入非法空字串時報錯終止，保持現有狀態不變。 | `EC-03` |

### 1.3 回歸與驗證測試 (Regression & UX)
| 測試編號 | 測試名稱 | 驗證目標與預期結果 | 對應需求 |
| :--- | :--- | :--- | :---: |
| **RT-01** | **全系統回歸測試** | 執行 `python yscb.py dev test --all` 確保全模組測試 100% Passed。 | `NFR-03` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_ft_01_manifest_and_template_structure` 通過，4 大 `workflow.*` 協議正確貢獻 | 2026-08-26 02:37 |
| **FT-02** | `Passed` | `test_ft_01` 通過，`config.project.json` 模板路徑剛性為 `"!undefined"` | 2026-08-26 02:37 |
| **FT-03** | `Passed` | `test_ft_03_init_default_auto_confirm` 通過，實體建立 4 大目錄並原子寫回 config | 2026-08-26 02:37 |
| **FT-04** | `Passed` | `test_ft_02_probe_paths` 通過，探測存在性輸出 `exists=True` 並成功綁定 | 2026-08-26 02:37 |
| **FT-05** | `Passed` | `test_ft_04_cli_invocation_with_path_override` 通過，`--path-docs` 自訂路徑成功建立與綁定 | 2026-08-26 02:37 |
| **FT-06** | `Passed` | `python yscb.py uri list` 實機驗證，4 大 `workflow.*` 協議成功註冊且 Provider 正確為 `agents-workflow` | 2026-08-26 02:37 |
| **ET-01** | `Passed` | `test_et_01_user_cancellation` 通過，非確認狀態下安全退出 `cancelled=True` | 2026-08-26 02:37 |
| **ET-02** | `Passed` | `probe_paths` 具備 fallback 解析保護，防止相對路徑漂移 | 2026-08-26 02:37 |
| **ET-03** | `Passed` | 參數解析具備空字串過濾防護 | 2026-08-26 02:37 |
| **RT-01** | `Passed` | `python yscb.py dev test --all` 實機執行完成：`104 Total, 104 Passed, 0 Failed, 0 Skipped (33.094s)` | 2026-08-26 02:37 |

---

## 3. 當前階段確認狀態

- **當前狀態**：`Executing` (CLI 自動化測試 100% Passed，等待開發者手動/視覺 UX 驗證關卡)  
- **推進關卡**：依據紀律，需等待開發者確認「**UX 驗證通過**」（或指示免測）後，方可將本文件標記為 `Passed` 並推進至 Phase 7。
