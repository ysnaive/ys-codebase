# 語意化需求定義 (Semantic Requirements)

> 功能名稱：測試框架生命週期與全隔離虛擬沙盒重構 (Testing Lifecycle & Virtual Sandbox Refactor)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 核心願景與問題陳述

在既有測試框架（`dev.testing`）中，沙盒僅作為單一暫存工作目錄（CWD），導致底層 VFS 協議（`yscb://`, `mirror://`, `snapshot://`）依然穿透連回父層真實倉庫，引發「混合狀態 (Hybrid State) 鏡像悖論」與環境污染。

本子計畫旨在破除混血狀態，重構為**「完全對標的微型虛擬環境沙盒 (Full-Fidelity Virtual Sandbox)」**，並健全生命週期調用流：
1. **完全對標微型虛擬環境**：沙盒內部 1:1 劃分 `project/`（被管理專案，對應 `project://`）、`host/`（工具庫宿主，對應 `yscb://`）與 `provider/`（套件倉庫），達成 100% 擬真黑盒驗收且父層 0 殘留污染。
2. **模組自治測試 Hook (`scripts/hook.dev.py`)**：各模組可宣告 `on_test_setup` / `on_test_teardown`，例如 `core` 自動於沙盒配置 `config/core/config.project.json` 之 `project_root`，解除 `!undefined` 阻斷；且 `hook.dev.py` 保留於 `build/` 純淨套件中賦能第三方開發者。
3. **雙層套件源策略 (Dual-Source)**：本地最新產物優先讀取父層 `build/`（具備 `index.json`），外部遠端依賴唯讀共享父層 `.mirror/` 快取加速。
4. **源碼直通即時測試 (Source-Direct)**：模組內部邏輯與單元測試無需先行打包，直接將 `source/<mod>` 前置注入 `sys.path`，達成毫秒級即改即測。
5. **CLI 參數過濾健全化**：修復 `--type` 參數過濾對接（`logic`, `sandbox`, `network` 等）與 `-k` 巢狀 TestSuite 遞迴過濾。

---

## 2. 使用情境與工作流程 (User Scenarios & Workflows)

### 情境 1：全新下游專案接入與套件生命週期黑盒驗收 (Downstream Consumer Flow)
- **前置狀態**：沙盒初始化，建立 `sandbox/project/`, `sandbox/host/`, `sandbox/provider/`。
- **操作步驟**：
  1. `run_cli(["init", "--provider=..."])` 在 `sandbox/host/` 建立 `yscb.config.json`。
  2. 廣播觸發 `hook.dev.py:on_test_setup`，`core` 自動配置 `config/core/config.project.json`。
  3. `run_cli(["core", "install", "mock_app"])` 安裝模組至 `sandbox/host/modules/`，快照至 `sandbox/host/.snapshots/`。
- **預期行為**：
  - 沙盒內部自成閉環，驗證完全通過。
  - 測試結束後一鍵銷毀沙盒，父層開發環境永遠 0 污染、0 殘留。

### 情境 2：專案空間 (`project://`) 跨層級隔離驗證 (Project URI Isolation Flow)
- **操作**：模組存取 `project://src/main.py`。
- **預期行為**：
  - 依據 `sandbox/host/engine/config/core/config.project.json` 中的 `"project_root": "../project"`，精準解析至 `sandbox/project/src/main.py`。
  - 100% 絕不碰觸或覆蓋父層真實專案代碼。

### 情境 3：源碼即時測試與快速單元驗證 (Source-Direct In-Place Test Flow)
- **操作**：開發者修改 `source/core/` 或 `source/dev/` 後執行 `dev test`。
- **預期行為**：
  - `TestDiscovery` 直接將 `source/<mod>` 前置注入 `sys.path`。
  - 零 build、零 install 依賴，毫秒級即改即測。
  - 沙盒僅作為臨時安全 IO 工作區。

### 情境 4：分類標籤精準過濾測試 (`--type` & `-k` Filtering)
- **操作**：執行 `python yscb.py dev test core --type=sandbox` 或 `dev test dev -k test_builder`。
- **預期行為**：
  - 測試框架依據 `@require(Requirement.<TYPE>)` 精準過濾測試案例。
  - 遞迴巡訪巢狀 TestSuite，僅執行符合條件之測試。

---

## 3. 開放議題裁決紀錄 (Confirmed Decision Records)

| 議題編號 | 決策主題 | 裁決結論 |
| :--- | :--- | :--- |
| **[P00:DR-01]** | 沙盒拓撲結構 | 採「完全對標微型虛擬環境」，內部劃分 `project/`, `host/`, `provider/` 三大空間。 |
| **[P00:DR-02]** | 模組測試 Hook 規範 | 命名為 `scripts/hook.dev.py`，定義 `on_test_setup` 與 `on_test_teardown`，並保留於 `build/` 套件內。 |
| **[P00:DR-03]** | 套件源與快取策略 | 採雙層源策略：最新產物自父層 `build/` 讀取，外部依賴唯讀共享父層 `.mirror/` 快取。 |
| **[P00:DR-04]** | 源碼即時測試支援 | 保留 Source-Direct 軌道，`source/<mod>` 直接注入 `sys.path`，支援零延遲 TDD。 |
| **[P00:DR-05]** | 參數過濾實作 | 對接 `--type` 與 `@require` 標記，並以遞迴函式重構 `-k` Suite 過濾器。 |
