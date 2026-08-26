# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：Dev 模組發布與驗證工具鏈重構 (Dev Release & Verification Toolchain Refactor)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 模組功能打磨 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. `build` 移除 `--clean` 選項，一律自動先清理目標資料夾。
  2. `release` 改為僅純淨打包，功能完全對標 `build`，無任何附加功能 (bump opts 之類的皆移除，不再為流水線)。
  3. `test` 改為流水線指令，會自動先跑 `build`，除非添加選項 `--no-build`。
  4. 新增 `bump-[major|minor|patch|revision] <module>`：獨立對模組版本號進行單向遞增。
  5. 新增 `release-check <module>`：檢查模組是否已準備就緒進行新版本發行（不支援 `--all`）。
  6. 新增 `release-git <module> <commit msg>`：工具鏈依序執行 `test <module>` ➔ `release-check <module>` ➔ 本地 `git commit` 並打上模組版本號 Tag（🚨 嚴禁連續 push 到 remote，僅完成本地端操作即可）。
- **核心目標**：
  - 徹底簡化並正規化 `dev` 工具鏈指令模型，達成指令職責清晰、參數極簡、行為一致。
  - `build` 與 `release` 形成鏡像對標（一個為完整開發包，一個為純淨發布包），均支援 `[module_name | --all]` 並自動先清空舊產物。
  - `test` 升級為標準驗證流水線，預設自動構建最新產物再進沙盒測試。
  - 提供獨立解耦的版本遞增 (`bump-*`)、發布前預檢 (`release-check`) 與本地 Git 提交流水線 (`release-git`)。
- **邊界排除 (Explicitly Excluded)**：
  - `release-git` 嚴禁自動向遠端倉庫執行 `git push`，所有 Git 提交與 Tag 嚴格限制在本地端完成。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

> 專題調研報告：[R01_dev_toolchain_refactor.md](./R01_dev_toolchain_refactor.md), [R02_release_toolchain_support.md](./R02_release_toolchain_support.md)

- **[P00:DR-01] `dev build` 自動清空目標資料夾**：
  - 廢除 `--clean` 選項。每次執行 `dev build [mod | --all]` 時，打包前一律自動清空目標模組專屬的 `build/<module>/` 目錄，確保零歷史產物殘留。
- **[P00:DR-02] `dev release` 純粹化、對標 `build` 與多版本時序滑動窗口治理**：
  - 移除 `bump_type`（major/minor/patch/revision）、`--yes`、`--dry-run`、`--tag`、`--no-test` 等所有流水線旗標與 Git 操作。
  - 語法完全對標 `build`：`python yscb.py dev release [module_name | --all]`。
  - **發布產物時序滑動窗口與收斂治理演算法**：
    - **同三元組時序滑動窗口 (至多 3 份 Revision)**：同一個 `major.minor.patch`（`X.Y.Z`）依時序/SemVer 由大到小排序，最多同時保留 3 個最新 Revision（`X.Y.Z.W`, `X.Y.Z.W-1`, `X.Y.Z.W-2`），發布第 4 個 Revision 時自動淘汰刪除更早的舊 Revision zip。
    - **跨三元組升級舊版收斂 (僅留 1 份 Revision)**：當 `patch` 或以上 level 產生遞增時（版本變為 `X.Y.Z+1.W` 或更高），所有過往舊三元組（`X.Y.Z`）的延遲保留版本將被清理，舊版僅留下該三元組最後且最高的 1 個 Revision（`X.Y.Z.W_max`）。
- **[P00:DR-03] `dev test` 流水線化與 `--no-build`**：
  - 語法：`python yscb.py dev test [module_name | --all] [options]`。
  - 核心行為：預設先自動調用 `dev build` 確保產出最新 build 產物，再建立沙盒執行測試。
  - 提供 `--no-build` 選項，供需要直接使用現有 build 產物進行快速測試之場景。
