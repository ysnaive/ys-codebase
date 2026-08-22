---
target: "Root/KnowledgeBase"
doc_type: "overview"
status: "active"
source_paths:
  - "ys_codebase/yscb_installer.py"
  - "ys_codebase/yscb_cli.py"
  - "ys_codebase/source/"
  - "ys_codebase/build/"
  - "test/run_regression.py"
related_docs:
  - "./_global/ARCHITECTURE.md"
  - "./_global/CLI_SPECIFICATION.md"
  - "./_project/STANDARDS.md"
last_updated: "2026-08-22"
---

# YS-Codebase 系統知識庫 (Knowledge Base)

歡迎查閱 `ys-codebase` 核心知識庫。本目錄記錄系統**最新架構、運作機制、規範標準與模組規格**。

---

## 🗺️ 知識庫導覽地圖 (Knowledge Map)

```text
docs/
├── 🌐 全域系統架構 (_global/)
│   ├── ARCHITECTURE.md          ← 宏觀架構全景、三層空間分流與 Core 相依體系
│   └── CLI_SPECIFICATION.md     ← yscb_installer.py 完整指令介面與參數合約
│
├── 📋 專案工程規範 (_project/)
│   ├── STANDARDS.md             ← 模組 Manifest 規範、零依賴紀律與測試驗收標準
│   └── CONTRIBUTING.md          ← 模組開發、打包構建 (build) 與發布指南
│
└── 📦 核心模組知識庫 (鏡像源碼)
    ├── Installer/               ← yscb_installer.py 核心引擎設計與內部元件
    ├── Core/                    ← ys_codebase/source/core/ 基礎基座定義與底層相依規則
    └── AgentsWorkflow/          ← agents-workflow SOP 工作流、3-Track 分流與定式腳本庫
```

---

## 🧭 快速索引 (Quick Links)

| 主題領域 | 文件連結 | 關鍵內容摘要 |
| :--- | :--- | :--- |
| **系統全貌** | [ARCHITECTURE.md](./_global/ARCHITECTURE.md) | 三層環境架構、Source / Build 分流哲學、Core 基座相依 |
| **指令規格** | [CLI_SPECIFICATION.md](./_global/CLI_SPECIFICATION.md) | `init`, `install`, `pull`, `build`, `push`, `status`, `list`, `remove` |
| **開發標準** | [STANDARDS.md](./_project/STANDARDS.md) | 純 Python 3 標準庫原則、Manifest JSON Schema、品質門檻 |
| **貢獻指南** | [CONTRIBUTING.md](./_project/CONTRIBUTING.md) | 模組建立、`build` 打包、`run_regression.py` 回歸驗證 |
| **Installer 引擎** | [Installer/README.md](./Installer/README.md) | `ConfigManager`, `GitRemoteClient`, `ModuleManager` 元件拆解 |
| **Core 基礎庫** | [Core/README.md](./Core/README.md) | `--source` 模式強制相依規則與純源碼基座定位 |
| **Agents 工作流** | [AgentsWorkflow/README.md](./AgentsWorkflow/README.md) | 3-Track 管控 (FT/Full/Umbrella)、9 大 SOP 工作流、定式工具庫 |
