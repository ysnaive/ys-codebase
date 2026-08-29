# 全專案核心工程規範與邊界架構 (Project Standards & Boundary Architecture)

> 本文件為 YS-Codebase 全專案的最高工程規範與架構準則，定義空間協議、組態矩陣與開發防呆邊界。

---

## 1. 語意空間協議清單 (Semantic Space Protocols)

系統嚴格劃分四大核心空間與開發專屬空間，杜絕脆弱的相對路徑與環境漂移：

| 語意 URI 協議 | 實體解析路徑 | 空間定義與職責 | Git 追蹤政策 |
| :--- | :--- | :--- | :---: |
| **`project://`** | 由 `config/core/config.project.json` 之 `project_root` 解算 | **宿主專案空間**（如外部被管理的專案根目錄） | 專案自行管理 |
| **`yscb://`** | 由 `yscb.config.json` 之 `yscb_root` 定位 | **YS-Codebase 工具庫根目錄** | ✅ 受追蹤 |
| **`module.root://`** | `yscb://modules/` | **本地模組運行端根目錄** | ✅ 受追蹤 |
| **`module://`** | `yscb://modules/{module}/` | **特定模組之運行端純淨代碼目錄** | ✅ 受追蹤 |
| **`config.root://`** | `yscb://config/` | **全域模組設定檔根目錄** | ✅ 受追蹤 |
| **`config://`** | `yscb://config/{module}/` | **特定模組專屬設定檔目錄** | ✅ 受追蹤 |
| **`cache.root://`** | `yscb://.cache/` | **全域模組編譯快取與中介產物根目錄** | 🚫 忽略 |
| **`cache://`** | `yscb://.cache/{module}/` | **特定模組專屬快取目錄** | 🚫 忽略 |
| **`mirror://`** | `yscb://.mirror/` | **本地端模組鏡像庫（版本化備份）** | 🚫 忽略 |
| **`temp://`** | `yscb://.temp/` | **系統隔離暫存區（含鎖與測試沙盒）** | 🚫 忽略 |
| **`snapshot://`** | `yscb://.snapshots/` | **組態快照備份目錄（用於災難恢復）** | 🚫 忽略 |
| *(開發)* **`module.source.root://`** | `yscb://source/` | **模組原始碼開發空間根目錄** | ✅ 受追蹤 |
| *(開發)* **`module.source://`** | `yscb://source/{module}/` | **特定模組原始碼開發空間** | ✅ 受追蹤 |
| *(開發)* **`module.build.root://`** | `yscb://build/` | **純淨安裝產物空間（本機套件發布庫）** | ✅ 受追蹤 |
| *(開發)* **`module.build://`** | `yscb://build/{module}/{version}/` | **特定模組之純淨發布產物版本包** | ✅ 受追蹤 |

---

## 2. 2x2 組態矩陣邊界規範 (Configuration Matrix)

全系統設定檔嚴格依據「專案 vs 本地」與「全域 vs 模組」進行 2x2 邊界劃分：

| 範圍維度 | 專案層級 (`config.project.json`)<br/>✅ **受 Git 追蹤 (Team Shared)** | 本地個人層級 (`config.local.json`)<br/>🚫 **Git 忽略 (Machine Specific)** |
| :--- | :--- | :--- |
| **全域層級** | `yscb.config.json`：宣告 `yscb_root`、預設 `default_provider` 與 `installed_modules` 清冊。 | `yscb.config.local.json`：本機覆蓋設定。 |
| **模組層級** | `yscb://config/{module}/config.project.json`：模組專案層級設定（如 `core` 的 `project_root`）。 | `yscb://config/{module}/config.local.json`：模組本機層級覆蓋。 |

### 🛡️ 組態管理三項鐵律
1. **`project://` 零 Fallback 鐵律**：`project_root` 預設為 `!undefined`。若設定檔缺失或為 `!undefined`，解析 `project://` 時必須直接拋出 `ValueError`，完全禁止 fallback 猜測當前目錄。
2. **自動分發與增量補齊**：模組安裝時自動分發預設組態；若目標已存在，遞迴原地補齊新增之缺失鍵，用戶既有之自訂值 100% 保持不變。
3. **中介層快照隔離**：框架衍生之 `contributes.merged.json` 必須輸出至 `cache://`，嚴禁污染 `config://` 目錄。

---

## 3. Dogfooding 自引用空間邊界與四步閉環 (Dogfooding Axiom)

專案呈現「自引用 (Dogfooding)」狀態，開發者與 Agent 必須強制遵守以下三大空間隔離與四步閉環流水線：

```mermaid
graph LR
    classDef s1 fill:#1e3a8a,stroke:#3b82f6,stroke-width:2px,color:#fff;
    classDef s2 fill:#14532d,stroke:#22c55e,stroke-width:2px,color:#fff;
    classDef s3 fill:#78350f,stroke:#f59e0b,stroke-width:2px,color:#fff;
    classDef s4 fill:#4c1d95,stroke:#8b5cf6,stroke-width:2px,color:#fff;

    Stage1["空間 ① 源碼開發<br/><code>source/{module}/</code><br/><i>唯一真理來源 (SSOT)</i>"]:::s1
    Stage2["Stage 2 打包構建<br/><code>dev build {module}</code><br/><i>產出本機 build/</i>"]:::s2
    Stage3["空間 ② 測試閘門<br/><code>dev test --all</code><br/><i>100% Passed</i>"]:::s3
    Stage4["空間 ③ 自引用消費<br/><code>install {mod}@build</code><br/><i>直裝通道安全同步</i>"]:::s4

    Stage1 --> Stage2 --> Stage3 --> Stage4
```

### 🚨 三大空間隔離禁令
1. **源碼空間 (`source/`) 為唯一 SSOT**：所有功能修改 100% 必須在 `source/` 進行。
2. **禁止直接修改運行端 (`modules/`)**：`modules/` 視為編譯與部署產物，嚴禁手動直接修改。
3. **測試未通過嚴禁發布**：實機測試未 100% 通過前，嚴禁將 `build/` 產物同步至 `modules/`。
