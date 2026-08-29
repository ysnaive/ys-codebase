# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_01_jit_invalidation_and_hot_healing  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1049_knowledge_db_algorithm_optimization`  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 全域聯集去重掃描與符號空間標籤化 | 掃描器 (`FingerprintScanner`) 與打包器 (`SemanticBundler`) 改為對全專案空間聯集 (Union Scope) 進行實體檔案路徑去重，所有檔案 100% 僅讀取與 AST 解析 1 次；符號模型 (`UnifiedSymbol`) 與索引 Posting 記錄其命中的空間集合 (`spaces: List[str]`)。 | P0 | [P00:DR-02] |
| **FR-02** | 單一全域倒排索引與 BM25 統計指標正規化 | 倒排索引 (`InvertedIndex`) 持久化為單一 `unified.index.bin.gz`；`doc_count`、`field_avgdl` 與 IDF 評分基準計算 100% 基於全域無重複真實符號池；查詢時若指定 `--space <name>`，以 O(1) 空間標籤進行過濾。 | P0 | [P00:DR-02] |
| **FR-03** | JIT 查詢時智能變更感知與熱自愈 | 在 `search` 檢索入口實作極低開銷（< 3ms）的 `mtime` / `st_size` JIT 嗅探機制；快照清冊採用極致緊湊之原生二進位格式 (`unified.meta.bin`)，反序列化耗時 < 0.1ms；若檢測到來源檔案有新增、修改或刪除（如開發者剛 pull 代碼），自動在背景觸發索引熱重建（Auto-Rebuild）並更新 `.cache/`，隨後立即回傳 100% 精準的最新搜尋結果。 | P0 | [P00:DR-01] |
| **FR-04** | 熱自愈狀態回饋與 CLI 控制參數 | 觸發背景熱重建時，於 `stderr` 輸出進度與耗時提示（例如 `[knowledge-db:auto-rebuild] Detected changes in source files, hot-rebuilding index... (135ms)`）；CLI 與 API 支援 `--no-auto-rebuild` / `auto_rebuild=False` 參數允許略過檢查。 | P1 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 快取索引缺失（初次使用或手動清空 `.cache/`） | JIT 檢測時若發現 `unified.index.bin.gz` 不存在，自動將其判定為 Dirty，無縫觸發首次全量建置並快取，不報錯。 |
| **EC-02** | 快取二進位索引損毀 (Corrupted Binary Cache) | 若 `unified.index.bin.gz` 解壓縮或載入失敗（如非預期斷電殘留），自動捕獲 Warning 並自愈觸發強制重建覆蓋。 |
| **EC-03** | 檔案被刪除或重新命名 (Deleted/Renamed Files) | JIT 偵測到既有快取指紋中的檔案在磁碟已消失時，自動判定為 Dirty 並自愈重建，徹底自索引中剔除舊符號。 |
| **EC-04** | 空專案或無符合條件檔案 (Empty Workspace) | 若空間內無任何有效程式碼或文檔檔案，安全生成空的 `unified.index.bin.gz`（`doc_count=0`），檢索時安全返回空結果清單，絕不拋出除零例外。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 檢索效能 | 無檔案變動時，JIT `mtime` 比對初篩開銷 $\le 5\text{ ms}$；觸發熱重建耗時 $\le 300\text{ ms}$（千檔規模專案）。 |
| **NFR-02** | Git 零污染與零衝突 | 索引與指紋產物 100% 儲存在 `cache://knowledge-db/`，0 二進位檔案寫入 `storage://`，杜絕任何 Git Merge Conflict。 |
| **NFR-03** | 架構純粹性與向後相容 | 100% 採用純 Python 原生標準庫（Zero External Dependency），現有 CLI 呼叫與 Public API 100% 向後相容。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- > [!IMPORTANT]
  > **空間標籤保留原則**：由全域聯集單一索引取代分空間索引時，必須確保在 `Posting` 與 `UnifiedSymbol` 的 `spaces` 標籤中正確記錄其所屬的所有 Space 名稱，以確保現有 CLI `--space <name>` 查詢功能維持 100% 行為一致性。
- > [!NOTE]
  > **Stderr 分流回饋**：JIT 熱自愈的進度提示文字一律輸出至 `sys.stderr`，絕不污染 `stdout`（確保 `knowledge-db search --json` 的結構化管道輸出不被破壞）。
