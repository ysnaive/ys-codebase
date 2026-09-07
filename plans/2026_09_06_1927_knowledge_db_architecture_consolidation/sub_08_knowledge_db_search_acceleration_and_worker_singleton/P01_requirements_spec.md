# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_08_knowledge_db_search_acceleration_and_worker_singleton  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | Worker 模組記憶體快取 | `server.worker` 維護 `_module_cache` 字典；首次按需載入目標模組 `scripts/cli.py` 後保留引用，後續派發直接複用已加載模組，杜絕每次請求重複調用 `spec.loader.exec_module`。 | P0 | [P00:DR-01] |
| **FR-02** | KnowledgeEngine 進程單例化 | `knowledge-db/scripts/cli.py` 提供 `get_engine() -> KnowledgeEngine` 模組單例進入點，跨請求複用記憶體中的 `IndexingPipeline` 與子組件，消除重複構造開銷。 | P0 | [P00:DR-01] |
| **FR-03** | 標準事件預熱機制 | Server Worker 就緒後透過 `core.events.broadcast("worker_warming", emit_module="server")` 廣播事件；`knowledge-db/scripts/hook.server.py` 定向預熱倒排索引與向量模型至記憶體。 | P0 | [P00:DR-02] |
| **FR-04** | Watcher 事件驅動 Dirty Flag | 整合 `server` 監聽器被動標記 Dirty；`pipeline.search()` 在未髒時 0ms 跳過全庫 280+ 檔案的實體 `os.stat` 比對。 | P0 | [P00:DR-03] |
| **FR-05** | contributes/server.json 宣告與 core SDK 注入 | 各領域模組在 `contributes/server.json` 純淨宣告 `services`；Server Master 透過 `core.contributes.get("server")` 動態載入並納管，廢除硬編碼與手動檔案走訪。 | P0 | [P00:DR-04] |
| **FR-06** | Background Services 狀態可觀測性 | `ServiceManager` 彙整託管之 ServiceWorker 運行狀態；`server status` 儀表板清楚展示已註冊背景服務之模組、名稱與狀態。 | P1 | [P00:DR-05] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 無 Server 運行時的 CLI 本地執行 | 若無後台常駐進程，`knowledge-db` 自動回退至進程內安全模式，由既有 JIT stat 兜底檢查檔案變更，行為 100% 保持一致。 |
| **EC-02** | 模組加載或 Worker 實例化失敗 | 若 `contributes/server.json` 指定之進入點載入失敗，Server Master 打印結構化 Error 日誌並記錄於 status 為 `FAILED`，嚴禁靜默吞噬。 |
| **EC-03** | 預熱逾時或模型載入失敗 | 預熱過程若遇例外或模型載入失敗，捕捉並降級為懶載入，確保 Worker 仍能正常接受後續請求。 |
| **EC-04** | 檔案變更頻繁觸發熱修補衝突 | Watcher 保持 500ms 防抖聚合；若檢索時恰遇背景熱修補，排他鎖確保讀寫一致性。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 檢索效能 | 常規 Warm 狀態下，純文字檢索響應時間 $\le 20\text{ms}$，混合向量檢索響應時間 $\le 50\text{ms}$。 |
| **NFR-02** | 啟動非阻塞 | 預熱勾點非同步執行，不得阻塞 Server Master 的 Ping 探針與 CLI 首個指令響應。 |
| **NFR-03** | 代碼規範 | 嚴格遵循微內核規範，Server 模組對 domain 模組 0 硬編碼相依，全量透過 `core.contributes` 與 `core.events` 銜接。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!IMPORTANT]`**：
  Server Worker 的 `_module_cache` 必須在 Master 觸發 `restart_worker` 時隨進程徹底重置，杜絕 Python 模組記憶體殘留污染。
- **`[!NOTE]`**：
  `contributes/server.json` 必須嚴格遵循 `core.contributes` 之 `module://<donor>/contributes/<target>.json` 拓撲，禁止私自定義非標準路徑。
