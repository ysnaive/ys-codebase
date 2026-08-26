# 實作計畫與定稿審查 (Implementation Plan & Review)

> 功能名稱：測試框架生命週期與全隔離虛擬沙盒重構 (Testing Lifecycle & Virtual Sandbox Refactor)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P01~P03：[P01](./P01_requirements_spec.md), [P02](./P02_architecture_plan.md), [P03](./P03_api_spec.md)  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 交叉審查核對清單 (Cross-Validation Checklist)

- [x] **FR 覆蓋完整性**：P01 中 FR-01 ~ FR-06 於 P03 API 規格書中皆有對應介面與簽名（`SandboxProvisioner`, `SandboxContext`, `hook.dev.py`, `filter_suite`, `Tester` 路由）。
- [x] **EC 錯誤處理對齊**：P01 中 EC-01 ~ EC-05 於 P02/P03 均具備顯式防禦（VFS 沙盒邊界、Hook 例外隔離、Windows 鎖定警告、`build` 保留 `hook.dev.py`）。
- [x] **追溯鏈剛性對齊**：`P00 議題` ➔ `P01 (FR/EC)` ➔ `P02/P03 (API/DR)` ➔ `P06 (FT/ET/RT)` 實現 100% 雙向追溯。
- [x] **零第三方依賴**：所有重構 100% 維持純 Python 3 標準庫實現。

---

## 2. 靈魂拷問 (Stress Test & Edge Case Scrutiny)

> **架構審查員提問**：  
> 「在執行 `dev test` 時，`op-mksb` 將 `source/` 複製至沙盒 `sandbox/host_env/engine/source/`。若測試中 `YSCBTestCase.run_cli(["core", "install", "mock_app"])` 執行了安裝，模組是安裝到哪裡？如果是測試 `core` 模組本體，`dev op-test core` 載入的是 `source/core` 還是 `modules/core`？兩者會不會再次發生混淆？」

**架構解析與防護回答**：
- **載入源碼路徑**：在沙盒中，`dev op-test core` 原地執行，`TestDiscovery` 將 `sandbox/host_env/engine/source/core` 注入 `sys.path[0]`，因此測試直接載入並驗證沙盒內的最新源碼。
- **安裝目標路徑**：當測試調用 `run_cli` 測試套件安裝時，套件被下載解壓至 `sandbox/host_env/engine/modules/`。
- **徹底解耦**：兩者皆 100% 局限於沙盒內部，既保證了測試驗證的是最新的即時代碼，又完整演練了套件安裝到 `modules/` 的真實物理路徑，徹底根除了舊架構下父層 `modules/` 殘留與源碼版本脫節的根本矛盾！

---

## 3. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

> 依據 7 大抽象知識維度，預排本次實作完成後需同步交付更新之文檔清單：

| 知識庫文檔路徑 | 知識維度 | 預排更新內容與主題 | 對應 P03/P06 驗收錨點 |
| :--- | :---: | :--- | :--- |
| [`docs/dev/testing_guide.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/dev/testing_guide.md) | 維度 3 | 完整更新 `dev op-mksb`, `dev op-test`, `dev test` 三階架構與微型虛擬環境沙盒指南 | P03 §1.2, §1.5 / FT-01~04 |
| [`docs/core/lifecycle_and_hooks.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/lifecycle_and_hooks.md) | 維度 3 | 補充 `scripts/hook.dev.py` 測試前置 Hook 規範與 `on_test_setup` 介面 | P03 §1.3 / FT-03 |
| [`docs/dev/DESIGN_NOTES.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/dev/DESIGN_NOTES.md) | 維度 5 | 登記 `DN-DEV-02`（三階指令解耦與完全對標虛擬沙盒） | [P02:DR-01~03] |
| [`docs/dev/README.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/dev/README.md) | 維度 2 | 更新 CLI 指令手冊補充 `dev op-mksb` 與 `dev op-test` 原子操作說明 | FR-01, FR-04 |

---

## 4. 實作任務清單 (Implementation Task Matrix)

| 任務編號 | 實作項目 | 目標檔案 | 對應 FR / EC | 依賴前置 |
| :--- | :--- | :--- | :--- | :---: |
| **TASK-01** | `Requirement` 列舉與條件標籤更新 | `source/dev/dev/testing/requirement.py` | FR-06 | 無 |
| **TASK-02** | `SandboxContext` 與 `SandboxProvisioner` (`op-mksb`) 實作 | `source/dev/dev/testing/sandbox.py` (NEW)<br/>`source/dev/dev/testing/case.py` | FR-01, FR-02, FR-04<br/>EC-01, EC-04 | TASK-01 |
| **TASK-03** | `core` 模組自治測試 Hook 實作 | `source/core/scripts/hook.dev.py` (NEW) | FR-03<br/>EC-02 | TASK-02 |
| **TASK-04** | `filter_suite` 遞迴過濾器與 `TestDiscovery` 強化 (`op-test`) | `source/dev/dev/testing/runner.py` | FR-04, FR-06<br/>EC-03 | TASK-01 |
| **TASK-05** | `dev.tester` 三階路由整合與 `dev.builder` 打包保留規則 | `source/dev/dev/tester.py`<br/>`source/dev/dev/builder.py` | FR-01, FR-04, FR-05<br/>EC-05 | TASK-02~04 |
| **TASK-06** | 持久化測試套件擴充與全量 100% 驗證 | `source/dev/tests/test_sandbox.py` (NEW)<br/>`source/dev/tests/test_tester.py` | FT-01~FT-06<br/>ET-01~ET-03<br/>RT-01 | TASK-01~05 |

---

## 5. 決策紀錄整合 (Decision Records Master List)

- `[P00:DR-01]`：採「完全對標微型虛擬環境」，內部劃分 `project/`, `host/`, `provider/` 三大空間。
- `[P00:DR-02]`：模組測試 Hook 命名為 `scripts/hook.dev.py`，定義 `on_test_setup` 與 `on_test_teardown`。
- `[P00:DR-03]`：雙層套件源策略：本地讀取父層 `build/`，外部依賴唯讀共享父層 `.mirror/`。
- `[P02:DR-01]`：`core.uri` 保持純淨 0 修改，沙盒透過將源碼複製至沙盒目錄，直接藉由 `__file__` 達成天然 VFS 自定位。
- `[P02:DR-03]`：`dev` 指令體系解耦為 `op-mksb` (環境工廠)、`op-test` (原地執行器) 與 `test` (組合門面) 三階架構，徹底終結二度沙盒遞迴。
- `[P03:DR-01]`：`SandboxContext` 作為沙盒初始化的安全中介層。

---

## 6. 閉合確認 (Closing Confirmation)

- [x] 開發者已確認：Phase 4 實作計畫定稿與靈魂拷問審查無誤，指示進入 Phase 5 開始實作
