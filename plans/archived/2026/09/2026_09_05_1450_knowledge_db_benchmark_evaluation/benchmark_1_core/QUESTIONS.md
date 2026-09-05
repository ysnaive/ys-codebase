# Knowledge-DB 基準評測題目集與驗證真值表 (Benchmark Questions & Ground Truth)

本文件定義針對 `ys-codebase` 知識庫與代碼理解能力的基準評測題目集。題目涵蓋三大維度（Level 1 符號定位與調用、Level 2 模組架構、Level 3 直白自然語言），並附帶客觀 Ground Truth 與計量標準。

---

## 📊 評測題目總覽 (Overview)

| 題號 | 難度分級 | 核心主題 | 測試焦點 | Ground Truth 目標檔案/符號 |
| :---: | :--- | :--- | :--- | :--- |
| **Q1.1** | **Level 1 (符號定位)** | 依賴規格解析與正規化 | 符號定位、函式簽名、參數與回傳型態、去重正規化邏輯 | `source/core/core/pip_manager.py`<br/>`PipManager.parse_pip_dependencies` |
| **Q1.2** | **Level 1 (調用排查)** | 上游調用者排查 (Callers) | 調用者定位、檔案路徑、精確行號 | `source/dev/dev/testing/sandbox.py`<br/>`SandboxProvisioner.adapt_build_pip_dependencies`<br/>調用者: `create_sandbox` (L360) |
| **Q1.3** | **Level 1 (影響分析)** | 多階重構影響半徑 (Impact) | Layer 1 直接依賴、Layer 2 間接依賴擴散 | `source/core/core/pip_manager.py`<br/>`PipManager` (L1: 4 個符號, L2: 5 個符號) |
| **Q2.1** | **Level 2 (模組情境)** | Dev 沙盒 3-Tier 微環境投影 | 投影機制、Windows/POSIX/降級兜底、關鍵實作函式 | `source/dev/dev/testing/sandbox.py`<br/>`SandboxProvisioner._project_venv`<br/>`docs/dev/testing_guide.md` (8.2) |
| **Q2.2** | **Level 2 (模組情境)** | AST 解析與零特權自貢獻 | Tree-sitter 宣告式解析、外掛自貢獻架構、設定檔格式 | `source/knowledge-db/.../tree_sitter_driver.py`<br/>`contributes/knowledge-db.json` |
| **Q2.3** | **Level 2 (模組情境)** | 4-Tier 測試分流與過濾 | 測試分類定義、預設跑測範圍、命令列過濾參數 | `source/dev/dev/testing/requirement.py`<br/>`Requirement` (LOGIC, ENV, WORKFLOW, PERF) |
| **Q3.1** | **Level 3 (自然語言)** | 測試輸出純化與崩潰診斷 | 非致命沙盒警告折疊機制、全量靜默、崩潰 tail 20 行保留 | `source/dev/dev/testing/tester.py`<br/>`docs/dev/testing_guide.md` (第 7 節) |
| **Q3.2** | **Level 3 (自然語言)** | 第三方套件隔離與自動適配 | 微環境隔離、manifest 宣告、沙盒預適配與防遞迴守門 | `source/core/core/pip_manager.py`<br/>`source/dev/dev/testing/sandbox.py`<br/>`YSCB_TEST_SANDBOX` |
| **Q3.3** | **Level 3 (自然語言)** | 複合檢索融合與離線兜底 | BM25 與向量特徵融合演算法 (RRF)、防噪門檻、剛性降級 | `source/knowledge-db/.../hybrid_search.py`<br/>`docs/knowledge-db/DESIGN_NOTES.md` (DN-09) |

---

## 🎯 Level 1：帶有明確符號需求之問題 (Explicit Symbol Queries)

### Q1.1 符號定位、簽名與依賴正規化邏輯
- **題目描述**：  
  「請指出靜態方法 `PipManager.parse_pip_dependencies` 定義在專案的哪個檔案與起始行號？其接受的參數型態與回傳型態為何？該方法內部是如何處理套件名稱與版本規格的清洗、去重與格式正規化的？」
