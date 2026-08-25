# 架構設計說明書 (Architecture Plan)

> 功能名稱：core contribute 系統優化與路徑系統打磨 (Core Contribute Optimization & URI Polish)  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 依據需求規格：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 狀態：`Confirmed`  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 系統架構拓撲 (Architecture Topology)

```mermaid
flowchart TD
    subgraph Microkernel ["Core 微內核基礎設施 (module:core)"]
        URI_VFS["URI / VFS 虛擬檔案系統<br/>(source/core/core/uri.py)"]
        JIT_Engine["JIT 熱補齊引擎<br/>(Prompt / Cascading / AutoSave)"]
        Contrib_Aggr["Contributes 聚合器<br/>(source/core/core/contributes.py)"]
        Topo_Sorter["拓撲排序器<br/>(Dependency Topology Ingestion)"]
        Contrib_SDK["Contributes 查詢 SDK<br/>(core.contributes.get)"]
    end

    subgraph Storage ["快取與組態持久層"]
        Merged_Cache["cache.root://{mod}/contributes.merged.json<br/>(__provider__ 標記)"]
        Project_Config["config.root://{mod}/config.project.json<br/>(JIT 自動回填寫入)"]
    end

    subgraph Downstream ["下游消費端模組"]
        Agents_AW["agents-workflow<br/>(工廠物化 / 自省指令)"]
        Dev_Tool["dev 工具箱<br/>(測試沙盒 / 打包)"]
        User_CLI["使用者終端 CLI<br/>(yscb.py 轉發)"]
    end

    User_CLI -->|呼叫指令| URI_VFS
    URI_VFS -->|探測 !undefined| JIT_Engine
    JIT_Engine -->|互動提示 / 回填| Project_Config
    JIT_Engine -->|熱刷新記憶體| URI_VFS

    Contrib_Aggr -->|取得模組拓撲順序| Topo_Sorter
    Contrib_Aggr -->|注入 __provider__| Merged_Cache
    Contrib_SDK -->|讀取快取 / 自愈重聚| Merged_Cache

    Agents_AW -->|SDK 查詢| Contrib_SDK
    Dev_Tool -->|SDK 查詢| Contrib_SDK
```

---

## 2. 核心呼叫循序圖 (Sequence Diagrams)

### 2.1 JIT 協議熱補齊與自動持久化循序圖

```mermaid
sequenceDiagram
    autonumber
    actor User as 使用者 / CLI
    participant VFS as core.uri.resolve()
    participant JIT as JIT Reconciler
    participant TTY as 終端互動介面 (sys.stdout/stdin)
    participant Cfg as config.project.json
    participant Cache as URI 記憶體快取

    User->>VFS: uri.resolve("plans://P01.md")
    VFS->>VFS: 查表發現 "plans" 協議解算為 "!undefined"
    alt interactive=False 或非 TTY
        VFS-->>User: 拋出 UndefinedURIError (附帶修復範例)
    else interactive=True 且為 TTY
        VFS->>JIT: 觸發 reconcile_undefined_uri("plans", provider, binding)
        JIT->>TTY: 顯示提示 ([-y <path> / -n / --help], yscb:// 基準)
        alt 使用者輸入 --help
            TTY->>JIT: "--help"
            JIT->>TTY: 輸出協議詳情與全系統已註冊 URI 清單
            JIT->>TTY: 重新提示輸入
        end
        User->>TTY: 輸入 "-y ./plans" (或 "project://plans")
        TTY->>JIT: "-y ./plans"
        opt 輸入包含未定義協議 (連鎖依賴)
            JIT->>JIT: 遞迴優先熱補齊基礎協議 (如 project://)
        end
        JIT->>Cfg: 原子寫入 paths.plans_dir = "./plans"
        JIT->>Cache: 即時刷新 URI 快取映射
        JIT-->>VFS: 熱補齊完成，返回實體路徑
        VFS-->>User: 正常返回 "H:/.../plans/P01.md"，命令無縫繼續執行
    end
```

### 2.2 依賴拓撲搜集與 `__provider__` 注入循序圖

```mermaid
sequenceDiagram
    autonumber
    participant Engine as core.engine (Reload / Boot)
    participant Aggr as ContributesAggregator
    participant Installer as core.installer (Dependency Solver)
    participant Cache as contributes.merged.json

    Engine->>Aggr: scan_and_inject(target_module)
    Aggr->>Installer: 取得已安裝模組之 Topological Order
    Installer-->>Aggr: 返回有序清單 ["core", "dev", "agents-workflow"]
    loop 依拓撲順序遍歷 donor 模組
        Aggr->>Aggr: 讀取 donor 的 manifest.json (contributes)
        Aggr->>Aggr: 自動為 Dict / List[Dict] 項目注入 __provider__ = donor
        Aggr->>Aggr: 有序合併至 target 合併池
    end
    Aggr->>Cache: 原子寫入 cache.root://{target}/contributes.merged.json
```

---

## 3. 模組影響盤點 (Impact Inventory)

| 影響檔案 | 變更類型 | 變更核心職責說明 |
| :--- | :---: | :--- |
| `source/core/core/uri.py` | Modify | 實作 `!undefined` 攔截、JIT 互動熱補齊、`--help` 協議清冊展開、連鎖遞迴解算與 `UndefinedURIError`。 |
| `source/core/core/contributes.py` | Modify | 實作 `__provider__` 自動注入、依賴拓撲順序遍歷、`core.contributes.get()` 與 `get_for_current_module()` SDK。 |
| `source/core/core/engine.py` | Modify | 在 Reload Stage 4 串接拓撲排序與 Contributes 聚合。 |
| `source/core/tests/test_contributes.py` | Modify / Add | 測試 `__provider__` 標記、拓撲合併順序與 SDK 查詢 API。 |
| `source/core/tests/test_uri.py` | Modify / Add | 測試 JIT 熱補齊、`--help` 清單展開、非 TTY 異常防護與連鎖未定義解析。 |
| `docs/core/README.md` | Modify | 更新 VFS JIT 熱補齊與 Contributes SDK 使用說明。 |
| `docs/core/DESIGN_NOTES.md` | Modify | 登記 `[DN-CORE-05]`（JIT 協議熱補齊哲學）與 `[DN-CORE-06]`（`__provider__` 追溯性）。 |

---

## 4. 架構決策記錄 (Architecture Decisions)

- **[P02:DR-01] VFS 最底層收斂 JIT 熱補齊**：
  - 將未初始化攔截統一下沉至 `core.uri.resolve()`，上層所有模組與 CLI 自動享有開箱即用的熱更新補齊能力，杜絕各模組重複造輪子。
- **[P02:DR-02] `yscb://` 統一相對路徑基準與語意協議直通**：
  - 熱補齊提示明確以 `yscb://` 為相對起始基準，並原生支援輸入語意協議（如 `project://`），消除路徑歧義並保持零臆測。
- **[P02:DR-03] `__provider__` 隱式自動注入與非破壞性**：
  - 微內核在搜集階段自動補齊來源模組標籤，對業務無感且不覆蓋顯式指定值，使所有聚合配置具備 100% 來源可追溯性。
