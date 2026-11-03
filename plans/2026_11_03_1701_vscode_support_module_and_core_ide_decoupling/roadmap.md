# 技術路線圖：`module:vscode-support` 獨立模組與 `core` 零 IDE 假設解耦 (Roadmap)

> 主題：`module:vscode-support` 獨立模組與 `core` 零 IDE 假設解耦 (`vscode_support_module_and_core_ide_decoupling`)  
> 歸檔日期：2026-11-03  
> 狀態：Proposed  
> 目標範疇：`core`（環境同步事件契約、組態模板留存）、新模組 `module:vscode-support`（工作區設定投影、本地工作區外掛合成、JSON Schema 編譯）、`agents-workflow`（Markdown 編譯語法輔助注入方）  
> 前置解鎖條件：Phase A 無阻塞可隨時啟動；Phase B 需先完成宿主 IDE 相容性實測（見第 3 節）  
> 模型：Claude Opus 5.5 (Medium)  
> 模板版本：v1.1  

---

## 1. 背景與長期願景 (Background & Vision)

- **核心痛點與動機**：
  - **微內核對下游 IDE 存在隱性假設**：`core` 於環境依賴同步流程中直接感知並改寫 `.vscode/` 工作區設定，使微內核知曉特定編輯器（VS Code / Pylance）之存在；下游使用者可能使用 PyCharm、Neovim、Zed、純 CLI Agent 或無頭 CI，此耦合違反微內核職責邊界。
  - **組態與擴充點缺乏編輯期即時校驗**：`contributes/*.json`、`config.*.json` 與 `_format.json` 目前僅能於 CLI 執行期（`contributes check` / `dev check`）發現錯誤，編輯器內無欄位補全、型別提示與即時紅線。
  - **單一全域 Schema 映射無法精準隔離**：若以工作區 `settings.json` 註冊 Schema，模組數量增長將導致設定檔膨脹，且難以做到「開啟某模組之擴充點檔案僅提示該模組欄位」之單檔級精準校驗。
- **長期願景與目標定位**：
  - 將所有 VS Code 相關投影邏輯自 `core` 100% 剝離至選配官方模組 `module:vscode-support`，達成「`core` 零 IDE 假設 + 顯式安裝即賦能（`install vscode-support`）+ 移除即乾淨還原（`remove vscode-support`）」。
  - 以本地工作區外掛為載體，依已安裝模組動態合成單檔級精準 JSON Schema 與語法輔助，`settings.json` 維持最小且恆定之靜態內容。
- **範疇與邊界約束**：
  - **誠實邊界聲明**：工作區本地外掛受 VS Code 安全模型約束——需工作區信任（Workspace Trust）、需開發者於擴充面板「Workspace Recommendations」手動安裝一次、內容變更需 Reload Window 生效；故本方案定位為「安裝後一次性啟用、此後自動同步」，而非全自動接管。
  - **最小版控污染而非零污染**：若仍需寫入 `.vscode/settings.json`，則屬受版控檔案之異動；目標為使該檔內容恆定（不隨 Python 版本或模組數量變動），並優先評估以外掛 `configurationDefaults` 取代直接寫入。
  - 不涵蓋非 VS Code 系 IDE；其他 IDE 支援應以同構之獨立模組（如 `jetbrains-support`）各自訂閱 `core` 事件實作。

---

## 2. 抽象架構原則與核心設計概念 (Architectural Principles & Concepts)

- **核心設計不變量 (Core Invariants)**：
  - **`core` 零 IDE 假設**：`core` 僅負責私有微環境與生命週期事件廣播，不得出現任何編輯器專屬路徑、設定鍵或判斷分支；新增之核心契約必須為 IDE 中立之通用能力。
  - **事件時序正確性**：IDE 投影必須掛載於「第三方依賴物化完成之後」的事件點。既有 `on_installed` 廣播早於依賴同步，故需由 `core` 新增 IDE 中立之 `on_env_synced` 事件（於依賴同步完成後廣播），作為 site-packages 路徑投影之唯一觸發點。
  - **自我還原可行性**：`on_remove` 於模組反註冊與刪除前廣播，`vscode-support` 可於自身被移除時完成 `_yscb_managed` 精確還原與本地外掛目錄清除。
  - **不搶寫共享檔案**：本地外掛目錄以自身目錄內之 `.gitignore`（內容為 `*`）達成自我忽略，嚴禁改寫專案根 `.gitignore`（避免與 `agents-workflow` 等既有寫入方競爭）。
  - **型別真理來自宣告而非猜測**：組態 Schema 以模組顯式宣告（選配 `configurable/_format.json`）為主軌；由範例值推導僅提供基本型別（bool / int / float / list / dict / str）保底，嚴禁對特定字面值（如 `"auto"`）做特例硬編碼；`!undefined` 屬 `core` 既有必填佔位慣例，可正式納入推導規則。
  - **Schema 轉譯單一真理**：`contributes` Schema 一律重用 `core` 既有 `_format.json` 型別簽名解析器轉譯，不另建平行解析邏輯；解析器本身之預設值字面解析缺陷（浮點數、負數）需先行修正（已登錄 TODO）。
