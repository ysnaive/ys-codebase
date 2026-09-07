# 需求規格說明書 (Requirements Specification)

> 功能名稱：optional_manifest_and_daemon_cleanup  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `manifest.json` optional 欄位標準 | 定義 `optional` 為合法擴充相依欄位，結構為 `{"<mod>": {"version": "<range>", "hint": "<desc>"}}` | P0 | [P00:DR-01] |
| **FR-02** | `core.installer` 安裝後提示機制 | 在模組安裝成功後走訪 `optional` 清單；若目標工作區尚未安裝該模組，以友善結構化卡片輸出提示說明與安裝指令 | P0 | [P00:DR-01] |
| **FR-03** | `dev.checker` 靜態合規檢核擴充 | 擴充 AST/JSON 合規管線，驗證 `optional` 若存在則型態必須為 `dict`，且各項必須包含 `version` (str) 與 `hint` (str) | P0 | [P00:DR-02] |
| **FR-04** | 徹底刪除 `daemon.py` | 移除 `source/knowledge-db/knowledge_db/daemon.py`，徹底告別模組私有守護進程，落實領域模組對冷/熱啟動零感知 | P0 | [P00:DR-03] |
| **FR-05** | 徹底刪除 `hook.core.py` 與殘留引用 | 移除 `source/knowledge-db/scripts/hook.core.py`；清理 `source/knowledge-db/scripts/cli.py` 殘留 import 與提示 | P0 | [P00:DR-03] |
| **FR-06** | `knowledge-db` 相依規格純化 | 將 `knowledge-db/manifest.json` 之 `"server": ">=1.0.0"` 自 `dependencies` 移轉至 `optional`，恢復純淨最小硬相依 | P0 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `manifest.json` 無 `optional` 欄位或為空 | `installer` 與 `checker` 透明忽略，向上完全相容舊版模組 |
| **EC-02** | `optional` 模組已安裝於環境中 | `installer` 檢測確認已存在，自動靜默跳過提示，不干擾使用者 |
| **EC-03** | `optional` 結構型態錯誤 (如 list 或缺少 hint) | `dev.checker` 攔截並印出錯誤檔案與欄位，阻斷模組發布 (Gate 1) |
| **EC-04** | 無 `server` 環境下執行 `knowledge-db` | 核心檢索、掃描、圖譜與打包以冷模式 100% 正常運作，無任何報錯 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 依賴純淨度 | `knowledge-db` 硬相依僅依賴 `core`，模組體積與載入相依最小化 |
| **NFR-02** | 代碼簡潔性 | 徹底刪除 2 個廢棄檔案，減少 300+ 行死碼，通過 `dev check` 全模組靜態檢核 |
| **NFR-03** | 終端可觀測性 | 安裝後提示以清晰 ANSI 提示呈遞，不干擾主安裝退出碼與進程狀態 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `knowledge-db` 的 `service.py` 已內建 `BaseServiceWorker` fallback，即使完全不安裝 `server` 也能安全載入執行。
- **`[!CAUTION]`** 刪除 `daemon.py` 後，需確保 `tests/` 下已無任何引用 `knowledge_db.daemon` 的測試檔案。
