---
target: "Project/KnowledgeMap"
doc_type: "overview"
status: "active"
related_docs:
  - "./_project/ARCHITECTURE.md"
  - "./_project/STANDARDS.md"
last_updated: "YYYY-MM-DD"
---

# 專案全域知識地圖 (Knowledge Map)

> 本文件是專案知識庫（`docs://`）的**全域總導覽入口**，也是開發者與 AI Agent 建立系統全貌認知的第一站。  
> **維護約束**：凡新增、移除或重構模組時，必須同步更新此地圖。

---

## 🏛️ 全域架構與工程公理 (System Axioms)

| 核心規範文件 | 知識維度 | 說明 |
| :--- | :--- | :--- |
| [ARCHITECTURE.md](./_project/ARCHITECTURE.md) | 維度 1, 2 | 全系統宏觀拓撲、依賴方向與分層邊界 |
| [STANDARDS.md](./_project/STANDARDS.md) | 維度 1, 4 | 全域工程標準、語意 URI 協定與 2×2 設定矩陣 |
| [CLI_SPECIFICATION.md](./_project/CLI_SPECIFICATION.md) | 維度 6 | 系統終端指令與參數規格合約 |
| [CONTRIBUTING.md](./_project/CONTRIBUTING.md) | 維度 6 | 協作規範、分支策略與測試驗收門檻 |

---

## 📦 模組事實手冊索引 (Module Handbooks)

| 模組名稱 (Module / Namespace) | 模組首頁路徑 | 當前狀態 | 核心職責簡述 |
| :--- | :--- | :--- | :--- |
| `[Core/CoreModule]` | [./CoreModule/README.md](./CoreModule/README.md) | `active` | 核心運行期 SDK、基礎型態與底層公用庫 |
| `[Services/NetworkService]` | [./NetworkService/README.md](./NetworkService/README.md) | `active` | 遠端連線通訊、RPC 協議封裝與事件分發 |

---

## 🧭 Agent 知識庫探索導覽順序

當 Agent 進入專案進行需求評估或開發時，建議遵循以下順序：

1. **宏觀認知**：先讀取 `docs/_project/ARCHITECTURE.md` 與 `STANDARDS.md`，確認系統全貌與全域公理。
2. **模組邊界**：前往目標模組的 `README.md`，確認其「做什麼 / 不做什麼」與公開介面。
3. **機制與坑點**：
   - 若涉及動態流向，閱讀該模組的專題手冊（`[topic].md`）。
   - **務必讀取**該模組的 `DESIGN_NOTES.md`，提前避開已知限制與 `[!CAUTION]` 坑點。
4. **歷史脈絡**：若涉及大規模重構，查閱該模組的 `CHANGELOG.md` 或歷史歸檔計畫。
