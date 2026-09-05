# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：knowledge_db_hot_reload_server_and_watcher  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 依據 P03：[P03_api_spec.md](./P03_api_spec.md)  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：
  - FR-01 ~ FR-11 在 `P03_api_spec.md` 均具備 1:1 對應之類別、方法簽名與契約定義。
  - FR-09 (`cache://` PID 隔離)、FR-10 (滾動 3 份日誌) 與 FR-11 (版本變更重啟) 完整融入 `HotReloadServer` 設計。
- [x] **邊界防護**：
  - EC-01 (殭屍 PID 清理)、EC-02 (防抖聚合)、EC-03 (原子檔案替換)、EC-05 (SIGTERM 清理) 均在 `daemon.py` 設計具體錯誤處理策略。
  - EC-06 (沙盒環境隔離) 保證 `YSCB_TEST_SANDBOX==1` 時不干擾外部環境。
- [x] **依賴純淨與 NFR 指標**：
  - 僅新增成熟之 `watchdog` 作為可選常駐依賴。
  - `on_pre_cli_dispatch` 短路延遲嚴格控制在 $\le 10\text{ms}$ (NFR-01)。
  - 閒置超時退出後記憶體佔用歸零 (NFR-02)。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/knowledge-db/README.md` | Modify | 補充 `HotReloadServer`、`daemon` CLI 指令與組態說明 |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 登載 `[DN-14]`：專屬 Server、Watchdog 防抖熱修補、Pre-dispatch 勾點喚醒與 3 世代滾動日誌 |
| **全域變更** | `CHANGELOG.md` | Modify | 結案時記錄 sub_07 完成高階變更摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若開發者在編輯器內高頻按下 Ctrl+S 或連續格式化，是否會引發大量重複的向量計算而卡死 CPU？  
> 💡 **防護解法**：實裝 **500ms 防抖計時器 (Debounce Window)**。每一次檔案儲存事件僅更新「最後變更時間」與「待處理路徑集合」，計時器自動延後。僅在完全停止儲存 500ms 後，由單一工作線程序列化調用 Pipeline，一次性完成所有 dirty 檔案的 AST/BM25/Graph/Vector 熱修補。

> ❓ **尖銳問題 2**：若使用者更新了 `knowledge-db` 的代碼（如執行 `install @build`），常駐中的 Server 是否會繼續執行舊代碼產生靜態結構不一致？  
> 💡 **防護解法**：落實 **FR-11 版本感知強制重啟協議**。PID 檔案內建記錄啟動當下的 `knowledge-db` 版本號。在每次 CLI 指令觸發 `on_pre_cli_dispatch` 時，探測若版本不一致，強制優雅終止舊進程並重啟新進程，100% 確保新代碼與新語意生效。

> ❓ **尖銳問題 3**：若機器突然重啟或進程異常崩潰，殘留的 PID 檔案是否會導致未來永遠無法再啟動 Server？  
> 💡 **防護解法**：`is_running()` 採用嚴格的兩階段驗證：首先檢驗 PID 檔案存在，接著以 `os.kill(pid, 0)`（或 Windows 跨平台處理）探測該 PID 是否真實存在，且透過進程名或命令列校驗。若為死進程，自動安全解除並清理殘留 PID 檔，隨後正常拉起新進程。

> ❓ **尖銳問題 4**：若專案中新增/修改了空間定義或 `contribute.json` include 路徑，常駐中的 Server 是否會遺漏新目錄？  
> 💡 **防護解法**：落實 **動態 Space 監聽與 Space 簽名失配自動重啟 (ADR P02:DR-05)**。Watcher 監控目錄 100% 由注入之 `SpaceManager` 動態解算（`resolve_space_include`），嚴禁寫死特定目錄；同時 PID 記錄當前所有空間與路徑之 `spaces_signature`。在每次呼叫 `ensure_running` 時比對空間簽名，若空間定義產生變動，強制重啟 Server 以最新空間目錄重新掛載 Watcher。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：在 `source/knowledge-db/manifest.json` 宣告新增 `"watchdog": ">=4.0.0"` 依賴。
- [ ] **TASK-02**：在 `source/knowledge-db/knowledge_db/config.py` 實作 `enable_hot_reload_server` 與 `hot_reload_server_inactivity_timer_sec` 組態及型態防禦。
- [ ] **TASK-03**：新建 `source/knowledge-db/knowledge_db/daemon.py`，完整實作 `HotReloadServer`、動態 Space 解算 Watcher 監控、防抖熱修補、PID (含空間簽名) 寫入 `cache://`、3 世代滾動日誌、空間/版本失配重啟與閒置超時自動退出。
- [ ] **TASK-04**：新建 `source/knowledge-db/scripts/hook.core.py`，實作 `on_pre_cli_dispatch` 生命週期勾點（支援版本/空間簽名比對與自動拉起）。
- [ ] **TASK-05**：在 `source/knowledge-db/scripts/cli.py` 註冊 `knowledge-db daemon [start|stop|status|watch]` 子命令。
- [ ] **TASK-06**：編寫單元與整合測試套件 `tests/test_hot_reload_server.py`，覆蓋 FT-01~11、動態空間解算、空間簽名失配重啟與 EC-01~09。
- [ ] **TASK-07**：執行全模組回歸驗證（`python3 yscb.py dev test --target=knowledge-db`），確保 100% 通過且 0 Unknown。
- [ ] **TASK-DOC**：更新 `docs/knowledge-db/DESIGN_NOTES.md` (`[DN-14]`, `[DN-15]`) 與 `docs/knowledge-db/README.md`。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 實作順序嚴格遵循依賴拓撲：Manifest $\rightarrow$ Config $\rightarrow$ Daemon $\rightarrow$ Hook $\rightarrow$ CLI $\rightarrow$ Test $\rightarrow$ Docs。
- **[P04:DR-02]** 測試套件全面遵守 `YSCBTestCase` 規範，補齊 `self.mark_passed()`，嚴禁產生 Unknown 狀態。
