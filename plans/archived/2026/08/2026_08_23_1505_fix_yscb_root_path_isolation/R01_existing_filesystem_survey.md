# 技術調研報告：YS-Codebase 現有檔案系統、快取儲存與 yscb:// 隔離架構調研 (Filesystem & Path Survey)

> 功能名稱：Module 檔案系統與 yscb:// 路徑隔離架構 (Module File System & Path Isolation System)  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 狀態：Concluded  
> 擴充項目：none  
> 模板版本：v1.0  

---

## 📌 1. 調研背景與目標

隨著 YS-Codebase 生態系統的演進，各模組（如 `agents-workflow` 的 IDE 快取、即將建立的 `knowledge-db` 倒排索引快取與同義詞庫、以及未來的自訂編譯/分析模組）對「快取 (Cache)」、「持久化儲存 (Storage/Data)」與「中繼產物 (Artifacts)」的管理需求急劇上升。同時，在使用者測試中發現當 `yscb_root`（`yscb://`）與專案根目錄（`project://`）分離配置時，安裝器與 CLI 存在嚴重的路徑脫鉤與寫死硬編碼問題。

本調研報告對系統現有的**目錄拓撲、Core SDK 路徑 API、語意 URI 協定、2×2 設定矩陣與 Installer 生命週期**進行地毯式盤點，分析痛點並提出標準化的模組檔案系統擴充與路徑隔離演進方案。

---

## 🏛️ 2. 現有檔案系統四層拓撲與盤點矩陣

```text
[四層檔案系統拓撲架構]

層級 ①：專案根目錄與全域配置空間 (Project Space: project://)
  ├── yscb_config.json / yscb_config.local.json
  ├── AGENTS.md
  └── docs/ / plans/ / extensions/

層級 ②：工具庫基底與模組空間 (Codebase Space: yscb://)
  ├── source/<module>/        (源碼 SSOT)
  ├── build/<module>/         (發布物)
  └── modules/<module>/       (安裝運行物)

層級 ③：語意化業務空間 (Semantic Domain Space)
  ├── plans://                (活躍計畫)
  ├── archive://              (封存計畫)
  ├── docs://                 (系統知識庫)
  └── sop_ext://              (SOP Extension 擴充)

層級 ④：中繼快取與暫存空間 (Cache Space: yscb://.yscb_cache/)
  ├── git_cache/              (遠端 Git 快取)
  ├── backup/                 (模組升級快照)
  └── modules/                (模組專屬命名空間快取)
```

### 現有路徑與檔案職責清單

| 目錄 / 檔案路徑 | 語意協議 | 讀寫模式 | 核心職責與現況行為 |
| :--- | :---: | :---: | :--- |
| `yscb_config.json` | `project://` | 讀寫 (Git 追蹤) | 記錄專案路徑 (`paths`)、遠端倉庫 (`remote`)、已安裝模組清單 (`installed_modules`)。 |
| `yscb_config.local.json` | `project://` | 讀寫 (Git 忽略) | 個人本機覆寫配置。 |
| `source/<module>/` | `yscb://` | 唯讀/開發 (Git 追蹤) | 模組源碼與單一事實來源 (SSOT)。 |
| `modules/<module>/` | `yscb://` | 讀寫 (Git 忽略) | 模組安裝運行空間（包含具體化 SOP 與 Hook 腳本）。 |
| `build/<module>/` | `yscb://` | 覆寫 (Git 追蹤) | `installer build` 封裝產物。 |
| `plans/` | `plans://` | 讀寫 (Git 追蹤) | 進行中 Dev Plan 目錄（由 `config.project.json` 之 `paths.plans_dir` 定義）。 |
| `archive_plans/` | `archive://` | 讀寫 (Git 追蹤) | 歷史計畫封存目錄（由 `config.project.json` 之 `paths.archive_dir` 定義）。 |
| `docs/` | `docs://` | 讀寫 (Git 追蹤) | 專案客觀知識庫（由 `config.project.json` 之 `paths.docs_dir` 定義）。 |
| `extensions/` | `sop_ext://` | 讀寫 (Git 追蹤) | 專案自定義 SOP Extension（由 `config.project.json` 之 `paths.extensions_dir` 定義）。 |
| `.yscb_cache/` | `yscb://` | 讀寫 (Git 忽略) | 中繼快取總根目錄（包含 `git_cache/`、`backup/` 與各模組私有快取）。 |

---

## 🔍 3. 現有路徑解析與語意協定機制剖析

### 3.1 Core SDK (`yscb_core.context.ProjectContext`)
目前 `ProjectContext` 提供的定位 API 包括：
- `get_project_root(start_dir) -> Path`：自動向上尋找 `yscb_config.json` 或 `.git`。
- `get_yscb_root(start_dir) -> Path`：定位工具庫根目錄。
- `get_module_dir(module_name) -> Path`：定位 `modules/<name>` 或 `source/<name>`。
- `resolve(rel_path) -> Path`：解析相對路徑或轉發語意 URI。
- `get_all_installed_manifests()` / `get_contributions(namespace)`：跨模組清單掃描。

### 3.2 語意 URI 系統 (`yscb_core.uri.ProjectURI`)
目前已註冊之協議包括：
- `project://<path>` ➔ `ProjectContext.get_project_root()`
- `yscb://<path>` ➔ `ProjectContext.get_yscb_root()`
- `plans://<path>` ➔ `agents-workflow` 之 `paths.plans_dir`
- `archive://<path>` ➔ `agents-workflow` 之 `paths.archive_dir`
- `docs://<path>` ➔ `agents-workflow` 之 `paths.docs_dir`
- `sop_ext://<path>` ➔ `agents-workflow` 之 `paths.extensions_dir`