- **概念機制與互動協議 (Conceptual Mechanism)**：
  - **雙載體投影**：
    1. **工作區設定投影（SettingsProjector）**：由既有 VS Code 設定軟合併邏輯遷移而來，維護 Python 分析路徑與目錄排除並以 `_yscb_managed` 記錄可還原差異。為使設定內容恆定，於私有微環境內建立無版本號之 site-packages 穩定連結（POSIX symlink / Windows 免權限 Directory Junction），使 Python 版本切換不再造成設定變動。
    2. **本地工作區外掛合成（WorkspaceExtensionSynthesizer）**：於 `.vscode/extensions/yscb-vscode-support/` 生成純宣告式外掛（`package.json` + `schemas/` + `snippets/` + `syntaxes/`），以 `contributes.jsonValidation` 對每個已安裝模組做 1 對 1 檔案匹配綁定。
  - **單檔級 Schema 映射語意**：`contributes/<target>.json` 與 `config/<target>/contribute.json` 綁定 `<target>` 模組 `_format.json` 轉譯之 Schema；`config/<mod>/config.*.json` 綁定該模組組態 Schema；`_format.json` 與 `manifest.json` 綁定元 Schema。純固定鍵物件設 `additionalProperties: false` 並放行 `__provider__` / `__providers__` 等合併元數據鍵。
  - **組態模板來源**：安裝流程會自運行端剝除 `configurable/` 模板。優先評估由本機模組鏡像之原始安裝包讀取模板（零 `core` 改動）；若不可行，再由 `core` 以 IDE 中立之「組態模板快照留存」通用能力保存至快取空間。
  - **開放擴充契約（`contributes/vscode-support.json`）**：`vscode-support` 本身無業務偏見，開放 `json_schemas`、`snippets`、`grammars`、`problem_matchers`、`configuration_defaults` 五類擴充點供自身與其他模組注入；其中 `configuration_defaults` 須採 `unique` 合併策略防止跨模組同鍵靜默覆蓋。Markdown 編譯語法（`__@{}`、`__$`、`__#`、`md:*` 指令）之高亮與片段注入方為 `agents-workflow`；`dev` 可注入合規檢查輸出之 ProblemMatcher。

---

## 3. 解鎖條件與演進構想 (Unlock Criteria & Evolution Stages)

- **前置解鎖條件與觸發時機**：
  - **Phase A**：無外部阻塞，可隨時啟動。
  - **Phase B 前置實測（必須先通過）**：
    1. 驗證目標宿主（含 Antigravity 等 VS Code 衍生版）是否支援 `.vscode/extensions/` 工作區本地外掛之探索、安裝與 `jsonValidation` 生效。
    2. 驗證外掛 `configurationDefaults` 能否承載 `python.analysis.extraPaths` 及各類 exclude 設定，且相對路徑能正確以工作區根解析；若可行則 Phase A 之 `settings.json` 寫入可進一步退場。
    3. 驗證本機模組鏡像能否穩定提供 `configurable/` 原始模板。
- **階段演進構想 (High-Level Stages)**：
  1. **Phase A（`core` 解耦與設定投影遷移）**：`core` 新增 `on_env_synced` 事件並移除所有 VS Code 相關程式碼與公開匯出；新建 `module:vscode-support` 承接設定軟合併、穩定 site-packages 連結與 `on_remove` 精確還原，確保既有 VS Code 開發體驗零退化。
  2. **Phase B（本地外掛與單檔級 Schema 編譯）**：實作外掛合成器與 Schema 編譯器（`contributes` 轉譯 + 組態雙軌推導），開放 `json_schemas` / `configuration_defaults` 擴充點並完成自注入。
  3. **Phase C（語法輔助與互動增強，長期）**：開放 `snippets` / `grammars` / `problem_matchers` 擴充點並由 `agents-workflow`、`dev` 注入；視需求評估以輕量外掛腳本提供語義 URI 之 `Ctrl+Click` 跳轉與懸停解析預覽（需審慎評估 JS 維護面與合併快取讀取契約）。

