# 技術調研報告：專屬索引建置 Server 與檔案監控器可行性評估 (Indexing Server & Watcher Feasibility)

> 調研主題：建立專屬索引建置 Server 配合檔案監控器達成真正的熱更新 (Continuous Hot Indexing)  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor (sub_07)  
> 調研狀態：Concluded  
> 模板版本：v1.0  

---

## 1. 調研背景與核心命題 (Background & Problem Statement)

### 1.1 現有 JIT 機制之侷限
在目前的 `knowledge-db` 架構中，索引維護採用**「被動式 JIT (On-Demand JIT)」**機制：
1. 僅在開發者或 Agent 發起檢索（如調用 `knowledge-db search`）時，才觸發 `FingerprintScanner` 進行變更感知。
2. 即使具備 sub_06 實作的動態探針與熔斷機制，當代碼變更符號量大時，首發搜尋仍必須面臨「降級為純 BM25 模式」或「等待數秒前台熱修補」的抉擇。
3. 對於需要頻繁寫代碼並即刻調用知識庫的高頻場景，被動式 JIT 無法達成「寫完代碼的瞬間，向量與圖譜索引已就緒」的零感體驗。

### 1.2 使用者新提案
**「建立專屬索引建置 Server，配合監控器，達成真正的熱更新」**。  
核心意圖是將索引建置從「被動查詢驅動」轉型為「主動檔案事件驅動」，透過獨立後台服務持續保持索引為最新狀態。

---

## 2. 三大候選方案架構對比 (Candidate Architecture Matrix)

針對「背景建置與真熱更新」目標，系統性對比三種潛在落地方案：

| 評估維度 | 方案 A：輕量按需背景進程<br/>*(原 sub_07 提案)* | 方案 B：純常駐 Daemon + Watcher<br/>*(使用者新提案)* | 方案 C：雙軌融合架構 (Hybrid Two-Tier)<br/>*(⭐️ 推薦落地方案)* |
| :--- | :--- | :--- | :--- |
| **觸發模式** | 被動觸發（搜尋逾時後非同步派發） | 主動觸發（監控器感知檔案 Save 即時觸發） | **主動為主、被動為輔**（Daemon 運行時即時主動；未運行時平滑回退 Standalone JIT） |
| **首查檢索體驗** | 首查落入現有快取/BM25，次查生效 | **首查即刻享有最新向量與圖譜**（sub-10ms 響應） | **Daemon 開啟時首查即最新**；未啟動時保有 JIT 保底 |
| **記憶體佔用** | 0 MB（平日不常駐，完成即退出） | 250MB ~ 380MB（FastEmbed ONNX 常駐） | 依使用者偏好隨選（預設按需，支援 `daemon start` 常駐） |
| **外部相依性** | 零新增（使用標準函式庫 `subprocess`） | 需新增 `watchdog` 依賴至 `pip_dependencies` | 需新增 `watchdog` 依賴（或內建簡易 Poller） |
| **Dev Container / VM 穩定度**| 100% 免疫虛擬化檔案系統事件遺失 | virtiofs / Docker 掛載下需防範 inotify 遺失 | 透過防抖 (Debounce) + Polling 保底機制達成 100% 穩定 |
| **維護與除錯複雜度** | 極低（~60 行代碼） | 高（需治理 Daemon 生命週期、殭屍進程、IPC） | 中等（採用「檔案層單向同步」解耦，免去複雜 IPC） |
| **CI / 自動化測試衝擊** | 零衝擊 | 需於測試沙盒中明確阻斷常駐進程 | 沙盒與測試環境維持純淨 Standalone 模式，零干擾 |

---

## 3. 關鍵維度深度論證 (In-Depth Technical Feasibility Analysis)

### 3.1 檔案監控技術選型 (Watcher Engine)
- **現況**：Python 標準函式庫並無跨平台檔案監聽器。業界標準為成熟的 `watchdog` 套件（支援 Linux inotify、macOS FSEvents、Windows ReadDirectoryChangesW）。
- **容器/沙盒坑點 (Virtiofs & Docker Bind Mounts)**：
  - 在 VS Code Remote Containers、Docker 或 WSL2 等虛擬化環境中，原生檔案系統事件可能延遲或丟失。
  - **解法**：監控器必須設計 **300ms ~ 500ms 防抖緩衝區 (Debounce Window)**，將高頻連續儲存（如編輯器格式化或 Git 批次切換）聚合為單次增量修補；並在配置中支援 `Observer` 與 `PollingObserver` 雙向切換。

### 3.2 服務架構與通訊解耦模式 (Decoupled Sync vs IPC)
常駐 Server 與前台 CLI 之間有兩種架構解耦路徑：

