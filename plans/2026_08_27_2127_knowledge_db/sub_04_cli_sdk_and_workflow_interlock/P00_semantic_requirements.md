# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：knowledge-db 子計畫 04: CLI 工具鏈、統一門面 SDK、生態整合與本地端快取儲存遷移 (CLI, Unified SDK, Workflow Interlock & Local Cache Storage Migration)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Confirmed  
> 計畫類型：Feature / Optimization  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：knowledge-db 模組所產出之資料庫文件（倒排索引、指紋快取、語意 Bundle 等）集成之資訊量過大，應存放於本地端（Local Cache），避免污染專案持久化目錄。
- **核心目標**：
  1. **資料庫檔案全面本地端化 (`cache://knowledge-db/`)**：
     - 將 `SpaceManager`、`FingerprintScanner`、`SemanticBundler` 與 `KnowledgeEngine` 的預設資料庫儲存目錄由 `storage://knowledge-db/` 遷移至 `cache://knowledge-db/`（對應物理路徑 `yscb://.cache/knowledge-db/`）。
     - 利用 `.cache/` 已由 `.gitignore` 全局忽略的特性，確保龐大的索引與符號 JSON 檔只留存於開發者本地端，不污染專案 Git 倉庫。
  2. **Python SDK 高階統一門面 (`KnowledgeEngine`)**：
     - 統一封裝 `SpaceManager`、`FingerprintScanner`、`ParserRegistry`、`SemanticBundler`、`ThesaurusEngine` 與 `BM25Engine`。
     - 提供 `status()`、`scan()`、`bundle()`、`index()`、`search()`、`clean()` 完整公開 API。
  3. **CLI 完整 6 大工具鏈 (`scripts/cli.py` & `manifest.json`)**：
     - 提供 `status`, `scan`, `bundle`, `index`, `search`, `clean` 子指令與美化終端表格輸出。
  4. **Core 套件解析嚴格化與 Build 包隔離**：
     - 廢除未發布模組之 dummy fallback，查無發布時嚴格拋出 `ModuleNotFoundError`。
     - 嚴格隔離 `module.build://`，僅在 `revision == "build"` 時允許觸發。
  5. **零外部相依 (Zero External Dependency)**：100% 採用純 Python 3.9+ 原生標準庫。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

### [P00:DR-01] 統一門面 SDK API 設計 (`KnowledgeEngine`)
- 提供 `KnowledgeEngine` 作為頂層聚合門面，支援一站式呼叫 `status()`、`scan()`、`bundle()`、`build_index()`、`search()`、`clean()`。

---

### [P00:DR-02] 倒排索引持久化與自動懶加載 (Index Persistence & Lazy Loading)
- 索引儲存路徑：`cache://knowledge-db/indices/<space_name>.index.json`。
- 檢索呼叫 `search()` 時，優先嘗試載入本地快取索引；若無快取或檔案有變更，自動執行增量掃描與索引刷新，保證開箱即用。

---

### [P00:DR-03] CLI 終端格式化美化輸出
- `search` 指令提供彩色/結構化終端表格輸出，標註序號、評分、類型、符號名稱、所屬空間、檔案行號與命中代碼/文檔摘要片段。

---

### [P00:DR-04] Core 模組套件解析嚴格化 (Strict Resolution & Zero Fallback)
- 在 `source/core/core/engine.py` 廢除 dummy fallback 兜底邏輯，未發布或查無模組時剛性拋出 `ModuleNotFoundError`。

---

### [P00:DR-05] Build 包物理隔離與精確版本觸發 (Build Package Isolation & Explicit Trigger)
- 僅在 `version == "build"` 或 `revision == "build"` 時允許查詢與複製 `module.build://`，常規安裝嚴禁跨界讀取測試建置包。

---

### [P00:DR-06] 資料庫與索引檔案全面遷移至本地端 (`cache://knowledge-db/`)
- **決策**：
  1. 將 `manifest.json` 中 `knowledge.storage` 協議目標調整為 `cache://knowledge-db/`。
  2. `SpaceManager._get_storage_root()` 預設解析 `cache://knowledge-db/`（回退至 `./.cache/knowledge-db`）。
  3. 模組產出之空間指紋 (`spaces/<space>/fingerprints.json`)、倒排索引 (`indices/<space>.index.json`) 與預設 Bundle (`bundles/<space>.bundle.json`) 全面寫入本地 `.cache/` 目錄。
  4. 徹底杜絕數萬行 AST 符號與 Postings JSON 檔案污染專案 `storage/` 與 Git 倉庫。

---

## 3. 開放議題與確認紀錄

- [x] **確認 1 (統一門面 API 命名與職責)**：`KnowledgeEngine` 作為頂層 Facade 提供完整純 Python API。
- [x] **確認 2 (CLI 指令集完整度)**：CLI 包含 status, scan, bundle, index, search, clean 6 大完整子指令。
- [x] **確認 3 (索引自動懶加載)**：檢索時若無索引自動進行即時掃描與建立。
- [x] **確認 4 (Core 套件解析嚴格化)**：廢除 dummy fallback，未發布或查無模組時剛性拋錯。
- [x] **確認 5 (Build 包嚴格隔離)**：非 `build` revision 請求嚴禁讀取與使用 `module.build://`。
- [x] **確認 6 (本地端快取儲存遷移)**：資料庫產物全面存入 `cache://knowledge-db/` (`.cache/knowledge-db/`)，杜絕體積膨脹與 Git 污染。