- **[P00:DR-04] 發布索引與安裝版本匹配機制確認**：
  - **索引實體同步 (Index SSOT)**：`release/<mod>/index.json` 的 `versions` 清單 100% 以磁碟上真實存在的 `.zip` 檔案為準進行收集與排序，已被淘汰/刪除的舊 revision 100% 自索引中排除。
  - **四元尾號不敏感確認 (屬實)**：經源碼核實（`core.semver:match_constraint`），三段式版本依賴（如 `1.0.0`、`>=1.0.0`）僅比對 `(major, minor, patch)` 三元組，對第四段 revision 尾號不敏感，`find_best_version` 會自動選出該三元組下的最新 revision。
- **[P00:DR-05] 發布不可變性與防回退校驗閘門 (Release Immutability & Monotonicity Guardrail)**：
  - **不可重複發布 (Immutability)**：待發布版本號 $V_{\text{target}}$ 嚴格不可與 `release/<mod>/` 中已存在的完整四元版本相同（若已存在同四元組 zip 或 index 記錄，拋出 `ReleaseVersionExistsError` 阻斷發布）。
  - **版本號不可回退 (Monotonicity)**：待發布版本號 $V_{\text{target}}$ 必須嚴格大於該模組發布庫中同三元組的最高已有 revision 版本（$V_{\text{target}} > V_{\text{highest\_in\_triplet}}$），且不可小於已發布歷史版本，嚴禁版本倒退。
- **[P00:DR-06] 發布工具鏈分層架構與拓撲批次發布 (Topological Release)**：
  - `dev.releaser.Releaser` 重構為輕量級發布調度器，封裝 Gate 1（靜態規格）、Gate 2（不可重複）、Gate 3（不可回退）校驗。
  - `dev release --all` 支援自動解析 `dependencies` 依賴圖，依拓撲排序順序發布（如 `core` ➔ `dev` ➔ `agents-workflow`）。
- **[P00:DR-07] 獨立版本遞增指令 (`dev bump-*`)**：
  - 指令：`dev bump-major <mod>`、`dev bump-minor <mod>`、`dev bump-patch <mod>`、`dev bump-revision <mod>`。
  - 行為：直接讀取 `source/<mod>/manifest.json`，對指定版本段遞增並寫回，輸出新舊版本對比。
- **[P00:DR-08] 獨立發布就緒檢查指令 (`dev release-check`)**：
  - 指令：`python yscb.py dev release-check <module>`（僅支援單一模組，不支援 `--all`）。
  - 行為：依序執行 Gate 1 (靜態規格)、Gate 2 (不可重複)、Gate 3 (不可倒退) 校驗，若出錯輸出詳細報告並以 exit 1 阻斷。
- **[P00:DR-09] 發布與版本控制工具鏈 (`dev release-git`)**：
  - 指令：`python yscb.py dev release-git <module> <commit msg>`。
  - 核心行為：依序執行以下 4 步安全流水線：
    1. `test <module>`（沙盒跑測，失敗即中斷流程）
    2. `release-check <module>`（發布預檢，失敗即中斷流程）
    3. `release <module>`（純淨發布打包，產出 zip 與更新 index.json，失敗即中斷流程）
    4. 本地 `git commit -m "<commit msg>"` 並打上模組版本號 Tag（如 `<module>/v<version>`）
  - 🚨 **防呆鐵律**：嚴禁自動連續 `git push` 到 remote，僅完成本地端操作即可。

---

## 3. 開放議題與確認紀錄

- [x] **指令語法對齊**：`dev build` 與 `dev release` 統一採用 `[module_name | --all]` 簽名格式。
- [x] **流水線順序**：`dev test` ➔ `dev build (預設)` ➔ `SandboxProvisioner` ➔ `op-test`。
- [x] **多版本治理與索引**：不同 X.Y.Z 歷史保留、同 X.Y.Z 淘汰舊 revision，索引以實體檔案為 SSOT 排除舊 revision。
- [x] **安裝匹配機制驗證**：確認三段式匹配對四元尾號不敏感，自動取最新 revision。
- [x] **版本管理工具**：新增 `bump-major/minor/patch/revision <module>`。
- [x] **發布就緒檢查**：新增 `release-check <module>`（僅單一模組）。
- [x] **版本控制流水線**：新增 `release-git <module> <commit msg>`（測試 ➔ 檢查 ➔ 本地 Commit & Tag，嚴禁 push）。
