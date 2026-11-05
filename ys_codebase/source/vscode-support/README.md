# `vscode-support` — VS Code 工作區設定投影、穩定微環境連結與單檔級 JSON Schema 編譯模組

`vscode-support`（內部套件命名為 `vscode_support`）為 YS-Codebase 生態系之選配官方 IDE 賦能模組，將原本暫存於 `core` 的 VS Code 耦合邏輯 100% 剝離，實現「`core` 零 IDE 假設 + 顯式安裝即賦能（`install vscode-support`）+ 移除即乾淨還原（`remove vscode-support`）」。

---

## 1. 核心架構與職責

1. **生命週期自動接管與完全可逆拆卸 (`SettingsProjector` & `scripts/hook.core.py`)**：
   - 訂閱 `core` 之 `on_env_synced`、`on_reload` 與 `on_remove` 事件。
   - 當專案已安裝 `vscode-support` 時，若 `project://.vscode/` 不存在則自動建立，並以 `_yscb_managed` 差集追蹤軟合併 `python.analysis.extraPaths`、`python.analysis.exclude`、`files.exclude`、`search.exclude`、`files.watcherExclude` 與 `json.schemas`，100% 保留使用者自訂條目。
   - 於 `remove vscode-support`（或執行 `vscode-support revert`）時，依據 `_yscb_managed` 100% 剔除所有注入項並清除 `.vscode/schemas/` 與穩定連結。

2. **無版本號穩定微環境路徑連結 (`yscb.venv://current-site-packages`)**：
   - 於 `yscb.venv://current-site-packages` 建立指向當前 Python 版本 `site-packages` 之連結（POSIX `os.symlink`、Windows `mklink /J` Directory Junction，不支援時自動降級為實際跨平台路徑），使 `.vscode/settings.json` 之 `python.analysis.extraPaths` 恆定維持單一路徑，不隨本機 Python 次版本變動而污染版控。

3. **單檔級精準 JSON Schema 編譯與直接綁定 (`SchemaCompiler`)**：
   - 嚴守 Zero-Probing 原則，自 `module://<mod>/contributes/_format.json` 與 `module.mirror://<mod>/<ver>.zip` 動態編譯單檔級 `contributes/<mod>.schema.json`、`config/<mod>.schema.json`（同時綁定 `config/<mod>/config.*.json` 與 `.config.local/<mod>/config.*.json`）與元 Schema（`format-meta.schema.json`、`manifest.schema.json`）至 `project://.vscode/schemas/`（由 `core.gitignore` 統一納管於根目錄 `.gitignore`），並直接寫入 `.vscode/settings.json` 之 `json.schemas` 免手動安裝外掛即刻生效。

---

## 2. CLI 指令速查

```bash
# 檢視 .vscode/settings.json 託管狀態、穩定連結目標與已編譯 Schema 清單
python yscb.py vscode-support status [--json]

# 強制重新編譯全模組 JSON Schema 並同步 .vscode/settings.json
python yscb.py vscode-support sync [--json]

# 乾淨剔除所有 YSCB 託管之 VS Code 設定、Schema 目錄與穩定連結
python yscb.py vscode-support revert [--json]
```

