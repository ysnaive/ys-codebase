# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：yscb_host_slimming_and_dual_channel_dispatch  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 (還原/自愈下沉)、FR-02 (全域 Help 聚合)、FR-03 (yscb 瘦身)、FR-04 (雙管道派發)、FR-05 (模糊建議) 均已於 P03 定義具體契約。
- [x] **邊界防護**：EC-01 (Server 崩潰降級)、EC-02 (未初始化報錯)、EC-03 (未知模組建議)、EC-04 (無 process 入口報錯) 均具體納入實作考量。
- [x] **依賴純淨**：`yscb.py` 嚴格限制為 100% Python 標準庫，代碼行數鎖定在 200~250 行 (NFR-01, NFR-02)。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/installer.md` | Modify | 記錄 `restore` 與自愈忽略規則機制 |
| **模組手冊** | `docs/core/contributes.md` | Modify | 記錄全域 Help 動態聚合引擎規格 |
| **路線圖結案** | `plans/roadmap/yscb_host_slimming_and_dual_channel_dispatch.md` | Modify | 標記此路線圖已於 sub_07 完整落地 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若常駐 `server` 守護進程在熱轉發過程中當機、假死或輸出畸形 NDJSON，用戶端 CLI 是否會卡死？  
> 💡 **防護解法**：`_try_hot_dispatch` 設定合理的網路與讀取逾時（HTTP 請求與 chunk 讀取均以 try-except 全域包裹），任何異常立即觸發 `return None`，透明無感降級至管道 A 本地進程內冷啟動執行，保障用戶命令 100% 成功交付。

> ❓ **尖銳問題 2**：若用戶在尚未安裝任何模組的全新空專案目錄執行 `python yscb.py --help` 或 `python yscb.py list`，是否會崩潰？  
> 💡 **防護解法**：若未初始化（無 `yscb.config.json` 或無 `core`），`yscb.py` 攔截並給出簡潔友好的 `init <root>` 引導，絕不拋出未捕獲之 Python Traceback。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：於 `source/core/core/installer.py` 實作 `generate_internal_gitignore`、`_restore_module_package` 與 `Installer.cmd_restore`。
- [ ] **TASK-02**：於 `source/core/core/contributes.py` 實作 `print_global_help()`，支援自 `contributes/core.json` 與 `manifest.json` 動態掃描各模組二級子命令。
- [ ] **TASK-03**：於 `source/core/scripts/cli.py` 掛載 `restore` 與 `help` 指令。
- [ ] **TASK-04**：重構 `yscb.py` 入口腳本，剝除冗餘代碼，實裝雙管道路由、Token 注入、模糊拼寫建議與 Exit Code 透傳，行數收斂至 200~250 行。
- [ ] **TASK-05**：編寫單元測試 `source/core/tests/test_installer_restore.py` 與 `source/core/tests/test_contributes_help.py`。
- [ ] **TASK-06**：執行全自動化測試套件與整合驗證。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 業務下沉至微內核**：`cmd_restore` 與 `.gitignore` 自愈維護全面歸屬 `core.installer`，全域動態說明歸屬 `core.contributes`。
- **[P04:DR-02] 宿主腳本極限收斂**：`yscb.py` 行數剛性鎖定在 200 ~ 250 行區間（上限 260 行），僅負責環境注入、自舉與雙管道派發。
