# 需求規格書 (Requirements Specification)

> 功能名稱：核心微內核基礎設施模組 (Core Infrastructure Module)
> 建立日期：2026-08-24
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)
> 依據 P00 / 調研報告：[P00_semantic_requirements.md](../P00_semantic_requirements.md) / [R01](../R01_module_architecture_survey.md), [R02](../R02_yscb_responsibilities.md), [R03](../R03_manifest_and_lifecycle_flow.md), [R04](../R04_lifecycle_invocation_flow.md)
> 狀態：Confirmed
> 擴充項目：none
> 模板版本：v1.4

---

## 功能需求 (Functional Requirements)

| ID | 功能描述 | 輸入 | 處理 | 輸出 | 對應 P00 語意 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **FR-01** | **語意 URI 與虛擬檔案系統 (`core.uri` / VFS SDK)** | 語意 URI 字串（例 `project://...`, `mirror://...`, `module://...`）與 VFS 操作指令 | 1. 依 `yscb.config.json` 動態錨定實體路徑。<br/>2. 支援 9 大通用協議解析與實體路徑雙向轉換。<br/>3. 支援 `{module}` 動態佔位符代換。<br/>4. **內建一級 VFS 檔案系統操作**：提供 `read_text`, `write_text`, `read_json`, `write_json`, `read_bytes`, `write_bytes`, `exists`, `is_file`, `is_dir`, `makedirs`, `remove`, `rmtree`, `listdir`, `copy`, `move` 等方法，業務模組**直接以 URI 進行 I/O**，徹底免除手動轉換與對接底層 `os` 模組。 | 讀寫資料內容、布林值或目錄清單 | P00 包含範疇 2.3；R02 §3.2；2026-08-24 VFS 增補需求 |
| **FR-02** | **12 大原子操作引擎 (`core.engine`)** | 操作指令與目標參數（模組名、版本、來源） | 實作 `ACT-01` ~ `ACT-12`：<br/>- `DOWNLOAD` / `DELETE`（鏡像庫管理）<br/>- `REGISTER` / `UNREGISTER`（清冊維護）<br/>- `SOLVE_DEPS`（版本約束與拓撲求解）<br/>- `PREPARE`（狀態校驗與缺漏補全）<br/>- `RELOAD`（兩階段純淨物化與注入廣播）<br/>- `SNAPSHOT` / `RESTORE_SNAPSHOT`（快照備份還原）<br/>- `FETCH<source>`（Provider 倉庫抓取） | 操作執行結果與狀態碼 | P00 包含範疇 2.2；R04 §1 |
| **FR-03** | **7 大 Installer 套件管理指令 (`scripts/cli.py`)** | 命令列輸入（`install`, `update`, `remove`, `list`, `status`, `rollback`, `reload`） | 1. `install`: 抓取純淨產物至 `mirror://`，雙重名稱校驗後部署至 `modules/`。<br/>2. `update`: 求解最新版本並批次升級。<br/>3. `remove`: 反向相依檢查後註銷（選用 `--clean` 刪除鏡像）。<br/>4. `list`: 列出本地與遠端可用模組。<br/>5. `status`: 診斷已安裝模組完整度與相依健康度。<br/>6. `rollback`: 自快照還原至指定歷史版本。<br/>7. `reload`: 重構純淨運行端並重新執行依賴注入。 | 格式化終端報告與 Exit Code | P00 包含範疇 2.1；R02 §3.1；R04 §2 |
| **FR-04** | **Contributes 聚合器與依賴注入 (`core.contributes`)** | 各模組之 `contributes` 宣告檔與專案組態 | 1. 掃描 5 大來源 contributes 宣告。<br/>2. 依相依拓撲排序執行注入。<br/>3. 提供衝突檢測與無效指標告警。 | 注入生效結果與診斷報告 | P00 包含範疇 2.4；R03 §2 |
| **FR-05** | **極簡 ExecutionContext 與微內核隔離** | 執行期呼叫端資訊 | 封裝 3 欄位極簡介面（`module_name`, `command`, `args`），嚴禁向業務模組暴露底層實體路徑。 | 語意執行上下文物件 | P00 包含範疇 2.5；R03 §3 |

---

## 非功能需求 (Non-Functional Requirements)

