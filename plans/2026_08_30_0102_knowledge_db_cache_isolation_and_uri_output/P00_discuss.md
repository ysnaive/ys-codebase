# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：knowledge-db 快取隔離零 Fallback 固化與搜尋輸出 URI 連結格式重構  
> 建立日期：2026-08-30  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 計畫類型：Bug Fix / Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 修復路徑洩漏問題：排查發現 `SpaceManager._get_storage_root()` 在 `_safe_resolve_uri("cache://knowledge-db/")` 失敗時，會隱式退化為 `Path("./.cache/knowledge-db")`，導致在專案宿主根目錄產生意外的快取目錄殘留。
  2. 修改 `knowledge-db search` 呈現方式，採用方案 2B：輸出 IDE 原生相容之 `[file:line](file:///...)` Markdown 檔案超連結，使人類開發者可於終端機 Ctrl+Click 直接跳轉，並使 Agent 讀取時獲得 100% 確定之物理路徑，杜絕路徑推算與拼接失誤。
- **核心目標**：
  1. 固化快取根目錄解析機制，嚴格落實《零 Fallback 鐵律》，無上下文且未指定 `storage_dir` 時拋出結構化異常，杜絕任何隱式污染 CWD 的副作用。
  2. 重構 `KnowledgeEngine` 與 CLI 輸出格式化引擎，為搜尋結果（簡易模式、詳細模式、預覽模式與 JSON 模式）注入完整的 `to_file_uri()` 與 `format_file_link()` 支援。
- **邊界排除 (Explicitly Excluded)**：
  - 不變更 BM25 檢索核心演算法與權重計算模型。
  - 不破壞 Public API 既有 `SearchResult` 與 `AggregatedFileResult` 基本資料型態。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] (快取路徑解析零 Fallback 固化)**：
  捨棄寬鬆的本地相對路徑回退，改採嚴格模式。當 `_safe_resolve_uri("cache://knowledge-db/")` 失敗且未傳入自訂 `storage_dir` 時，強制拋出 `InvalidSpaceConfigError`，所有測試環境必須顯式透過 `tempfile` 或 mock 隔離目錄注入。
- **[P00:DR-02] (搜尋輸出採用方案 2B Markdown/IDE 連結格式)**：
  所有 CLI 文字輸出中的檔案位址標頭，統一重構為 `[relative_path:line](file:///absolute_path#Lline)` 格式；JSON 模式則擴充 `file_uri` 欄位。

---

## 3. 開放議題與確認紀錄

- [x] 快取洩漏修復方式確認：採嚴格模式 (Zero Fallback) 拋錯。
- [x] 搜尋路徑呈現方式確認：採方案 2B (IDE 絕對路徑 / Markdown 連結)。
- [x] 計畫執行模式確認：Full Track (Level 1) + `/Auto` 連續推進。
