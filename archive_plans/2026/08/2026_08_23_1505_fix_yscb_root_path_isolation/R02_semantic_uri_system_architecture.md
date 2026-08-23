# 技術調研報告：YS-Codebase 現有語意協議盤點與 URI 系統完備性演進 (Semantic URI System Architecture)

> 功能名稱：Semantic URI 語意協議系統完備性升級 (Comprehensive Semantic URI System)  
> 建立日期：2026-08-23  
> 所屬主計畫：2026_08_23_1505_fix_yscb_root_path_isolation  
> 狀態：Concluded  
> 擴充項目：none  
> 模板版本：v1.0  

---

## 📌 1. 從需求出發：現有 6 大語意協議與語意定義盤點

YS-Codebase 目前於系統核心與已安裝模組中註冊了 6 個語意 URI 協議。從開發者、AI Agent 與工具庫維護者的真實使用需求出發，其語意職責、邊界與實體對應關係如下：

### 1.1 現有協議完整矩陣 (Current Schemes Inventory)

| 協議 (Scheme) | 語意核心定義 (Semantic Role) | 誰在何種情境使用 (User Scenario) | 實體解析來源 (Resolution Target) | 治理層級 |
| :--- | :--- | :--- | :--- | :---: |
| **`project://`** | **專案使用者主體空間 (Project Root)** | • AI Agent 存取專案全域根目錄檔案<br>• 定位業務源碼、`AGENTS.md`、專案設定檔 | `ProjectContext.get_project_root()`<br>(依 `yscb_config.json` 或 `.git` 向上搜尋) | **Core 保留字**<br>(唯讀不可覆寫) |
| **`yscb://`** | **工具庫安裝與管理基底 (YSCB Root)** | • Installer/CLI 定位工具庫資產<br>• 存放 `modules/`、`source/`、`build/`、`.yscb_cache/` | `ProjectContext.get_yscb_root()`<br>(依 `paths.yscb_root` 解析絕對路徑) | **Core 保留字**<br>(唯讀不可覆寫) |
| **`plans://`** | **活躍進行中開發計畫空間 (Active Plans)** | • Agent 開立新計畫目錄、產出 P00~P07<br>• `ContextInit` / `Continue` 掃描進行中進度 | `agents-workflow` 模組之 `paths.plans_dir`<br>(預設為 `project://plans/`) | **模組宣告**<br>(contributes) |
| **`archive://`** | **歷史封存開發計畫空間 (Archived Plans)** | • CLI 執行計畫歸檔 (`archive`)<br>• 檢索歷史決策紀錄 (DR) 與架構演進脈絡 | `agents-workflow` 模組之 `paths.archive_dir`<br>(預設為 `project://archive_plans/`) | **模組宣告**<br>(contributes) |
| **`docs://`** | **專案客觀知識庫空間 (Knowledge Base)** | • 查閱宏觀架構手冊、模組 Topic Docs、`DESIGN_NOTES.md`<br>• 維護 7 大抽象知識維度 | `agents-workflow` 模組之 `paths.docs_dir`<br>(預設為 `project://docs/`) | **模組宣告**<br>(contributes) |
| **`sop_ext://`** | **SOP 擴充清單與驗證外掛庫 (SOP Extensions)** | • Phase 1 擴充探測 (`ext list/show`)<br>• Review 階段調度專案特化 Verifier 腳本 | `agents-workflow` 模組之 `paths.extensions_dir`<br>(預設為 `project://extensions/`) | **模組宣告**<br>(contributes) |

---

## 🔍 2. 現有協議的語意邊界與痛點分析 (Gaps & Requirements)

```text
[現有協議 vs. 需求缺口]
現有體系 (6 個協議)
  ├── 空間協議: project://, yscb://
  └── 領域協議: plans://, archive://, docs://, sop_ext:// (全屬 agents-workflow)

需求缺口 (即將面臨的模組化痛點):
  1. 缺乏模組專屬快取通道 ➔ 如 knowledge-db 的倒排索引快取放哪？需 cache://<module>/<file>
  2. 缺乏模組持久化儲存通道 ➔ 如自訂模組的獨立資料庫/狀態檔放哪？需 storage://<module>/<file>
  3. yscb:// 與 project:// 脫鉤 ➔ 當 yscb:// 為子目錄時，現有解析邏輯會退化混淆
  4. 缺乏沙盒圍欄防護 ➔ 透過 docs://../../ 仍可能逃逸出專案空間
  5. 缺乏統一入口強制性約束 ➔ 部分模組自行拼接路徑，未 100% 透過統一轉換器
```

### 缺口 1：缺乏模組命名空間快取協議 (`cache://`)
- **需求**：當建立 `knowledge-db` 或其他編譯/生成模組時，模組需要讀寫快取。若沒有 `cache://<module>/...`，模組只能自己硬拼路徑，容易引發名稱衝突與 Git 污染。

### 缺口 2：缺乏模組持久化儲存協議 (`storage://`)
- **需求**：某些模組需要存放專案級的本機持久化資料（非暫存快取），需有標準的 `storage://<module>/...` 映射至 `project://.yscb_storage/<module>/`。

