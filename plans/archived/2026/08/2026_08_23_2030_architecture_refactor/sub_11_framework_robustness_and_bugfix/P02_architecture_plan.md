# 架構與模組設計說明書 (Architecture & Module Plan)

> 功能名稱：套件框架健壯性強化與缺陷修復 (Framework Robustness & Bug Fixes)  
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
    classDef host fill:#1e1e2e,stroke:#cba6f7,stroke-width:2px,color:#cdd6f4;
    classDef core fill:#0f172a,stroke:#3b82f6,stroke-width:2px,color:#60a5fa;
    classDef dev fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#34d399;
    classDef box fill:#1e293b,stroke:#64748b,stroke-width:2px,color:#f8fafc;

    subgraph HostEntry ["超薄宿主入口 (yscb.py)"]
        LoadCfg["<b>load_config()</b><br/>• 剛性錨定同層目錄<br/>• 移除向上爬樹防沙盒逃逸"]:::host
        Dispatch["<b>dispatch_module()</b><br/>• 動態派發至 modules/{mod}"]:::host
    end

    subgraph CoreModule ["Core 核心基礎設施模組 (source/core/core/)"]
        ContextSSOT["<b>context.py</b><br/>• ExecutionContext (frozen dataclass SSOT)"]:::core
        SemVerEngine["<b>semver.py (NEW)</b><br/>• VersionTuple / parse_semver<br/>• match_constraint / find_best_version"]:::core
        UriEngine["<b>uri.py</b><br/>• _get_host_config (拓撲保證重構)<br/>• resolve (非標準字串 ValueError)<br/>• module_scope / host_scope CM"]:::core
        EngineSys["<b>engine.py</b><br/>• act_snapshot (納入 config.root://)<br/>• act_restore_snapshot (雙層還原)<br/>• act_download (版本目錄嚴格比對)<br/>• act_solve_deps (接入 SemVer)"]:::core
        InstallerSys["<b>installer.py</b><br/>• cmd_update (SemVer 數值排序)<br/>• 移除 default_provider 後門"]:::core
        ContribSys["<b>contributes.py</b><br/>• 移除 source/ 與 project:// 穿透"]:::core
    end

    subgraph DevModule ["Dev 開發與測試模組 (source/dev/dev/)"]
        SandboxSys["<b>testing/sandbox.py</b><br/>• 動態讀取 manifest.json 版本<br/>• 剛性定位 host_d/yscb.py"]:::dev
        RunnerSys["<b>testing/runner.py</b><br/>• Contract / Custom 精準分類計數<br/>• 獨立清單列出失敗測試案例"]:::dev
    end

    LoadCfg --> Dispatch
    Dispatch --> UriEngine
    UriEngine -->|Re-export| ContextSSOT
    InstallerSys --> SemVerEngine
    EngineSys --> SemVerEngine
    EngineSys --> UriEngine
    ContribSys --> UriEngine
    SandboxSys --> UriEngine
    RunnerSys --> DevModule
```

---

## 2. 核心運作流程與循序圖 (Lifecycle Sequence Flow)

### 2.1 SemVer 版本求解與升級循序圖 (FR-05)

```mermaid
sequenceDiagram
    autonumber
    actor Dev as 開發者 / CLI
    participant Inst as installer.py (cmd_update)
    participant Eng as engine.py (act_solve_deps)
    participant Sem as semver.py (NEW)
    participant Prov as Provider / Mirror

    Dev->>Inst: yscb core update <mod>
    activate Inst
    Inst->>Prov: 讀取 index.json ["versions"]
    Prov-->>Inst: 回傳版本清單 ["1.8.0", "1.9.0", "1.10.0"]
    Inst->>Sem: find_best_version(versions, constraint=None)
    activate Sem
    Sem->>Sem: parse_semver 數值排序: 1.10.0 > 1.9.0
    Sem-->>Inst: 回傳最新版 "1.10.0"
    deactivate Sem
    
    Inst->>Eng: act_solve_deps(mod, ">=1.0.0", prov_url)
    activate Eng
    Eng->>Sem: match_constraint(candidate, ">=1.0.0")
    Sem-->>Eng: 匹配通過最高版本
    Eng-->>Inst: 依賴求解清單 [(mod, "1.10.0")]
    deactivate Eng
    Inst-->>Dev: 執行原子升級並反饋成功
    deactivate Inst
```

### 2.2 雙層組態快照備份與回滾循序圖 (FR-08)

```mermaid
sequenceDiagram
    autonumber
    actor CLI as 套件安裝器 / 回滾命令
    participant Eng as engine.py
    participant VFS as uri.py
    participant Snap as snapshot://snap_{id}/

    Note over CLI,Snap: 1. 安裝前建立雙層快照
    CLI->>Eng: act_snapshot(tag)
    activate Eng
    Eng->>VFS: 備份 yscb.config.json 至 snapshot://
    Eng->>VFS: 遞迴複製 config.root:// 至 snapshot://config/
    Eng-->>CLI: 回傳 snapshot_id
    deactivate Eng

    Note over CLI,Snap: 2. 安裝失敗或執行 rollback 時還原
    CLI->>Eng: act_restore_snapshot(snapshot_id)
    activate Eng
    Eng->>VFS: 覆蓋還原 yscb.config.json
    Eng->>VFS: 完整清空並覆蓋還原 config.root://
    Eng->>Eng: act_reload() (自 mirror 重新物化 modules/)
    Eng-->>CLI: 達成 100% 純淨回滾
    deactivate Eng
