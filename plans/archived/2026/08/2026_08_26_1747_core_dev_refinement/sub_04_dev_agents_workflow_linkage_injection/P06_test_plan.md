# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Dev 與 Agents-Workflow 模組連動注入 (Dev & Agents-Workflow Linkage Injection)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 模組功能打磨 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Passed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :---: | :--- |
| **FT-01** | 單元測試 | 驗證 `dev/manifest.json` 包含合法 `contributes["agents-workflow"]` 宣告，且 `DevEngineeringStandards.md` 存在 | FR-01, FR-02 | `python yscb.py dev test dev -k test_manifest` |
| **FT-02** | 單元測試 | 驗證 `agents-workflow` Stage 1 編譯時成功讀取 `dev` 之 `insert` 宣告並將規範注入至 `DevelopmentStandards.md` | FR-04 | `python yscb.py dev test agents-workflow -k test_compiler` |
| **FT-03** | 單元測試 | 驗證 `install <module>@build` 能自動從 `module.build://` 正確下載並安裝 `.build.zip` | FR-03 | `python yscb.py dev test core -k test_install_build_revision` |
| **ET-01** | 邊界測試 | 驗證 `install <module>@build` 在本地 `build/` 缺少 `.build.zip` 時拋出清晰之引導錯誤訊息 | EC-01 | `python yscb.py dev test core -k test_install_build_not_found` |
| **RT-01** | 回歸測試 | 全模組沙盒端到端回歸測試 100% 通過（114/114 Passed） | NFR-02 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_dev_contributes_and_standards_exist`: dev manifest 包含 contributes["agents-workflow"] 且 DevEngineeringStandards.md 齊備包含禁令 | 2026-08-26 23:15 |
| **FT-02** | `Passed` | `test_ft_10_dev_engineering_standards_injection`: below 模式注入規範至 DevelopmentStandards.md 且抹除錨點成功 | 2026-08-26 23:15 |
| **FT-03** | `Passed` | `test_download_build_revision_special_case`: install @build 直接從 module.build:// 下載物化成功 | 2026-08-26 23:15 |
| **ET-01** | `Passed` | `test_download_build_revision_not_found_raises`: 缺少 build zip 時正確拋出 FileNotFoundError 與 dev build 引導提示 | 2026-08-26 23:15 |
| **RT-01** | `Passed` | 全模組沙盒端到端測試 118/118 100% 通過 (47.770s, 0 Failed, 0 Skipped) | 2026-08-26 23:15 |


---

## 3. 人工 / UX 驗證 Checkpoint

- [ ] **UX-01**：執行 `agents-workflow release antigravity` 後，檢查 `.agents/standards/DevelopmentStandards.md` 尾部是否已完整包含「YS-Codebase 模組開發專案特化工程規範」且排版乾淨無殘留標籤。
- [ ] **UX-02**：實機測試 `python yscb.py install dev@build --force`，確認本機開發一鍵更新流暢。
