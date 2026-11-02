# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：`module:space` 通用檔案空間、分級指紋快取與背景監聽底座模組 (`v1.0.0.0`) 實作  
> 建立日期：2026-11-02  
> 所屬主計畫：2026_11_02_0339_module_space_feasibility_research / sub_01_space_module_core  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Full Track  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：依據主計畫 [`R01_module_space_evaluation.md`](../R01_module_space_evaluation.md)、[`R02_space_api_and_architecture_design.md`](../R02_space_api_and_architecture_design.md) 與 [`R03_ecosystem_contracts_and_cli_design.md`](../R03_ecosystem_contracts_and_cli_design.md) 定案之架構與生態系契約，建置 `ys_codebase/source/space/`（`module:space@1.0.0.0`）底座模組。
- **核心目標**：
  1. **模組骨架與 Contributes 契約**：建立 `ys_codebase/source/space/manifest.json`（宣告 `"pip_dependencies": {"watchdog": ">=4.0.0"}`）、`contributes/_format.json`（定義 `spaces` schema，含 `include`、`exclude`、`file_patterns`、`hash_policy`、`large_file_threshold_mb`、`follow_symlinks`、`watch`）、`contributes/core.json`、`contributes/server.json` 與 `contributes/agents-workflow.json`。
  2. **雙軌空間配置聚合與 URI 解算 (`SpaceManager`)**：聚合各已安裝模組 `contributes/space.json` 與宿主 `config://space/contribute.json`，支援列表型欄位（`include`/`exclude`/`file_patterns`）附加合併、純量欄位（`hash_policy`/`large_file_threshold_mb`/`watch`）宿主覆寫、URI 解算與路徑邊界防護，以及 `define_ephemeral_space()` 動態空間註冊。
  3. **雙階段門檻與四模分級雜湊 (`FingerprintScanner`)**：
     - 第一道門檻：`os.scandir()` 比對 `(mtime_ns, size)`，搭配 10ms Racy-Clean 時間窗防護（`abs(scan_start_ns - mtime_ns) < 10_000_000` 強制重算雜湊）。
     - 第二道門檻（支援 `adaptive`、`full_hash`、`stat_only`、`lazy_stabilized` 四種 `hash_policy`）：`adaptive` 預設對 `< 10MB` 採 `blake2b(digest_size=20)` 全量雜湊，對 `>= 10MB` 採頭/中/尾各 64KB（共 192KB）稀疏抽樣雜湊；`lazy_stabilized` 於背景模式對未滿 2 秒冷卻期之大檔標記 `pending_stabilization` 延遲雜湊。
  4. **二進位快照 (`YFP2`)、Merkle Root 與多消費者獨立水位線 (`BinarySnapshotManager` & Cursor Manager)**：
     - 快照落檔於 `cache://space/snapshots/<space_name>.yfp2.bin`（含 `head_generation`、`merkle_root`、每檔 `created_gen`、`updated_gen`、`is_deleted` 墓碑紀錄與 `os.replace` 原子寫入）。
     - 消費者游標落檔於 `cache://space/cursors/<consumer_id>.json`，提供 `diff(space_name, consumer_id)`、`ack(space_name, consumer_id, generation)`、`reset_cursor()`、`consume_diff()` context manager 與 `merkle_root()` O(1) 複合指紋查詢。
  5. **原生 `watchdog` 背景監聽服務 (`SpaceWatcherServiceWorker`)**：註冊 `space-watcher` 常駐 Worker，支援 500ms 防抖批次收斂、`.yscb.lock` 交易鎖讓路、更新 `YFP2` 快照並透過 `core.events.broadcast("on_space_changed", payload, emit_module="space")` 與程序內 `subscribe()` 派發增量變更。
  6. **5 個標準 CLI 子命令 (`scripts/cli.*.py`)**：實作 `space status`、`space scan`、`space files`、`space diff`、`space clean`（全數支援 `--json` 雙模輸出與 `--help` 自省）。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 演進自 `ys_codebase/source/knowledge-db/knowledge_db/{space.py,scanner.py,service.py}`，將單一消費者覆寫模型升級為 `YFP2` 世代日誌 + 多消費者游標隔離模型。
  - 復用 `from core import uri, config, events, utils, console` 標準基礎設施。
- **邊界排除 (Explicitly Excluded)**：
  - 不包含 `.gitignore` 受管區塊同步邏輯。
  - 本子計畫僅建置並測試 `ys_codebase/source/space/` 模組本體；`knowledge-db` 遷移重構交由 `sub_02` 執行。
- **架構影響範圍**：新增 `ys_codebase/source/space/` 及 `ys_codebase/source/space/tests/`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 保留四模分級雜湊 (`hash_policy`)**：遵循開發者裁決保留 `adaptive`（預設）、`full_hash`、`stat_only`、`lazy_stabilized`，以適應下游未知的大型資產或純源碼使用情境。
- **[P00:DR-02] 直接依賴 `watchdog>=4.0.0`**：於 `space/manifest.json` 宣告 `"pip_dependencies": {"watchdog": ">=4.0.0"}`，承接跨平台作業系統原生檔案事件監聽。
- **[P00:DR-03] 讀寫分離之多消費者游標隔離 (`YFP2` + `cursors/<consumer_id>.json`)**：快照本體僅由 `refresh()` 或 `SpaceWatcherServiceWorker` 寫入；各下游模組透過獨立 `consumer_id` 游標計算 `diff` 並於成功消費後 `ack`，徹底根除多模組覆寫快照之競態條件。

---

## 3. 開放議題與確認紀錄

- 所有 API 簽名、CLI 規格與二進位格式已於主計畫 `R02` 與 `R03` 完整確認，可直接推進實作。

