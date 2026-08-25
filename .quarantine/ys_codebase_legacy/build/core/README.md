# YS-Codebase Core Base (`source/core`)

本模組為 `ys-codebase` 的核心底層基座 (Core Base Infrastructure)。

---

## 🏛️ 核心定位與職責

1. **純源碼基座 (Pure Source Base)**：
   `core` 永遠只存在於 `source/core/` 空間，**不生成任何 `build/core/` 產出物**。
2. **強制底層相依 (Mandatory Base Dependency)**：
   任何模組若以開發者源碼模式 (`--source`) 安裝，`yscb_installer.py` 會自動將 `core` 注入至相依鏈最前端並先行就緒。
3. **卸載防護機制 (Dependency Guard)**：
   當專案中存在任何處於 `source` 模式的模組時，系統強制阻斷單獨移除 `core`，防止開發環境基底損毀。
4. **共享常數與基礎規範**：
   提供全域版本識別 (`__version__`)、基礎元數據與後續跨模組工具庫之標準接口契約。

---

## 🪝 模組生命週期 Hook 規範 (Module Lifecycle Hooks)

所有模組可於 `scripts/`（或模組根目錄）提供以下專用 Hook 腳本，由 `yscb_installer.py` 在執行特定生命週期事件時自動調用：

| Hook 腳本 | 調用時機 | 參數契約 | 職責與用途 |
|---|---|---|---|
| **`_installed.py`** | 模組初次安裝或重新安裝完成後 | `<module_dir> <mode>`<br>*(例: `modules/foo build`)* | 執行安裝後置初始化（如生成範本、建立初始目錄、註冊 IDE 指令等）。 |
| **`_uninstall.py`** | 模組被移除前 | `<module_dir> <mode>`<br>*(例: `modules/foo build`)* | 執行卸載前置清理（如移除 IDE 生成指令、釋放本地關聯資源等）。 |
| **`_migration.py`** | 模組版本升級/覆寫安裝時 | `<old_version> <new_version>`<br>*(例: `1.0.0 1.1.0`)* | 執行跨版本資料遷移（如升級本地 `config.json` 結構、相容性路徑修正、Schema 轉移等）。 |
