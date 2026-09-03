# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：build_git_decoupling  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Passed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `_generate_internal_gitignore` 包含 `/.build/` 條目且標記區塊軟合併無損 | FR-01 | `python yscb.py dev test --target=core:TestBuildGitDecoupling.test_ft_01_gitignore_contains_dot_build` |
| **FT-02** | 單元測試 | 驗證 `module.build.root://` 與 `module.build://` 協議精確解析至 `yscb://.build/` | FR-02 | `python yscb.py dev test --target=core:TestBuildGitDecoupling.test_ft_02_uri_resolution_to_dot_build` |
| **FT-03** | 單元測試 | 驗證 `Builder.build_package` 產物輸出至 `.build/` 目錄並生成 ZIP 與 index.json | FR-03 | `python yscb.py dev test --target=core:TestBuildGitDecoupling.test_ft_03_builder_outputs_to_dot_build` |
| **FT-04** | 單元測試 | 驗證 `_restore_module_package` 優先自 `.build/` 提取最新建置產物 | FR-04 | `python yscb.py dev test --target=core:TestBuildGitDecoupling.test_ft_04_restore_prioritizes_dot_build` |
| **FT-05** | 規格檢驗 | 驗證 `STANDARDS.md` 空間協議表政策為 `🚫 忽略` 且實體路徑為 `yscb://.build/` | FR-05 | 檔案結構與關鍵字核驗 |
| **ET-01** | 邊界測試 | 驗證 `.build/` 目錄不存在時建置管線自動創建且不拋出異常 | EC-01 | `python yscb.py dev test --target=core:TestBuildGitDecoupling.test_et_01_nonexistent_dot_build_auto_create` |
| **PT-01** | 效能測試 | 驗證協議解析為靜態映射，零額外耗時開銷 | NFR-01 | `python yscb.py dev test --target=core:TestBuildGitDecoupling.test_pt_01_uri_resolve_perf` |
| **RT-01** | 全量回歸 | 驗證全生態系四大模組單元測試 100% 通過 (305/305) | NFR-03 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `PASS` | 通過。`test_ft_01_gitignore_contains_dot_build`: 成功建立含 `/.build/` 與 `/.modules/` 之標記區塊，並與自訂規則無損軟合併。 | 2026-09-03 11:10 |
| **FT-02** | `PASS` | 通過。`test_ft_02_uri_resolution_to_dot_build`: `module.build://` 與 `module.build://core` 精確解析至包含 `.build` 之實體路徑。 | 2026-09-03 11:10 |
| **FT-03** | `PASS` | 通過。`test_ft_03_builder_outputs_to_dot_build`: Builder 輸出路徑定位至 `.build/mock_mod`。實機執行 `dev build core` 產出至 `ys_codebase/.build/core/1.0.2.build.zip`。 | 2026-09-03 11:11 |
| **FT-04** | `PASS` | 通過。`test_ft_04_restore_prioritizes_dot_build`: 當 `.build/` 與舊 `build/` 同時存在時，優先解壓 `.build/` 產物。 | 2026-09-03 11:10 |
| **FT-05** | `PASS` | 通過。`test_ft_05_standards_doc_check`: `docs/_project/STANDARDS.md` 標示 `module.build.root://` 為 `yscb://.build/` 且政策為 `🚫 忽略`。 | 2026-09-03 11:10 |
| **ET-01** | `PASS` | 通過。`test_et_01_nonexistent_dot_build_auto_create`: 缺失目錄時安全創建。 | 2026-09-03 11:10 |
| **PT-01** | `PASS` | 通過。`test_pt_01_uri_resolve_perf`: 100 次循環平均耗時 $< 0.02\text{ms}$，遠低於 1.0ms 上限。 | 2026-09-03 11:10 |
| **RT-01** | `PASS` | 通過。`python yscb.py dev test --all` 實機執行：agents-workflow (50/50), core (73/73), dev (52/52), knowledge-db (130/130)，總計 305/305 通過 (4.943s)。 | 2026-09-03 11:12 |

---

## 3. 人工 / UX 驗證 Checkpoint (User Verified)

- [x] **UX-01**：執行 `python yscb.py dev build core`，確認產物產出至 `ys_codebase/.build/core/`，且 `git status` 乾淨無任何 `.build/` 變更。（已驗證通過：產物精確輸出至 `.build/core/1.0.2.build.zip` 且受 Git 忽略）
- [x] **UX-02**：執行 `python yscb.py dev test core`，確認沙盒環境無縫自 `.build/` 載入套件並 100% 通過測試。（已驗證通過：沙盒成功提取 `.build/` 產物，73/73 測試全數通過）
