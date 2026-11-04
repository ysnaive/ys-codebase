---
target: "VSCodeSupport/DesignNotes"
doc_type: "design_notes"
status: "active"
source_paths:
  - "yscb://source/vscode-support/vscode_support/projector.py"
  - "yscb://source/vscode-support/vscode_support/schema_compiler.py"
  - "yscb://source/vscode-support/scripts/hook.core.py"
related_docs:
  - "./README.md"
  - "../core/README.md"
last_updated: "2026-11-04"
---

# `vscode-support` 設計決策與邊界防坑紀錄 (Design Notes)

---

## [DN-01] `core` 零 IDE 假設解耦與 `on_env_synced` 事件時序

- **背景與原因**：`core` 的 `on_installed` 與 `on_update` 事件廣播時機早於 `Installer.sync_pip_dependencies()`，若 IDE 投影掛載於 `on_installed`，執行時私有微環境的 `site-packages` 尚未完成物化。
- **設計決策**：於 `Installer.sync_pip_dependencies()` 完成後廣播 IDE 中立之 `on_env_synced` 事件；`vscode-support/scripts/hook.core.py` 僅訂閱 `on_env_synced`、`on_reload` 與 `on_remove`，避免單次安裝重複觸發 3 次磁碟同步。

---

## [DN-02] `yscb.venv://current-site-packages` 穩定目錄連結與安全移除

> [!CAUTION]
> **嚴禁對 `current-site-packages` 呼叫 `shutil.rmtree()`！**
> 在部分平台或 Python 版本下，對 Windows Directory Junction 執行 `shutil.rmtree` 可能會穿透連結清空目標 `site-packages` 內已安裝的所有第三方套件。移除舊連結時必須統一使用 `projector._safe_remove_link()`（僅呼叫 `os.unlink()` 或 `os.rmdir()`）。

- **設計決策**：
  1. 建立連結前先執行 `os.makedirs(target_site_pkg, exist_ok=True)`，確保在所有模組皆無 `pip_dependencies` 的冷啟動環境下不會產生懸空連結（Dangling Link）。
  2. 透過固定連結 `./ys_codebase/.venv/current-site-packages`，使 `.vscode/settings.json` 的 `python.analysis.extraPaths` 不再包含 `py311`/`py312` 等版本字串，徹底消除跨開發者切換 Python 次版本時的 Git Diff。
  3. 透過 `core.platform.list_module_search_roots(self.yscb_dir, prefer_source=True)` 自動將各模組搜尋根目錄（若 `source/<mod>` 存在則優先投影 `./ys_codebase/source/<mod>`，否則投影 `./ys_codebase/.modules/<mod>`）追加至 `python.analysis.extraPaths`；當 `extraPaths` 包含 `/.modules/` 路徑時，動態自 `python.analysis.exclude` 省略 `**/.modules/**`，確保 Pylance 在母倉與下游專案皆能 100% 精準解析 `from core import uri, vfs` 等跨模組匯入。

---

## [DN-03] 嚴守 Zero-Probing：僅自 `module://` 與 `module.mirror://` 編譯 Schema

> [!CAUTION]
> **嚴禁在 `vscode-support` 業務代碼中存取 `"module.source://"` 或 `"config.project.json"` 字面量！**
> `dev check` 的 AST 靜態掃描器（`checker.py`）會將非 `core`/`dev` 模組中的 `"module.source://"` 判定為 `[FAIL] [PROBING]`，並將 `"config.project.json"` 字串常數判定為 `[FAIL] [ANTIPATTERN]`。

- **設計決策**：
  - 擴充點 Schema 100% 讀取運行態 `module://<mod>/contributes/_format.json`。
  - 組態 Schema 優先讀取 `module://<mod>/configurable/_format.json`（同構支援 `uri` / `path` 協議前綴 `defaultSnippets` 與 `@desc(...)` 欄位說明），並從 `module.mirror://<mod>/<ver>.zip` 記憶體讀取 `configurable/config.*.json` 提取預設值或作為無 `_format.json` 時之型別推導來源。

---

## [DN-04] `.vscode/settings.json` 之 JSONC 字串感知剝離與 `.bak` 保護

- **背景與原因**：開發者手動維護之 `.vscode/settings.json` 常包含 `//` 行註解、`/* */` 區塊註解與尾隨逗號（JSONC），且檔案內如 `"https://..."` 字串值不可被誤判為註解。
- **設計決策**：
  1. `projector.strip_jsonc(raw_text)` 採用兩階段字元狀態機：先安全剝離字串外之單行與區塊註解，再剝離 `}` / `]` 前之尾隨逗號。
  2. 當原始 `.vscode/settings.json` 因含 JSONC 語法而無法由標準 `json.loads` 直接解析，但經 `strip_jsonc` 後解析成功時，自動將原始內容備份至 `.vscode/settings.json.bak`，再執行 `_yscb_managed` 差集軟合併與原子寫入。
  3. 若剝離後仍非合法 JSON 物件，同樣備份至 `.vscode/settings.json.bak` 並回傳 `False`，絕不靜默清空使用者設定。


