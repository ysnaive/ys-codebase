# 需求規格說明書 (Requirements Specification)

> 功能名稱：server_console_config  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 組態整合與預設值 | 整合 `core.config.get("server", "enable_console", default=False)`，支援 `enable_console: bool` 組態，預設值為 `False` | P0 | [P00:DR-01] |
| **FR-02** | 啟動模式決策矩陣 | `server start` 實作優先級分流：CLI 顯式參數（`--console` / `--daemon`）> `core.config` 設定 > 內建預設值 `False` | P0 | [P00:DR-02] |
| **FR-03** | CLI 互斥與防呆解析 | CLI 參數解析器採用 `add_mutually_exclusive_group()` 管理 `--console` 與 `--daemon`，`default=None` 以便識別 CLI 顯式輸入 | P0 | [P00:DR-03] |
| **FR-04** | 前台 Console 模式 | 決策為 `console=True` 時，以 `MasterSupervisor.start(foreground=True)` 於當前終端前台阻塞運行，即時印出日誌供除錯 | P0 | [P00:DR-02] |
| **FR-05** | 背景脫鉤模式 | 決策為 `console=False` 時，以 `spawn_detached` 背景靜默運行，輸出重定向至 `DEVNULL` | P0 | [P00:DR-02] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | CLI 同時指定 `--console` 與 `--daemon` | 由 `argparse.MutuallyExclusiveGroup` 在解析階段直接攔截並拋出參數衝突錯誤 |
| **EC-02** | 組態檔之 `enable_console` 為字串或整數型別 | 防禦性轉換：若為字串 `"true"`、`"1"` 視為 `True`，其餘非布林非法值防禦回退 `False` |
| **EC-03** | Server 已處於運行中狀態 | 無論前台或背景模式，啟動前透過 `_read_daemon_state` 與 `is_process_alive` 探測，已運行直接印出提示並返回 `0` |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零外部依賴 | 100% 複用微內核 `core.config` 與 Python 標準庫，不引入任何第三方套件 |
| **NFR-02** | 配置熱自癒 | 支援 `core.config` 內建之 `mtime` 比對，修改 `config.project.json` 或 `config.local.json` 即刻生效 |
| **NFR-03** | 測試覆蓋率 | 新增自動化測試針對 Default、Config Override、CLI Override 達成 100% 分支覆蓋 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

> [!NOTE]
> `parser.add_argument("--daemon", action="store_true", default=True)` 會導致預設值恆為 `True`，進而永遠遮蔽 `core.config` 的判斷。必須使用互斥群組且設定預設為 `None`。
