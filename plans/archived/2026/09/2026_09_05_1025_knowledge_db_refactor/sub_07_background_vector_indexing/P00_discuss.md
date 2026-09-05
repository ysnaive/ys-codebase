# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：knowledge_db_hot_reload_server_and_watcher  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  > 傾向出口 ①，可以連 BM25 和 AST 一起整併，但有考量，我希望藉由一個設定來決定要不要開起這個 server，又不想每次都要手動開，所以我傾向註冊 pre dispatch evt，當 local config enable_hot_reload_server == true 時自動啟動，另外一個參數 hot_reload_server_inactivity_timer_sec 設定多久沒有檔案變更後自動關閉進程，釋放 mem
- **核心目標**：
  1. **專屬 Hot Reload Server 整合建置**：建立後台專屬服務，將 AST 解析、BM25 倒排索引更新、NetworkX 調用圖譜分析與 FastEmbed 向量嵌入全流程一體化整合；監聽專案檔案變更（防抖 500ms），在檔案儲存時即時熱更新二進位快取，達成全語意零等待真熱更新。
  2. **Pre-dispatch Hook 自動自癒啟動**：於 `scripts/hook.core.py` 實作 `on_pre_cli_dispatch`。當組態 `enable_hot_reload_server == True` 且 Server 尚未啟動時，自動於背景非同步拉起 Server 進程，使用者與 Agent 均無需手動執行 `start`。
  3. **閒置超時自動關閉 (Inactivity Auto-Shutdown)**：新增 `hot_reload_server_inactivity_timer_sec`（預設 600 秒）。當指定時間內無任何檔案變更時，Server 進程自動優雅退出並清理 PID/Lock，釋放 250MB~380MB 記憶體。
  4. **第一軌 Standalone JIT 保底相容**：當 `enable_hot_reload_server == False`（預設值、CI 或沙盒跑測環境）時，100% 維持既有 CLI 獨立 JIT 檢索與逾時安全降級機制，保持極致靈活與環境純淨。
- **邊界排除 (Explicitly Excluded)**：
  - 不強制修改 CLI 既有 Public API 簽名。
  - 不在測試沙盒 (`dev test`) 中自動常駐 Server，避免測試進程殘留與跨環境污染。
  - 不強制要求使用者手動管理背景 Server 行程。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 組態命名與預設值規範**：
  - 新增核心組態：
    1. `knowledge-db.enable_hot_reload_server` (布林值，預設 `False`)：決定是否啟用背景常駐真熱更新 Server。
    2. `knowledge-db.hot_reload_server_inactivity_timer_sec` (整數，預設 `600`)：無檔案變更後自動退出進程之超時秒數。
  - 支援命令：`python yscb.py config set knowledge-db enable_hot_reload_server true [--local]`。
- **[P00:DR-02] YSCB Pre-Dispatch 生命週期勾點整合**：
  - 在 `source/knowledge-db/scripts/hook.core.py` 實作 `on_pre_cli_dispatch(ctx)`。
  - 執行前置檢查：若 `enable_hot_reload_server == True`，透過 PID/Lock 探測 Server 存活狀態；若未存活則在背景以 Detached Process 拉起 Server，過程耗時 $<5\text{ms}$，不阻塞當前 CLI 命令。
- **[P00:DR-03] AST + BM25 + Graph + Vector 全流程整併**：
  - Server 內部初始化時載入 `IndexingPipeline`，常駐記憶體模型與解析器。
  - 採用 `watchdog` 監控 `source/`、`docs/`、`plans/` 檔案變更；經 500ms 防抖後，單次走訪完成：
    1. 增量 Tree-sitter AST 解析。
    2. 增量 BM25 倒排索引更新。
    3. 增量 NetworkX 調用圖譜更新。
    4. 增量 FastEmbed 向量嵌入推論。
    5. 原子替換磁碟二進位快取 (`unified.*.bin.gz`)。
- **[P00:DR-04] 閒置超時自動退出與資源回收**：
  - Server 內部維護 `last_activity_timestamp`。
  - 定時器每 10 秒檢查一次：若 `time.time() - last_activity_timestamp > inactivity_timer_sec`，記錄退出日誌，解除 PID 檔案與行程鎖，安全退出進程以釋放記憶體。
- **[P00:DR-05] 測試沙盒與雙軌防干擾隔離**：
  - `dev test` 測試環境強制覆蓋 `enable_hot_reload_server=False`，所有單元與回歸測試嚴格維持 Standalone 記憶體或沙盒內模式，杜絕外洩。

---

## 3. 開放議題與確認紀錄

- [x] 是否已確認採「出口 ①（雙軌整合）」並擴充 sub_07 範疇？（已確認）
- [x] 是否已確認透過 `on_pre_cli_dispatch` 依 config 自動喚醒 Server？（已確認）
- [x] 是否已確認設定 `hot_reload_server_inactivity_timer_sec` 自動超時退出釋放記憶體？（已確認）
