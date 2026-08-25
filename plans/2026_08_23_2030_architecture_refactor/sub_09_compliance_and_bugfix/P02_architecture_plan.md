# 架構與模組設計 (Architecture & Module Design)

> 功能名稱：架構合規性缺陷修復與穩固性強化 (Architecture Compliance Bugfix & Hardening)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 架構拓撲與模組分層設計

```mermaid
graph TD
    classDef host fill:#1e293b,stroke:#64748b,stroke-width:2px,color:#f8fafc;
    classDef core fill:#0f172a,stroke:#3b82f6,stroke-width:2px,color:#60a5fa;
    classDef dev fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#34d399;

    subgraph HostLayer ["宿主層 (Host: yscb.py)"]
        HostBoot["宿主啟動器 (yscb.py)<br/>• 讀取 yscb.config.json 取得 yscb_root<br/>• 派發 CLI 時注入 YSCB_HOST_DIR"]:::host
        HostCfg["宿主組態 (yscb.config.json)<br/>• 記錄 yscb_root, default_provider, installed_modules"]:::host
    end

    subgraph MicrokernelLayer ["微內核層 (module:core)"]
        VFS["First-Class VFS SDK (core.uri)<br/>• yscb://: 基於 __file__ 常數確定性自定位<br/>• project://: 僅由 config/core/config.project.json 解算 (Zero Fallback)"]:::core
        Engine["AtomicEngine (core.engine)<br/>• 宿主組態操作: 直接透過 host_dir 讀寫 yscb.config.json (脫離 project://)<br/>• act_solve_deps: 遞迴相依拓撲排序 + 循環相依檢測"]:::core
        Installer["套件管理器 (core.installer)<br/>• cmd_remove: 實作反向相依阻斷檢查 (支援 --force)"]:::core
    end

    subgraph DevToolchainLayer ["開發者工具鏈 (module:dev)"]
        Builder["純淨打包器 (dev.builder)<br/>• build_module(): 打包後自動更新 build/{module}/index.json 版本清冊"]:::dev
    end

    HostBoot -->|1. 派發子程序時注入 host_dir| MicrokernelLayer
    VFS -->|2. 提供確定性 VFS 路徑| Engine
    VFS -->|2. 提供確定性 VFS 路徑| Builder
    Engine -->|3. 組態管理與相依拓撲| Installer
```

---

## 2. 核心循序與調用流程 (Sequence & Flowcharts)

### 2.1 宿主派發與 Host Context 注入循序圖
```mermaid
sequenceDiagram
    autonumber
    actor User as 使用者
    participant Host as yscb.py (宿主)
    participant Core as core (CLI/Engine)
    participant VFS as core.uri (VFS SDK)

    User->>Host: python yscb.py dev test --all
    Host->>Host: 讀取 yscb.config.json 確定 yscb_root
    Host->>Host: 計算 host_dir (自身目錄)
    Host->>Core: subprocess.run([cli.py, ...], env={..., YSCB_HOST_DIR: host_dir})
    Core->>VFS: 初始化/讀取 host_dir
    VFS-->>Core: 確立宿主目錄基準 (零動態猜測)
```

### 2.2 `yscb://` 代碼位置常數確定性解析流程
```mermaid
flowchart TD
    Call["呼叫 uri.resolve('yscb://...')"] --> Probe["獲取 core.uri 之 __file__ 絕對實體路徑"]
    Probe --> Calc["往上 3 層計算: os.path.dirname(os.path.dirname(os.path.dirname(__file__)))"]
    Calc --> Match["得到確定性 yscb_root 實體目錄 (零 while 迴圈、零 getcwd 猜測)"]
    Match --> Resolve["與子路徑拼接並正規化返回"]
```

