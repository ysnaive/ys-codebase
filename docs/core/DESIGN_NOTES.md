---
target: "Core"
doc_type: "design_notes"
status: "active"
source_paths:
  - "yscb.host://yscb.py"
  - "yscb://source/core/core/__init__.py"
  - "yscb://source/core/core/uri.py"
  - "yscb://source/core/core/vfs/"
  - "yscb://source/core/core/engine.py"
  - "yscb://source/core/core/contributes.py"
  - "yscb://source/core/core/pip_manager.py"
  - "yscb://source/core/core/ide_projector.py"
  - "yscb://source/core/core/events.py"
related_docs:
  - "./README.md"
  - "./contributes_architecture.md"
  - "./uri_protocols.md"
  - "./vfs.md"
  - "./cli_commands_architecture.md"
  - "./ZIP_PACKAGE_SPEC.md"
  - "../_project/STANDARDS.md"
last_updated: "2026-10-15"
---

# Core 微內核設計決策與工程註記 (Core Design Notes)

> 本文件記錄 Core 微內核系統中的非直觀實作、工程妥協與關鍵防呆決策（維度 ⑤）。  
> 常規架構機制已下沉至對應中觀專題手冊；所有維護者與 Agent 在修改微內核代碼前，**必須強制閱讀本文件並恪守防禦紅線**！

---

## 登錄決策清單 (Decision Registry)

