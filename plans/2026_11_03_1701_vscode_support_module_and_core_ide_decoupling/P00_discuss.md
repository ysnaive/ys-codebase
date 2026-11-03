# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：2026_11_03_1701_vscode_support_module_and_core_ide_decoupling  
> 建立日期：2026-11-03  
> 所屬主計畫：N/A (Root Plan)  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：將原本暫存於 `core/ide_projector.py` 的 VS Code 耦合邏輯 100% 剝離出 `core`，獨立為選配官方模組 `module:vscode-support`，同時修補 `[TODO-18]` `core/validator.py` 預設值字面解析不支援浮點數與負數之缺陷；以單一 Full Track 推進，並聚焦於目前實際需要之核心功能（`settings.json` 直接綁定 `json.schemas` 免手動啟用外掛、`current-site-packages` 穩定連結、自動建立 `.vscode/`、以及 `json_schemas` 單檔級 Schema 編譯），其餘進階擴充點（`snippets` / `grammars` / `problem_matchers` / `configuration_defaults`）轉入 `/todo`（`[TODO-19]`）。
- **核心目標**：
  1. **`core` 零 IDE 假設（Zero IDE Assumption）與 `[TODO-18]` 修復**：自 `core` 徹底拔除 `IdeProjector` 及所有 `.vscode` 相關程式碼與匯出；於 `core/installer.py:sync_pip_dependencies()` 結尾新增 IDE 中立之 `on_env_synced` 事件廣播；修正 `ContributesValidator._parse_default_literal` 以支援正負整數與浮點數預設值。
  2. **建立 `module:vscode-support` 承接生命週期投影與完整自我拆卸**：透過 `scripts/hook.core.py` 響應 `on_reload` / `on_env_synced` / `on_installed` / `on_update`：
     - 若 `project://.vscode/` 不存在則**自動建立 `.vscode/` 目錄**。
     - 於 `yscb.venv://` 建立或更新無版本號之穩定目錄連結 `./ys_codebase/.venv/current-site-packages`（POSIX 使用 `os.symlink`，Windows 使用免管理員權限之 `mklink /J` Directory Junction，若檔案系統不支援則自動 fallback 至實際跨平台路徑），使 `.vscode/settings.json` 之 `python.analysis.extraPaths` 恆定指向 `["./ys_codebase/.venv/current-site-packages"]`，**保證 `settings.json` 狀態不隨本機外部 Python 環境版本變動**。
     - 於 `.vscode/settings.json` 寫入 `json.schemas` 單檔級綁定（並納管於 `_yscb_managed["jsonSchemas"]`），**免除手動安裝外掛與 Reload Window 即刻生效**。
     - 於 `on_remove`（或 `vscode-support revert`）依據 `_yscb_managed` 100% 乾淨還原 `.vscode/settings.json`（含 `extraPaths`、`excludes`、`analysisExclude`、`json.schemas`）並清除生成的 Schema 目錄與穩定連結。
  3. **單檔級精準 JSON Schema 編譯（`SchemaCompiler`）与 `json_schemas` 擴充點**：重用 `core/validator.py` 之 `parse_type_signature` 與 `module.source://` / `module.mirror://` 內之 `configurable/` 原始模板，為每個已安裝模組動態編譯 `contributes/<mod>.schema.json`、`config/<mod>.schema.json` 與元 Schema（`format-meta.schema.json`、`manifest.schema.json`），輸出至受內建 `.gitignore` (`*`) 自我忽略保護的 `.vscode/schemas/`（或 `.vscode/extensions/yscb-vscode-support/schemas/`）目錄。
- **既有組件復用與查重 (Reuse Discovery)**：
  - **設定檔軟合併**：100% 遷移並升級既有 `ys_codebase/source/core/core/ide_projector.py`（`IdeProjector` $\to$ `SettingsProjector`），保留 `_yscb_managed` 差集追蹤、Zero-Touch 寫入守衛與非標準 JSON（含註解）防破壞安全略過機制。
  - **Schema 型別解析**：100% 復用 `core.validator.ContributesValidator.parse_type_signature`。
  - **組態模板讀取**：優先讀取 `module.source://<mod>/configurable/`，不存在時自 `module.mirror://<mod>/<ver>.zip` 記憶體讀取 `configurable/config.*.json`，無須修改 `core/engine.py`。
- **邊界排除 (Explicitly Excluded)**：
  - 排除尚未使用的本地外掛擴充點（`snippets`、`grammars`、`problem_matchers`、`configuration_defaults`）與 `extension.js`，已轉入 `[TODO-19]`。
  - 排除改寫專案根目錄 `project://.gitignore`（Schema 產物目錄內建 `.gitignore` 寫入 `*` 自我忽略）。
  - 排除對範例值字串（如 `"auto"`）做特例硬編碼型別推導。