| ID | 類別 | 約束描述 | 驗證方式 |
| :--- | :--- | :--- | :--- |
| **NFR-01** | **零外部依賴** | 100% 僅使用 Python 3.8+ 標準庫（`sys`, `os`, `json`, `urllib.request`, `subprocess`, `shutil`, `hashlib`, `zipfile`, `tarfile` 等）。 | 純淨虛擬環境單元測試與 import 掃描 |
| **NFR-02** | **操作原子性與自癒性** | 所有檔案寫入與模組物化均採用「暫存 ➔ 驗證 ➔ 原子覆蓋」機制；`RELOAD` 階段一保證 100% 純淨初始狀態。 | 模擬中斷與異常注入測試 |
| **NFR-03** | **跨平台路徑無感** | 語意 URI 統一採用標準 Forward Slash (`/`) 格式，內部自動適配 Windows 與 POSIX 實體路徑。 | Windows/Linux 路徑對映測試 |

---

## Edge Cases

| ID | 場景描述 | 預期行為 | 對應 FR |
| :--- | :--- | :--- | :--- |
| **EC-01** | `install` / `update` 時偵測到相依版本衝突 | `SOLVE_DEPS` 立即阻斷並輸出衝突拓撲報告，不破壞現有安裝環境。 | FR-02, FR-03 |
| **EC-02** | `remove` 被其他已安裝模組相依之核心模組 | 反向相依檢查攔截並提示「無法移除：模組 X 正被模組 Y 相依」，拒絕解除安裝。 | FR-02, FR-03 |
| **EC-03** | Provider 來源的 `index.json` 或 `manifest.json` 損壞/缺失 | 雙重名稱校驗失敗，立即清理暫存並報錯，不寫入 `mirror://`。 | FR-02, FR-03 |
| **EC-04** | 離線環境下執行 `rollback` 或 `reload` | 完全不依賴網路，直接使用本地 `snapshot://` 與 `mirror://` 產物完成秒級還原。 | FR-02, FR-03 |
| **EC-05** | 運行端 `modules/` 出現未登記之幽靈檔案或被前次注入污染 | `RELOAD` 階段一全量清空覆蓋為純淨鏡像檔案，徹底清除髒狀態。 | FR-02, FR-04 |
| **EC-06** | 透過 VFS 存取未支援之 URI 協議（例 `unknown://file`） | VFS 拋出明確之 `ValueError: Unsupported URI scheme: unknown://`，阻斷非法存取。 | FR-01 |

---

## 專案擴充特化判定矩陣 (Extension Specialization Matrix)

| 擴充項目名稱 | 觸發模式 | 本計畫適用性判定 | 納入 / 排除具體理由 |
| :--- | :--- | :--- | :--- |
| `sop_ext` 清單 | `on_demand` | ❌ 排除 (Excluded) | 本子計畫為核心微內核 SDK 與套件管理基礎設施，不涉及業務特化擴充 |

---

## Decision Records

### [P01:DR-01] 微內核目錄架構與源碼路徑
- **議題**：`core` 模組之原始碼應存放於何處？
- **結論**：按照標準開發者規範放置於 `source/core/`，包含 `manifest.json`、`scripts/cli.py` 與內部 `core/` SDK 套件（`uri.py`, `engine.py`, `installer.py`, `contributes.py`）。
- **理由**：落實「源碼空間 `source/`」與「純淨運行端 `modules/`」的標準空間隔離。

### [P01:DR-02] RELOAD 兩階段純淨物化保證
- **議題**：如何徹底杜絕模組重載時的髒狀態殘留？
- **結論**：`RELOAD` 強制分為「階段一：自 `mirror://` 全量純淨物化覆蓋」與「階段二：掃描 5 大來源 contributes 依賴注入與事件廣播」。
- **理由**：保證運行端始終處於 100% 可預期的無污染純淨初始狀態。

### [P01:DR-03] URI-First 虛擬檔案系統 (VFS) 一級介面
- **議題**：業務模組存取檔案時是否需要手動調用 `uri.resolve()` 轉為 OS 實體路徑再對接 `open()` 或 `os` 模組？
- **結論**：`core.uri` 直接升級為一級 **VFS (Virtual File System)** 介面，內建常用的檔案與目錄操作方法（`read_text`, `write_text`, `read_json`, `write_json`, `exists`, `is_file`, `is_dir`, `makedirs`, `remove`, `rmtree`, `listdir`, `copy`, `move` 等），直接接收語意 URI 作為路徑參數。
- **理由**：
  1. 真正實現模組的「**路徑無知性 (Path Ignorance)**」，模組代碼 100% 擺脫對實體路徑與作業系統檔案 API 的依賴；
  2. 統一集中管理所有檔案 I/O，自動保證編碼（UTF-8）、目錄自動創建與原子寫入；
  3. 大幅簡化業務模組開發，代碼可讀性與安全性顯著提升。