### 缺口 3：空間協議 `yscb://` 實作脫鉤
- **需求**：當 `yscb://` 設為子目錄（如 `./yscb`）時，所有工具庫內部操作（`modules/`、`source/`、`.yscb_cache/`）必須嚴格錨定在 `yscb://`，不能散落至 `project://`。

### 缺口 4：缺少最長前綴反向匹配 (LPM) 與沙盒圍欄保護
- **需求**：`to_uri(path)` 必須能自動挑選最精準的 Scheme（如 `docs://` 優先於 `project://docs/`），且 `resolve(uri)` 必須嚴格阻斷越界逃逸。

### 缺口 5：路徑處理未強制收斂至統一轉換器 (API Gateway Invariant)
- **需求**：嚴禁任何模組自定義或拼湊脆弱的相對路徑查找專案與工具庫資產，**所有路徑處理必須 100% 透過 `ProjectURI` / `ProjectContext` 統一轉換器**，且轉換器 API 必須內建完備度與邊界校驗。

---

## 🏛️ 3. 升級後完備協議體系與 API 統一轉換器架構 (Target State)

### 3.1 協議矩陣 (Protocol Matrix)

```text
+---------------------------------------------------------------------------------------------------------+
|                                    YS-Codebase 完備語意 URI 體系                                        |
+-------------------+----------------------+------------------------------------+-------------------------+
| 協議類別          | Scheme 語法          | 語意職責與實體對應                 | 治理歸屬                |
+-------------------+----------------------+------------------------------------+-------------------------+
| ① 空間根協議      | project://<path>     | 專案使用者主體空間 (Project Root)  | Core 核心保留           |
|    (Spatial)      | yscb://<path>        | 工具庫安裝管理基底 (YSCB Root)     | (不可被覆寫)            |
+-------------------+----------------------+------------------------------------+-------------------------+
| ② 資源快取協議    | cache://<mod>/<path> | 模組專屬快取空間                   | Core 泛型協議           |
|    (Cache)        |                      | (yscb://.yscb_cache/modules/<mod>/)| (自動支援所有模組)      |
+-------------------+----------------------+------------------------------------+-------------------------+
| ③ 持久儲存協議    | storage://<mod>/<p>  | 模組專屬持久化空間                 | Core 泛型協議           |
|    (Storage)      |                      | (project://.yscb_storage/<mod>/)   | (專案級持久化)          |
+-------------------+----------------------+------------------------------------+-------------------------+
| ④ 領域設定協議    | plans://<path>       | 活躍開發計畫目錄                   | agents-workflow 模組    |
|    (Domain Config)| archive://<path>     | 歷史歸檔計畫目錄                   | (經由 manifest 宣告)    |
|                   | docs://<path>        | 系統客觀知識庫目錄                 |                         |
|                   | sop_ext://<path>     | SOP 擴充清單目錄                   |                         |
+-------------------+----------------------+------------------------------------+-------------------------+
```

---

### 3.2 統一路徑轉換器 API 契約與完備度校驗 (Unified Converter Gateway)

在 Core SDK 的 `ProjectURI` 與 `ProjectContext` 建立剛性閘門，所有模組與腳本必須遵照以下 API 契約：

```python
from yscb_core import ProjectURI, ProjectContext

# ── 1. 統一解析閘門 (嚴格型態、正規化、沙盒圍欄防護) ──────────────
# 支援語意 URI、字串路徑、Path 物件，內部自動統一解析與安全校驗
path: Path = ProjectURI.resolve("docs://_project/STANDARDS.md")
cache_p: Path = ProjectURI.resolve("cache://knowledge-db/index.json")

# ── 2. 嚴格邊界與完備度校驗 (Completeness & Sanity Validation) ──
# 驗證傳入 URI 格式、Scheme 是否有效、實體目錄是否已初始化且未越界
is_valid, err_msg = ProjectURI.validate("cache://knowledge-db/data.bin")

# ── 3. 雙向最長前綴精確轉換 (LPM) ──────────────────────────────
# 實體絕對路徑自動反向轉為最精確之語意 URI
uri_str: str = ProjectURI.to_uri(path)

# ── 4. 高階直讀直寫 (原子化、自動建立父目錄、編碼防呆) ──────────
content: str = ProjectURI.read_text("project://AGENTS.md", encoding="utf-8")
ProjectURI.write_text("cache://knowledge-db/meta.json", json_data, auto_mkdir=True)
```

---

## 🎯 4. 結論與架構裁決 (Architectural Decisions)

1. **[ARCH:DR-URI-01] 語意 URI 統一入口鐵律**：
   全專案所有模組（`core`、`installer`、`cli`、`agents-workflow`、`knowledge-db` 等）凡涉及檔案路徑定位、中繼檔案存取或設定讀取，**一律嚴格透過 `ProjectURI` / `ProjectContext` 統一轉換器 API 解析**，嚴禁在模組內部私自拼接未經校驗之相對路徑。
2. **[ARCH:DR-URI-02] 完備度校驗與沙盒防護**：
   `ProjectURI.resolve()` 內建路徑正規化與 `is_relative_to` 圍欄檢查，任何越界逃逸均立即拋出 `SecurityError` 或標記為 `!undefined`。
3. **[ARCH:DR-URI-03] 協議生態向下相容與全域擴充**：
   保持既有 6 大協議無損，並以泛型方式原生接入 `cache://` 與 `storage://`。
