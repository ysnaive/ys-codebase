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

---

### [DN-01] `project://` 顯式配置與零 Fallback 阻斷

- **核心決策**：`project://` 協議不屬於微內核自舉最小集。其解析嚴格依賴 `yscb://config/core/config.project.json` 中配置之 `project_root`。預設為 `!undefined`。若檔案不存在或為 `!undefined`，必須直接拋出 `ValueError`。
- **背後考量**：若微內核在未配置時隱式猜測當前工作目錄（`os.getcwd()`），在跨 CLI、不同 IDE（VSCode vs Antigravity vs 終端）以及自引用環境中，會產生難以排查的路徑漂移與跨目錄覆蓋問題。
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
  > 專案嚴格遵守 R01~R05 剛性拓撲原則，禁止為規避局部報錯而擅自引入跨空間穿透與動態猜測代碼。

---

### [DN-09] 四段式版本尾號不具比較性與單一 Revision 淘汰

- **核心決策**：四段式版本尾號 `revision` 在日常三元安裝與依賴求解中不具獨立比較意義；`release/` 發布庫中針對相同 `X.Y.Z` 僅允許保留單一最新 Revision 產物。
- **背後考量**：避免多個微小修訂號並存導致來源庫混亂與版本求解複雜度爆炸，常態性以三元語意版本進行發布與消費。

---

### [DN-10] 同 Major 升級鎖定原則

- **核心決策**：`yscb update` 指令預設自動將升級範圍約束在當前 Major 內（`^current_version`）。
- **背後考量**：防止日常更新時意外拉取破壞性大版本升級導致專案崩潰。跨 Major 升級必須明確指定 `yscb install <mod>@<new_major>`。

---

### [DN-11] 模組運行空間純粹化與 config 模板自動剝除

- **核心決策**：模組安裝包（`mirror://` / `release://`）中的 `config.project.json` 與 `config.local.json` 作為配置種子模板，在 `act_reload` 完成種子提取並軟合併進 `config/{mod}/` 後，自動將其從 `modules/{mod}/` 運行目錄中移除。
- **背後考量**：`modules/` 必須維持純粹可執行代碼，避免配置雙頭維護與開發者修改路徑混淆。