- **架構影響範圍**：
  - `ys_codebase/source/core/`（移除 `ide_projector.py` 與對應測試、更新 `__init__.py`、`installer.py` 廣播 `on_env_synced`、`validator.py` 支援負數與浮點數預設值）
  - `ys_codebase/source/vscode-support/`（新建模組：`manifest.json`、`contributes/`、`locales/`、`vscode_support/`、`scripts/cli.py`、`scripts/hook.core.py`、`tests/`）
  - `docs/core/` 與 `docs/vscode-support/`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `core` 徹底剝離 `IdeProjector` 並以 `on_env_synced` 事件解耦**：
  - `core` 刪除 `core/ide_projector.py` 並自 `core/__init__.py` 移除匯出；`Installer.sync_pip_dependencies()` 在完成 `PipManager.install_packages` 後廣播 `events.broadcast("on_env_synced", ExecutionContext("core", "env_sync", []), emit_module="core")`。
- **[P00:DR-02] 嚴守 Zero-Probing：組態模板與擴充規格 100% 由 `module://` 與 `module.mirror://` 讀取（零 `module.source://` 探測與零 `core/engine.py` 侵入）**：
  - 為通過 `dev check` 之 `PROBING` 檢查（非 `core`/`dev` 模組嚴禁存取 `module.source://`）並避免 `configurable/_format.json` 觸發非標準組態檔名告警與被 `engine.py` 當作模板部署：`SchemaCompiler` 僅自 `module://<mod>/contributes/_format.json` 讀取擴充定義，並自 `module.mirror://<mod>/<installed_ver>.zip` 記憶體讀取 `configurable/config.*.json`（由範例值推導組態 Schema，不再引入 `configurable/_format.json`）。
- **[P00:DR-03] 採用做法 B（直接寫入 `.vscode/settings.json` 之 `json.schemas` 免手動啟用外掛）**：
  - 生成之單檔 Schema 統一存放於 `.vscode/` 下受內建 `.gitignore` (`*`) 保護的子目錄，並將 `{ "fileMatch": [...], "url": "./.vscode/..." }` 同步寫入 `.vscode/settings.json` 的 `"json.schemas"` 陣列（同時記錄於 `_yscb_managed["jsonSchemas"]` 確保使用者自訂之其他 `json.schemas` 條目 100% 保留、且 `revert` 時可精準剔除），確保免安裝外掛、免 Reload Window 即刻生效，且路徑與已安裝模組清單完全確定、不隨本機外部環境變動。
- **[P00:DR-04] 採用 `current-site-packages` 穩定目錄連結消除 Python 版本路徑漂移**：
  - 於 `yscb://.venv/current-site-packages` 建立指向當前 Python 版本 `site-packages` 之連結（POSIX `os.symlink`、Windows `mklink /J` Directory Junction；不支援時 fallback 為實際路徑），使 `.vscode/settings.json` 之 `python.analysis.extraPaths` 恆定維持 `["./ys_codebase/.venv/current-site-packages"]`，不因開發者本機 Python 次版本不同而產生 Git diff。
- **[P00:DR-05] 顯式安裝 `vscode-support` 後自動建立 `project://.vscode/`**：
  - 既然使用者已顯式安裝 `vscode-support`，當 `project://.vscode/` 不存在時自動建立該目錄並寫入 `settings.json` 與 Schema。
- **[P00:DR-06] 擴充點精簡聚焦 `json_schemas`，進階擴充點轉入 `[TODO-19]`**：
  - `vscode-support/contributes/_format.json` 本次僅開放實際使用之 `json_schemas` 擴充點；`snippets`、`grammars`、`problem_matchers`、`configuration_defaults` 已登錄至 `[TODO-19]`。

---

## 3. 開放議題與確認紀錄

- **已全部確認完畢（0 開放議題）**：
  1. 採用做法 B（同時寫入 `settings.json` 的 `json.schemas` 免手動啟用外掛，僅保證 `settings.json` 狀態不隨本機外部環境變動）$\to$ 已固化為 `[P00:DR-03]`。
  2. 採用 `current-site-packages` 穩定連結 $\to$ 已固化為 `[P00:DR-04]`。
  3. 安裝 `vscode-support` 後若 `project://.vscode/` 不存在則自動建立 $\to$ 已固化為 `[P00:DR-05]`。
  4. 先聚焦現在需要的功能，其餘列入 `/todo` $\to$ 已登錄 `[TODO-19]` 並固化為 `[P00:DR-06]`。
