# 成果展示與結案報告 (Walkthrough)

> 功能名稱：版本相容性事後修正機制、釋出元數據與更新嚴重度治理 (sub_02)  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1138_release_binary_storage_optimization  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **`index.json["releases"]` 依賴覆寫優先級、`core` 版本相容過濾與 `mirror://` 離線快取 (`FR-01`)**：`AtomicEngine` 在解析候選版本時，優先採用 `index.json["releases"][<ver>]["dependencies"]` 覆寫 `.zip/manifest.json`，並在挑選最高版本與執行 `cmd_update` 前先過濾出與當前已安裝 `core` 版本相容之候選版本；`act_solve_deps` 新增對 `dep_name == "core"` 之相容校驗（含 `.build` 後綴正規化）；每次讀取或下載 `index.json` 皆同步快取至 `module.mirror://<mod>/index.json`，並於 `_reload_materialize_single_module` 覆寫解壓後之 `manifest.json`，確保離線 `reload` 與 `rollback` 100% 冪等保留事後依賴修補。
  2. **`dev index-patch` 輕量事後修補 CLI 與 `Checker._check_manifest` Schema 校驗 (`FR-02`)**：新增 `python yscb.py dev index-patch <module> --ver=<ver> [--dep="..."] [--status=active|pruned] [--type=...] [--urgency=...] [--summary="..."]`（支援 `;` 分號分隔與重複 `--dep`），免重壓 `.zip` 原地修補歷史版本之相容性範圍、狀態與嚴重度；`Checker._check_manifest` 新增對選填 `"release"` 欄位之型別與非空字串校驗。
  3. **雙軌釋出元數據 (`type`/`urgency`/`summary`) 寫入與歷史修補保護 (`FR-03`)**：`dev release` 與 `dev release-git` 支援選填 `--type`、`--urgency`、`--summary` 雙軌寫入 `source/<mod>/manifest.json["release"]` 與 `release/<mod>/index.json["releases"][<ver>]`；`Builder._update_release_index` 嚴格保留歷史版本已事後修補之 `dependencies` 與元數據。
  4. **向前相容元數據解析、跨版本（含 `pruned`）聚合與 `[CRITICAL UPDATE]` 告警 (`FR-04`)**：`UpdateChecker` 對未知 `type`/`urgency` 向前相容降級，過濾同主版本且與已安裝 `core` 相容之最高可用版本，並掃描 `(cur_ver, latest_ver]` 區間內所有版本（含已標為 `pruned` 之中間版本）聚合最高嚴重度，對 `critical` 更新渲染雙線 `[!] [CRITICAL UPDATE]` 警告橫幅。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/engine.py` | Modify | 實作 `index.json["releases"]` 依賴覆寫優先級、候選版本相容過濾、`act_solve_deps` 對 `core` 依賴校驗、`module.mirror://<mod>/index.json` 快取與 `_reload_materialize_single_module` 離線覆寫 |