```

---

## 3. 受影響模組與檔案矩陣 (Impacted Files Matrix)

| 檔案路徑 | 變更類型 | 核心職責與修改重點 | 對應 FR / EC |
| :--- | :---: | :--- | :--- |
| [`yscb.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/yscb.py) | Modify | 移除 `load_config` 之 `while True` 向上爬樹，剛性錨定同層 `yscb.config.json`。 | FR-01<br/>EC-01 |
| [`source/core/core/context.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/context.py) | Modify | 定義最新版 `@dataclass(frozen=True)` 之 `ExecutionContext` 作為單一真相來源 (SSOT)。 | FR-07 |
| [`source/core/core/semver.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/semver.py) | **NEW** | 純 Python 標準庫 SemVer 2.0.0 運算器：三元組解析、比較、排序與範圍過濾器（`>=, >, <=, <, ==, ~=, *`）。 | FR-05<br/>EC-02, EC-03 |
| [`source/core/core/uri.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/uri.py) | Modify | 1. `_find_host_config` 重命名為 `_get_host_config` 並補齊拓撲註解。<br/>2. `resolve()` 移除非法字串雙重猜測，非標準拋出 `ValueError`。<br/>3. 提供 `module_scope` 與 `host_scope` 上下文管理器。<br/>4. `from core.context import ExecutionContext` 重新導出。 | FR-03, FR-06, FR-07, FR-10<br/>EC-01, EC-06 |
| [`source/core/core/engine.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/engine.py) | Modify | 1. `act_solve_deps` 接入 `core.semver` 範圍解算。<br/>2. `act_snapshot` / `act_restore_snapshot` 納入 `config.root://` 雙層備份還原。<br/>3. `act_download` 嚴格比對特定版本目錄與 manifest 版本。<br/>4. 補齊 OS 原子鎖與快照還原註解。 | FR-05, FR-06, FR-08, FR-09<br/>EC-03, EC-04, EC-05 |
| [`source/core/core/installer.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/installer.py) | Modify | 1. `cmd_update` 接入 SemVer 排序。<br/>2. 移除 `default_provider` 3 層 fallback 與硬編碼後門。 | FR-04, FR-05 |
| [`source/core/core/contributes.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/contributes.py) | Modify | 移除對 `module.source.root://` 與 `project://` 的跨空間穿透 fallback。 | FR-02 |
| [`source/dev/dev/testing/sandbox.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/testing/sandbox.py) | Modify | 1. 拷貝模組時動態讀取真實 `manifest.json` 版本號。<br/>2. 移除宿主 `yscb.py` 猜測，剛性定位 `host_d/yscb.py`。 | FR-04, FR-11 |
| [`source/dev/dev/testing/runner.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/testing/runner.py) | Modify | 1. 分離 Contract 與 Custom 通過數/失敗數統計。<br/>2. 於測試結果印出獨立的失敗案例詳細清單。 | FR-12 |
| [`source/core/tests/test_semver.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/tests/test_semver.py) | **NEW** | SemVer 2.0.0 解析、排序、前綴範圍與邊界異常單元測試。 | FR-05<br/>EC-02, EC-03 |
| [`source/core/tests/test_robustness.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/tests/test_robustness.py) | **NEW** | 雙層快照還原、Context Manager 隔離防護、無效 URI 攔截與 Provider 版本校驗整合測試。 | FR-03, FR-08, FR-09, FR-10<br/>EC-01, EC-04, EC-05, EC-06 |

---

## 4. 決策紀錄整合 (Decision Records Master List)

- `[P02:DR-01]`：`yscb.py` 剛性錨定同層目錄 `yscb.config.json`，徹底移除向上爬樹以杜絕沙盒穿透。
- `[P02:DR-02]`：建立純標準庫 `core.semver` 子模組，支援標準三元組比對與 `>=, >, <=, <, ==, ~=, *` 範圍匹配，杜絕 `"1.10.0" < "1.9.0"` 字串排序 Bug。
- `[P02:DR-03]`：將 `_find_host_config()` 重構為 `_get_host_config()`，補齊微內核常量自定位物理拓撲不變量之架構註解。
- `[P02:DR-04]`：採方案 B 將 `ExecutionContext` 收斂於 `core/core/context.py` 作為唯一 SSOT，`core.uri` re-export 保持向後相容。
- `[P02:DR-05]`：`act_snapshot` 範圍擴充納入 `config.root://`，還原時雙層覆蓋還原，達成 100% 純淨的組態級回滾。
- `[P02:DR-06]`：`core.uri` 提供 `module_scope` 與 `host_scope` 上下文管理器，退出時 `finally` 自動還原舊狀態。
- `[P02:DR-07]`：沙盒繼承動態讀取真實 `manifest.json` 版本號；`dev.runner` 精準分離測試計數並以獨立清單展示失敗詳情。
