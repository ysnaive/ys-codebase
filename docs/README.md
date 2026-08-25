# YS-Codebase 系統架構與全域知識地圖 (System Overview & Architecture Map)

> 歡迎查閱 **YS-Codebase** 核心架構知識庫！  
> 本專案為 100% Python 標準庫、零第三方依賴構建之現代化模組化微內核系統。

---

## 1. 系統宏觀分層架構 (High-Level Architecture)

```mermaid
graph TD
    classDef host fill:#1e293b,stroke:#64748b,stroke-width:2px,color:#f8fafc;
    classDef micro fill:#0f172a,stroke:#3b82f6,stroke-width:2px,color:#60a5fa;
    classDef tool fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#34d399;
    classDef ext fill:#4c1d95,stroke:#8b5cf6,stroke-width:2px,color:#c084fc;

    Host["超薄宿主啟動器 (Thin Host)<br/><code>yscb.py</code><br/><i>無狀態指令轉發與核心自舉</i>"]:::host
    
    subgraph Microkernel ["Core 微內核基礎設施 (module:core)"]
        URI["語意 URI 協議與 First-Class VFS SDK<br/><code>core.uri</code> (Zero Fallback)"]
        Engine["AtomicEngine 12 原子操作引擎<br/><code>core.engine</code>"]
        Installer["套件管理與生命週期調度器<br/><code>core.installer</code>"]
        Contrib["5 來源依賴注入與快取聚合器<br/><code>core.contributes</code>"]
    end
    class Microkernel micro;

    subgraph Toolchain ["開發者工具鏈 (module:dev)"]
        Scaffold["模組腳手架 (Scaffolder)<br/><code>dev create</code>"]
        Checker["靜態合規檢查器 (Checker)<br/><code>dev check</code>"]
        Builder["純淨打包建置器 (Builder)<br/><code>dev build</code>"]
        Testing["沙盒測試與契約合成引擎 (Tester)<br/><code>dev test</code>"]
    end
    class Toolchain tool;

    subgraph Extensions ["領域擴充模組生態 (Extension Ecosystem)"]
        Agents["工作流與規範管理<br/><code>agents-workflow</code>"]
        CustomMod["其他自訂業務模組<br/><code>custom-modules...</code>"]
    end
    class Extensions ext;

    Host -->|自舉與動態調度| Microkernel
    Microkernel -->|提供底層 SDK 與擴充點| Toolchain
    Microkernel -->|依賴注入與生命週期廣播| Extensions
    Toolchain -->|腳手架、檢查、打包與測試| Extensions
```

---

## 2. 全域知識庫導覽地圖 (Knowledge Base Index)

| 核心維度 | 知識手冊路徑 | 說明 |
| :--- | :--- | :--- |
| **維度 2：核心規範** | [STANDARDS.md](./_project/STANDARDS.md) | 全專案四大空間協議、2x2 組態邊界、Dogfooding 自引用三層空間與標準閉環流水線 |
| **維度 2：核心內核** | [core/README.md](./core/README.md) | Core 微內核架構、AtomicEngine 12 原子操作、First-Class VFS SDK 與套件管理 |
| **維度 3：專題手冊** | [core/uri_protocols.md](./core/uri_protocols.md) | 語意 URI 協議規範、`project://` 零 Fallback 阻斷與中介快照動態解算機制 |
| **維度 3：專題手冊** | [core/lifecycle_and_hooks.md](./core/lifecycle_and_hooks.md) | 命名空間 Hook 對接規範 (`hook.{emit_module}.py`)、`ExecutionContext` 介面與例外隔離 |
| **維度 5：工程妥協** | [core/DESIGN_NOTES.md](./core/DESIGN_NOTES.md) | Core 微內核關鍵工程決策與設計註記 (`DN-01` ~ `DN-06`)，含宿主組態解耦 (DN-05) 與常數自定位零猜測阻斷 (DN-06) |
| **維度 2：開發工具** | [dev/README.md](./dev/README.md) | Dev 工具鏈架構、Scaffold 模組建立、Checker 規範檢驗、Builder 純淨打包 |
| **維度 3：專題手冊** | [dev/testing_guide.md](./dev/testing_guide.md) | `YSCBTestCase` 隔離沙盒生命週期、Auto-Contract 自動契約合成與兩階段測試 |
| **維度 5：工程妥協** | [dev/DESIGN_NOTES.md](./dev/DESIGN_NOTES.md) | Dev 開發者工具鏈關鍵設計註記 (`DN-DEV-01`) |

---

## 3. 模組生態總覽 (Module Registry)

| 模組名稱 | 版本 | 職責定位 | 主要進入點 |
| :--- | :---: | :--- | :--- |
| **`core`** | `1.0.0` | 系統微內核、VFS 檔案系統、套件生命週期、依賴注入與 Hook 派發 | `modules/core/scripts/cli.py` |
| **`dev`** | `1.0.0` | 開發者工具箱：腳手架、靜態檢查、純淨套件打包、單元/契約測試引擎 | `modules/dev/scripts/cli.py` |
