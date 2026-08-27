# 需求規格說明書 (Requirements Specification)

> 功能名稱：測試架構完善 (Test Architecture Refinement)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Confirmed`  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `Requirement.ISOLATED_SANDBOX` 標籤定義 | 於 `dev.testing.requirement.Requirement` 列舉新增 `ISOLATED_SANDBOX = auto()`，支援 `@require(Requirement.ISOLATED_SANDBOX)` 標記，並支援與 `LOGIC`、`HOST_CLI`、`NETWORK` 進行按位元 OR 組合。 | P0 | [P00:DR-01] |
| **FR-02** | `YSCBTestCase` 預設共用與獨立沙盒分流機制 | 1. **預設共用沙盒**：未標記 `ISOLATED_SANDBOX` 之測試方法，同一個 `TestCase` 類別內共用同一個沙盒實例（Class-level Lazy Sandbox），大幅降低磁碟目錄重複複製之 I/O 開銷。<br/>2. **獨立沙盒**：標記 `ISOLATED_SANDBOX` 之測試方法，於 `setUp` 建立專屬獨立沙盒、`tearDown` 清理。<br/>3. **屬性透明性**：`self.ctx`, `self.sandbox_dir`, `self.sandbox_host_dir`, `self.run_cli()`, `self.create_mock_package()` 在兩種模式下均 100% 透明無感運作。 | P0 | [P00:DR-02] |
| **FR-03** | 測試環境識別環境變數 `YSCB_TEST_SANDBOX` 注入 | 1. `YSCBTestCase.setUp`、`TestRunner.run_suite` 與 `Tester._run_test` 於測試啟動時將 `os.environ["YSCB_TEST_SANDBOX"] = "1"`。<br/>2. `YSCBTestCase.run_cli` 子行程調用中自動透傳 `YSCB_TEST_SANDBOX="1"`。 | P0 | [P00:DR-03] |
| **FR-04** | URI JIT 測試環境靜默跳過與防護 | `core.uri.reconcile_undefined_uri` 增加 `os.environ.get("YSCB_TEST_SANDBOX") == "1"` 檢測。當檢測到測試環境標籤時，靜默跳過 `input()` 互動提示，直接拋出結構化 `UndefinedURIError`；日常非測試環境維持 100% 完整的 JIT 終端互動與寫回行為。 | P0 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 同一類別內混合共用與獨立測試方法 | 執行獨立沙盒測試方法時，切換至專屬沙盒，測試結束後安全切回或不污染共用沙盒之上下文與環境變數。 |
| **EC-02** | 測試失敗時沙盒保留策略 | 當共用沙盒測試失敗時保留共用沙盒；當獨立沙盒測試失敗時保留獨立沙盒目錄，一律遵循 `sub_01` 滾動 3 個保留上限。 |
| **EC-03** | 環境變數與 `sys.path` 隔離與還原 | `YSCBTestCase.tearDown` 與 `tearDownClass` 必須 100% 還原 `os.environ` 與 `sys.path`，防止 `YSCB_TEST_SANDBOX` 殘留至非測試流程中。 |
| **EC-04** | 既有測試套件無痛相容 | 全系統既有 134 個單元與契約測試（`core`, `dev`, `agents-workflow`）在沙盒共享啟用後 100% 通過無衰退。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能提升 (Performance) | `dev test dev`（35 個測試）在沙盒共享機制啟用後，總執行耗時預期降低 50% 以上。 |
| **NFR-02** | 零新增依賴與 API 相容 (Compatibility) | 100% 採用 Python 標準庫，不破壞既有 Public API 簽名與 CLI 指令。 |
| **NFR-03** | 測試覆蓋度 (Test Coverage) | 為 `Requirement.ISOLATED_SANDBOX`、共用沙盒生命週期與 `YSCB_TEST_SANDBOX` JIT 防護新增專屬單元測試。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`**：在自引用空間中，所有修改必須在 `ys_codebase/source/core/` 與 `ys_codebase/source/dev/` 進行，未通過全量回歸前嚴禁手動改動 `modules/`。
- **`[!CAUTION]`**：某些測試（如測試打包或多模組物理安裝）若直接修改沙盒中的目錄結構，應顯式標記 `@require(Requirement.ISOLATED_SANDBOX)`，避免對同類別後續共用沙盒之測試產生狀態污染。
