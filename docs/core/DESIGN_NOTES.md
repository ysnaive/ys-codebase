# Core 微內核設計決策與工程註記 (Core Design Notes)

> 本文件記錄 Core 微內核系統中的非直觀實作、工程妥協與關鍵防呆決策（維度 5）。  
> 所有維護者與 Agent 在修改相關邏輯前，**必須強制閱讀本文件**！

---

## 登錄決策清單 (Decision Registry)

| 決策編號 | 標題 / 主題 | 影響檔案 | 風險等級 |
| :--- | :--- | :--- | :---: |
| **DN-01** | `project://` 顯式配置與零 Fallback 阻斷 | `source/core/core/uri.py` | 🚨 CRITICAL |
| **DN-02** | 依賴注入中介層快照存於 `cache://` | `source/core/core/contributes.py` | ⚠️ WARNING |
| **DN-03** | 模組組態遞迴原地增量補齊 | `source/core/core/engine.py` | ⚠️ WARNING |
| **DN-04** | 命名空間 Hook 對接與例外隔離 | `source/core/core/engine.py` | 💡 INFO |
| **DN-05** | 宿主組態實體路徑解耦 (脫離 project://) | `source/core/core/engine.py` | 🚨 CRITICAL |
| **DN-06** | `yscb://` 常數自定位與零猜測阻斷 | `source/core/core/uri.py` | 🚨 CRITICAL |
| **DN-07** | OS 核心原子鎖保護與 10s 自修復機制 | `source/core/core/engine.py` | ⚠️ WARNING |
| **DN-08** | 剛性拓撲回歸與 6 大軟相容全面清除 | 全域多模組 | 🚨 CRITICAL |
| **DN-09** | 四段式版本尾號不具比較性與單一 Revision 淘汰 | `source/core/core/semver.py`<br/>`source/dev/dev/builder.py` | 🚨 CRITICAL |
| **DN-10** | 同 Major 升級鎖定原則 | `source/core/core/installer.py`<br/>`source/core/core/engine.py` | ⚠️ WARNING |
| **DN-11** | 模組運行空間純粹化與 config 模板自動剝除 | `source/core/core/engine.py` | 💡 INFO |
| **DN-12** | JIT `!undefined` 熱更新補齊機制與自引用防護 | `source/core/core/uri.py` | 🚨 CRITICAL |
| **DN-13** | Contributes `__provider__` 拓撲聚合與 SDK 查詢 | `source/core/core/contributes.py` | ⚠️ WARNING |
| **DN-14** | `yscb.host://` 宿主協議常數解算與 fast-path 路由 | `source/core/core/uri.py` | 🚨 CRITICAL |
| **DN-15** | `yscb.venv://` 私有微虛擬環境剛性隔離與 Wheel-Only 保證 | `source/core/core/pip_manager.py` | 🚨 CRITICAL |
| **DN-16** | IDE 自動感知與 `_yscb_managed` 宣告式可復原軟合併 | `source/core/core/ide_projector.py` | ⚠️ WARNING |
| **DN-17** | virtiofs 跨平台掛載環境符號連結動態探測與複製降級 | `source/core/core/pip_manager.py` | ⚠️ WARNING |
| **DN-18** | 微內核獨立事件總線 (core.events) 與 Engine 徹底解耦 | `source/core/core/events.py` | 🚨 CRITICAL |

---

### [DN-01] `project://` 顯式配置與零 Fallback 阻斷

- **核心決策**：`project://` 協議不屬於微內核自舉最小集。其解析嚴格依賴 `yscb://config/core/config.project.json` 中配置之 `project_root`。預設為 `!undefined`。若檔案不存在或為 `!undefined`，在非互動模式下必須拋出 `UndefinedURIError`。
- **背後考量**：若微內核在未配置時隱式猜測當前工作目錄（`os.getcwd()`），在跨 CLI、不同 IDE 以及自引用環境中，會產生難以排查的路徑漂移與跨目錄覆蓋問題。
- **防禦宣告**：
  > [!CAUTION]
  > **嚴禁在此處新增任何 `os.getcwd()` 或父目錄猜測 Fallback 代碼！**

---

### [DN-02] 依賴注入中介層快照存於 `cache://`

- **核心決策**：`ContributesAggregator.scan_and_inject()` 的物化快照輸出至 `cache.root://{target}/contributes.merged.json`，且當模組未接收任何注入時不落地空檔。
- **背後考量**：`config://` 是受 Git 追蹤的使用者/專案設定空間，若將框架衍生的中介檔案寫入 `config/`，會污染專案設定庫並產生無意義的 Git Diff。
- **防禦宣告**：
  > [!IMPORTANT]
  > 中介層快照屬於衍生快取，嚴禁寫入 `config://` 目錄。

---

### [DN-03] 模組組態遞迴原地增量補齊

- **核心決策**：當模組在 `source/` 提供之預設組態新增了欄位時，物化安裝或 `reload` 會進行遞迴比對，自動補齊缺失鍵，但既有設定值 100% 保持不變。
- **背後考量**：防止套件版本更新時覆蓋使用者已調整的自訂設定。

---

### [DN-04] 命名空間 Hook 對接與例外隔離

- **核心決策**：Hook 檔案採用 `scripts/hook.{emit_module}.py`，Core 調度時實施 `try-except` 隔離。
- **背後考量**：明確權責，避免單一外掛模組的語法錯誤或崩潰導致整體 CLI 安裝或更新流程卡死。

---

### [DN-05] 宿主組態實體路徑解耦 (脫離 `project://`)

- **核心決策**：`AtomicEngine` 內部所有對 `yscb.config.json` 的讀寫、清冊維護與快照還原，一律依賴宿主目錄實體路徑（透過 `_get_host_config()`），嚴禁調用 `project://`。
- **背後考量**：`project://` 代表被管理的外部下游專案根目錄（預設未配置），而 `yscb.config.json` 是工具庫自身的基礎設施，兩者在架構職責上完全隔離。

---

### [DN-06] `yscb://` 常數自定位與零猜測阻斷

- **核心決策**：`yscb://` 直接以 `core.uri` 代碼位置（`__file__` 往上 3 層）常數自定位；宿主 Context 顯式傳遞；徹底移除動態向上爬目錄迴圈與 `os.getcwd()` 猜測。
- **背後考量**：徹底根除環境路徑漂移與跨目錄執行時的隱性 Bug，貫徹「零臆測 (Zero Speculation)」鐵律。

---

### [DN-07] OS 核心原子鎖保護與 10s 自修復機制

- **核心決策**：`AtomicEngine.act_lock` 使用作業系統核心層標誌 `os.O_CREAT | os.O_EXCL` 建立 `temp://.yscb.lock`，由 OS 核心提供剛性互斥保證。
- **背後考量**：在單進程同步調度模型下，10s 超時判定僅用於前次執行非正常中斷崩潰後的自動容災修復 (Self-Healing)，正常執行流程中 `os.O_EXCL` 提供 100% 互斥安全。

---

### [DN-08] 剛性拓撲回歸與 6 大軟相容全面清除

- **核心決策**：全面清除代碼中的 6 大軟相容退化點：
  1. `yscb.py:load_config` 移除向上爬樹，剛性錨定同層目錄。
  2. `contributes.py` 嚴格僅讀取 `modules/` 運行空間產物，徹底移除對 `source/` 的穿透 fallback。
  3. `contributes.py` 移除對 `project://` 的穿透 fallback，僅讀取模組專屬 `config.root://`。
  4. `uri.resolve()` 嚴格攔截非標準 URI 與非絕對路徑，拋出 `ValueError`。
  5. `installer.py` 移除 `default_provider` 硬編碼後門。
  6. `sandbox.py` 剛性定位宿主 `yscb.py`。
- **防禦宣告**：
  > [!CAUTION]
  > 專案嚴格遵守剛性拓撲原則，禁止為規避局部報錯而擅自引入跨空間穿透與動態猜測代碼。

---

### [DN-09] 四段式版本尾號不具比較性與單一 Revision 淘汰

- **核心決策**：四段式版本尾號 `revision` 在日常三元安裝與依賴求解中不具獨立比較意義；`release/` 發布庫中針對相同 `X.Y.Z` 僅允許保留單一最新 Revision 產物。
- **背後考量**：避免多個微小修訂號並存導致來源庫混亂與版本求解複雜度爆炸，常態性以三元語意版本進行發布與消費。

---

### [DN-10] 同 Major 升級鎖定原則

- **核心決策**：CLI 執行 `update` 時，預設僅在同一個 Major 主版本內尋找最新 Minor/Patch/Revision 進行安全升級；跨 Major 破壞性升級必須顯式指定版本或執行 `install <module>@<new_major>`。
- **背後考量**：防止自動更新意外拉入破壞性 API 變更導致專案中斷。

---

### [DN-11] 模組運行空間純粹化與 config 模板自動剝除

- **核心決策**：模組在運行空間（`modules/<module>/`）內部嚴禁留存任何 `config.*.json` 模板或 `.yscbignore` 檔案；`act_reload` 在掃描提取組態至 `config/` 後，無條件實體刪除模組目錄下的模板。
- **背後考量**：徹底避免執行期代碼、外部套件或下游應用誤讀模組內的預設模板而產生組態分叉。

---

### [DN-12] JIT `!undefined` 熱更新補齊機制與自引用防護

- **核心決策**：
  1. 當 `uri.resolve()` 遇到未定義（`!undefined`）之協議時，在 TTY 終端主動提示 `[-y <path> / -n / --help]`。
  2. 使用者輸入 `-y <path>` 時，相對路徑一律以 `yscb://`（工具庫根目錄）為基準展開，支援連鎖未定義依賴遞迴解算。
  3. 自動將輸入值寫回所屬模組（`__provider__`）之 `config.project.json` 並刷新記憶體 URI 快取，無縫繼續原呼叫。
  4. 建立 `_reconciling_tokens: Set[str]`，當檢測到自引用或循環依賴時立即拋出 `CyclicURIDependencyError` 阻斷無窮迴圈。
  5. 在非 TTY（CI/CD、背景任務、靜態分析）或 `interactive=False` 模式下，直接拋出結構化 `UndefinedURIError`。
- **防禦宣告**：
  > [!IMPORTANT]
  > JIT 補齊嚴格以 `yscb://` 為相對起始基準，嚴禁擅自回退為 `os.getcwd()` 或 `project://`。

---

### [DN-13] Contributes `__provider__` 拓撲聚合與 SDK 查詢

- **核心決策**：
  1. 在微內核 `scan_and_inject()` 搜集 donor 模組 contributes 時，自動遞迴為 Dict 與 List[Dict] 項目注入 `"__provider__": donor_name`。若物件已顯式宣告 `__provider__` 則予以保留不覆蓋。
  2. 依據已安裝模組之依賴拓撲順序 (Topological Order) 有序合併，保證底層基礎設施優先註冊，擴充模組後續追加。
  3. 提供標準微內核查詢 SDK `core.contributes.get(target_module, key=None, default=None)` 與 `get_for_current_module()`，內建自愈快取。
- **背後考量**：徹底解決下游外掛模組無法溯源能力提供者、合併順序非決定性以及缺乏標準查詢 API 的痛點。

---

### [DN-14] `yscb.host://` 宿主協議常數解算與 fast-path 路由

- **核心決策**：
  1. 引入 `yscb.host://` 一等公民常數協議，類型為 `const`，模板值為 `{yscb_host}`。
  2. 強制指向起手腳本 `yscb.py` 與 `yscb.config.json` 所在之專案宿主工程根目錄。
  3. 於 `uri.resolve()` 提供 O(1) fast-path 解析，並相容自引用與外部專案宿主上下文。
- **背後考量**：當工具庫（`yscb://`）位於子目錄（如 `ys_codebase/`）時，模組與工作流需精準定位包含起手腳本的宿主根目錄，避免混淆 `project://`（受被管理目標路徑組態影響）與 `yscb://`（工具庫源碼根目錄）。

---

### [DN-15] `yscb.venv://` 私有微虛擬環境剛性隔離與 Wheel-Only 保證

- **核心決策**：
  1. 微環境根目錄為 `yscb://.venv/py{major}{minor}/`，強制鎖定 `include-system-site-packages = false`，達成 100% 零全域環境污染。
  2. 呼叫 pip 安裝時強制附加 `--only-binary=:all:` 與 `--no-warn-script-location`，若無預編譯 Wheel 則直接拋出 `PipInstallError`。
  3. `core` 模組本身保持純 Python 標準庫實作（Zero-Pip），其餘模組可自由進行 pip 宣告。
- **背後考量**：徹底消除跨專案與宿主 Python 之全域依賴污染；避免在缺乏 gcc/clang/msvc 之容器或用戶本機嘗試編譯 C 擴充模組導致的崩潰。
- **防禦宣告**：
  > [!CAUTION]
  > **嚴禁在微環境安裝管線中移除 `--only-binary=:all:`！嚴禁在 `core` 模組自身引入任何第三方 pip 依賴！**

---

### [DN-16] IDE 自動感知與 `_yscb_managed` 宣告式可復原軟合併

- **核心決策**：
  1. 自動探測 `project://.vscode` 是否存在，若不存在完全靜默略過，絕不主動建立 `.vscode/` 目錄。
  2. 若存在，以 `_yscb_managed` 宣告式清冊結構記錄注入之 `extraPaths`、`defaultInterpreterPath` 與排除規則（`files.watcherExclude`、`search.exclude`、`files.exclude`），100% 保留使用者既有配置，並支援乾淨無損回滾。
- **背後考量**：避免在未配置 VS Code 之專案目錄下產生冗餘空目錄；杜絕暴力覆蓋導致使用者自訂設定遺失；避免檔案監視器因掃描微環境數萬個第三方檔案引發高負載。
- **防禦宣告**：
  > [!IMPORTANT]
  > **嚴禁在 `project://.vscode` 不存在時主動創建該目錄；嚴禁以整檔覆蓋模式寫入 `settings.json`！**

---

### [DN-17] virtiofs 跨平台掛載環境符號連結動態探測與複製降級

- **核心決策**：
  1. 在建立微環境前，透過 `_can_symlink()` 即時探測目標目錄是否支援有效可解算的符號連結（相容 virtiofs / 容器掛載磁碟）。
  2. 若符號連結不可解算，自動降級為複製 Python 可執行檔，並優先自 `ensurepip` 解壓預置 wheel，避免因檔案權限操作（如 `chmod`）引發 `OSError: [Errno 1] Operation not permitted`。
- **背後考量**：Dev Container 與 Docker 掛載宿主檔案系統時，符號連結常因宿主/虛擬機路徑不同而斷鏈或拋出權限錯誤。
- **防禦宣告**：
  > [!WARNING]
  > **嚴禁在 POSIX 環境中盲目假設符號連結必可解算，必須維持動態探測與降級保護！**

---

### [DN-18] 微內核獨立事件總線 (`core.events`) 與 Engine 徹底解耦

- **核心決策**：
  1. 將事件廣播管線獨立實作於 `source/core/core/events.py`，徹底剔除 `Engine.act_broadcast_event` 舊門面。
  2. 宿主入口（`yscb.py`）、微內核安裝器（`installer.py`）與各模組（如 `dev.testing.sandbox`）全面直接調用 `core.events.broadcast()`，不得依賴重型 `Engine` 實例。
  3. 支援 `search_roots` 動態搜尋路徑注入（如沙盒臨時模組目錄），並透過單一契約 `scripts/hook.{emit_module}.py` 對接，函式名支援 `on_{event}` 與 `{event}` 雙向彈性匹配。
- **背後考量**：若事件廣播依賴 `Engine` 實例，宿主在 CLI 冷啟動階段執行生命週期廣播（如 `pre_cli_dispatch`）前就必須初始化完整 `Engine`（包含依賴注入、路徑掃描、狀態快照），造成嚴重冷啟動延遲與狀態循環依賴；解耦後事件總線成為無狀態純淨微核心管線。
- **防禦宣告**：
  > [!CAUTION]
  > **嚴禁在 `core.events` 內反向導入 `Engine` 或在事件派發前隱式初始化 `Engine`！嚴禁於模組內重複實作 Ad-hoc Hook 派發邏輯！**

---

### [DN-19] PipManager SDK 公開導出與順序去重相依性解析器

- **核心決策**：
  1. 將 `PipManager`、`PipInstallError` 與 `pip_manager` 模組正式導出至 `core.__all__`，支援標準匯入契約 `from core import PipManager, PipInstallError`。
  2. 於 `PipManager` 實作標準靜態方法 `parse_pip_dependencies(pip_deps: Any) -> List[str]`，支援將字典（`{"pkg": ">=1.0.0"}`）或清單（`["pkg>=1.0.0"]`）正規化為乾淨、已順序去重之 pip 規格字串清單。
- **背後考量**：下游模組（如 `dev` 工具鏈在建置虛擬基環境/沙盒前適配 build 版依賴）需要統一、強健的 pip 工具 SDK，若由各模組手刻正則或字典遍歷容易發生邊界條件例外（例如 None 值、首尾空白未清理、重複套件多次調用 pip）；收斂至 `PipManager` 達成 DRY 與高保真。
- **防禦宣告**：
  > [!IMPORTANT]
  > **解析模組 `pip_dependencies` 宣告時嚴禁各模組自造正則或手刻字串拼接，必須統一調用 `PipManager.parse_pip_dependencies()`！**