- **Ground Truth**：
  - **檔案路徑與行號**：`ys_codebase/source/core/core/pip_manager.py` (約 Line 44 起)
  - **函式簽名**：`def parse_pip_dependencies(deps: Any) -> Dict[str, str]`
  - **核心邏輯**：
    1. 支援 `dict` 與 `list` 兩種輸入型態。若為 `dict`，清理鍵值前後空白並保證為字串。
    2. 若為 `list`，以正則或字串拆解套件名稱與運算子（`==`, `>=`, `<=`, `~=`, `>`, `<`），未指定版本時規格預設為空字串 `""`。
    3. 保留相依性順序並進行鍵名去重，防禦非字串與非合法型態輸入。

---

### Q1.2 上游調用者排查 (Callers Analysis)
- **題目描述**：  
  「在整個程式庫中，方法 `adapt_build_pip_dependencies` 是由哪個模組、哪個類別定義的？有哪些上游方法調用了它？請明確列出調用者的完整符號名稱 (FQN)、所在檔案路徑與調用行號。」
- **Ground Truth**：
  - **定義位置**：`ys_codebase/source/dev/dev/testing/sandbox.py` (Line 189 起，`SandboxProvisioner.adapt_build_pip_dependencies`)
  - **上游調用者**：
    - 調用者符號：`SandboxProvisioner.create_sandbox`
    - 所屬檔案：`ys_codebase/source/dev/dev/testing/sandbox.py`
    - 調用行號：Line 360 (`self.adapt_build_pip_dependencies(...)` 或 `SandboxProvisioner.adapt_build_pip_dependencies(...)`)

---

### Q1.3 多階重構影響半徑評估 (Impact Analysis)
- **題目描述**：  
  「若核心團隊計畫重構 `core` 模組中的 `PipManager` 類別，請以 2 階深度 (depth=2) 分析其重構影響面：有哪些類別與方法屬於直接調用/依賴的 Layer 1，有哪些屬於間接依賴的 Layer 2？請列出受影響符號及其所屬檔案。」
- **Ground Truth**：
  - **目標符號**：`core.pip_manager.PipManager` (`ys_codebase/source/core/core/pip_manager.py`)
  - **Layer 1 (直接調用/依賴者，共 4 個)**：
    1. `SandboxProvisioner._project_venv` (`ys_codebase/source/dev/dev/testing/sandbox.py`)
    2. `SandboxProvisioner.adapt_build_pip_dependencies` (`ys_codebase/source/dev/dev/testing/sandbox.py`)
    3. `IdeProjector.__init__` (`ys_codebase/source/core/core/ide_projector.py`)
    4. `Installer.sync_pip_dependencies` (`ys_codebase/source/core/core/installer.py`)
  - **Layer 2 (間接依賴擴散者，共 5 個)**：
    1. `SandboxProvisioner.create_sandbox` (`ys_codebase/source/dev/dev/testing/sandbox.py`)
    2. `Installer.cmd_install` (`ys_codebase/source/core/core/installer.py`)
    3. `Installer.cmd_update` (`ys_codebase/source/core/core/installer.py`)
    4. `Installer.cmd_reload` (`ys_codebase/source/core/core/installer.py`)
    5. `Installer.cmd_remove` (`ys_codebase/source/core/core/installer.py`)

---

## 🔍 Level 2：帶有大致關鍵模組訊息之問題 (Module Context Queries)

### Q2.1 Dev 沙盒微環境零拷貝投影與 3-Tier 降級機制
- **題目描述**：  
  「在 `dev` 模組的測試沙盒 (sandbox) 機制中，系統如何將宿主環境的微虛擬環境 (`.venv`) 零拷貝投影到沙盒內部？遇到不支援目錄連結（如 Windows 無管理員權限或容器掛載磁碟）時，採用了哪三階 (3-Tier) 平滑降級機制？其關鍵實作函式名稱與檔案為何？」
