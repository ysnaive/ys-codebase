# 架構設計書 (Architecture Plan)

> 功能名稱：Core 模組功能打磨 (Core Module Polish)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.2  

---

## 1. 系統架構拓撲 (System Architecture)

```mermaid
flowchart TD
    subgraph ConfigLayer ["專案組態層 (Explicit Config Space: yscb://config/)"]
        CoreCfg["yscb://config/core/config.project.json<br/>(project_root: './' 顯式路徑)"]
        ModCfg["yscb://config/{module}/config.project.json<br/>(各模組獨立專案組態)"]
    end

    subgraph URISystem ["core.uri: 語意 URI 與虛擬檔案系統 (VFS)"]
        Resolver["uri.resolve(path_or_uri)"]
        Context["ExecutionContext(module_name, command, args)"]
        
        Resolver -->|"project://"| CoreCfg
        Resolver -->|"config://"| ModCfg
        Resolver -->|"config.root://"| CfgRoot["yscb://config/"]
        Resolver -->|"動態 URI 協議 (type: config)"| ModCfg
        Resolver -->|"自訂佔位符 {token}"| DynamicHandler["調用 Handler 函式 (傳入 Context)"]
    end

    subgraph LifecycleEngine ["core.engine: 生命週期與事件調度引擎"]
        Installer["core.installer.Installer"]
        Engine["core.engine.AtomicEngine"]
        
        Installer -->|"物化安裝 / act_reload"| ConfigSeeder["_seed_module_configs(mod)<br/>(自動分發與增量補齊)"]
        ConfigSeeder -->|"若不存在: 複製範本<br/>若已存在: 補齊缺失鍵且保留舊值"| ModCfg
        
        Engine -->|"act_broadcast_event(emit_mod, event, ctx)"| EventDispatcher["動態掃描已安裝模組<br/>module.root://*/scripts/hook.{emit_mod}.py"]
        EventDispatcher -->|"try-except 例外隔離"| HookExec["執行 target_func(context)"]
    end
```

---

## 2. 模組分層與職責劃分 (Module Components)

