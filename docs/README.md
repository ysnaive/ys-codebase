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
  - "./_project/ARCHITECTURE.md"
  - "./_project/CLI_SPECIFICATION.md"
  - "./_project/STANDARDS.md"
last_updated: "2026-08-22"
---

# YS-Codebase 系統知識庫 (Knowledge Base)

歡迎查閱 `ys-codebase` 核心知識庫。本目錄記錄系統**最新架構、運作機制、規範標準與模組規格**。

---

## 🗺️ 知識庫導覽地圖 (Knowledge Map)

```text
docs/
├── 🌐 專案系統架構與規範 (_project/)
│   ├── ARCHITECTURE.md          ← 宏觀架構全景、2x2 設定矩陣與 Core SDK 體系
│   ├── CLI_SPECIFICATION.md     ← yscb_cli.py 與 yscb_installer.py 指令合約
│   ├── STANDARDS.md             ← 模組 Manifest 規範、2x2 設定協定與品質門檻
│   └── CONTRIBUTING.md          ← 模組開發、打包構建 (build) 與發布指南
│
└── 📦 核心模組知識庫 (鏡像源碼)
    ├── Core/                    ← yscb_core 運行期 SDK 定義與 API 使用手冊
    ├── Installer/               ← yscb_installer.py 核心引擎設計與內部元件
    └── AgentsWorkflow/          ← agents-workflow SOP 工作流、3-Track 與定式工具庫
```

---

## 🧭 快速索引 (Quick Links)

| 主題領域 | 文件連結 | 關鍵內容摘要 |
| :--- | :--- | :--- |
| **系統全貌** | [ARCHITECTURE.md](./_project/ARCHITECTURE.md) | 100% 專案自包含、2x2 設定矩陣、Core SDK 體系 |
| **指令規格** | [CLI_SPECIFICATION.md](./_project/CLI_SPECIFICATION.md) | `init`, `install`, `pull`, `build`, `push`, `status`, `list`, `remove` |
| **開發標準** | [STANDARDS.md](./_project/STANDARDS.md) | 純 Python 3 標準庫、2x2 設定協定、Manifest Schema |
| **貢獻指南** | [CONTRIBUTING.md](./_project/CONTRIBUTING.md) | 模組建立、SDK 引用、`build` 打包、`run_regression.py` 回歸 |
| **Core 基礎庫** | [Core/README.md](./Core/README.md) | `yscb_core` SDK (ProjectContext, ConfigManager, Console) |
| **語意 URI 系統** | [Core/SEMANTIC_URI_SYSTEM.md](./Core/SEMANTIC_URI_SYSTEM.md) | 五層協議模型、沙盒圍欄防護 (Chroot Guard)、LPM 演算法與 Direct I/O API |
| **Installer 引擎** | [Installer/README.md](./Installer/README.md) | `ConfigManager`, `GitRemoteClient`, `ModuleManager` 元件拆解與連動廣播 |
| **Agents 工作流** | [AgentsWorkflow/README.md](./AgentsWorkflow/README.md) | 3-Track 管控 (FT/Full/Umbrella)、9 大 SOP 工作流、定式工具庫 |
| **連動協定手冊** | [AgentsWorkflow/SOP_INTERLOCK_PROTOCOL.md](./AgentsWorkflow/SOP_INTERLOCK_PROTOCOL.md) | 三大合約、Slot 插槽注入、雙層 Extension 發現與 IDE 無感同步 |