- **Ground Truth**：
  - **實作位置**：`ys_codebase/source/dev/dev/testing/sandbox.py` 的 `SandboxProvisioner._project_venv`（文件記錄於 `docs/dev/testing_guide.md` 第 8.2 節）。
  - **3-Tier 降級機制**：
    1. **Tier 1 (Windows)**：優先使用 Windows 目錄重析點 `_winapi.CreateJunction`，零管理員權限、sub-1ms 瞬時完成。
    2. **Tier 2 (POSIX)**：優先使用目錄符號連結 `os.symlink`。
    3. **Tier 3 (降級兜底)**：當引發 `OSError`（如容器掛載磁碟或 exFAT），在沙盒 `engine/.venv` 建立輕量 `site-packages` 目錄並寫入 `host_venv.pth` 指向宿主微環境。

---

### Q2.2 Knowledge-DB 通用 AST 解析與零特權自貢獻架構
- **題目描述**：  
  「在 `knowledge-db` 模組中，程式碼解析引擎是如何實作多語言 AST 解析的？它是透過什麼架構達成『零特權外掛自貢獻 (Zero-Privilege Dogfooding)』的？若欲新增一種程式語言的解析支援，需要編寫什麼語法查詢檔？應在哪份設定檔中進行宣告？」
- **Ground Truth**：
  - **解析引擎**：`TreeSitterDriver` (`ys_codebase/source/knowledge-db/knowledge_db/parsers/tree_sitter_driver.py`)，採用 Tree-sitter S-Expression 聲明式語法查詢（`.scm` 檔案）提取結構化 AST。
  - **零特權自貢獻**：`LanguageRegistry` 與 `ParserRegistry` 採外掛架構，所有語言由 `contributes.knowledge-db` 動態加載；模組內建語言亦不具核心硬編碼特權，一律透過自身宣告物化。
  - **新增語言所需**：
    1. S-Expression 查詢檔：放置於 `queries/<lang>.scm`，定義 class, function, call_site, docstring 等 capture 標籤。
    2. 設定檔宣告：在 `ys_codebase/source/knowledge-db/contributes/knowledge-db.json`（或各模組 contributes）中宣告語言名稱、副檔名 (`extensions`)、文法套件名稱與查詢檔路徑。

---

### Q2.3 Dev 測試套件 4-Tier 需求分流與跑測過濾機制
- **題目描述**：  
  「在 `dev` 模組中，測試套件被劃分為哪 4 個層級 (4-Tier Requirement)？各層級代表什麼意義？日常預設跑測指令會執行哪些層級？如何透過命令列參數指定執行耗時較長的多進程沙盒工作流測試？」
- **Ground Truth**：
  - **列舉類別與定義位置**：`Requirement` 列舉（位於 `ys_codebase/source/dev/dev/testing/requirement.py`，說明見 `docs/dev/testing_guide.md` 第 9 節）。
  - **4-Tier 定義**：
    1. `LOGIC`：純記憶體單元測試（預設執行）。
    2. `ENV`：模組相依、DI、VFS 輕量環境測試（預設執行）。
    3. `WORKFLOW`：多步驟複合工作流、重度多進程實體沙盒、打包與跨進程鎖測試（預設排除）。
    4. `PERF`：效能基準與高壓負載測試（預設排除）。
  - **預設跑測**：`LOGIC | ENV` (`Requirement.ALL_DEFAULT`)。
  - **CLI 過濾參數**：`python yscb.py dev test --workflow`（僅跑工作流測試）或 `python yscb.py dev test --all-types`（全量跑測）。

---

## 💬 Level 3：直白敘述式問題 (Natural Language Queries)

### Q3.1 測試警告收斂折疊與崩潰尾部診斷機制
- **題目描述**：  
  「當專案執行單元測試時，測試終端輸出的非致命沙盒警告（如未解 URI 警告）是如何被收集與折疊的？如果測試發生非預期的沙盒崩潰或致命報錯，系統又是如何避免除錯資訊被安靜吞掉、精準呈現錯誤原因的？」
