# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：ecosystem_hot_update_git_decoupling_and_pip_governance  
> 建立日期：2026-09-02  
> 狀態：In Progress  
> Umbrella 模式：Incremental (增量演進型)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：
  - 統籌落實兩大調研成果（[R01: 全生態系安全熱更新與 JIT 變更感知自愈機制](file:///workspace/ys-codebase/plans/2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance/R01_ecosystem_safe_hot_update_and_jit_synchronization.md) 與 [R02: YSCB 私有 Pip 相依性治理體系與可選硬體加速架構](file:///workspace/ys-codebase/plans/2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance/R02_pip_dependency_governance_and_optional_acceleration.md)），並針對架構演進中的關鍵環節進行增量型打磨與品質加固。
  - 消除生態系內的快取盲區、文檔過期斷層與 Git 歷史沈澱，建立高響應、零阻塞之 JIT 熱自愈與智慧升級提示機制。
  - 完成 `modules/` 運行端產物的冷啟動再生管線與 Git 解耦，驅動倉庫代碼純淨化。
  - 建立 YSCB 私有微虛擬環境治理體系，在堅持「使用者端零全域污染、開箱即用、雙軌原生平穩降級」的前提下，賦能極速硬體加速與 IDE 智慧推導。
- **架構邊界**：
  - `core` 模組：`contributes` JIT 快照嗅探閘門、`UpdateChecker` 12 小時節流探測、私有 Pip 微環境隔離管理器 (`pip_manager`) 與冷啟動再生 (`bootstrap` / `restore`)。
  - `agents-workflow` 模組：資產特徵指紋校驗與 JIT Release Target 投影自動物化同步。
  - `dev` 模組：Dogfooding 閉環加固（`--sync` 直裝）、`dev env` 本地 IDE 設定增量投影與沙盒環境微微虛擬環境對接。
  - `knowledge-db` 模組：雙軌加速外掛試點（`zstandard` / `lmdb` / `tree-sitter`）與純 Python 原生兜底。
  - 專案根目錄與規範：`ys_codebase/modules/` 解耦 Git 追蹤、`docs/_project/STANDARDS.md` 空間協議更新。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_ecosystem_safe_hot_update_and_jit_synchronization` | Full Track | `Completed` | 全生態系安全熱更新與 JIT 變更感知自愈機制（依據 [R01](file:///workspace/ys-codebase/plans/2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance/R01_ecosystem_safe_hot_update_and_jit_synchronization.md)，涵蓋 core contributes JIT 自愈、agents-workflow JIT 投影同步、12 小時來源版本探測提示、dev dogfooding 閉環加固） |
| **sub_02** | `sub_02_modules_git_decoupling` | Full Track | `Completed` | `modules/` 運行端冷啟動再生管線與 Git 追蹤解耦（含 bootstrap/restore 命令、.gitignore 配置、空間協議更新） |
| **sub_03** | `sub_03_build_git_decoupling` | Full Track | `Completed` | `build/` 建置產物 Git 追蹤解耦與空間協議更名為 `.build/`（含協議重構、.gitignore 配置、工具鏈對齊、空間協議更新） |
| **sub_04** | `sub_04_pip_dependency_governance_and_optional_acceleration` | Full Track | `Pending` | YSCB 私有 Pip 相依性治理體系與可選加速架構（依據 [R02](file:///workspace/ys-codebase/plans/2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance/R02_pip_dependency_governance_and_optional_acceleration.md)，含私有 .venv 隔離、dev env IDE 增量投影、knowledge-db 雙軌加速外掛與原生平穩降級） |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1 (sub_01)**：完成全生態系安全熱更新與 JIT 變更感知自愈機制，全模組消除過期快取與手動 reload 負擔。
- [x] **里程碑 2 (sub_02)**：完成 `modules/` 運行端冷啟動再生與 Git 追蹤解耦，達成倉庫歷史瘦身與發布產物解耦。
- [x] **里程碑 3 (sub_03)**：完成 `build/` 建置產物 Git 追蹤解耦與 `.build/` 空間協議重構，徹底消除開發打包對 Git 歷史之冗餘污染。
- [ ] **里程碑 4 (sub_04)**：完成 YSCB 私有 Pip 相依性治理體系與可選硬體加速，實現 10x 效能躍升、IDE 智慧補全與 100% 原生安全降級。
- [ ] **里程碑 5 (收斂結案)**：全生態系全量單元測試 100% 通過，完成整體架構審查並收斂 Umbrella 主計畫。
