# 技術路線圖：Core 內核 VFS 虛擬檔案系統與語意空間演進 (Roadmap)

> 主題：Core 內核 VFS 虛擬檔案系統與語意空間演進  
> 歸檔日期：2026-09-06  
> 狀態：Proposed  

---

## 1. 問題陳述與架構定位 (Problem & Architectural Positioning)

### 1.1 痛點現象
目前 YS-Codebase 的檔案存取僅透過 `core.uri` 提供字串層級的路徑解析（如 `resolve("cache://knowledge-db")`），其餘檔案讀寫、目錄遍歷、原子覆蓋與快照管理皆由各業務模組直接調用 Python 原生 `open()`、`pathlib` 或 `os` 函式。這引發以下問題：
1. **路徑跨平台不一致**：Windows 反斜線 `\`、Linux 斜線 `/` 以及長路徑（`\\?\`）適配散落在各模組，易引發路徑比對撕裂。
2. **缺乏原子寫入防護**：各模組各自實作 `.tmp` 替換邏輯，缺乏統一的崩潰回滾與並行鎖保護。
3. **語意空間與 IO 脫節**：語意空間協議（`project://`、`yscb://`、`config://`、`cache://`）僅止於路徑計算，無法直接支援虛擬掛載、唯讀沙盒限制與存取稽核。

### 1.2 內核唯一性決策 (Single Microkernel Decision)
在架構論證中，曾考量是否獨立為 `vfs` 一級模組。但依據專案最高準則：
- **`core` 是全系統唯一微內核 (Sole Microkernel)**。
- 語意 URI 是全生態系的基石定址協議，若將基於 URI 的 VFS 剝離為獨立模組，會打破內核純粹性，導致全生態系依賴複雜度上升 (`["core", "vfs"]`)，並引發 `core.config` 等內核功能對外部模組的依賴倒置。
- **架構定調**：VFS 必須深度收斂於 `core` 模組內部（作為 `core.vfs` 子套件），保持 `core` 作為唯一底座。

### 1.3 領域模組解耦說明
本路線圖專注於 `core.vfs` 抽象規格與實作，**暫不耦合 `knowledge-db` 或其他業務模組**；待 `core.vfs` 完工並通過合約測試後，各模組（含 `knowledge-db`）於自身演進時自行平滑遷移。

---

## 2. 核心架構設計 (Core Architecture & Design)

```
core.vfs
├── path.py      # VirtualPath 實體（支援 uri 與跨平台路徑運算）
├── resolver.py  # 語意空間掛載與動態解析中樞 (相容 core.uri)
├── io.py        # 跨平台原子讀寫、安全刪除與備份回滾
└── sandbox.py   # 邊界防護（禁止逃逸出專案根目錄）
```

- **統一定址與 Path-like 封裝**：
  提供 `VirtualPath` 物件，支援 `vfs.get("cache://knowledge-db/index.bin")`，可直接執行 `.exists()`、`.read_bytes()`、`.atomic_write(data)`。
- **跨平台路徑正規化**：
  在內核層面徹底消除 Windows/Linux 斜線差異與大小寫敏感性陷阱。
- **無損寫入與原子事務**：
  整合快照機制，在執行覆寫時由 VFS 自動處理同分區臨時檔與原子替換 (`os.replace`)。

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 A：併入 `core` (`core.vfs`) | 方案 B：獨立 `vfs` 模組 |
| :--- | :--- | :--- |
| **架構純粹度 (Single Kernel)** | ⭐️⭐️⭐️⭐️⭐️ (維持唯一微內核公理) | ⭐️⭐️ (內核分裂為 core 與 vfs) |
| **依賴複雜度 (Dependency)** | ⭐️⭐️⭐️⭐️⭐️ (模組僅需依賴 core) | ⭐️⭐️ (全生態系多重依賴) |
| **升級與維護成本 (Maintenance)** | ⭐️⭐️⭐️⭐️⭐️ (隨 core 統一版本治理) | ⭐️⭐️⭐️ (跨模組版本矩陣) |
| **功能內聚性 (Cohesion)** | ⭐️⭐️⭐️⭐️⭐️ (URI 與 IO 完美合一) | ⭐️⭐️⭐️ (協議與操作分離) |

---

## 4. 推薦架構規格與介面範式 (API Spec)

```python
from core.vfs import VirtualPath, vfs

# 1. 語意空間路徑解析 (100% 向後相容 core.uri.resolve)
cfg_path: VirtualPath = vfs.resolve("config://knowledge-db/config.project.json")

# 2. 原生原子讀寫操作
content = cfg_path.read_text(encoding="utf-8")
cfg_path.atomic_write(new_content, backup=True)

# 3. 空間遍歷與安全邊界檢查
for file in vfs.walk("project://src", pattern="*.py"):
    if not vfs.is_safe_path(file):
        continue  # 杜絕逃逸出工作區
```

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
作為中長期核心架構資產儲備，待完成當前各模組架構統整修復後，於 `core` 模組排定專屬計畫落地。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1 (介面規格與相容層)**：在 `core` 建立 `core.vfs`，實現 `VirtualPath` 並向下相容封裝 `core.uri.resolve`。
2. **Stage 2 (跨平台原子 IO 與沙盒守門)**：實作 `atomic_write`、跨平台路徑正規化與目錄逃逸防護。
3. **Stage 3 (Core 內部自舉遷移)**：將 `core.config`、`core.snapshot` 全面切換至 `core.vfs` 進行驗收。
4. **Stage 4 (生態系下游遷移)**：提供遷移指南，供 `knowledge-db`、`agents-workflow` 等模組自行平滑切換。
