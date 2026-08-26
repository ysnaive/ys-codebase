# 需求規格說明書 (Requirements Specification)

> 功能名稱：core contribute 系統優化與路徑系統打磨 (Core Contribute Optimization & URI Polish)  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 狀態：`Confirmed`  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `__provider__` 來源自動標記 | 在 `ContributesAggregator` 自動搜集階段，針對 donor 模組提供之 Dict 與 List[Dict] 項目，自動注入 `"__provider__": donor_module_name`（若未顯式宣告）。 | P0 | [P00:DR-01] |
| **FR-02** | 依賴拓撲聚合排序 | `scan_and_inject()` 搜集 donor 模組時，改依據已安裝模組之依賴拓撲順序（Topological Order）依序遍歷合併，保證基礎模組先於上層擴充模組被註冊。 | P0 | [P00:DR-02] |
| **FR-03** | 微內核標準 Contribute 查詢 SDK | 在 `core.contributes` 提供 `get(target_module, key=None, default=None)` 與 `get_for_current_module()` 高階查詢介面，支援自動快取讀取與損毀自動自愈重聚。 | P0 | [P00:DR-03] |
| **FR-04** | `!undefined` 語意協議 JIT 攔截與選單 | `uri.resolve()` 檢測到協議值為 `!undefined` 時，在互動終端（TTY）攔截並彈出 `[-y <path> / -n / --help]` 互動選單，標示相對路徑以 `yscb://` 為基準起始。 | P0 | [P00:DR-04] |
| **FR-05** | JIT `--help` 協議清冊展開 | 使用者在熱補齊選單輸入 `--help` 時，展開目標協議資訊、綁定之 Config Key，並即時列出當前全系統已註冊之可用 URI 協議清冊。 | P0 | [P00:DR-04] |
| **FR-06** | 連鎖未定義依賴遞迴補齊 | 使用者輸入包含其他語意協議之複合路徑（如 `project://plans`）時，若底層協議亦為 `!undefined`，自動依拓撲遞迴先提示補齊底層協議。 | P1 | [P00:DR-04] |
| **FR-07** | 自動持久化與記憶體熱重載 | 使用者輸入 `-y <path>` 後，自動定位所屬 `config.root://{__provider__}/config.project.json` 原子寫回對應欄位，記憶體即時刷新 URI 快取並無縫繼續執行。 | P0 | [P00:DR-04] |
| **FR-08** | 非互動與診斷工具安全防護 | 當處於非 TTY 環境或傳入 `interactive=False`（如 `uri check` 靜態診斷）時，不彈出 prompt，直接拋出結構化 `UndefinedURIError`。 | P0 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 使用者宣告自引用循環協議 (例 `foo://` 指向 `foo://bar`) | 微內核維護 `_reconciling_tokens` 集合，檢測到循環重入時立即中斷並拋出 `CyclicURIDependencyError`，防止無窮死鎖。 |
| **EC-02** | 使用者在熱補齊輸入 `-n` 拒絕配置 | 終端輸出友善引導提示並以 exit code 1 優雅退出，絕不拋出未捕獲之 Python Traceback。 |
| **EC-03** | 目標設定檔 `config.project.json` 尚不存在或其 parent 目錄不存在 | 自動建立所需之 parent 目錄，並以預設結構原子建立/更新目標 JSON 檔案。 |
| **EC-04** | donor 模組 Manifest 之 contributes 格式損毀或非 JSON | 記錄警告並安全跳過該 donor，不中斷微內核全量聚合流水線。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 相容性 (Compatibility) | 100% 向後相容現有 `uri.resolve()` 呼叫端，無顯式 break 變更。 |
| **NFR-02** | 效能 (Performance) | 快取命中時 `core.contributes.get()` 與 `uri.resolve()` 解算耗時 < 1ms。 |
| **NFR-03** | 依賴約束 (Zero External Dependency) | JIT 提示與熱更新完全採用 Python 原生標準庫（`sys`, `os`, `json`, `readline`）。 |

---

## 4. 專案特化擴充判定矩陣 (Extension Specialization Scan)

| 擴充功能名稱 | 判定結果 | 納入 / 排除理由 |
| :--- | :---: | :--- |
| **中央標準庫擴充清單** | `Excluded` | 本模組為微內核底層設施，無相依之外部 SOP 擴充。 |
