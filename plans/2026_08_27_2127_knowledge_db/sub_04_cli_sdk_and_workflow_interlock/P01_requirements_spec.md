# 需求規格說明書 (Requirements Specification)

> 功能名稱：knowledge-db 子計畫 04: CLI 工具鏈、統一門面 SDK、生態整合與本地端快取儲存遷移 (CLI, Unified SDK, Workflow Interlock & Local Cache Storage Migration)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 / 決策 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | **Python SDK 高階統一門面 (`KnowledgeEngine`)** | 實作 `KnowledgeEngine` 類別，統一整合 `SpaceManager`、`FingerprintScanner`、`ParserRegistry`、`SemanticBundler`、`ThesaurusEngine` 與 `BM25Engine`。 | P0 | [P00:DR-01] |
| **FR-02** | **系統狀態與快取統計 API (`status`)** | 提供 `status() -> Dict[str, Any]`，彙整已註冊空間清單、來源路徑、指紋快取檔案數、同義詞組數與倒排索引快取狀態。 | P0 | [P00:DR-01] |
| **FR-03** | **增量指紋掃描 API (`scan`)** | 提供 `scan(space: Optional[str] = None, force: bool = False) -> Dict[str, ScanDiffResult]`，支援單一空間或全空間聯集增量掃描。 | P0 | [P00:DR-01] |
| **FR-04** | **語意打包與導出 API (`bundle`)** | 提供 `bundle(space: Optional[str] = None, export_path: Optional[Union[str, Path]] = None) -> List[SemanticBundle]`，執行符號提取並原子導出 `.bundle.json`。 | P0 | [P00:DR-01] |
| **FR-05** | **倒排索引快取建置 API (`build_index`)** | 提供 `build_index(space: Optional[str] = None, force: bool = False) -> Dict[str, InvertedIndex]`，建立空間倒排索引並持久化至 `cache://knowledge-db/indices/<space>.index.json`。 | P0 | [P00:DR-01, DR-06] |
| **FR-06** | **多空間語意檢索 API (`search`)** | 提供 `search(query: str, space=None, kinds=None, languages=None, min_score=0.01, limit=10) -> List[SearchResult]`，支援自動懶加載索引或即時建置。 | P0 | [P00:DR-01, DR-02] |
| **FR-07** | **空間快取清理 API (`clean`)** | 提供 `clean(space: Optional[str] = None) -> None`，安全清除指紋快取、Bundle 檔案與倒排索引快取。 | P0 | [P00:DR-01] |
| **FR-08** | **CLI 完整 6 大子指令體系** | 在 `scripts/cli.py` 完整實作 `status`, `scan`, `bundle`, `index`, `search`, `clean` 6 大子指令與結構化美化表格輸出。 | P0 | [P00:DR-02, DR-03] |
| **FR-09** | **模組開發測試自治 Hook (`hook.dev.py`)** | 在 `scripts/hook.dev.py` 實作 `on_test_setup` 與 `on_test_teardown`，支援 YSCB 沙盒測試生命週期環境準備。 | P0 | [P00:DR-01] |
| **FR-10** | **模組元數據與生態連動宣告** | 在 `manifest.json` 完整宣告 `commands` 防呆規範（pros/cons 欄位）與 URI 協議。 | P0 | [P00:DR-01] |
| **FR-11** | **Core 套件解析嚴格化 (Zero Fallback)** | 在 `core.engine.AtomicEngine` 中，當目標模組於 Release 庫、本地 Provider 與遠端 Index 皆不存在時，廢除 dummy fallback 字典，剛性拋出 `ModuleNotFoundError`。 | P0 | [P00:DR-04] |
| **FR-12** | **Build 包物理隔離與精確觸發** | 在 `act_download` 與 Manifest 查詢中，僅當請求之版本明確包含 `build` 標記時才被允許查詢與複製 `module.build://`，常規安裝嚴禁跨界挪用測試建置包。 | P0 | [P00:DR-05] |
| **FR-13** | **資料庫與索引全面本地端化 (`cache://`)** | `SpaceManager` 預設存儲路徑由 `storage://knowledge-db/` 遷移至 `cache://knowledge-db/`，指紋、Bundle 與倒排索引全面寫入本地 `.cache/`，100% 避免 Git 倉庫污染。 | P0 | [P00:DR-06] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | **執行 `search` 時目標空間尚未建立索引** | 自動觸發增量掃描、解析與索引建置（懶索引 Lazy Indexing），透明回傳正確檢索結果。 |
| **EC-02** | **操作未註冊或不存在之空間名稱** | 拋出結構化 `SpaceNotFoundError`，CLI 輸出友好錯誤訊息並回傳 exit code 1。 |
| **EC-03** | **`clean` 清理不存在的快取目錄** | 忽略不存在路徑，安全返回，不拋出 `FileNotFoundError`。 |
| **EC-04** | **`search` 傳入無效 filter 或超出範圍之 limit** | 自動矯正（如 `limit = max(1, limit)`），防禦無效參數。 |
| **EC-05** | **多空間聯集檢索存在重複符號 ID** | 依評分全局去重排序，確保同一符號不重複出現在檢索結果中。 |
| **EC-06** | **CLI 傳入非合法子指令或未知參數** | 印出通用說明手冊並回傳 exit code 1。 |
| **EC-07** | **原子寫入暫存檔目錄權限異常** | 捕獲底層 OSError 並轉換為結構化 `KnowledgeDBError`。 |
| **EC-08** | **大併發或連續呼叫 `build_index`** | 索引檔案以原子替換寫入，確保讀取端不受併發寫入污染。 |
| **EC-09** | **常規安裝未發布或不存在之模組 (`install unreleased_mod`)** | `core` 立即拋出 `ModuleNotFoundError`，中斷依賴求解並輸出清晰錯誤，禁止生成 dummy config 或幽靈安裝。 |
| **EC-10** | **常規安裝請求存在 `build/` 但不存在 `release/` 之模組** | 隔離防禦生效，不掃描 `module.build://`，直接判定未發布並拒絕安裝。 |
| **EC-11** | **本地 `.cache/knowledge-db/` 快取被手動清空** | 系統具備完全自癒能力，執行 `status`、`scan` 或 `search` 時自動透明重建目錄與快取，不引發崩潰。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | **零外部相依 (Zero External Dependency)** | 100% 純 Python 3.9+ 原生標準庫（Zero 3rd-party dependencies）。 |
| **NFR-02** | **模組全量跑測品質守門** | 執行 `python yscb.py dev test knowledge-db` 與 `dev test core` 達成 100% Passed。 |
| **NFR-03** | **模組靜態合規守門** | 執行 `python yscb.py dev check knowledge-db` 達成 100% Passed (0 錯誤)。 |
| **NFR-04** | **1:1 知識庫手冊交付** | 交付完整的模組手冊、架構圖解、CLI 使用手冊與 SDK 快速上手。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- > [!IMPORTANT]
  > **高階 Facade 職責分明**：`KnowledgeEngine` 應作為輕量薄封裝門面，核心邏輯保持在底層子系統（`SpaceManager`, `FingerprintScanner`, `ParserRegistry`, `SemanticBundler`, `BM25Engine`），嚴禁在 Engine 類別中重新實作底層邏輯。
- > [!CAUTION]
  > **本地快取邊界**：資料庫索引與指紋屬於可重建之本地衍生資料，必須 100% 寫入 `cache://knowledge-db/`，嚴禁寫入 `storage://` 導致代碼庫體積膨脹。
