# 語意化需求書 (Semantic Requirements)

> 功能名稱：Module 檔案系統與快取/儲存擴充 (Module File System & Storage Extension)  
> 建立日期：2026-08-23  
> 計畫類型：Feature  
> 所屬主計畫：無  
> 狀態：Discussing  
> 擴充項目：none  
> 模板版本：v1.1  

---

## [類型：Feature] 語意化需求

### 使用情境 (User / Developer Scenarios)

**情境 1：模組擁有標準、統一且受生命週期管理的快取與持久化路徑**
在開發如 `knowledge-db`（符號倒排索引與檔案指紋快取）、`agents-workflow`（IDE 指令清單快取）、或其他編譯/生成型模組時，各模組需要讀寫快取 (Cache)、中繼產物 (Artifacts/Build intermediates) 或持久化狀態 (State/Storage)。目前各模組容易自行硬編碼路徑（如直接寫在模組目錄內或專案根目錄），缺乏標準的目錄劃分與生命週期管理。模組開發者期望透過 Core SDK 提供的標準 API（如 `ProjectContext.get_module_cache_dir(module_name)`、`ProjectContext.get_module_storage_dir(module_name)`），一鍵取得符合規範的獨立路徑。

**情境 2：語意 URI 協定擴充 (Semantic URI Extension)**
開發者或 AI Agent 在操作或設定模組時，可透過標準化的語意 URI（例如 `cache://<module>/<file>` 或專案自訂快取協議）精準定位中繼檔案與快取，無需拼湊脆弱的本機實體相對路徑，且支援透過 `python yscb_cli.py uri resolve` 動態解析與列出。

**情境 3：標準化的快取清理與生命週期維護指令 (Cache Management Tooling)**
專案維護者或 CI/CD 流水線需要統一清理廢棄快取或重置模組狀態時，無需手動尋找各模組產生的快取檔案。透過統一的 CLI 工具（例如 `python yscb_cli.py cache clean [module] [--all]` 或 Core SDK API），能夠安全、原子化且具防呆保護地管理所有模組的快取空間。

---

### API 使用者心智 (Developer Mental Model)

```python
# 1. 模組開發者透過 Core SDK 取得標準檔案系統路徑
from yscb_core import ProjectContext

# 取得該模組專屬的快取目錄 (預設為 .yscb_cache/modules/knowledge-db/)
cache_dir = ProjectContext.get_module_cache_dir("knowledge-db")
cache_file = cache_dir / "index_cache.json"

# 取得該模組專屬的持久化儲存目錄
storage_dir = ProjectContext.get_module_storage_dir("knowledge-db")

# 2. 語意 URI 解析
resolved_path = ProjectContext.resolve_uri("cache://knowledge-db/index_cache.json")
```

---

### 明確的非目標 (Explicit Out of Scope)

- **不涉及雲端物件儲存 (S3/GCS 等)**：聚焦於本機專案檔案系統的標準化目錄與語意協定。
- **不變更既有 2×2 設定檔 (config.project.json / config.local.json) 核心合併機制**：本計畫聚焦於檔案、快取、儲存空間與路徑 API 的規範化。

---

## 開放議題紀錄 (Open Questions)

| # | 議題描述 | 狀態 | 結論 |
|---|---------|------|------|
| 1 | 模組快取目錄結構劃分：是採用統一集中式 `.yscb_cache/modules/<module_name>/`，還是專案根目錄 `.yscb_cache/<module_name>/`？ | 🔄 討論中 | 待討論 |
| 2 | 是否新增 `cache://` 或 `storage://` 等語意 URI 協議支援？ | 🔄 討論中 | 待討論 |
| 3 | 模組卸載 (`installer remove <module>`) 時，是否自動詢問或預設清理該模組的快取目錄？ | 🔄 討論中 | 待討論 |

---

## 討論結束確認 (Discussion Close Gate)

- [ ] **開發者已明確宣告討論結束**，P00 語意需求內容已完整且正確。

---

## 三大分流層級判定 (Three-Tier Phasing Matrix)

| 分流層級 | 判定結果 | 適用場景與判定理由 |
| :--- | :---: | :--- |
| **Level 0：Fast Track** | ☐ | 修改檔案 ≤ 2、不變更 Public API、無跨模組依賴 |
| **Level 1：Full Track** | ☐ | 單一功能語意、單一模組的新增或重構（推薦：涉及 Core SDK 與 Installer 擴充） |
| **Level 2：Full Track $\times$ n<br/>(啟用分類型主計畫 Umbrella)** | ☐ | 多個功能語意/情境、跨模組大型架構重構 |
