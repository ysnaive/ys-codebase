# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：Dev 模組發布強制覆蓋模式 (Dev Release Force Override Support)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 核心能力演進與完善 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  > "dev release，在剛進行打包就馬上發現有小瑕疵時使用，例如發布訊息沒改好之類的"
- **核心目標**：
  1. 為 `dev release`、`dev release-check` 與 `dev release-git` 指令擴充 `--force` / `-f` 參數支援。
  2. 在本地開發剛打包發布、立即發現文檔、註解或發布訊息等小瑕疵時，允許透過 `--force` 原地覆蓋同版本發布產物（`<ver>.zip`）並同步更新 `release/<mod>/index.json`，避免被迫 bump 版本號造成版本號無意義膨脹。
  3. 保留基礎安全防護：預設模式（無 `--force`）依然維持嚴格的 3-Gate 不可變性與單調遞增檢查；`--force` 僅放行「覆蓋同版本（等於當前最高 Revision）」之情境，依然防禦小於歷史舊版本的回退行為。
- **邊界排除 (Explicitly Excluded)**：
  1. **不影響預設 3-Gate 守門行為**：無 `--force` 時所有發布行為與守門規則 100% 保持原有嚴格檢查不變。
  2. **不支援版本號倒退**：即使傳入 `--force`，若版本號小於歷史已存在的更低版本（非當前最高版本），依然予以阻斷，防止破壞版本歷史。
  3. **不涉及遠端 Git 操作**：`dev release-git` 依舊維持嚴格 Local-Only 紀律，禁止向遠端 push。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] (Gate 2/3 在 `--force` 下的判定放行邏輯)**：
  - **議題**：當使用者啟用 `--force` 時，Gate 2（不可變性）與 Gate 3（單調性）應如何判定？
  - **結論**：
    1. **Gate 2 (Immutability)**：在 `force=True` 時，若 `release/<mod>/<target_ver>.zip` 已存在，不拋出 `ReleaseVersionExistsError`，而是記錄 warning 並允許物理覆蓋該 zip 產物。
    2. **Gate 3 (Monotonicity)**：在 `force=True` 時，若待發布版本 `target_ver` 與在庫最高 revision 相同（`target == highest`），判定為原地修訂並予於放行；若 `target < highest` 則依然判定為回退錯誤（阻斷）。
- **[P00:DR-02] (CLI 參數與傳遞鏈貫穿)**：
  - **議題**：哪些 CLI 入口需要支援 `--force` 參數？
  - **結論**：
    - `dev release <mod> [--force|-f]`
    - `dev release-check <mod> [--force|-f]`
    - `dev release-git <mod> "<msg>" [--force|-f]`
    - 函式簽名：`Releaser.release_check(module_name: str, force: bool = False)`、`Releaser.release_module(module_name: str, force: bool = False)`、`Releaser.release_all(force: bool = False)`。
- **[P00:DR-03] (`dev release-git` 智慧感應已發布版本自動略過打包)**：
  - **議題**：當目標版本已由前置步驟手動 `dev release` 產出時，`dev release-git` 應如何處置？
  - **結論**：
    - 在 `release_git()` 流水線中，先檢查 `release/<mod>/<target_ver>.zip` 是否在庫：
      1. **情況 A（尚未發布）**：依序執行 `release_check` ➔ `release_module` ➔ `git commit & tag`。
      2. **情況 B（已發布且無 `--force`）**：印出提示 `[dev:release-git] Version '<ver>' is already released. Skipping packaging step.`，安全略過 release 打包步驟，直接推進執行後續的 Local Git Commit & Tag。
      3. **情況 C（已發布且傳入 `--force`）**：強制重新調用 `release_module(force=True)` 物理覆蓋 zip 產物，再執行 Local Git Commit & Tag。

---

## 3. 開放議題與確認紀錄

- [x] 是否已明確界定 `--force` 僅放行同版本覆蓋，不放行歷史版本回退？（已於 [P00:DR-01] 定義）
- [x] 是否已明確界定 `release-git` 對已發布版本的智慧檢測與略過行為？（已於 [P00:DR-03] 定義）
- [ ] 請問更新後的 P00 需求陳述與邊界定義是否確認無誤，可正式確認結束 Phase 0 並指示推進至 FT-1 (Fast Track 規劃)？
