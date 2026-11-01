# 成果展示與結案報告 (Walkthrough)

> 功能名稱：發布產物二進位解耦、本地同版本自給自足與孤兒分支分發管線 (sub_01)  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1138_release_binary_storage_optimization  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **通用發布事件廣播 (`on_module_released`) 與 `index.json` 雙軌版本帳本 SSOT**：於 `dev` 模組註冊並廣播 `on_module_released` 標準事件；重構 `Builder._update_release_index` 與 `Releaser._collect_all_known_released_versions`，使 `index.json` 同時維護活躍可下載視窗 `versions` 與永久歷史帳本 `releases[<ver>]`（含 `"status": "active" | "pruned"`），確保本機無 `.zip` 時 Gate 2/3 與 3-Revision 滑動視窗仍 100% 精準運作。
  2. **本地嚴格同版 (`source_version == target_version`) 動態打包自給自足**：於 `yscb.py`、`core/engine.py` 與 `core/installer.py` 實作無 `.zip` 時比對本地 `source/<mod>/manifest.json` 嚴格同版即時打包至 `.mirror/` 並解壓（排除 `tests/` 與 `.yscbignore`，拒絕版本不符混裝）。
  3. **`pruned` 版本同三元組 (`X.Y.Z.*`) 自動平滑遞補與組態同步**：當請求之舊版已被滑動視窗淘汰且本地無 `.mirror/` 時，自動從 `index.json["versions"]` 解析同三元組最高可用 `active` 版本還原並同步更新 `yscb.config.json`。
  4. **遠端 `releases` 孤兒分支 Provider 對接與雙層 URL 無感遷移**：將預設 Provider URL 切換至 `releases` 分支、支援舊版 `main` URL 自動遷移，並建立 `.github/workflows/release-publish.yml` 單層孤兒分支自動同步工作流。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `yscb.py` | Modify | 更新 `DEFAULT_PROVIDER_URL` 為 `releases` 分支；新增舊官方 `main` URL 無感遷移、純標準庫同版本 `source/<mod>` 動態打包器，以及 `pruned` 同三元組自動平滑遞補 |
| `ys_codebase/source/core/core/engine.py` | Modify | 新增本地同版本 `source/<mod>` 動態打包 fallback、`act_reload` 同三元組 `pruned` 遞補、舊官方 URL 無感遷移，以及 `_find_manifest_in_local_provider` 讀取 `index.json["releases"]` 依賴元數據 |
| `ys_codebase/source/core/core/installer.py` | Modify | 更新 `cmd_restore` 預設 URL、`_restore_module_package` 本地同版本 `source/<mod>` 動態打包與 `pruned` 同三元組自動遞補 |
| `ys_codebase/source/core/core/update_checker.py` | Modify | 讀取配置探測更新時支援舊官方 `main` Provider URL 無感遷移至 `releases` URL |
| `ys_codebase/source/dev/dev/builder.py` | Modify | `_update_release_index` 支援無歷史 `.zip` 下基於 `index.json` 計算 3-Revision 滑動視窗並維護 `releases[<ver>]` (`status: "active"\|"pruned"`, `dependencies`) |
| `ys_codebase/source/dev/dev/releaser.py` | Modify | `release_check` (Gate 2/3) 與 `release_git` 改以 `index.json` (`versions` $\cup$ `releases`) $\cup$ 本地 `.zip` 為準；`release_module` 廣播 `on_module_released` 事件 |
| `ys_codebase/source/dev/dev/checker.py` | Modify | `_check_sandbox_hooks` 納入 `on_module_released` / `module_released` 合法 hook 校驗 |
| `ys_codebase/source/dev/contributes/core.json` | Modify | 於 `events` 區段宣告 `on_module_released` 事件 |
| `ys_codebase/source/dev/contributes/_manifest.md` | Modify | 同步記錄 `on_module_released` 事件契約 |
| `.github/workflows/release-publish.yml` | New | 當 `main` 推送變更時，自動打包並以單一無父節點孤兒 Commit 同步至 `origin/releases` 分支 |
| `ys_codebase/source/core/tests/test_distribution_lifecycle.py` | Modify | 更新預設 Provider URL 斷言，並新增本地同版本 `source/` 動態打包、`pruned` 同三元組遞補、跨三元組拒絕與舊 URL 遷移單元測試 |
| `ys_codebase/source/dev/tests/test_builder.py` | Modify | 新增無歷史 `.zip` 環境下 `index.json` 滑動視窗與 `releases` 帳本保留測試 |
| `ys_codebase/source/dev/tests/test_release_pipeline.py` | Modify | 新增無歷史 `.zip` 環境下 `release_check` Gate 2/3 守門與 `on_module_released` 事件廣播測試 |
| `docs/core/DESIGN_NOTES.md` | Modify | 登記 `[DN-14]` 本地同版本 `source/` 自給自足打包與 `pruned` 同三元組平滑遞補設計紀錄 |
| `docs/dev/DESIGN_NOTES.md` | Modify | 登記 `[DN-DEV-05]` `on_module_released` 事件廣播與 `index.json` 雙軌帳本 SSOT 設計紀錄 |
| `docs/dev/README.md` | Modify | 補充 `dev release` 更新雙軌帳本與廣播 `on_module_released` 說明 |
| `CHANGELOG.md` | Modify | 記錄 `sub_01` 變更摘要 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：`core` 模組 `210 / 210 (100.0%)` 通過，`dev` 模組 `81 / 81 (100.0%)` 通過，`dev check` 與 `contributes check --all` (15/15) 100% 通過，支柱三盲眼審計複審 `REVIEW_STATUS: PASSED`。
- **實機 UX / 人工驗證**：`UX-01` 已由開發者標記 `[跳過/免測]`。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已交付 | 同步記錄 `sub_01` 雙軌帳本、同版動態打包、`pruned` 遞補與孤兒分支 CI |
| **中觀 (Meso)** | `docs/dev/README.md` | 已交付 | 更新 `dev release` 指令矩陣職責說明 |
| **中觀 (Meso)** | `docs/dev/topics/release_governance.md` | 免更（待 `sub_02` 一併更新完整 `releases` Schema） | 專題手冊將於 `sub_02` 補齊 `status`/`dependencies`/`release` 完整欄位後統一更新 |
| **中觀 (Meso)** | `docs/core/DESIGN_NOTES.md`, `docs/dev/DESIGN_NOTES.md` | 已交付 | 登記 `core` `[DN-14]` 與 `dev` `[DN-DEV-05]` 防坑邊界 |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已交付 | 嚴格維護 Docstring，零工單編號污染 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(core,dev): decouple release binaries with index.json ledger SSOT and exact-version source packaging
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify sub_01_release_binary_and_git_history` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

