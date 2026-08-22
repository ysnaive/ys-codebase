---
target: "Core/Base"
doc_type: "readme"
status: "active"
source_paths:
  - "source/core/manifest.json"
  - "source/core/README.md"
related_docs:
  - "../_global/ARCHITECTURE.md"
  - "../Installer/README.md"
last_updated: "2026-08-22"
---

# Core 核心基底模組 (`source/core`)

`source/core/` 是 `ys-codebase` 工具庫的底層基礎基座，定義了中央標準庫的基本元數據與核心契約。

---

## 🏛️ 核心邊界與約束

> [!IMPORTANT]
> 1. **純源碼基座 (Pure Source Base)**：`core` 永遠只存在於 `source/core/`，**絕無 `build/core/` 產出物**。
> 2. **源碼模式強制底層相依 (Mandatory Base Dependency)**：
>    任何模組若以 `--source` 源碼模式安裝，`yscb_installer.py` 會自動將 `core` 置於相依鏈的最前端並先行安裝。
> 3. **卸載保護**：
>    當本地存在任何以源碼模式運行的模組時，系統禁止卸載 `core`，防止開發環境基底損毀。

---

## 📁 模組檔案
- `manifest.json`：宣告 `core` 模組元數據（`version: 2.0.0`）。
- `README.md`：核心說明文檔。
