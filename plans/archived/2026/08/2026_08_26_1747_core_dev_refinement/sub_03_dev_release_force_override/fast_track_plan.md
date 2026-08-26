# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：Dev 模組發布強制覆蓋模式 (Dev Release Force Override Support)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 核心能力演進與完善 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Draft  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.1  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與架構決策
- **需求目標**：
  1. 為 `dev release`、`dev release-check` 與 `dev release-git` 擴充 `--force` / `-f` 旗標支援。
  2. 剛打包發布後發現文檔、註解等小瑕疵時，允許透過 `--force` 物理覆蓋同名 `<ver>.zip` 產物並同步更新 `release/<mod>/index.json`，避免被迫 bump 版本號。
  3. `dev release-git` 具備智慧檢測：
     - 若目標版本**尚未發布**：正常執行 `release_check` ➔ `release_module` ➔ `git commit & tag`。
     - 若目標版本**已發布且無 `--force`**：自動略過 `release_module` 打包動作，直接推進執行後續的 Local Git Commit & Tag。
     - 若目標版本**已發布且傳入 `--force`**：重新調用 `release_module(force=True)` 覆蓋打包後再打 Commit/Tag。
- **架構決策紀錄**：
  - **`[FT-01:DR-01]` (3-Gate 在 force 模式下的放行規則)**：
    - Gate 1 (Manifest 合規)：始終嚴格執行。
    - Gate 2 (Immutability 不可變性)：`force=True` 時若 zip 已存在，記錄 warning 並放行覆蓋。
    - Gate 3 (Monotonicity 單調性)：`force=True` 時若待發布版本等於在庫最高版本（`target == highest`），允許原地覆蓋；若 `target < highest` 依然嚴格阻斷（防歷史回退）。
  - **`[FT-01:DR-02]` (受影響檔案清單 $\le 2$)**：
    - `source/dev/dev/releaser.py`：擴充 `release_check`、`release_module`、`release_all`、`release_git` 之 `force` 支援與已發布略過判斷。
    - `source/dev/scripts/cli.py`：擴充 `cmd_release`、`cmd_release_check`、`cmd_release_git` 之 `--force` / `-f` 參數解析與幫助訊息。

---

### 1.2 實作任務與測試規劃

#### 📋 實作任務清單
- [x] **TASK-01**：修改 `source/dev/dev/releaser.py`：
  - `release_check(module_name, force=False)`：支援 `force=True` 時放行 Gate 2 衝突與 Gate 3 同版本判定。
  - `release_module(module_name, force=False)`：傳遞 `force` 至 `release_check` 並執行打包覆蓋。
  - `release_all(force=False)`：批次發布支援 `force`。
  - `release_git(module_name, message, force=False)`：加入已發布自動感應，未發布則打包，已發布無 force 略過打包，有 force 強制覆蓋打包。
- [x] **TASK-02**：修改 `source/dev/scripts/cli.py`：
  - 在 `cmd_release`、`cmd_release_check`、`cmd_release_git` 解析 `--force` / `-f`。
  - 更新 CLI `--help` 說明文字。
- [x] **TASK-03**：在 `source/dev/tests/test_release_pipeline.py` 中擴充單元測試，覆蓋 `--force` 覆蓋發布、歷史回退阻斷與 `release-git` 智慧略過行為。

#### 🧪 測試案例規劃與執行紀錄 (Test Cases & Execution)
| 測試編號 | 測試類型 | 驗證目標與斷言 | 執行結果 | 驗證時間 |
| :--- | :--- | :--- | :---: | :---: |
| **FT-01** | 單元測試 | 驗證 `dev release <mod> --force` 在同版本已存在時成功物理覆蓋 zip 與更新 index.json | `Passed` | 2026-08-26 22:15 |
| **FT-02** | 單元測試 | 驗證 `dev release-git <mod> "<msg>"` 在版本已發布且無 force 時自動略過 release 打包直接執行 git commit/tag | `Passed` | 2026-08-26 22:15 |
| **FT-03** | 單元測試 | 驗證 `dev release-git <mod> "<msg>" --force` 在版本已發布時重新打包覆蓋並執行 git commit/tag | `Passed` | 2026-08-26 22:15 |
| **ET-01** | 邊界測試 | 驗證 `dev release <mod>` 在無 `--force` 且同版本已存在時依然嚴格拋出 `ReleaseVersionExistsError` 阻斷 | `Passed` | 2026-08-26 22:15 |
| **ET-02** | 邊界測試 | 驗證 `dev release <mod> --force` 在版本小於歷史舊版本（`target < highest`）時依然拋出 `VersionRollbackError` 阻斷 | `Passed` | 2026-08-26 22:15 |
| **RT-01** | 回歸測試 | 驗證全模組沙盒端到端回歸測試 100% 通過（113/113 Passed） | `Passed` | 2026-08-26 22:16 |
| **UX-01** | 手動驗證 | 驗證 `python yscb.py dev release --help` 輸出清晰完整 | `Passed` | 2026-08-26 22:16 |

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  1. `Releaser.release_check` 完整支援 `force=True` 放行 Gate 2 覆蓋與 Gate 3 原地同版本覆蓋。
  2. `Releaser.release_git` 實作智慧感應，已發布且無 `--force` 自動安全略過打包，傳入 `--force` 重新打包覆蓋並對 tag 追加 `-f`。
  3. `scripts/cli.py` 全面解析 `--force` / `-f` 並更新說明。
- **實機測試日誌**：
  - `dev test dev`：29/29 Passed (31.401s)。
  - `dev test --all`：113/113 Passed (44.703s)（`agents-workflow` 20/20, `core` 64/64, `dev` 29/29）。

---

## 3. 結案與交付確認 (FT-3 Closure & Walkthrough)

- **結案狀態**：`Completed`
- **知識庫交付**：更新 `docs/dev/user_guide.md` 與 `docs/dev/README.md`。
- **全域變更日誌**：追加 `CHANGELOG.md` 發布紀錄。