```mermaid
graph TD
    subgraph "模式 1: 檔案層單向同步 (File-Level Sync) ⭐️ 推薦"
        W1[Watchdog 監控器] -->|檔案變更| S1[專屬 Server Daemon]
        S1 -->|AST / 圖譜 / 向量計算| S1
        S1 -->|原子替換| D1[(磁碟二進位快取<br/>unified.*.bin.gz)]
        C1[CLI knowledge-db] -->|mmap / 唯讀載入| D1
    end

    subgraph "模式 2: IPC 記憶體直連 (IPC Socket / gRPC)"
        W2[Watchdog 監控器] --> S2[專屬 Server Daemon<br/>(常駐記憶體模型)]
        C2[CLI knowledge-db] -->|Unix Domain Socket| S2
        S2 -->|回傳搜尋結果| C2
    end
```

- **模式 1（檔案層單向同步）**：
  - Server Daemon 僅作為「背景索引生產者」，完成計算後以臨時檔原子替換磁碟二進位檔案。
  - 前台 CLI 維持純粹的「快取消費者」，直接讀取磁碟快取，**無需建立任何 Socket 連線或網路端口**。
  - **優勢**：極致強韌！即便 Daemon 當機或未啟動，CLI 檢索邏輯 100% 正常運作，零跨進程連線死鎖風險。
- **模式 2（IPC 記憶體直連）**：
  - CLI 將搜尋 Query 透過 Socket 發送給 Server，直接於 Server 記憶體執行推論與排序。
  - **缺點**：通訊握手、序列化、連線逾時處理、跨平台具名管道相容性極其複雜，對 CLI 輕量門面契約侵入過大。

### 3.3 並行讀寫安全與一致性保證
1. **原子檔案替換 (Atomic Swap)**：
   - Server 產生新向量與倒排索引時，一律先寫入 `unified.vectors.bin.gz.tmp`，寫入完成校驗無誤後調用 `os.replace` 進行原子替換。前台 CLI 在任何時刻讀取檔案，只會讀到前一版本完整檔或新版本完整檔，絕對不會讀到破損的半成品。
2. **進程互斥鎖 (Daemon PID Lock)**：
   - 在 `storage/indices/knowledge_db_daemon.pid` 與 `.lock` 標記運行狀態，防止重複啟動多個 Daemon 實例。

### 3.4 資源消耗與生命週期治理
- **RAM 佔用實測評估**：
  - Python runtime + Tree-sitter + NetworkX：~60MB
  - FastEmbed ONNX Runtime (`bge-small-zh-v1.5`)：~200MB ~ 250MB
  - **常駐總量約 260MB ~ 320MB**。在現代開發機（8GB~64GB RAM）上極其輕量，但在 512MB 低配虛擬機上較為吃緊。
- **治理決策**：
  - Daemon 必須為 **完全可選 (Opt-in)**，預設不強制常駐。
  - 提供直觀的 CLI 生命週期控制指令：
    - `python yscb.py knowledge-db daemon start`（背景啟動）
    - `python yscb.py knowledge-db daemon stop`（安全停止）
    - `python yscb.py knowledge-db daemon status`（狀態與心跳監控）
    - `python yscb.py knowledge-db watch`（前台監視模式，方便除錯）

---

## 4. 客觀結論與推薦落地路徑 (Recommendation)

### 4.1 結論：強烈推薦採「方案 C：雙軌融合架構 (Hybrid Architecture)」
方案 B（專屬 Server + 監控器）在技術上**完全可行**，且能徹底達成真正的「零感熱更新」。然而，若全面捨棄 Standalone 模式，會造成 CI 環境、沙盒測試與輕量設備的過度依賴與脆弱性。

**最佳實踐是「雙軌融合」**：
1. **底座（第一軌：CLI Standalone JIT）**：
   - 保留既有獨立執行能力，並實裝輕量逾時背景分發（原 sub_07 核心），作為永遠可靠的保底層。
2. **飛輪（第二軌：專屬 Daemon + Watcher）**：
   - 引入 `watchdog`，新增 `knowledge_db/daemon.py` 與 `knowledge_db/watcher.py`。
   - 提供 `knowledge-db daemon start`，在本地開發時啟動專屬 Server。
   - 監控檔案變更 ➔ 防抖 500ms ➔ 記憶體增量熱修補 ➔ 原子寫入磁碟 ➔ 前台查詢零等待。

---

## 5. 出口路徑與下一步決策 (Decision Gates)

請開發者評估並裁定後續落地方式：

1. **選項 1（雙軌全功能落地 - 推薦）**：
   - 將 `sub_07` 範疇重構擴充為「向量索引背景熱更新與專屬 Daemon Watcher 整合」，同時交付 CLI 輕量背景安全網與專屬 Daemon 監控服務。
2. **選項 2（分階段推進）**：
   - `sub_07` 先完成輕量背景任務分發與現有資料優先檢索（快速交付，~100行代碼）。
   - 另闢 `sub_08` 專題專責打造「專屬 Indexing Daemon Server 與 Watchdog 監控器」。
3. **選項 3（純 Daemon 模式）**：
   - 放棄單次查詢逾時分發，全力實作常駐 Daemon Server 與 Watcher 機制。
