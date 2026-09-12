# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：optional_manifest_and_daemon_cleanup  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  > 「我認為有些設計需要修改，因為對於 knowledge db 來說，server 是擴充，我們是不是可以考慮優化 manifest 的定義，除了 dependencies 外，添加 optional，不會強制安裝，但在下載工具鍊安裝完後，發現有 optional module 沒安裝，會給出相應提示，格式為: optional { "<module>": { version: "", hint: "" } }。另外，daemon.py 還有存在意義嗎? 理論上新架構對於其他 module 的其他功能來說，應是無區分冷/熱啟動的吧」
- **核心目標**：
  1. **Manifest `optional` 擴充欄位標準化**：定義與實作 `optional` 欄位規範，支援 `{ version, hint }` 宣告；安裝工具鏈（`core.installer`）完成安裝後檢測未安裝之 optional 模組並印出引導提示。
  2. **靜態合規檢驗支援 (`dev.checker`)**：支援 `optional` 欄位結構合規檢核。
  3. **徹底移除 `daemon.py` 與私有 Hook**：落實「模組對冷/熱啟動零感知」哲學，徹底刪除 `knowledge-db` 殘留之 `daemon.py` 與 `hook.core.py`，收斂 CLI 入口。
  4. **`knowledge-db` 相依純淨化**：將 `server` 由 `dependencies` 移至 `optional`，使 `knowledge-db` 保持對 `core` 的唯一最小相依。
- **邊界排除 (Explicitly Excluded)**：
  - 不強制自動拉取 optional 模組（維持擴充自願性）。
  - 不更動 `server` 內部既有的 Master-Worker 調度架構。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] Manifest `optional` 擴充欄位規格與安裝提示落地**：
  - 於 `manifest.json` 引入可選的 `"optional"` 字典欄位：
    ```json
    "optional": {
      "<module_name>": {
        "version": ">=1.0.0",
        "hint": "提供常駐背景檔案監聽熱自癒與極速預熱派發"
      }
    }
    ```
  - `core.installer` 在安裝模組完成後，遍歷其 `optional` 宣告；若目標工作區尚未安裝該擴充模組，以友善結構化卡片輸出提示與 `python yscb.py install <module>` 安裝引導。
- **[P00:DR-02] `dev.checker` 擴充合規校驗**：
  - 檢驗 `manifest.json` 若包含 `optional`，其值必須為 `dict`，且內部各鍵之值必須包含 `version` (str) 與 `hint` (str) 欄位。
- **[P00:DR-03] 模組對冷/熱啟動零感知，徹底廢除 `daemon.py` 與 `hook.core.py`**：
  - 在全新微內核架構下，冷/熱啟動的派發調度全權由宿主 `yscb.py`（`_try_hot_dispatch` 與 `_maybe_auto_spawn_server`）統一處理，各模組僅需實作純業務之 `process(args)` 入口。
  - 徹底刪除 `source/knowledge-db/knowledge_db/daemon.py`。
  - 徹底刪除 `source/knowledge-db/scripts/hook.core.py`。
  - 清理 `source/knowledge-db/scripts/cli.py` 中對 `daemon.py` 的殘留引用與提示。
- **[P00:DR-04] `knowledge-db` 依賴架構純化**：
  - `knowledge-db/manifest.json` 將 `server` 從 `dependencies` 移至 `optional`，還原純淨之最小硬相依（僅依賴 `core`）。

---

## 3. 開放議題與確認紀錄

- [x] **安全性檢核**：`service.py` 內建抽象 `BaseServiceWorker` fallback，即使環境無 `server` 亦能安全靜態載入，100% 具備可選擴充特性。 (Confirmed)
- [x] **零感知架構**：所有領域模組均無須專屬守護進程，全面回歸純淨業務入口。 (Confirmed)