| `ys_codebase/source/core/core/installer.py` | Modify | `_discover_available_versions_for_module` 過濾與當前環境相容之候選版本，且 `cmd_update` 無論是否升級皆呼叫 `UpdateChecker().invalidate_cache` |
| `ys_codebase/source/core/core/update_checker.py` | Modify | 實作 `normalize_release_metadata` 向前相容解析、同主版本與 `core` 相容過濾、`(cur_ver, latest_ver]` 跨版本（含 `pruned`）嚴重度聚合與 `[CRITICAL UPDATE]` 橫幅渲染 |
| `ys_codebase/source/core/core/commands/resolver.py` | Modify | `OptionResolver.resolve` 支援重複傳入 `--dep` 時以 `;` 串接保留所有項目 |
| `ys_codebase/source/dev/dev/builder.py` | Modify | `_update_release_index` 提取 `manifest.json["release"]` 寫入 `releases[<ver>]` 並保護既有版本已事後修補之 `dependencies` 與元數據 |
| `ys_codebase/source/dev/dev/releaser.py` | Modify | 新增 `patch_release_index` 與 `_apply_release_meta_to_source_manifest`，於 `release_module` / `release_git` 支援 `release_meta` 雙軌寫入 |
| `ys_codebase/source/dev/dev/checker.py` | Modify | `_check_manifest` 新增對選填 `"release"` 欄位 (`type`, `urgency`, `summary`) 之校驗 |
| `ys_codebase/source/dev/scripts/cli.py` | Modify | `_normalize_bags` 補齊新選項與 `--dep` 串接；新增 `index_patch` 命令；為 `release` 與 `release_git` 支援釋出元數據選項 |
| `ys_codebase/source/dev/contributes/core.json` | Modify | 註冊 `dev index-patch` 命令契約並擴充 `dev release` / `dev release-git` 選項 |
| `ys_codebase/source/dev/contributes/_manifest.md` | Modify | 同步更新 `dev` CLI 貢獻清冊 |
| `ys_codebase/config/agents-workflow/skills/bump-revision/SKILL.md` | Modify | 擴充 `/bump-revision` 技能支援選填 `--type`、`--urgency`、`--summary` 參數 |
| `ys_codebase/source/core/tests/test_update_checker.py` | Modify | 新增跨版本 `pruned` 之 `critical` 告警聚合、未知 `type`/`urgency` 向前相容與不相容 `core` 版本過濾測試 |
| `ys_codebase/source/core/tests/test_distribution_lifecycle.py` | Modify | 新增 `index.json["releases"]` 依賴覆寫、`act_solve_deps` 對 `core` 依賴攔截與 `mirror://` 離線 `reload` 冪等覆寫測試 |
| `ys_codebase/source/dev/tests/test_release_pipeline.py` | Modify | 新增雙軌 `release_meta` 寫入、`dev index-patch` 修補與歷史保留、以及 `Checker._check_manifest` `"release"` 欄位校驗測試 |
| `docs/dev/topics/release_governance.md` | Modify | 新增釋出元數據、事後相容性修補 (`dev index-patch`) 與跨版本嚴重度治理專節 |
| `docs/dev/README.md` | Modify | 更新 `dev release`、`dev release-git` 與 `dev index-patch` 指令矩陣說明 |
| `docs/dev/user_guide.md` | Modify | 增補 `dev index-patch` 與釋出元數據旗標使用指南 |
| `docs/core/DESIGN_NOTES.md` | Modify | 登記 `[DN-15]` `index.json["releases"]` 依賴覆寫優先級、`core` 相容過濾與 `mirror://` 離線快取設計紀錄 |
| `docs/dev/DESIGN_NOTES.md` | Modify | 增補 `[DN-DEV-05]` 雙軌釋出元數據與事後修補保護設計紀錄 |
| `CHANGELOG.md` | Modify | 記錄 `sub_02` 變更摘要 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：`core` 模組 `213 / 213 (100.0%)` 通過，`dev` 模組 `82 / 82 (100.0%)` 通過，`dev check` 與 `contributes check --all` (15/15) 100% 通過，支柱三盲眼審計複審 `REVIEW_STATUS: PASSED`。
- **實機 UX / 人工驗證**：`UX-01` 已由開發者標記 `[跳過/免測]`。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已交付 | 同步記錄 `sub_02` 依賴事後修補、雙軌元數據與跨版本 `[CRITICAL UPDATE]` 告警 |
| **中觀 (Meso)** | `docs/dev/README.md`, `docs/dev/user_guide.md` | 已交付 | 完整補齊 `dev index-patch` 與 `dev release` 元數據選項說明 |
| **中觀 (Meso)** | `docs/dev/topics/release_governance.md` | 已交付 | 補齊雙軌元數據、事後修補與跨版本嚴重度聚合專節 |
| **中觀 (Meso)** | `docs/core/DESIGN_NOTES.md`, `docs/dev/DESIGN_NOTES.md` | 已交付 | 登記 `core` `[DN-15]` 與更新 `dev` `[DN-DEV-05]` 防坑邊界 |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已交付 | 嚴格維護 Docstring，零工單編號污染 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(core,dev): add post-release index-patch CLI, dual-track release metadata, and cross-version critical update alerts
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify sub_02_release_metadata_and_compat_governance` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