---

## ⚠️ 4. 現況痛點與架構缺陷分析 (Pain Points & Gaps)

```text
[當前架構缺陷圖示]
.yscb_cache/
  ├── git_cache/                  ← Installer 專用
  ├── backup/                     ← Installer 專用
  └── ide_manifest_*.json         ← agents-workflow 寫在快取根目錄，未命名空間隔離
  └── (knowledge_db_cache.json?) ← 🚨 即將面臨：各模組直接往 .yscb_cache 根目錄亂塞快取！
```

### 痛點 1：`yscb://` 語意協定隔離失效（安裝基底脫鉤）
- 當 `yscb_config.json` 中配置 `paths.yscb_root = "./yscb"` 時，Installer (`ModuleManager`) 仍寫死將 `modules/`、`source/` 安裝在 `self.root_dir`（即 `project://`），導致工具庫檔案污染使用者專案根目錄。
- `ConfigManager.get_yscb_root()` 未讀取設定檔中宣告的 `paths.yscb_root`，無條件回傳當前目錄。
- `ProjectContext.get_module_dir()` 與 `yscb_cli.py` 依賴寫死候選路徑（硬編碼 `"ys_codebase"`），未透過 `get_yscb_root()` 動態定位。

### 痛點 2：模組私有快取空間缺乏命名空間隔離 (Wildcat Caches)
- `agents-workflow` 目前在 `ide_sync.py` 中直接寫入快取根目錄。
- 當新增 `knowledge-db`（`cache.json`）或其他多個模組時，`.yscb_cache` 根目錄將充斥各模組散落的檔案，極易引發檔名命名碰撞，且無法依模組進行單獨清理。

### 痛點 3：Core SDK 缺乏 Module-Scoped 快取與儲存 API
- `ProjectContext` 僅提供 `get_module_dir(module_name)`（指向代碼安裝目錄 `modules/<module>/`）。
- 若模組把快取寫在 `modules/<module>/` 內，當執行 `installer update` 或 `installer install --force`（全量覆寫目錄）時，快取資料將被意外刪除；反之若寫在專案根目錄又會污染 Git。

### 痛點 4：語意 URI 缺乏 `cache://` 通道
- 開發者無法使用 `python yscb_cli.py uri resolve cache://knowledge-db/index.json` 直觀定位快取檔案。

### 痛點 5：生命週期與清理工具鏈缺位
- 缺乏標準的 `python yscb_cli.py cache clean [module] [--all]` 指令。
- 當執行 `installer remove <module>` 卸載模組時，無法自動或提示清理該模組遺留在 `.yscb_cache/` 的孤兒快取。

---

## 💡 5. 模組檔案系統擴充演進方案 (Architectural Proposals)

### 方案：集中式命名空間快取與 yscb:// 完全解耦架構

```text
yscb:// (工具庫根目錄，可為 ./ 或 ./yscb 等)
├── modules/                      # 模組運行產物
│   ├── core/
│   └── agents-workflow/
├── source/                       # 模組源碼 (開發者模式)
├── build/                        # 模組打包發布物
└── .yscb_cache/                  # 工具庫中繼快取 (受 .gitignore 忽略)
    ├── installer/                # Installer 專用
    │   ├── git_cache/
    │   └── backup/
    └── modules/                  # 模組專屬命名空間快取 (Module Caches)
        ├── agents-workflow/      # agents-workflow 專用快取
        │   └── ide_manifest_antigravity.json
        └── knowledge-db/         # knowledge-db 專用快取
            ├── index_cache.json
            └── hash_registry.json
```

#### API 設計演進：
```python
# 1. 取得模組快取目錄 (自動建立目錄，路徑：yscb://.yscb_cache/modules/<module_name>/)
cache_dir = ProjectContext.get_module_cache_dir("knowledge-db")

# 2. 取得系統全域快取根目錄 (路徑：yscb://.yscb_cache/)
cache_root = ProjectContext.get_cache_root()

# 3. 取得工具庫根目錄 (正確解析 paths.yscb_root)
yscb_root = ProjectContext.get_yscb_root()

# 4. 取得模組目錄 (自 yscb_root 動態定位)
module_dir = ProjectContext.get_module_dir("knowledge-db")
```

#### 語意 URI 擴充：
- `cache://<module>/<path>` ➔ 自動解析至 `yscb://.yscb_cache/modules/<module>/<path>`
- `yscb://<path>` ➔ 精準解析至 `ProjectContext.get_yscb_root() / <path>`

#### CLI 工具鏈擴充：
- `python yscb_cli.py cache clean [module] [--all]`：清理指定模組或全域快取。
- `python yscb_cli.py cache status`：檢視各模組快取佔用與空間狀態。
- `installer remove <module>`：卸載模組時自動聯動清理 `cache://<module>` 快取。

---

## 🎯 6. 調研結論與後續建議

1. **整合效益**：將 `2026_08_23_1404_module_filesystem_extension` 與 `fix_yscb_root_path_isolation` 整合為單一整體計畫，能夠一次性徹底解決工具庫安裝路徑、模組目錄定位、快取命名空間、語意 URI 與生命週期清理的全鏈條問題。
2. **影響範圍**：
   - `core` 模組：`ProjectContext`、`ProjectURI`、`ConfigManager`。
   - `installer` & `cli`：`yscb_installer.py`、`yscb_cli.py`。
   - `agents-workflow` 模組：`ide_sync.py` 快取路徑遷移。
3. **建議推進軌道**：採用 **Level 1 (Full Track)** 完整推進本計畫。
