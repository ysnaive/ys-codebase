# 需求規格說明書 (Requirements Specification)

> 功能名稱：測試框架生命週期與全隔離虛擬沙盒重構 (Testing Lifecycle & Virtual Sandbox Refactor)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P00/調研報告：[P00_semantic_requirements.md](./P00_semantic_requirements.md), [R01_testing_lifecycle_flow.md](./R01_testing_lifecycle_flow.md)  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格說明 | 對應 P00 語意 |
| :--- | :--- | :--- | :--- |
| **FR-01** | 沙盒建造原子指令 (`dev op-mksb`) | 提供 `op-mksb` 底層原子指令：自動於 `temp://sandbox_<uuid>`（或指定路徑）建立 1:1 對標的三大獨立空間（`mock_downstream_project/`, `host_env/`, `mock_provider/`），將 `source/` 複製至沙盒，並調度 `scripts/hook.dev.py : on_test_setup` 完成自治前置初始化。 | P00 §2 情境 1<br/>[P00:DR-01] |
| **FR-02** | 沙盒 VFS 天然常數自定位 | 利用 `core.uri._get_yscb_root()` 既有的 `__file__` 往上 3 層常數自定位機制，在將源碼複製進沙盒 `sandbox/host_env/engine/source/` 後，天然錨定 `yscb://` 於沙盒內，無須修改 `core.uri` 程式碼即可杜絕父層穿透。 | P00 §2 情境 1/2<br/>[P00:DR-01] |
| **FR-03** | 模組測試前置自治 Hook 體系 | 1. 建立 `scripts/hook.dev.py` 標準，定義 `on_test_setup(context)` 與 `on_test_teardown(context)` 介面。<br/>2. `dev.testing` 在 `op-mksb` 沙盒初始化時自動掃描並調度各模組之 Hook。<br/>3. `core` 模組提供 `scripts/hook.dev.py`，自動將沙盒內 `config/core/config.project.json` 的 `"project_root"` 配置為 `"../mock_downstream_project"`，消除 `!undefined` 阻斷。 | P00 §2 情境 1/2<br/>[P00:DR-02] |
| **FR-04** | 原地測試執行原子指令 (`dev op-test`) | 提供 `op-test` 底層原子指令：純粹的內層單元測試執行器，只在「當前環境」內進行 TestDiscovery、載入 Auto-Contract 與 Custom Tests 並執行，**絕對不建立沙盒、不複製檔案、不遞迴**。 | P00 §2 情境 3<br/>[P00:DR-04] |
| **FR-05** | 端到端測試高階門面 (`dev test`) | 提供 `dev test` 高階組合指令：在父層調用 `op-mksb` 產出沙盒 ➔ 進入沙盒調用 `op-test` 執行測試 ➔ 收集結果並依狀態執行清理或保留現場。 | P00 §2 情境 1/3<br/>[P00:DR-04] |
| **FR-06** | CLI 參數過濾與雙層套件源 | 1. `dev op-test` 與 `dev test` 支援 `--type=<type>` 與 `@require` 標記精準對接。<br/>2. 實作遞迴 `filter_suite(suite, pattern)` 函式，支援任意深度之 `-k` 篩選。<br/>3. 沙盒環境支援雙層套件源：本地讀取父層 `build/`，外部依賴共享父層 `.mirror/`。 | P00 §2 情境 4<br/>[P00:DR-03, DR-05] |

---

## 2. 邊界與異常情況處理 (Edge Cases)

| 邊界編號 | 邊界情境說明 | 防禦處置與預期行為 | 對應需求 |
| :--- | :--- | :--- | :--- |
| **EC-01** | 沙盒內路徑越界存取 | 任何在沙盒內執行的 `uri.resolve()` 與 IO 操作若企圖逃逸至父層開發目錄，必須被 VFS 沙盒邊界嚴格隔絕在沙盒目錄內。 | FR-01<br/>FR-02 |
| **EC-02** | 模組 Hook 執行拋錯與例外隔離 | 若某模組的 `scripts/hook.dev.py` 發生語法錯誤或執行期例外，`dev.testing` 必須輸出 Warning 日誌並實施例外隔離，不得中斷整個測試執行。 | FR-03 |
| **EC-03** | `--type` 傳入無效或未定義類型 | 若傳入未定義之類型字串（如 `--type=invalid`），輸出錯誤提示與支援的合法類型清單（`logic`, `sandbox`, `network`），並以 Exit Code 1 退出。 | FR-06 |
| **EC-04** | Windows 檔案鎖定導致沙盒清理受阻 | `tearDown` 刪除沙盒時，若因 Windows 行程或檔案鎖定導致 `rmtree` 拋錯，捕捉例外並輸出 Warning，不得覆蓋測試本體的 Pass/Fail 判定。 | FR-01 |
| **EC-05** | 打包建置時保留 `hook.dev.py` | `dev.builder` 在執行 `build` 時，必須在排除 `tests/` 的同時保留 `scripts/hook.dev.py`，確保發布套件賦能第三方開發者。 | FR-03 |

---

## 3. 非功能需求 (Non-Functional Requirements)

- **NFR-01（毫秒級沙盒建立效能）**：單次測試沙盒的三層子目錄鋪設與環境變數注入總耗時必須 $\le 5\text{ ms}$。
- **NFR-02（零殘留環境保護 0-Leakage）**：測試執行完畢後，父層 `ys_codebase/.mirror`、`.snapshots` 與 `yscb.config.json` 必須 100% 達成零變更、零檔案殘留。
- **NFR-03（向下相容與純標準庫）**：所有重構 100% 維持 Python 3.10+ 純標準庫，現有 38 項測試回歸無損。

---

## 4. 專案擴充特化判定矩陣 (Extension Specialization Matrix)

| 擴充功能名稱 | 觸發模式 | 判定結果 | 評估理由 |
| :--- | :---: | :---: | :--- |
| `dogfooding_pipeline_ext` | always | **Excluded (排除)** | 依開發者指示，本子計畫聚焦測試框架本體重構，暫不納入此擴充。 |

---

## 5. 踩坑紀錄與設計註記巡檢 (Design Notes Pre-check)

- **DN-01 / DN-05（宿主組態與專案空間隔離）**：沙盒內 `yscb.config.json` 必須歸屬 `host_dir`，而 `project://` 必須由 `config/core/config.project.json` 定義，兩者嚴禁混淆。
- **DN-06（`yscb://` 常數自定位與動態覆蓋）**：`_get_yscb_root()` 僅在偵測到 `YSCB_ROOT` 環境變數時動態覆蓋，未設定時維持 `__file__` 常數自定位。
