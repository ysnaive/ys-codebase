# 語意 URI 協議與動態解析專題手冊 (Semantic URI Protocol & Dynamic Resolution)

> 本手冊為維度 3 中觀專題手冊，詳細定義 YS-Codebase 方案 B 語意 URI 協議、`@/` 當前模組自省、跨模組尋址與 `project://` 零 Fallback 阻斷規範。

---

## 1. 語意 URI 核心原則與自宣告注入架構

YS-Codebase 採用「方案 B：全量 Root 化 + `@/` 標籤語法模型」，徹底廢除所有 `*.root://` 協議與 `temp://`，形成清晰正交的 8 大標準協議庫：

```mermaid
graph TD
    classDef comp fill:#1e293b,stroke:#3b82f6,stroke-width:2px,color:#fff;
    classDef cache fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#fff;

    M1["Core 模組<br/><code>source/core/manifest.json</code><br/><i>宣告 8 組核心協議 (Root 化)</i>"]:::comp
    M2["Dev 模組<br/><code>source/dev/manifest.json</code><br/><i>宣告 3 組開發協議 (Root 化)</i>"]:::comp
    
    Aggregator["依賴注入聚合器<br/><code>ContributesAggregator</code><br/><i>合併 contributes (reload 時執行)</i>"]:::comp
    
    CacheFile["中介層物化快照<br/><code>cache://core/contributes.merged.json</code><br/><i>O(1) 高速查表快取</i>"]:::cache
    
    Resolver["語意路徑解算器<br/><code>core.uri.resolve()</code>"]:::comp

    M1 --> Aggregator
    M2 --> Aggregator
    Aggregator --> CacheFile
    CacheFile --> Resolver
```

---

## 2. 8 大標準 Canonical URI 協議清單

| 協議 Token | 注入來源 | 物理映射 | Git 策略 | 說明與跨模組尋址範例 |
| :--- | :---: | :--- | :---: | :--- |
| **`storage://`** | `core` | `yscb://storage/` | **Tracked** | 模組持久化儲存空間（跨模組：`storage://dev/file.json`；自省：`storage://@/data.json`） |
| **`cache://`** | `core` | `yscb://.cache/` | **Ignored** | 模組快取與暫存空間（替代已廢除之 `temp`；沙盒：`cache://dev/sandbox/`） |
| **`config://`** | `core` | `yscb://config/` | **Tracked** | 模組專屬設定檔空間（跨模組：`config://agents-workflow/config.project.json`） |
| **`module://`** | `core` | `yscb://modules/` | **Installed** | 本地模組運行端空間（自省：`module://@/manifest.json`） |
| **`module.source://`** | `dev` | `yscb://source/` | **Dev-Only** | 模組源碼開發空間（跨模組：`module.source://core/core/uri.py`） |
| **`module.build://`** | `dev` | `yscb://build/` | **Dev-Only** | 本地開發完整建置產物空間 |
| **`module.release://`** | `dev` | `yscb://release/` | **Dev-Only** | 模組純淨發布產物來源空間 |
| **`module.mirror://`** | `core` | `yscb://.mirror/` | **Ignored** | 本地模組壓縮鏡像庫空間 |

---

## 3. 方案 B 解算模型 (Option B Addressing Rules)

### 3.1 跨模組顯式尋址
- 語法：`{scheme}://{module}/{path}`
- 範例：`storage://dev/state.json` ➔ `yscb://storage/dev/state.json`
- 規範：協議 Token 直接對應空間根目錄，後面第一段 Path 為目標模組名稱，**絕無雙重嵌套**。

### 3.2 當前模組自省尋址 (`@/` 語法)
- 語法：`{scheme}://@/{path}`
- 範例：在 `agents-workflow` 模組執行時調用 `storage://@/release_manifest.json` ➔ `yscb://storage/agents-workflow/release_manifest.json`。
- 上下文保護 (EC-01)：若無 active module context 且未傳入 `current_module`，`uri.resolve()` 強制拋出 `UndefinedModuleContextError`，杜絕資料跨模組污染。

### 3.3 空間根目錄存取
- 語法：`{scheme}://`
- 範例：`storage://` ➔ `yscb://storage/`。

### 3.4 舊協議相容轉譯層 (Backwards Compatibility)
- 調用舊版 `storage.root://`、`cache.root://`、`module.root://` 等協議時，解算器自動發出 `DeprecationWarning` 並重定向至 Canonical 協議，確保歷史設定平滑過渡。

---

## 4. `project://` 顯式配置與零 Fallback 阻斷規範

- **唯一配置來源**：`yscb://config/core/config.project.json` 中配置之 `project_root` 鍵。
- **預設值**：`"!undefined"`。
- **阻斷行為**：未配置時調用 `uri.resolve("project://...")` 強制拋出例外，**嚴禁 Fallback 猜測 `os.getcwd()`**。

---

## 5. `yscb://` 雙軌對稱注入體系與常數自定位

- **常數基準自省**：預設依據 `core.uri` 物理路徑向上 3 層確定性解算，零 `os.getcwd()` 猜測。
- **宿主目錄注入 (`host_dir`)**：
  - 記憶體注入：`uri.set_host_dir(path)` 與 `uri.host_scope(path)` Context Manager。
  - 環境變數：`YSCB_HOST_DIR`。
- **核心工具庫注入 (`yscb_root`)**：
  - 記憶體注入：`uri.set_yscb_root(path)` 與 `uri.yscb_scope(path)` Context Manager。
  - 環境變數：`YSCB_ROOT_DIR`。
- **三階自省優先順序**：
  $$\text{記憶體注入 } (\texttt{\_active\_yscb\_dir}) \;\longrightarrow\; \text{環境變數 } (\texttt{YSCB\_ROOT\_DIR}) \;\longrightarrow\; \text{常數基準 } (\texttt{\_\_file\_\_})$$
- **沙盒鉤子隔離保證**：測試 Runner 在調度 `scripts/hook.dev.py` 時，強制包覆 `with uri.host_scope(ctx.host_dir), uri.yscb_scope(ctx.engine_dir):`，確保所有 VFS 與 `core.config` 操作 100% 沙盒化。


