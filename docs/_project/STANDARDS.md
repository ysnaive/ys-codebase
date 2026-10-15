---
target: "Project/Standards"
doc_type: "overview"
status: "active"
source_paths:
  - "yscb://source/core/core/uri.py"
  - "yscb://source/core/core/engine.py"
  - "yscb://source/core/core/config.py"
related_docs:
  - "../core/README.md"
  - "../core/uri_protocols.md"
  - "../core/ZIP_PACKAGE_SPEC.md"
last_updated: "2026-10-15"
---

# 全專案核心工程規範與邊界架構 (Project Standards & Boundary Architecture)

> 本文件為 YS-Codebase 全專案的最高工程規範與架構準則，定義空間協議、組態矩陣與開發防呆邊界。

---

## 1. 語意空間協議清單 (Semantic Space Protocols)

系統嚴格劃分核心空間、模組空間與工作流協議，杜絕脆弱的相對路徑與環境漂移（SSOT 唯一真理來源為 `python yscb.py uri list`）：

| 語意 URI 協議 | 提供者 | 實體解析路徑 | 空間定義與職責 | Git 追蹤政策 |
| :--- | :---: | :--- | :--- | :---: |
| **`project://`** | `core` | 由 `config/core/config.project.json` 之 `project_root` 解算 | **宿主專案根目錄**（被管理之專案工作空間） | 專案自行管理 |
| **`yscb://`** | `core` | 由 `yscb.config.json` 之 `yscb_root` 定位 | **YS-Codebase 核心程式庫目錄** (`ys_codebase/`) | ✅ 受追蹤 |
| **`yscb.host://`** | `core` | 由 `yscb.config.json` 之 `yscb_host` 定位 | **YS-Codebase 宿主環境根目錄** | ✅ 受追蹤 |
| **`module://`** | `core` | `yscb://.modules/` | **本機模組運行端目錄** | 🚫 忽略 |
| **`module.mirror://`** | `core` | `yscb://.mirror/` | **本機端模組鏡像庫（版本化快照備份）** | 🚫 忽略 |
| **`config://`** | `core` | `yscb://config/` | **全域與模組設定檔根目錄** | ✅ 受追蹤 |
| **`cache://`** | `core` | `yscb://.cache/` | **全域與模組編譯快取與中介產物根目錄** | 🚫 忽略 |
| **`storage://`** | `core` | `yscb://storage/` | **跨環境共享持久化資料空間** | ✅ 受追蹤 |
| **`snapshot://`** | `core` | `yscb://.snapshots/` | **組態快照備份目錄（用於災難恢復與回滾）** | 🚫 忽略 |
| **`yscb.venv://`** | `core` | `yscb://.venv/` | **YSCB 私有微虛擬環境空間根目錄** | 🚫 忽略 |
| **`module.source://`** | `dev` | `yscb://source/` | **模組原始碼開發空間（SSOT 源碼）** | ✅ 受追蹤 |
| **`module.build://`** | `dev` | `yscb://.build/` | **本地開發完整建置產物空間** | 🚫 忽略 |
| **`module.release://`** | `dev` | `yscb://release/` | **本機發布產物準備空間** | ✅ 受追蹤 |
| **`knowledge.storage://`** | `knowledge-db` | `cache://knowledge-db/` | **知識庫 AST 與向量快取專用空間** | 🚫 忽略 |
| **`workflow.plans://`** | `agents-workflow` | `project://plans/` | **工作流開發與推進計畫空間** | 專案自行管理 |
| **`workflow.docs://`** | `agents-workflow` | `project://docs/` | **專案知識庫與架構文檔空間** | 專案自行管理 |
| **`workflow.roadmap://`** | `agents-workflow` | `project://plans/roadmap/` | **長期演進藍圖與策略主題空間** | 專案自行管理 |
| **`workflow.archived://`** | `agents-workflow` | `project://plans/archived/` | **歷史歸檔計畫空間** | 專案自行管理 |

---

## 2. 2x2 組態矩陣邊界規範 (Configuration Matrix)

全系統設定檔嚴格依據「專案 vs 本地」與「全域 vs 模組」進行 2x2 邊界劃分：

| 範圍維度 | 專案層級 (`config.project.json`)<br/>✅ **受 Git 追蹤 (Team Shared)** | 本地個人層級 (`config.local.json`)<br/>🚫 **Git 忽略 (Machine Specific)** |
| :--- | :--- | :--- |
| **全域層級** | `yscb.config.json`：宣告 `yscb_root`、預設 `default_provider` 與 `installed_modules` 清冊。 | `yscb.config.local.json`：本機覆蓋設定。 |
| **模組層級** | `yscb://config/{module}/config.project.json`：模組專案層級設定（如 `core` 的 `project_root`）。 | `yscb://config/{module}/config.local.json`：模組本機層級覆蓋。 |

### 🛡️ 組態管理與打包物化四項鐵律
1. **SSOT 原則**：模組預設組態模板宣告於 `source/{module}/configurable/`（或 `contribute.json`），專案層級覆蓋於 `config.project.json`，個人特化於 `config.local.json`。
2. **Git 政策防護**：`config.local.json` 嚴禁入庫；`config.project.json` 必須入庫共享。
3. **無損寫入保證**：透過 `core.config` 修改組態時，自動執行原子備份快照至 `snapshot://`。
4. **模組組態遞迴原地增量補齊與產物驗證（原 `DN-03`）**：
   - 當模組版本更新並在組態模板中新增欄位時，安裝或 `reload` 流程（`AtomicEngine._deep_infill_dict`）會對 `config://{module}/` 執行遞迴比對，**僅自動補齊缺失鍵，使用者已修改之既有設定值 100% 原地保留不覆蓋**。
   - 打包與安裝產物驗證：單檔 Zip 下載與物化時強制驗證 Archive CRC 完整性與 Zip Slip 路徑邊界；組態部署完成後無條件從 `module://{module}/` 物理剝除組態模板與 `.yscbignore`。

---

## 3. 模組開發與 Dogfooding 閉環流程 (Dogfooding Cycle)

```mermaid
graph LR
    classDef s1 fill:#1e3a8a,stroke:#3b82f6,stroke-width:2px,color:#fff;
    classDef s2 fill:#14532d,stroke:#22c55e,stroke-width:2px,color:#fff;
    classDef s3 fill:#78350f,stroke:#f59e0b,stroke-width:2px,color:#fff;
    classDef s4 fill:#4c1d95,stroke:#8b5cf6,stroke-width:2px,color:#fff;

    Stage1["空間 ① 源碼開發<br/><code>source/{module}/</code><br/><i>唯一真理來源 (SSOT)</i>"]:::s1
    Stage2["Stage 2 打包構建<br/><code>dev build {module}</code><br/><i>產出本機 .build/</i>"]:::s2
    Stage3["空間 ② 測試閘門<br/><code>dev test --all</code><br/><i>100% Passed</i>"]:::s3
    Stage4["空間 ③ 自引用消費<br/><code>install {mod}@build</code><br/><i>直裝通道安全同步</i>"]:::s4

    Stage1 --> Stage2 --> Stage3 --> Stage4
```

### 🚨 三大空間隔離禁令
1. **源碼空間 (`source/`) 為唯一 SSOT**：所有功能修改 100% 必須在 `source/` 進行。
2. **禁止直接修改運行端 (`.modules/`)**：`.modules/` 視為編譯與部署產物，嚴禁手動直接修改。
3. **測試未通過嚴禁發布**：實機測試未 100% 通過前，嚴禁將 `.build/` 產物同步至 `.modules/`。
