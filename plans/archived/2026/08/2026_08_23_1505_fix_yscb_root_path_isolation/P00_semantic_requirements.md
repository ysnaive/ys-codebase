# 語意化需求書 (Semantic Requirements)

> 功能名稱：Module 檔案系統、快取儲存與 yscb:// 統一路徑轉換器完備性架構 (Module File System, Cache & Unified URI Architecture)  
> 建立日期：2026-08-23  
> 計畫類型：Feature & Refactor / Bug Fix  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.1  

---

## 語意概念強定義 (Semantic URI Protocol Axiom)

本專案定義兩大核心語意根協議：
1. **`project://`（專案根協議）**：對應 `ProjectContext.get_project_root()`，代表使用者專案主體空間（存放專案業務源碼、`project://AGENTS.md`、`project://docs/`、`project://plans/` 等）。
2. **`yscb://`（工具庫根協議）**：對應 `ProjectContext.get_yscb_root()`，代表工具庫基底空間（存放 `yscb://modules/`、`yscb://source/`、`yscb://build/`、`yscb://.yscb_cache/` 等）。

兩者在語意上完全解耦，`yscb://` 可相對於 `project://` 指向同層（`./`）或任何子目錄（例如 `./yscb` 或自訂目錄）。

---

## 使用情境與語意需求 (User / Developer Scenarios)

### 情境 1：`yscb://` 工具庫安裝基底隔離與路徑動態解耦 (Path Isolation & Root Decoupling)
- **觸發情境**：使用者在 `project://yscb_config.json` 中宣告 `paths.project_root = "."` 且 `paths.yscb_root = "./yscb"`（或任何自訂工具庫子目錄），並執行 `install`、`build`、`pull`、`remove`、`status` 或 `diff`。
- **期望結果**：
  - 模組運行產物 100% 安裝至 `yscb://modules/<module>`。
  - 模組源碼 100% 安裝至 `yscb://source/<module>`。
  - 模組編譯產物 100% 輸出至 `yscb://build/<module>`。
  - 工具庫中繼快取與升級快照 100% 寫入 `yscb://.yscb_cache/`。
  - 專案主體空間 `project://` 保持純淨，不被工具庫產物散落污染。
  - 若 `yscb://` 目錄尚未存在，Installer 自動遞迴建立目標結構。

### 情境 2：模組專屬命名空間快取與 Core SDK 標準 API (Module-Scoped Caches)
- **觸發情境**：模組（如 `knowledge-db` 符號倒排索引、`agents-workflow` IDE 指令清單快取、自訂分析工具）需要讀寫快取或暫存資料。
- **期望結果**：
  - 各模組不再隨意往快取根目錄散落檔案，而是透過 Core SDK 提供的標準 API `ProjectContext.get_module_cache_dir(module_name)` 取得專屬快取路徑（`yscb://.yscb_cache/modules/<module>/`），自動建立並隔離命名空間。
  - 模組在 `installer update` 或重裝時，快取資料受保護不被覆寫；卸載時可安全清理。

### 情境 3：`cache://` 與 `storage://` 語意 URI 動態解析與 CLI 調度 (Semantic URI Extension)
- **觸發情境**：開發者或 AI Agent 需要定位或讀取模組快取或持久化資料。
- **期望結果**：
  - 支援 `cache://<module>/<file>` 語意協議，自動動態解析為 `yscb://.yscb_cache/modules/<module>/<file>`。
  - 支援 `storage://<module>/<file>` 語意協議，自動動態解析為 `project://.yscb_storage/<module>/<file>`。
  - 支援 `python yscb_cli.py uri resolve cache://knowledge-db/index.json` 直觀解析與列出。

### 情境 4：統一路徑轉換器與 API 完備度校驗 (Unified Path Gateway & Completeness Validation)
- **觸發情境**：系統中所有模組（`core`、`installer`、`cli`、`agents-workflow`、`knowledge-db` 等）存取路徑或進行檔案 I/O。
- **期望結果**：
  - **統一入口約束**：所有模組內部嚴禁私自拼湊未經校驗之本機相對路徑，**100% 必須經由 `ProjectURI` / `ProjectContext` 統一轉換器處理**。
  - **API 接口完備度校驗**：`ProjectURI.resolve()` 與 `ProjectURI.validate()` 內建路徑格式正規化、合法性斷言與 `is_relative_to` 沙盒圍欄防護，杜絕 `..` 越界逃逸。

### 情境 5：統一快取生命週期維護工具鏈與卸載連動 (Cache Lifecycle Tooling)
- **觸發情境**：維護者需要檢視快取佔用或清理廢棄快取；使用者卸載模組。
- **期望結果**：
  - 提供 `python yscb_cli.py cache clean [module] [--all]` 統一清理指定或全部模組快取。
  - 提供 `python yscb_cli.py cache status` 檢視各模組快取佔用與空間狀態。
  - 執行 `installer remove <module>` 時，自動連動清理該模組遺留於 `cache://<module>` 的快取目錄。

