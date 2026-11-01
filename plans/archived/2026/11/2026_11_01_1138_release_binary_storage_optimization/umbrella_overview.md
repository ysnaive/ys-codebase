# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：2026_11_01_1138_release_binary_storage_optimization  
> 建立日期：2026-11-01  
> 計畫狀態：Completed  
> Umbrella 模式：Incremental (增量演進型)  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：
  - 根治 `ys_codebase/release/**/*.zip` 二進位發布包混入 Git `main` 分支歷史導致 Packfile 膨脹（佔比達 45.67%）之長期技術債，建立兼顧「第三方模組通用性（標準事件廣播 + `index.json` 版本帳本 SSOT）」、「母倉本地同版本 `source/` 自給自足動態打包」、「事後相容性邊界修正與釋出元數據嚴重度治理」與「GitHub Actions 單層孤兒分支 (`releases`) 免 Token 遠端分發」之現代化發布架構，並一次性完成存量遷移與 Git 歷史徹底淨化。
- **架構邊界**：
  - 涵蓋 `yscb.py` 單檔引導器、`ys_codebase/source/{core,dev}` 發布與安裝引擎、`.github/workflows/` 自動化發布管線、`.gitignore` 追蹤邊界，以及存量 37 個 `.zip` 遷移與 `git filter-repo` 歷史清洗。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_release_binary_and_git_history` | Standard Track | `Completed` | 通用發布事件廣播 (`on_module_released`)、`index.json` 版本帳本 SSOT、本地同版本 `source/` 自給自足打包、`pruned` 版本同三元組自動遞補、母倉 `releases` 孤兒分支 CI 管線與舊版 URL 無感遷移 |
| **sub_02** | `sub_02_release_metadata_and_compat_governance` | Standard Track | `Completed` | 事後相容性邊界修正 (`index.json` 依賴覆寫 + `"status": "active"\|"pruned"` + `dev` 輕量維護指令)、版本釋出元數據 (`type`/`urgency`/`summary` 向前相容解析)、雙軌發布注入與 `UpdateChecker` 跨版本 `[CRITICAL UPDATE]` 告警 |
| **sub_03** | `sub_03_legacy_release_migration_and_history_purge` | Standard Track | `Completed` | 存量 37 個 `.zip` 全數保留遷移與 `index.json` 元數據自動回填、本次變更模組 (`core`/`dev`/`yscb.py`) 正式升版發布、`.gitignore` 切換與 `git filter-repo` 全歷史一次性徹底淨化 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 0 (`R01`)**：完成發布產物二進位儲存解耦與 Git 歷史瘦身深度調研（[`R01_release_binary_and_git_history_analysis.md`](./R01_release_binary_and_git_history_analysis.md)）並拍板四大支柱架構。
- [x] **里程碑 1 (`sub_01`)**：完成 [`sub_01_release_binary_and_git_history`](./sub_01_release_binary_and_git_history/P00_discuss.md) 發布解耦架構與本地同版本自給自足引擎改造。
- [x] **里程碑 2 (`sub_02`)**：完成 [`sub_02_release_metadata_and_compat_governance`](./sub_02_release_metadata_and_compat_governance/P00_discuss.md) 事後相容性修正機制、釋出元數據與更新嚴重度告警。
- [x] **里程碑 3 (`sub_03`)**：完成 [`sub_03_legacy_release_migration_and_history_purge`](./sub_03_legacy_release_migration_and_history_purge/P00_discuss.md) 存量發布遷移、新版本發布與 Git 歷史徹底淨化。