| 決策編號 | 原編號對照 | 標題 / 主題 | 影響檔案 | 風險等級 |
| :--- | :---: | :--- | :--- | :---: |
| **[DN-01](#dn-01-project-顯式組態與嚴禁-osgetcwd-隱式回退防污染-原-dn-01)** | `DN-01` | `project://` 顯式組態與嚴禁 `os.getcwd()` 隱式回退防污染 | `source/core/core/uri.py` | 🚨 CAUTION |
| **[DN-02](#dn-02-contributes-快照寫入-cache-與零空檔物化-原-dn-02)** | `DN-02` | Contributes 快照寫入 `cache://` 與零空檔物化 | `source/core/core/contributes.py` | ⚠️ WARNING |
| **[DN-03](#dn-03-atomicengine-宿主組態與-project-解耦不變量-原-dn-05)** | `DN-05` | `AtomicEngine` 宿主組態與 `project://` 解耦不變量 | `source/core/core/engine.py` | 🚨 CAUTION |
| **[DN-04](#dn-04-yscb-常數自定位與嚴禁向上攀爬目錄樹-原-dn-06)** | `DN-06` | `yscb://` 常數自定位與嚴禁向上攀爬目錄樹 | `source/core/core/uri.py` | 🚨 CAUTION |
| **[DN-05](#dn-05-osocreat--osoexcl-原子鎖與-10-秒-stale-lock-自癒閾值-原-dn-07)** | `DN-07` | `os.O_CREAT \| os.O_EXCL` 原子鎖與 10 秒 Stale Lock 自癒閾值 | `source/core/core/engine.py`<br/>`source/core/core/platform/` | ⚠️ WARNING |
| **[DN-06](#dn-06-act_reload-解壓安裝時無條件物理剝離-modulesmod-內之組態模板與-yscbignore-原-dn-11)** | `DN-11` | `act_reload` 解壓安裝時無條件物理剝離 `.modules/<mod>/` 內之組態模板與 `.yscbignore` | `source/core/core/engine.py` | ⚠️ WARNING |
| **[DN-07](#dn-07-jit-undefined-相對基準防遞迴死鎖與-undefinedurierror-前綴契約-原-dn-12--dn-27)** | `DN-12`<br/>`DN-27` | JIT `!undefined` 相對基準、防遞迴死鎖與 `UndefinedURIError` 前綴契約 | `source/core/core/uri.py` | 🚨 CAUTION |
| **[DN-08](#dn-08-微內核零-pip-純標準庫鐵律與-yscbvenv-強制---only-binaryall-防編譯風暴-原-dn-15--dn-23)** | `DN-15`<br/>`DN-23` | 微內核零 Pip 純標準庫鐵律與 `yscb.venv://` 強制 `--only-binary=:all:` 防編譯風暴 | `source/core/core/pip_manager.py`<br/>`source/core/core/validator.py` | 🚨 CAUTION |
| **[DN-09](#dn-09-vs-code-零目錄污染與-_yscb_managed-差集追蹤軟合併-原-dn-16)** | `DN-16` | VS Code 零目錄污染與 `_yscb_managed` 差集追蹤軟合併 | `source/core/core/ide_projector.py` | ⚠️ WARNING |
| **[DN-10](#dn-10-virtiofs-容器掛載點-_can_symlink-動態探測與實體拷貝降級-原-dn-17)** | `DN-17` | `virtiofs` 容器掛載點 `_can_symlink()` 動態探測與實體拷貝降級 | `source/core/core/pip_manager.py` | ⚠️ WARNING |
| **[DN-11](#dn-11-core__init__py-pep-562-延遲載入與-coreevents-零-atomicengine-反向依賴-原-dn-18--dn-22)** | `DN-18`<br/>`DN-22` | `core/__init__.py` PEP 562 延遲載入與 `core.events` 零 `AtomicEngine` 反向依賴 | `source/core/core/__init__.py`<br/>`source/core/core/events.py` | 🚨 CAUTION |
| **[DN-12](#dn-12-vfs-同目錄原子替換防同前綴穿越mtime-快取與宿主自更新-url-物理正交分離-原-dn-20--dn-26--dn-28)** | `DN-20`<br/>`DN-26`<br/>`DN-28` | VFS 同目錄原子替換、防同前綴穿越、`mtime` 快取、宿主自更新 URL 分離與零盲猜自舉 | `source/core/core/vfs/`<br/>`source/core/core/uri.py`<br/>`yscb.py` | 🚨 CAUTION |

---

### [DN-01] `project://` 顯式組態與嚴禁 `os.getcwd()` 隱式回退防污染 (原 `DN-01`)

- **核心決策**：`project://` 協議不屬於微內核自舉最小集，其解析嚴格依賴 `config://core/config.project.json` 中顯式配置之 `project_root`（預設為 `"!undefined"`）。若未配置或為 `"!undefined"`，在非互動模式下強制拋出 `UndefinedURIError`。
- **背後考量**：若微內核在未配置時隱式猜測當前工作目錄（`os.getcwd()`），在跨目錄調用 CLI、不同 IDE 工作區以及沙盒自引用環境中，會產生難以排查的路徑漂移與跨目錄檔案覆蓋災難。
- **防禦宣告**：
  > [!CAUTION]
  > **嚴禁在 `core.uri` 解析 `project://` 時新增任何 `os.getcwd()` 或父目錄猜測 Fallback 代碼！**

---

### [DN-02] Contributes 快照寫入 `cache://` 與零空檔物化 (原 `DN-02`)

- **核心決策**：`ContributesAggregator.scan_and_inject()` 的物化快照統一輸出至 `cache://{target}/contributes.merged.json`（連同指紋元資料 `cache://core/contributes.meta.json`）；且當目標模組未接收任何注入（空字典）時不落地空檔（若舊檔存在則自動清理）。
- **背後考量**：`config://` 是受 Git 追蹤的使用者/專案設定空間。若將框架動態衍生的聚合中介快照寫入 `config://`，會嚴重污染專案版本庫並產生無意義的 Git Diff。
- **防禦宣告**：
  > [!WARNING]
  > **Contributes 聚合快照屬於衍生快取，嚴禁寫入 `config://` 目錄；無注入資料之模組嚴禁物化空 JSON 檔案！**

---

### [DN-03] `AtomicEngine` 宿主組態與 `project://` 解耦不變量 (原 `DN-05`)

- **核心決策**：`AtomicEngine` 內部所有對宿主配置 `yscb.config.json` 的讀寫、安裝清冊維護與快照還原，一律依賴宿主目錄實體路徑（透過 `uri._get_host_config()` 定位 `yscb.host://`），嚴禁調用 `project://`。
- **背後考量**：`project://` 代表被管理的外部下游專案根目錄（在 `yscb.py init` 初期預設為 `!undefined`），而 `yscb.config.json` 是工具庫自身的宿主基礎設施，兩者在生命週期與架構職責上必須 100% 正交隔離。
- **防禦宣告**：
  > [!CAUTION]
  > **嚴禁在 `AtomicEngine` 讀寫 `yscb.config.json` 時透過 `project://` 解算路徑，否則將導致新工作區未配置 `project_root` 前無法安裝或重載任何模組！**

---

### [DN-04] `yscb://` 常數自定位與嚴禁向上攀爬目錄樹 (原 `DN-06`)

- **核心決策**：`yscb://` 在未顯式注入記憶體/環境變數作用域時，直接以 `core.uri` 代碼物理位置（`__file__` 往上 3 層）常數自定位；宿主設定 `yscb.config.json` 僅檢查顯式候選位置（`injected_host`、`dirname(yscb_dir)`、`yscb_dir`），徹底移除動態向上攀爬目錄樹（`while parent != curr`）與 `os.getcwd()` 猜測。
- **背後考量**：動態向上攀爬目錄樹會在巢狀子專案或沙盒測試失敗殘留目錄時誤綁定外層宿主，違反「零臆測 (Zero Speculation)」鐵律。
- **防禦宣告**：
  > [!CAUTION]
  > **嚴禁在 `core.uri` 或 `yscb.py:load_config` 中引入向上遞迴爬樹 (`while` loop) 尋找設定檔的隱式搜尋邏輯！**

---

### [DN-05] `os.O_CREAT | os.O_EXCL` 原子鎖與 10 秒 Stale Lock 自癒閾值 (原 `DN-07`)

- **核心決策**：`AtomicEngine.act_lock` 與跨進程互斥機制基於作業系統原語（`os.O_CREAT | os.O_EXCL` 及 `core.platform.InterProcessLock`）於 `cache://.yscb.lock` 建立排他鎖，並配置 `10.0s` 超時與陳舊鎖（Stale Lock）自癒閾值。
- **背後考量**：在多終端或背景代理並發執行套件操作時，必須由 OS 核心保證原子互斥；同時若前次進程遭強制 `SIGKILL` 中斷導致鎖殘留，10 秒閾值與檔案鎖釋放機制可確保系統自動容災恢復而不致永久死鎖。
- **防禦宣告**：
  > [!WARNING]
  > **嚴禁使用非原子的「先 `os.path.exists` 再 `open('w')`」模式實作進程鎖，以免產生 TOCTOU 競爭條件 (Race Condition)！**

---

### [DN-06] `act_reload` 解壓安裝時無條件物理剝離 `.modules/<mod>/` 內之組態模板與 `.yscbignore` (原 `DN-11`)

- **核心決策**：模組運行空間（`module://<module>/`，即 `.modules/<module>/`）內部嚴禁留存任何 `configurable/`、`config.*.json` 組態模板或 `.yscbignore` 檔案；`act_reload` 在 Stage 3 掃描並將缺失組態增量補齊至 `config://<module>/` 後，無條件物理刪除 `.modules/<module>/` 內的模板檔案與目錄。
- **背後考量**：徹底杜絕執行期程式碼、外部套件或下游應用誤讀 `.modules/` 內的預設組態模板，確保 `config://` 為執行期組態的唯一真理來源 (SSOT)。
- **防禦宣告**：
  > [!WARNING]
  > **嚴禁在 `.modules/<module>/` 運行空間保留 `config.*.json` 或 `.yscbignore`；任何組態讀取一律透過 `core.config` 或 `config://` 協議存取！**

---

### [DN-07] JIT `!undefined` 相對基準、防遞迴死鎖與 `UndefinedURIError` 前綴契約 (原 `DN-12` + `DN-27`)

- **核心決策**：
  1. **相對路徑剛性基準**：當 `uri.resolve()` 觸發互動式 JIT 補齊且使用者輸入 `-y <relative_path>`（或設定檔內存儲相對路徑）時，一律強制以 `yscb://`（工具庫根目錄）為基準展開，嚴禁使用 `os.getcwd()`。
  2. **防自引用死鎖 (`_reconciling_tokens`)**：解算連鎖依賴時維護 `_reconciling_tokens: Set[str]`，一旦偵測到循環或自引用（如將 `project://` 設為 `project://sub`）立即拋出 `CyclicURIDependencyError`。
  3. **例外訊息結構契約**：`UndefinedURIError` 透過 `format_undefined_uri_hint()` 在訊息尾部附加 `Quick fix: <cli_cmd>` 時，必須 100% 保留原有 `Semantic URI '{scheme}://' is undefined (!undefined)...` 前綴字串。
- **背後考量**：保持相對路徑基準恆定可避免工作目錄切換引發路徑偏移；而保留 `UndefinedURIError` 標準前綴可確保下游與單元測試的正則斷言契約不因體驗優化而破裂。
- **防禦宣告**：
  > [!CAUTION]
  > **JIT 補齊相對路徑嚴禁回退至 `os.getcwd()`；修改 `UndefinedURIError` 提示訊息時，嚴禁刪除或改寫 `Semantic URI '{scheme}://' is undefined (!undefined).` 前綴結構！**

---

### [DN-08] 微內核零 Pip 純標準庫鐵律與 `yscb.venv://` 強制 `--only-binary=:all:` 防編譯風暴 (原 `DN-15` + `DN-23`)

- **核心決策**：
  1. **Core 100% 純標準庫 (Zero-Pip)**：`core` 微內核自身（含 `core.validator` 輕量 Schema DSL 驗證引擎、`core.vfs`、`core.uri`、`yscb.py`）強制 100% 使用 Python 標準庫實作，零第三方套件依賴（嚴禁引入 `pydantic`、`jsonschema` 等）。
  2. **私有微環境剛性隔離與預編譯 Wheel 強制約束**：擴充模組宣告之第三方依賴統一由 `core.pip_manager` 安裝至 `yscb.venv://`（`.venv/py{major}{minor}/`，鎖定 `include-system-site-packages = false`），且調用 `pip install` 時強制附加 `--only-binary=:all:` 與 `--no-warn-script-location`；若目標套件缺乏預編譯 Wheel 則立即拋出 `PipInstallError` 阻斷。
- **背後考量**：微內核零依賴確保 `yscb.py` 在任何裸機 Python 環境皆可冷自舉；強制 `--only-binary=:all:` 則徹底防止在無 C/C++ 編譯工具鏈（gcc/clang/MSVC）的容器或使用者端觸發源碼編譯風暴與卡死。
- **防禦宣告**：
  > [!CAUTION]
  > **嚴禁在 `core` 模組自身引入任何第三方 Pip 依賴！嚴禁在 `PipManager.install_packages` 中移除 `--only-binary=:all:` 旗標！**

---

### [DN-09] VS Code 零目錄污染、跨平台雙路徑恆定與 Zero-Touch 軟合併 (原 `DN-16`)

- **核心決策**：
  1. **零目錄污染**：`core.ide_projector` 在同步 IDE Python 路徑時，先探測 `project://.vscode` 是否存在；若不存在則**完全靜默略過**，絕不主動建立 `.vscode/` 目錄。
  2. **跨平台雙路徑併存 (`extraPaths`)**：於 `python.analysis.extraPaths` 同時注入 POSIX (`lib/pythonX.Y/site-packages`) 與 Windows (`Lib/site-packages`) 雙候選路徑。Pylance 自動忽略不存在之路徑，確保跨平台協作時版本庫 100% 恆定 0 diff。
  3. **解耦 `python.defaultInterpreterPath`**：停止將隨作業系統變動之直譯器路徑自動寫入共用 `settings.json`，並清理舊版 YSCB 託管值，使用者自訂之直譯器 100% 保留。託管判定（`_is_yscb_managed_interpreter`）僅認「等於舊 `_yscb_managed` 記錄值」或「解析後位於 `yscb_dir/.venv/` 之下」，**不得以路徑字串含 `.venv` 判定**，否則會誤刪使用者專案自有 `.venv` 直譯器。
  4. **Zero-Touch 寫入防護與 JSONC 防覆寫**：若計算後內容與磁碟既有 JSON 完全一致，跳過寫入，杜絕無謂的檔案 `mtime` 變更；若既有 `settings.json` 解析失敗（例如含 VS Code 允許之 JSONC 註解或尾逗號）或非 JSON 物件，輸出 stderr 警告並回傳 `False` 安全略過，絕不以空字典 `{}` 整檔覆寫。
  5. **VFS 文字寫入固定 LF (`newline="\n"`)**：`OSBackend.write_text` 與 `atomic_write` 文字模式固定以 `newline="\n"` 開檔，防止 Windows 將 `\n` 自動轉譯為 `\r\n` 造成受追蹤設定檔跨平台位元組差異。
- **背後考量**：避免在非 VS Code 使用者的專案中製造無用空目錄污染；同時杜絕跨平台（Windows 與 Linux）交替開發時因直譯器與 site-packages 差異導致 Git Working Tree 持續 Dirty。
- **防禦宣告**：
  > [!WARNING]
  > **嚴禁在 `project://.vscode` 不存在時主動建立該目錄；嚴禁以整檔覆蓋模式寫入 `settings.json`；嚴禁向共用 `settings.json` 寫入平台特化之單一直譯器路徑；嚴禁以 `".venv" in path` 字串比對判定託管直譯器！**

---

### [DN-10] `virtiofs` 容器掛載點 `_can_symlink()` 動態探測與實體拷貝降級 (原 `DN-17`)

- **核心決策**：`PipManager` 在建立私有微環境前，強制透過 `_can_symlink()` 在目標目錄實測符號連結是否可正常建立並解算；若在 Docker / Dev Container 的 `virtiofs` 或跨系統掛載磁碟區探測失敗，自動降級為實體檔案拷貝（`copies=True`）並自 `ensurepip` 解壓預置 Wheel。
- **背後考量**：容器掛載宿主檔案系統時，POSIX 符號連結常因宿主與容器內部絕對路徑不一致而形成斷鏈，或在權限受限的掛載點拋出 `OSError: [Errno 1] Operation not permitted`。
- **防禦宣告**：
  > [!WARNING]
  > **嚴禁在 POSIX 環境中盲目假設符號連結必可解算，建立微環境時必須維持 `_can_symlink()` 動態探測與實體拷貝降級保護！**

---

### [DN-11] `core/__init__.py` PEP 562 延遲載入與 `core.events` 零 `AtomicEngine` 反向依賴 (原 `DN-18` + `DN-22`)

- **核心決策**：
  1. **PEP 562 按需延遲載入**：`core/__init__.py` 透過模組級 `__getattr__` 動態延遲載入重型子系統（`AtomicEngine`、`Installer`、`PipManager` 等），僅在 `TYPE_CHECKING` 下保留靜態型別導入，使 CLI 熱路徑單獨導入 `core.commands` 或 `core.uri` 的冷啟動耗時維持在 $< 5\text{ms}$。
  2. **`core.events` 零 `AtomicEngine` 反向依賴**：事件廣播管線獨立實作於 `core.events.broadcast()`，不依賴任何 `AtomicEngine` 實例。
- **背後考量**：若 `core/__init__.py` 頂層急切導入所有子模組，或 `core.events` 在派發 `pre_cli_dispatch` 前反向導入並實例化 `AtomicEngine`，將迫使每次輕量 CLI 呼叫都執行全量模組掃描與引擎初始化，造成 $> 70\text{ms}$ 的冷啟動退化與循環依賴。
- **防禦宣告**：
  > [!CAUTION]
  > **嚴禁在 `core/__init__.py` 頂層直接 `import` 重型子模組（必須維持 `__getattr__` 延遲映射）！嚴禁在 `core.events` 內反向導入或隱式初始化 `AtomicEngine`！**

---

### [DN-12] VFS 同目錄原子替換、防同前綴穿越、`mtime` 快取與宿主自更新 URL 物理正交分離 (原 `DN-20` + `DN-26` + `DN-28`)

- **核心決策**：
  1. **VFS 同目錄臨時檔 `os.replace` 防跨磁碟區 `EXDEV`**：`OSBackend.atomic_write` 強制在目標檔案之**同級目錄**生成 `.tmp` 臨時檔，完成 `flush()` 與 `os.fsync()` 後執行 `os.replace` 原子替換，嚴禁使用系統 `/tmp`。
  2. **`target_base + os.sep` 防同前綴兄弟目錄穿越**：`uri.resolve()` 與 `OSBackend.assert_safe_path` 檢驗路徑逃逸時，強制比對 `resolved_path == target_base or resolved_path.startswith(target_base + os.sep)`，阻斷利用 `cache://../.cache_hack` 等同前綴兄弟目錄名稱繞過 `startswith(target_base)` 的安全漏洞。
  3. **URI 協議清冊 `(yscb_dir, mtime)` 記憶體快取自動失效**：`core.uri._get_merged_uri_schemes` 以 `contributes.merged.json` 之 `mtime` 作為快取鍵（命中耗時 $< 0.1\text{ms}$），檔案更新時自動失效重載。
  4. **`DEFAULT_SELF_UPDATE_URL` 與 `DEFAULT_PROVIDER_URL` 物理正交分離**：宿主 `yscb.py` 將腳本自更新網址 `DEFAULT_SELF_UPDATE_URL` 與套件來源 `DEFAULT_PROVIDER_URL` 定義為兩個完全獨立的常數，`_resolve_self_update_target_url()` 僅接受顯式 `--url` 覆寫。
  5. **宿主自適應重建與零盲猜 Fallback 鐵律**：當下游專案 clone 至新設備（`yscb.config.json` 存在但 `.modules/core` 尚未物化）時，`yscb.py` 僅依組態中已知的確定性 `provider` 與 `version` 下載 `core` 並觸發 `restore`；若來源遺失或 `_discover_latest_core` 探測失敗，一律回傳 `(None, None)` 並輸出明確修復指引，**嚴禁硬編碼退回特定版本（如 `"1.1.0.1"` 或 `"1.0.0.0"`）或私自 fallback 至 `DEFAULT_PROVIDER_URL`**。
- **背後考量**：容器環境中 `/tmp` 與工作區常處於不同掛載分區，跨區 `os.replace` 會直接拋出 `EXDEV` 崩潰；將宿主自更新 URL 與套件 Provider URL 物理拆離，可防止因套件庫目錄結構調整導致 `self-update` 404 損毀；而禁止跨版本/跨來源盲猜 fallback 可避免靜默載入與組態不符之舊版套件造成環境狀態分裂。
- **防禦宣告**：
  > [!CAUTION]
  > **原子寫入臨時檔嚴禁建立於系統 `/tmp`！路徑邊界校驗必須包含 `+ os.sep`！嚴禁在 `yscb.py` 中對 `provider` 參數進行字串切分來推導 `yscb.py` 自更新網址，或於探測/還原失敗時硬編碼偽造預設版本號！**