### 情境 6：既有快取平滑自動遷移 (Smooth Migration)
- **觸發情境**：既有專案升級至新版 Core SDK 與 Installer。
- **期望結果**：
  - `agents-workflow` 原寫於 `.yscb_cache/ide_manifest_*.json` 之舊版快取，在首次執行時自動平滑遷移至 `yscb://.yscb_cache/modules/agents-workflow/`，保持完全向後相容。

---

## API 使用者心智 (Developer Mental Model)

```python
from yscb_core import ProjectContext, ProjectURI

# 1. 取得工具庫與專案根目錄
proj_root = ProjectContext.get_project_root()  # -> project://
yscb_root = ProjectContext.get_yscb_root()      # -> yscb://

# 2. 定位模組目錄 (自 yscb_root 動態解析，徹底解耦)
mod_dir = ProjectContext.get_module_dir("knowledge-db")

# 3. 透過統一轉換器取得模組專屬命名空間快取目錄
cache_dir = ProjectContext.get_module_cache_dir("knowledge-db")
index_cache = cache_dir / "inverted_index.json"

# 4. 語意 URI 統一轉換與完備度校驗
resolved_cache = ProjectURI.resolve("cache://knowledge-db/inverted_index.json")
is_valid, err = ProjectURI.validate("cache://knowledge-db/inverted_index.json")

# 5. 反向最長前綴精確匹配 (LPM)
uri_str = ProjectURI.to_uri(index_cache)  # -> cache://knowledge-db/inverted_index.json
```

---

## 明確的非目標 (Explicit Out of Scope)

- **不涉及雲端/遠端物件儲存**：聚焦於本地專案與工具庫檔案系統結構與快取。
- **不破壞既有 2×2 設定協定**：維持 `config.project.json` / `config.local.json` 核心合併原則。

---

## 開放議題紀錄 (Open Questions)

| # | 議題描述 | 狀態 | 結論 |
|---|---------|------|------|
| 1 | 當 `yscb://` 指向子目錄且該實體目錄尚不存在時，執行 `install` 是否應自動 `mkdir -p` 建立 `yscb://` 及其子結構？ | ✅ 已解決 | 自動遞迴建立，保證安裝與建置流程流暢無阻礙。 |
| 2 | 當 `yscb_config.json` 位於 `project://`，起手腳本無論自 `project://` 還是 `yscb://` 啟動，是否均應支援自動雙向探測並正確路由？ | ✅ 已解決 | 支援父目錄與子目錄雙向探測設定檔，保證跨目錄無感調度。 |
| 3 | Core SDK 與 CLI 中過去硬編碼的 `"ys_codebase"` 歷史相容候選路徑，是否全面廢除並統一收斂至 `yscb://`？ | ✅ 已解決 | 全面解耦廢除硬編碼字串，一律透過 `ProjectContext.get_yscb_root()` 動態定位。 |
| 4 | 工具庫所有中繼檔案（遠端 Git 快取、backup 升級快照、IDE 清單快取）是否剛性收斂至 `yscb://.yscb_cache/`？ | ✅ 已解決 | 100% 收斂至 `yscb://.yscb_cache/`，並按模組命名空間 (`modules/<module>/`) 隔離。 |
| 5 | 模組卸載 (`installer remove <module>`) 時，是否自動聯動清理該模組的快取目錄？ | ✅ 已解決 | 自動清理 `cache://<module>/`，杜絕孤兒快取殘留。 |
| 6 | 是否強制規定全專案所有模組路徑存取必須 100% 透過 `ProjectURI` / `ProjectContext` 統一轉換器？ | ✅ 已解決 | 是，作為架構鐵律寫入工程規範，並在 API 接口執行完備度與沙盒邊界校驗。 |

---

## 討論結束確認 (Discussion Close Gate)

- [x] **開發者已明確宣告討論結束**，P00 語意需求內容已完整且正確。

---

## 三大分流層級判定 (Three-Tier Phasing Matrix)

| 分流層級 | 判定結果 | 適用場景與判定理由 |
| :--- | :---: | :--- |
| **Level 0：Fast Track** | ☐ | 修改檔案 ≤ 2、不變更 Public API、無跨模組依賴 |
| **Level 1：Full Track** | ☑️ | 本次整合涵蓋 Core SDK (`context.py`, `uri.py`)、`yscb_installer.py`、`yscb_cli.py`、`agents-workflow` 快取遷移、統一路徑轉換器 API 與全新 `cache` CLI，是標準且關鍵的跨模組檔案系統架構升級，**剛性推薦採用 Level 1 (Full Track)** 推進 |
| **Level 2：Full Track $\times$ n<br/>(啟用分類型主計畫 Umbrella)** | ☐ | 多個獨立功能情境或超大型重構。本次為檔案系統與路徑隔離的單一整體主題，Full Track 單一計畫最為精準高效 |
