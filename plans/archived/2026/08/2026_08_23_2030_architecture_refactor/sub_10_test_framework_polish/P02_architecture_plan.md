# 架構與模組設計說明書 (Architecture & Module Plan)

> 功能名稱：測試框架生命週期與全隔離虛擬沙盒重構 (Testing Lifecycle & Virtual Sandbox Refactor)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 系統模組劃分與邊界 (Module Architecture & Boundaries)

```mermaid
graph TD
    classDef core fill:#0f172a,stroke:#3b82f6,stroke-width:2px,color:#60a5fa;
    classDef dev fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#34d399;
    classDef box fill:#1e293b,stroke:#64748b,stroke-width:2px,color:#f8fafc;

    subgraph DevCLI ["Dev CLI 指令體系 (source/dev/dev/tester.py)"]
        TestCmd["<b>dev test</b> (高階門面)<br/>• 調用 op-mksb ➔ 進入沙盒調用 op-test ➔ 清理"]:::dev
        OpMksb["<b>dev op-mksb</b> (原子操作)<br/>• 建造 mock_downstream_project, host_env, mock_provider<br/>• 複製 source/ 並調度 hook.dev.py"]:::dev
        OpTest["<b>dev op-test</b> (原子操作)<br/>• 原地 TestDiscovery + TestRunner<br/>• 100% 零沙盒建立、零遞迴"]:::dev
    end

    subgraph CoreModule ["Core 基礎設施模組 (source/core)"]
        CoreHook["<b>scripts/hook.dev.py</b><br/>• on_test_setup()<br/>• 自動配置沙盒 config.project.json"]:::core
    end

    subgraph SandboxEnv ["完全對標微型虛擬環境 (temp://sandbox_<uuid>)"]
        Proj["<b>mock_downstream_project/</b><br/>(project:// 空間)"]:::box
        Host["<b>host_env/</b><br/>• yscb.config.json (host_dir)<br/>• engine/ (yscb:// 空間)"]:::box
        Prov["<b>mock_provider/</b><br/>(套件源空間)"]:::box
    end

    TestCmd -->|1. 調度| OpMksb
    OpMksb -->|建立並配置| SandboxEnv
    OpMksb -->|調度前置 Hook| CoreHook
    CoreHook -->|寫入 project_root| Host
    TestCmd -->|2. 在沙盒內執行| OpTest
```

---

## 2. 測試執行期循序圖 (Lifecycle Sequence Flow)

```mermaid
sequenceDiagram
    autonumber
    actor Dev as 開發者 / CI
    participant HostTester as yscb.py dev test (父層門面)
    participant OpMksb as dev op-mksb (環境工廠)
    participant CoreHook as core/scripts/hook.dev.py
    participant SubTester as sandbox/.../yscb.py dev op-test (沙盒執行器)
    participant Disc as TestDiscovery
    participant Runner as TestRunner

    Dev->HostTester: python yscb.py dev test [target] [--all]
    activate HostTester
    
    HostTester->OpMksb: 執行 dev op-mksb
    activate OpMksb
    OpMksb->OpMksb: 1. 建立 sandbox (project, host, provider)
    OpMksb->OpMksb: 2. 複製 source/ 至 sandbox/host_env/engine/source/
    OpMksb->OpMksb: 3. 生成 host/yscb.config.json
    OpMksb->CoreHook: on_test_setup(context)
    CoreHook-->>OpMksb: 完成 config.project.json 設置
    OpMksb-->>HostTester: 返回 sandbox 路徑
    deactivate OpMksb

    HostTester->SubTester: subprocess: sandbox/host_env/yscb.py dev op-test [target]
    activate SubTester
    SubTester->Disc: build_suite_for_module()
    Disc->Disc: 原地載入 Auto-Contract & Custom Tests
    Disc-->>SubTester: master_suite
    SubTester->Runner: run_suite()
    Runner-->>SubTester: TestResult
    SubTester-->>HostTester: 返回 Exit Code (0 或 1) 與診斷輸出
    deactivate SubTester

    alt 測試通過且未指定 --keep-sandbox
        HostTester->HostTester: rmtree(sandbox_dir)
    else 測試失敗或指定 --keep-sandbox
        HostTester->HostTester: 保留沙盒現場並提示路徑
    end
    HostTester-->>Dev: 印出報告並退出
    deactivate HostTester
```

---

## 3. 受影響模組與檔案矩陣 (Impacted Files Matrix)

| 檔案路徑 | 變更類型 | 核心職責與修改重點 | 對應 FR / EC |
| :--- | :---: | :--- | :---: |
| [`source/core/scripts/hook.dev.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/scripts/hook.dev.py) | NEW | 實作 `on_test_setup` 與 `on_test_teardown`，於沙盒中配置 `project_root`。 | FR-03<br/>EC-02 |
| [`source/dev/dev/testing/case.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/testing/case.py) | Modify | 重構 `YSCBTestCase`：三層虛擬沙盒鋪設、源碼複製、Hook 調度、雙層套件源支援與安全清理。 | FR-01, FR-02, FR-04<br/>EC-01, EC-04 |
| [`source/dev/dev/testing/runner.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/testing/runner.py) | Modify | `TestDiscovery` 健全 `--type` 過濾與遞迴 `filter_suite(suite, pattern)`。 | FR-05, FR-06<br/>EC-03 |
| [`source/dev/dev/testing/requirement.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/testing/requirement.py) | Modify | 補齊 `Requirement.LOGIC`, `Requirement.HOST_CLI`, `Requirement.NETWORK` 列舉值與過濾輔助函式。 | FR-06 |
| [`source/dev/dev/builder.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/builder.py) | Modify | 打包時確保保留 `scripts/hook.dev.py`。 | EC-05 |

---

## 4. 決策紀錄整合 (Decision Records Master List)

- `[P02:DR-01]`：`core.uri` 保持純淨 0 修改，沙盒透過將源碼複製至 `sandbox/host_env/engine/source/`，直接藉由 `__file__` 達成天然 VFS 自定位。
- `[P02:DR-02]`：沙盒內環境採用「全黑盒自治」模式，每個測試案例具備專屬的三層子目錄（`project`, `host`, `provider`）。
- `[P02:DR-03]`：模組測試前置 Hook 統一命名為 `scripts/hook.dev.py`，作為 `dev` 模組調度的標準協議。
