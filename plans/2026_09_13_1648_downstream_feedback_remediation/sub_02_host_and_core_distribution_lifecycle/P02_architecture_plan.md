# 架構設計說明書 (Architecture Design)

> 功能名稱：sub_02_host_and_core_distribution_lifecycle  
> 建立日期：2026-09-13  
> 所屬主計畫：2026_09_13_1648_downstream_feedback_remediation  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 模組架構分層與職責邊界 (Layered Architecture)

```text
+-------------------------------------------------------------------------------+
|                      Host Bootstrapper Layer (yscb.py)                        |
|  - 官方 Provider 常數 (DEFAULT_PROVIDER_URL: .../ys-codebase/main/release)     |
|  - Self-Update 來源解算器 (_resolve_self_update_url: 智能錨定 repo 根目錄)      |
|  - 自包含 Version Discovery (_discover_latest_core: 本地/遠端 semver 探測)   |
|  - Init & Self-Healing 引擎 (cmd_init: 預設 .yscb 根目錄，--fix 自癒與連鎖 reload)|
|  - 內部忽略規則清冊 (INTERNAL_IGNORE_PATTERNS: 納入 yscb.py.bak, *.bak)         |
+-------------------------------------------------------------------------------+
                                      |
                                      v (物化 .modules/core 並分派)
+-------------------------------------------------------------------------------+
|                      Core Module Engine & Lifecycle Layer                     |
|  - core.installer:                                                            |
|      * generate_internal_gitignore: 同步 yscb.py.bak 忽略規則                  |
|      * cmd_install / cmd_update: 安裝完成後連動 UpdateChecker 快取失效          |
|  - core.update_checker:                                                       |
|      * invalidate_cache: 模組變更後及時清除已解決之更新快取項目                 |
+-------------------------------------------------------------------------------+
```

---

## 2. 核心資料流與循序圖 (Data Flow & Sequence Diagram)

### 2.1 `yscb init --fix` 自癒修復與連鎖 Reload 流程

```mermaid
sequenceDiagram
    autonumber
    actor User as 開發者 / Agent
    participant Host as yscb.py (cmd_init)
    participant Provider as 套件來源 (Local / Remote)
    participant VFS as 實體磁碟 (.modules/core)
    participant Core as core.commands (dispatcher)

    User->>Host: python yscb.py init [--fix]
    Host->>Host: 檢查 yscb.config.json 是否存在
    alt 設定檔存在但 core 缺失 或 帶有 --fix
        Host->>Host: 讀取既有 default_provider 與 yscb_root
        Host->>Provider: 探測最新 core 版本 (_discover_latest_core)
        Provider-->>Host: 返回最高 semver (如 1.1.0.1)
        Host->>Provider: 下載並解壓 core/1.1.0.1.zip
        Host->>VFS: 原子寫入 .modules/core
        Host->>Host: 更新 yscb.config.json 內 core 版本資訊
        Host->>Core: 連鎖調用 dispatch_module("core", ["reload"])
        Core-->>Host: 刷新完成 (0)
        Host-->>User: [yscb] Core healed and environment reloaded successfully.
    else 設定檔已存在且 core 完好 (無 --fix)
        Host-->>User: Error: Configuration already exists. (提示使用 --fix)
    else 全新初始化 (設定檔不存在)
        Host->>Host: yscb_root 預設為 ".yscb"
        Host->>Provider: 探測最新 core 並解壓至 .yscb/.modules/core
        Host->>Host: 建立新 yscb.config.json
        Host->>Core: 連鎖調用 dispatch_module("core", ["reload"])
        Host-->>User: [yscb] Initialized successfully.
    end
```

### 2.2 `yscb self-update` 來源解析與安全原子替換流程

```mermaid
sequenceDiagram
    autonumber
    actor User as 開發者 / CLI
    participant Host as yscb.py (cmd_self_update)
    participant Remote as GitHub / Remote Server
    participant OS as 作業系統檔案系統

    User->>Host: python yscb.py self-update [--provider=... | --url=...]
    Host->>Host: 解算目標位址 (若 provider 含 /release 則取 dirname/yscb.py)
    Host->>Remote: 下載最新 yscb.py
    Remote-->>Host: 返回腳本內容
    Host->>Host: ast.parse(content) 語法安全檢驗
    Host->>OS: 寫入 yscb.py.tmp
    Host->>OS: 複製當前 yscb.py -> yscb.py.bak
    Host->>OS: os.replace(yscb.py.tmp, yscb.py)
    Host-->>User: [yscb] yscb.py updated successfully (backup saved at yscb.py.bak).
```

---

## 3. 受影響檔案與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `yscb.py` | Modify | 修正 `DEFAULT_PROVIDER_URL`；實作 `_resolve_self_update_target_url` 與 `cmd_self_update`；實作自包含 `_discover_latest_core`；重構 `cmd_init` 支援 `--fix`、預設 `".yscb"` 與連鎖 reload；補齊 `INTERNAL_IGNORE_PATTERNS`。 |
| `source/core/core/installer.py` | Modify | 於 `INTERNAL_IGNORE_PATTERNS` 增加 `"yscb.py.bak"`、`"*.bak"`；在 `cmd_install` 與 `cmd_update` 成功後調用 `UpdateChecker.invalidate_cache()`。 |
| `source/core/core/update_checker.py` | Modify | 新增 `invalidate_cache(module_name: Optional[str] = None)` 方法，支援局部或全量清除過期快取項目。 |
| `source/core/tests/test_distribution_lifecycle.py` | New | 新增單元測試驗證自包含 semver 探測、`init --fix` 自癒、self-update 解析、gitignore 忽略模式與快取失效。 |

---

## 4. 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 宿主自舉自包含 Version Discovery**：
  - 在 `yscb.py` 尚未解壓 `core` 之前無法導入 `core.semver`。
  - 於 `yscb.py` 實作自包含純字串/元組輕量語意版本解析函式 `_parse_simple_semver(v_str)`，以 4-tuple `(major, minor, patch, revision)` 進行純數學比對，兼具零依賴自舉與準確性。
- **[P02:DR-02] 連鎖 Reload 剛性執行**：
  - `cmd_init`（無論初次或 `--fix`）在解壓 core 模組與寫回設定檔後，必須立即以 `return dispatch_module("core", ["reload"])` 結束，保證環境狀態刷新為同一進程原子操作。
