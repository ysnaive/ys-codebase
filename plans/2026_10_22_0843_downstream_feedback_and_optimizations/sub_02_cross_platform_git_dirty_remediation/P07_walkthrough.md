# 成果展示與結案報告 (Walkthrough)

> 功能名稱：sub_02_cross_platform_git_dirty_remediation  
> 建立日期：2026-10-22  
> 所屬主計畫：2026_10_22_0843_downstream_feedback_and_optimizations  
> 狀態：Completed  
> 模型：Claude Opus 5.5 (Medium)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **`release_manifest.json` 移出 Git 追蹤區 (`FR-01`, `FR-02`, `[P05:DR-01]`)**：Project 軌物化清單改存 `cache://agents-workflow/project_release_manifest.json`，發布時自動遷移並刪除舊版 `storage://` 清單；不新增任何忽略規則。目錄型資產 SHA-1 先做 UTF-8 文字 CRLF→LF 正規化（二進位檔維持原始 bytes）。
  2. **`.vscode/settings.json` 跨平台恆定 (`FR-03`, `FR-04`)**：`extraPaths` 注入 POSIX 與 Windows 雙路徑；停止寫入 `python.defaultInterpreterPath`，以 `yscb_dir/.venv/` 實際根目錄前綴判定並清理舊託管值（保留使用者自訂與專案自有 `.venv` 直譯器，`EC-03`）；內容無異動時跳過寫盤 (`EC-04`)。
  3. **範疇外處置 (`[P05:DR-02]`)**：補齊前計畫 `2026_10_17_1133 sub_02` 未提交之工作流資產（對照其 FR-01~FR-08 全數恢復，新增 `FT-07`）；依開發者指示修正 `core` `test_ft_05` 過時之 `module.build.root://` 斷言。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/vfs/os_backend.py` | Modify | `write_text` 與 `atomic_write` 文字模式固定 `newline="\n"` (`REV-01`) |
| `ys_codebase/source/core/core/pip_manager.py` | Modify | 新增 `get_cross_platform_site_packages_dirs()` |
| `ys_codebase/source/core/core/ide_projector.py` | Modify | 雙平台 `extraPaths`、停寫直譯器並清理託管值（`_is_yscb_managed_interpreter`）、Zero-Touch、JSONC 解析失敗防覆寫 (`REV-02`)；`revert_vscode_settings` 同步 |
| `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` | Modify | 清單遷至 `cache://`、舊 `storage://` 清單遷移刪除、CRLF→LF 正規化；移除誤導性 `*_STORAGE_URI` 別名並更新 docstring |
| `ys_codebase/source/core/tests/test_ide_projector_cross_platform.py` | New | `FT-03`~`FT-07`、`FT-05b`、`FT-06b`、`REV-01`、`REV-02` |
| `ys_codebase/source/agents-workflow/tests/test_publisher_cross_platform.py` | New | `FT-01`、`FT-02`、`ET-01`、`ET-02` |
| `ys_codebase/source/agents-workflow/tests/test_manifest_placement.py`、`test_publisher.py` | Modify | 改用 `PROJECT_MANIFEST_CACHE_URI` 並更新描述（需求變更） |
| `ys_codebase/source/core/tests/test_build_git_decoupling.py` | Modify | `test_ft_05` 改斷言 `module.build://` 存在、`module.build.root://` 不得出現 |
| `ys_codebase/source/agents-workflow/assets/`（22 檔） | Modify | 補齊前計畫遺失之技能 / SOP / 模板變更（詳見 `P05` 偏差表範疇外列） |
| `ys_codebase/source/agents-workflow/tests/test_plans_model_record.py` | Modify | 新增 `FT-07` 覆蓋補回資產 |
| `docs/core/DESIGN_NOTES.md`、`docs/core/README.md` | Modify | `[DN-09]` 雙路徑、直譯器解耦與託管判定邊界、Zero-Touch |
| `docs/agents-workflow/DESIGN_NOTES.md`、`docs/agents-workflow/README.md` | Modify | 新增 `[DN-AW-09]`；更新清單位置描述 |
| `CHANGELOG.md` | Modify | 追加 `sub_02` 結案摘要 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：`core` 204/204、`agents-workflow` 108/108（100%）；`dev check core` / `dev check agents-workflow` PASSED；`plan verify --all` 3/3 PASSED；已完成 `core@build` 與 `agents-workflow@build` 自部署與舊清單實體遷移驗證。
- **實機 UX / 人工驗證**：UX-01 `[跳過/免測]`（開發者指示：目前無跨平台實機環境）。
- **已知殘留風險**：原列之 VFS `write_text` 換行符與 JSONC 覆寫風險已於 `revision_log.md` (`REV-01`, `REV-02`) 根治；僅餘兩平台 Python 次版本不同時 `.venv/py{ver}` 路徑自然不同（屬微環境跨版本隔離設計）。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | CHANGELOG.md | 已更新 | `sub_02` 結案摘要 |
| **中觀 (Meso)** | `docs/core/README.md`、`docs/agents-workflow/README.md` | 已更新 | IDE 投射行為、清單位置 |
| **中觀 (Meso)** | `docs/core/vfs.md` | 已更新 | `atomic_write` / `write_text` 跨平台 LF 換行保證 (`REV-01`) |
| **中觀 (Meso)** | `docs/core/DESIGN_NOTES.md`、`docs/agents-workflow/DESIGN_NOTES.md` | 已更新 | `[DN-09]` 託管判定邊界、`[DN-AW-09]` 不以忽略規則掩蓋 |
| **微觀 (Micro)** | `ide_projector.py`、`pip_manager.py`、`publisher.py` Docstrings | 已更新 | 新增方法契約與 Why 註解 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack（已移除誤導性別名與越權之虛構文檔）。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言（測試變更均屬需求變更，已登記於 `P05`）。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
fix(core,agents-workflow): stop cross-platform git working tree pollution and restore lost workflow assets

- agents-workflow: move project release manifest to cache:// and auto-migrate/remove legacy storage:// manifest; normalize CRLF->LF before asset SHA-1
- core: inject dual POSIX/Windows site-packages into VS Code extraPaths, stop writing defaultInterpreterPath (prefix-based managed detection), zero-touch write
- agents-workflow: restore skill/SOP/template changes lost from 2026_10_17_1133 sub_02 and add FT-07 coverage
- core: fix stale module.build.root:// assertion in test_ft_05
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed。

