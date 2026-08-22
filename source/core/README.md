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