### 2.3 `cmd_remove` 反向相依安全阻斷防護流程
```mermaid
flowchart TD
    Start["執行 cmd_remove(mod, force=False)"] --> HardGuard{"mod == 'core' ?"}
    HardGuard -- 是 --> BlockCore["拋錯: Cannot remove 'core' 基礎設施"]
    HardGuard -- 否 --> ScanDeps["掃描所有已安裝模組之 manifest.json"]
    ScanDeps --> DepCheck{"是否有其他模組<br/>宣告依賴 mod ?"}
    DepCheck -- 否 --> Proceed["安全執行 UNREGISTER ➔ RELOAD"]
    DepCheck -- 是 --> ForceCheck{"force == True ?"}
    ForceCheck -- 是 --> WarnProceed["輸出 Warning 提示 ➔ 強制執行移除"]
    ForceCheck -- 否 --> BlockRemoval["輸出 Error: Required by {dependents}. Use --force to override. ➔ Exit 1"]
```

### 2.4 `dev build` 自動更新 `index.json` 流程
```mermaid
flowchart TD
    BuildPass["模組純淨打包至 build/{module}/{version}/ 成功"] --> ScanVersions["掃描 build/{module}/ 下所有版本目錄"]
    ScanVersions --> ParseSemVer["提取所有版本號並依 SemVer 升序排序且去重"]
    ParseSemVer --> WriteIndex["寫入/更新 build/{module}/index.json<br/>{name, description, versions: [...]}"]
    WriteIndex --> Complete["完成 Build 返回成功報告"]
```

---

## 3. 受影響檔案與變更矩陣

| 檔案路徑 | 變更性質 | 影響模組 / 核心職責 | 說明 |
| :--- | :---: | :--- | :--- |
| [`source/core/core/uri.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/uri.py) | Modify | `core.uri` | 實作 `__file__` 常數自定位、`set_host_dir()`、環境變數 `YSCB_HOST_DIR` 探測，徹底移除 `while` 爬目錄與 `os.getcwd()` 猜測。 |
| [`source/core/core/engine.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/engine.py) | Modify | `core.engine` | `_get_config`, `_save_config`, `act_init`, `act_snapshot`, `act_restore_snapshot` 改用 `host_dir` 操作；實作 `act_solve_deps` 遞迴相依拓撲求解與循環相依檢測。 |
| [`source/core/core/installer.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/installer.py) | Modify | `core.installer` | `cmd_remove` 增加反向相依阻斷檢查（支援 `--force` 旗標與參數解析）。 |
| [`source/dev/dev/builder.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/builder.py) | Modify | `dev.builder` | `build_module` 打包完成後自動維護 `build/{module}/index.json`。 |
| [`source/dev/contributes.format.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/contributes.format.md) | NEW | `dev` | 建立 Dev 模組對外貢獻說明書。 |
| [`yscb.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/yscb.py) | Modify | `host` | `cmd_init` 補齊 `default_provider`；`dispatch_module` 派發子程序時注入 `YSCB_HOST_DIR` 環境變數。 |
| [`source/core/tests/`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/tests/) | Modify/NEW | `core.tests` | 補充宿主組態解耦、反向相依阻斷、`FileNotFoundError` 阻斷與相依拓撲測試案例。 |
| [`source/dev/tests/`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/tests/) | Modify/NEW | `dev.tests` | 補充 `index.json` 自動生成驗證測試。 |

---

## 4. 決策紀錄 (Decision Records)

### [P02:DR-01] 宿主 Context 注入採用「環境變數傳遞 + API 設定」雙通道
- **結論**：`yscb.py` 在 `dispatch_module` 時，將自身的 `host_dir` 注入至 `os.environ["YSCB_HOST_DIR"]`；`core.uri` 提供 `set_host_dir(path)` 與 `get_host_dir()` 作為程式碼調用通道。
- **理由**：既滿足 CLI 子程序調度時的無縫傳遞，又滿足外部 Python 程式碼直接引用 SDK 時的顯式配置。

### [P02:DR-02] `index.json` 採原地掃描增量維護
- **結論**：`Builder.build_module` 在每次成功產出版本目錄後，掃描 `build/{module}/` 目錄下所有包含 `manifest.json` 的子目錄，提取版本號並依 SemVer 排序寫入 `index.json`。
- **理由**：保證 `index.json` 永遠與本地套件庫實體版本目錄 100% 同步，且不遺漏手動放置或歷史建置之版本。

---

## 5. 閉合確認 (Closing Confirmation)

- [x] 開發者已確認：P02 架構設計與循序圖確認無誤，可進入 Phase 3