- **Ground Truth**：
  - **架構與設計決策**：測試輸出純化與信息聚合體系（`docs/dev/testing_guide.md` 第 7 節與 `[DN-DEV-07]`）。
  - **警告折疊機制**：子進程與調度器採用統一 JSON IPC (`--report-json`) 跨進程交換，非致命沙盒警告（如未解 URI 編譯警告）在一般模式下由宿主調度器收斂折疊為單行摘要 `[*] Notices: N sandbox warning(s) captured (suppressed, run with --verbose to inspect)`；可附加 `--verbose` 展開原始串流。
  - **崩潰診斷機制**：在節流模式 (`--quiet`) 下，若沙盒進程遭遇非預期致命錯誤（未產生 report JSON 且返回碼非 0），系統會自動精準擷取子進程 stderr 尾部 20 行切片呈遞，既杜絕日誌洗版，又守護除錯可觀測性。

---

### Q3.2 第三方套件隔離與自動適配機制
- **題目描述**：  
  「在 YSCB 生態系中，如果某些模組需要使用第三方 Python 套件（例如 Tree-sitter、FastEmbed），系統是如何避免污染開發者的全域 Python 環境，並在沙盒測試或模組安裝時自動把它們裝起來的？」
- **Ground Truth**：
  - **微虛擬環境隔離**：YSCB 在 `yscb://.venv/` 建立專屬微虛擬環境，由 `PipManager` 管理，與宿主系統全域 Python 完全隔離。
  - **依賴宣告與靜態檢核**：模組在 `manifest.json` 中以 `pip_dependencies` 字典宣告第三方套件；`dev check` 會進行靜態合規性校驗。
  - **安裝與沙盒自動適配**：
    1. 安裝階段：`Installer.sync_pip_dependencies` 透過 `PipManager.parse_pip_dependencies` 正規化後自動安裝。
    2. 沙盒測試階段：`SandboxProvisioner.adapt_build_pip_dependencies` 在沙盒建置前自動掃描待測模組的依賴並靜默安裝至微環境，並透過 3-Tier 零拷貝投影至沙盒。
    3. 防遞迴守門：沙盒環境會設置 `YSCB_TEST_SANDBOX=1`，防止沙盒內二次跑測時產生重複 pip 調用循環。

---

### Q3.3 知識庫複合檢索融合演算法與離線兜底機制
- **題目描述**：  
  「知識庫在搜尋程式碼或文檔時，是怎麼把關鍵字文字匹配與向量語意相似度結合在一起的？遇到系統沒有安裝向量模型、缺少推論相依套件或使用者想純離線查詢時，系統有什麼兜底保證？」
- **Ground Truth**：
  - **複合檢索融合演算法**：`HybridSearchEngine` 採用倒數排名融合演算法 (Reciprocal Rank Fusion, RRF $k=60$)，將 BM25 詞法倒排索引排序分數與 FastEmbed ONNX (BAAI/bge-small-zh-v1.5) 向量餘弦相似度進行無母數加權融合（詳見 `docs/knowledge-db/DESIGN_NOTES.md` `[DN-09]`）。
  - **防噪過濾門檻**：對未命中 BM25 的純向量候選，設有語意相似度最低門檻（$\ge 0.70$）與長複合查詢詞覆蓋率門檻（$\ge 50\%$），防止向量語意幻覺噪訊。
  - **離線兜底與剛性降級**：支援 `--lexical-only` CLI 旗標；若 FastEmbed 未安裝或推論引發例外，系統 100% 剛性平滑降級為純 BM25 檢索，確保完全離線且功能可用。

---

## 📈 評測計量指標與計分準則 (Metrics & Rubric)

評測 Agent 必須對每題如實記錄以下指標，以客觀量化工具效能：

1. **讀取與檢索 Token 消耗 (Read/Search Tokens)**：
   - 工具回傳字元數總計 $\div 4$（例如每 4 chars 約等於 1 token）。
2. **工具調用次數 (Tool Call Count)**：
   - 完成該題所觸發的工具調用總次數（如 `run_command`, `view_file`, `grep_search` 等）。
3. **思考步驟數 (Thinking Steps)**：
   - 該題解答過程中的推論與思考次數。
4. **耗時 (Wall-Clock Seconds)**：
   - 該題自開始檢索至產出答案所花費的秒數。
5. **答案準確率與覆蓋度 (Accuracy Score, 0~100%)**：
   - 比對上述 Ground Truth，若檔案路徑、符號、核心機制皆正確且無幻覺，記為 100%；漏答部分關鍵點依比例扣分。
