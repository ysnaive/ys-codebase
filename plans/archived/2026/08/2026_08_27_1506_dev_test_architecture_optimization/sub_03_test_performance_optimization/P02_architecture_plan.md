# 架構設計說明書 (Architecture Plan)

> 功能名稱：測試分類體系重構、效能深水區與沙盒型別安全防固 (Test Taxonomy, Performance & Sandbox Type Safety)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Confirmed`  
> 模板版本：v1.2  

---

## 1. 系統架構與模組拓撲圖 (System Topology & Architecture)

```mermaid
flowchart TD
    subgraph CLI["CLI 調度層 (dev.tester.Tester)"]
        A["使用者指令 (dev test [mod] [flags])"] --> B{"解析 --target / --type / --all"}
        B -->|"多模組並行 (--all)"| C1["ProcessPoolExecutor 並行工作佇列"]
        B -->|"單模組模式"| C2["單模組 Runner"]
    end

    subgraph TripleLock["三道防呆守門鎖體系 (Triple-Lock Guard)"]
        L1["【第 1 鎖：靜態門禁】\ndev.checker.Checker\nAST 語法樹禁止原生 unittest.TestCase"]
        L2["【第 2 鎖：動態門禁】\ndev.testing.runner.TestDiscovery\nisinstance(test, YSCBTestCase) 斷言"]
        L3["【第 3 鎖：入口門禁】\ndev.testing.case.YSCBTestCase.setUp\n檢測非沙盒宿主環境 ➔ 拋出 SecurityError 阻斷"]
    end

    subgraph FilterEngine["分類與過濾引擎 (dev.testing.runner.filter_suite)"]
        F1["預設過濾遮罩：DEFAULT_MASK = LOGIC | ENV"]
        F2["顯式分類過濾：--logical, --env, --workflow, --perf, --all-types"]
        F3["精準目標定位：--target=<mod>:[<case>][.<method>]"]
    end

    subgraph SandboxEnv["虛擬沙盒執行環境 (cache://dev/sandbox/uuid/)"]
        S1["模組 A 沙盒 (獨立 PID)"]
        S2["模組 B 沙盒 (獨立 PID)"]
        S3["模組 C 沙盒 (獨立 PID)"]
    end

    C1 --> TripleLock
    C2 --> TripleLock
    TripleLock --> FilterEngine
    FilterEngine --> S1
    FilterEngine --> S2
    FilterEngine --> S3
```

---

## 2. 核心架構時序圖 (Sequence Diagrams)

### 2.1 測試分類過濾與目標定位時序圖

```mermaid
sequenceDiagram
    autonumber
    actor Dev as 開發者
    participant Tester as dev.tester.Tester
    participant Discovery as dev.testing.runner.TestDiscovery
    participant Filter as dev.testing.runner.filter_suite
    participant Runner as dev.testing.runner.TestRunner
    participant Case as YSCBTestCase

    Dev->>Tester: python yscb.py dev test --all
    Tester->>Discovery: discover_modules() & build_suite_for_module(mod)
    Discovery->>Discovery: 檢查 isinstance(test, YSCBTestCase) [動態守門]
    Discovery-->>Tester: raw_suite (含所有方法)
    Tester->>Filter: filter_suite(raw_suite, types=['logic', 'env'], target=None)
    Filter->>Filter: 僅保留 LOGIC 與 ENV 測試 (略過 WORKFLOW 與 PERF)
    Filter-->>Tester: filtered_suite
    Tester->>Runner: run_suite(filtered_suite)
    Runner->>Case: setUp() [入口守門]
    Case->>Case: 驗證處於沙盒環境 (YSCB_TEST_SANDBOX==1)
    Runner-->>Dev: 輸出跑測診斷報告 (快速回歸完成)
```

---

## 3. 技術選型與設計決策 (Design Decisions)

| 設計維度 | 決策方案 | 決策理由與替代方案對比 |
| :--- | :--- | :--- |
| **四層測試列舉** | `Requirement(Flag)` 包含 `LOGIC`, `ENV`, `WORKFLOW`, `PERF`, `ISOLATED_SANDBOX` | 採用 Python `enum.Flag` 支援位元 OR 組合（如 `@require(Requirement.LOGIC \| Requirement.ISOLATED_SANDBOX)`）。 |
| **預設過濾策略** | `DEFAULT_MASK = LOGIC \| ENV` | 保障日常開發與全量回歸可在秒級快速完成；重型 E2E 工作流與壓力測試需顯式開關觸發。 |
| **非標準入口阻斷** | `YSCBTestCase.setUp` 拋出 `SecurityError` | 防止任何在宿主裸跑之行為侵犯真實檔案系統，防禦強度超越靜態文件規範。 |
| **多模組並行跑測** | `concurrent.futures.ProcessPoolExecutor` | 各模組沙盒相互獨立，利用多核心將跑測耗時壓縮至單一最慢模組時間。 |