| 模組 / 檔案路徑 | 職責定義 | 依賴關係 | 對應 FR |
| :--- | :--- | :--- | :--- |
| [`source/core/core/uri.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/uri.py) | 1. 實作 `ExecutionContext` 資料類別。<br/>2. 實作 `project://` 顯式無 Fallback 解算（讀取 `config/core/config.project.json` 之 `project_root`，未定義拋出 `ValueError`）。<br/>3. 將 `config.root://` 更新為 `yscb://config/`，`config://` 更新為 `yscb://config/{module}/`。<br/>4. 打通 `contributes` 宣告之 `type: "config"` 與 `type: "const"` 自訂 URI 協議與 `path_placeholders` 動態 handler 解算。 | `json`, `os`, `importlib` | FR-01, FR-02, FR-05 |
| [`source/core/core/engine.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/engine.py) | 1. 實作 `act_broadcast_event(emit_module, event_name, context)`：動態遍歷模組載入 `hook.{emit_module}.py` 並調度執行，實施 try-except 例外隔離。<br/>2. 實作 `_seed_or_update_config`：支援組態不存在時自動部署，已存在時遞迴比對增量補齊缺失條目。 | `core.uri`, `importlib.util` | FR-03, FR-04 |
| [`source/core/core/installer.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/installer.py) | 1. 於 `cmd_install` / `cmd_update` / `cmd_reload` 流程中觸發組態自動分發與增量補齊。<br/>2. 觸發 `on_install`, `on_update`, `on_remove`, `on_reload` 事件廣播。 | `core.engine`, `core.uri` | FR-03, FR-04 |
| `R01 ~ R04 白皮書` | 同步回填最新架構設計（`hook.{emit_module}.py`、顯式 `config/`、`project://` 零 Fallback、增量補齊）。 | 無 | NFR-04 |

---

## 3. 關鍵流程循序圖 (Sequence Diagrams)

### 3.1 命名空間 Hook 事件廣播流程 (`hook.{emit_module}.py`)

```mermaid
sequenceDiagram
    autonumber
    actor Emitter as 發起端模組 (例: dev / core)
    participant Engine as core.engine.AtomicEngine
    participant VFS as core.uri (VFS)
    participant Receiver as 接收端 (例: agents-workflow)

    Emitter->>Engine: act_broadcast_event("dev", "on_before_build", context)
    Engine->>VFS: listdir("module.root://") 取得所有模組
    loop 遍歷每個已安裝模組
        Engine->>VFS: exists("module.root://{mod}/scripts/hook.dev.py")
        alt 存在 hook.dev.py 檔案
            Engine->>Engine: importlib 動態載入 hook 模組
            alt 模組定義了 on_before_build 函式
                Engine->>Receiver: 調用 on_before_build(context)
                Note over Engine,Receiver: try-except 隔離保護：若拋出異常僅記錄 Warning
            end
        else 不存在該發起端 hook 檔案
            Engine->>Engine: 靜默略過
        end
    end
    Engine-->>Emitter: 廣播完成，繼續主流程
```

### 3.2 組態預設分發與增量缺失補齊流程 (Config Seeding & Auto-Fill)

```mermaid
sequenceDiagram
    autonumber
    actor CLI as Installer / act_reload
    participant Engine as core.engine.AtomicEngine
    participant VFS as core.uri (VFS)
    participant ConfigFile as yscb://config/{mod}/config.project.json

    CLI->>Engine: 物化模組並執行 _seed_module_configs(mod)
    Engine->>VFS: 檢查 mirror://{mod}/{ver}/ 是否附帶預設 config.project.json
    alt 存在預設組態範本
        Engine->>VFS: exists("config.root://{mod}/config.project.json")
        alt 目標組態不存在 (全新安裝)
            Engine->>ConfigFile: 直接複製預設範本至 yscb://config/{mod}/config.project.json
        else 目標組態已存在 (升級或重載)
            Engine->>ConfigFile: 讀取專案既有組態 data_existing
            Engine->>Engine: 遞迴遞補缺失鍵 (補齊 new_keys，用戶值 100% 保持不變)
            Engine->>ConfigFile: 寫回增量補齊後之 JSON
        end
    end
```

---

## 4. 影響檔案清單 (Impacted Files)

| 檔案路徑 | 變更類型 | 說明 |
| :--- | :---: | :--- |
| [`source/core/core/uri.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/uri.py) | Modify | 實作 `ExecutionContext`、`project://` 顯式配置解算（無 fallback）、`config/` 顯式目錄與動態 contributes 解析 |
| [`source/core/core/engine.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/engine.py) | Modify | 實作 `act_broadcast_event`（命名空間 hook 調度與隔離）與 `_seed_or_update_config`（增量補齊） |
| [`source/core/core/installer.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/installer.py) | Modify | 整合組態自動分發、生命週期事件發送與 `project://` 零 fallback 防護 |
| [`source/core/tests/test_uri.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/tests/test_uri.py) | Modify | 新增 `project://` 顯式與未配置阻斷測試、`config/` 新協議測試 |
| [`source/core/tests/test_engine.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/tests/test_engine.py) | Modify | 新增命名空間 hook 廣播、例外隔離與組態增量補齊測試 |
| [`source/core/tests/test_installer.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/tests/test_installer.py) | Modify | 新增模組安裝時自動種入與增量補齊組態驗證 |
| `R01_module_architecture_survey.md` ~ `R04_lifecycle_invocation_flow.md` | Modify | 回填對齊最新白皮書規範 |

---

## 5. 本階段決策紀錄 (Phase 2 Decision Records)

- **[P02:DR-01] 顯式 project_root 組態路徑**：`project://`  строго 從 `yscb://config/core/config.project.json` 之 `project_root` 解算；未配置直接拋出 `ValueError`。
- **[P02:DR-02] 顯式 config/ 專案目錄**：`config.root://` = `yscb://config/`，`config://` = `yscb://config/{module}/`。
- **[P02:DR-03] 命名空間 Hook 動態載入策略**：動態載入 `hook.{emit_module}.py` 時採用獨立模組名稱注入 `sys.modules`，防止全域命名空間污染。
- **[P02:DR-04] 字典遞迴深度補齊演算法**：組態補齊採用原地鍵補齊（Recursive Key Infill），僅新增缺失的 key，既有 key 的 value 絕對不被覆寫。
