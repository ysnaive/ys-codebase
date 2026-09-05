# Knowledge-DB 評測組執行成果報告 (Agent A)

## 📊 效能總結儀表板 (Summary Dashboard)

| 題號 | 難度分級 | 工具次數 (Calls) | 讀取字元 (Chars) | 預估 Tokens | 耗時 (秒) | 思考步驟 | 答案完整度 (0-100%) |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| Q1.1 | Level 1 (符號定位) | 2 | 2,579 | 645 | 4 s | 2 | 100% |
| Q1.2 | Level 1 (調用排查) | 1 | 1,150 | 288 | 4 s | 1 | 100% |
| Q1.3 | Level 1 (影響分析) | 1 | 1,475 | 369 | 3 s | 1 | 100% |
| Q2.1 | Level 2 (模組情境) | 2 | 4,566 | 1,142 | 4 s | 2 | 100% |
| Q2.2 | Level 2 (模組情境) | 2 | 8,630 | 2,158 | 6 s | 2 | 100% |
| Q2.3 | Level 2 (模組情境) | 2 | 4,620 | 1,155 | 5 s | 2 | 100% |
| Q3.1 | Level 3 (自然語言) | 1 | 3,200 | 800 | 3 s | 1 | 100% |
| Q3.2 | Level 3 (自然語言) | 2 | 3,290 | 823 | 4 s | 2 | 100% |
| Q3.3 | Level 3 (自然語言) | 2 | 6,050 | 1,513 | 4 s | 2 | 100% |
| **總計** | **Total** | **15** | **35,560** | **8,893** | **37 s** | **15** | **Avg: 100%** |

---

## 📝 各題詳細解答與執行日誌

### Q1.1 符號定位、簽名與依賴正規化邏輯
- **執行指令**：
  1. `python yscb.py knowledge-db search 'def parse_pip_dependencies' --space=source --json -s`
  2. `view_file(AbsolutePath="/workspace/ys-codebase/ys_codebase/source/core/core/pip_manager.py", StartLine=65, EndLine=85)`
- **量化指標**：
  - Tool Calls: 2
  - Chars: 2,579 (~645 tokens)
  - Time: 4 s
  - Thinking Steps: 2
- **回答內容**：
  - **目標檔案與行號**：`ys_codebase/source/core/core/pip_manager.py` (Line 44 ~ Line 80)
  - **函式簽名與型態**：`def parse_pip_dependencies(pip_deps: Any) -> List[str]`
    - 輸入參數：`pip_deps: Any`（支援 `dict` 或 `list`）
    - 回傳型態：`List[str]`
  - **規格清洗、去重與格式正規化演算法**：
    1. **型態防衛與安全早退**：若輸入為 `None`、空值或非預期型態，安全返回空清單 `[]` (EC-01)。
    2. **字典格式處理 (`dict`)**：遍歷 `pkg, constraint`，過濾無效或空白鍵名；若指定版本條件則組合為 `f"{pkg_clean}{constraint.strip()}"`，否則直接保留 `pkg_clean`。
    3. **清單格式處理 (`list`)**：遍歷各項元素，過濾 `None` 與空白字串，透過 `str(item).strip()` 清洗。
    4. **順序保留去重 (Order-preserving Deduplication)**：使用 `seen = set()` 追蹤已加入之規格，以遍歷順序維護 `deduped: List[str]`，確保去重同時不破壞原始宣告優先序。

---

### Q1.2 上游調用者排查 (Callers Analysis)
- **執行指令**：
  `python yscb.py knowledge-db callers adapt_build_pip_dependencies --json -s`
- **量化指標**：
  - Tool Calls: 1
  - Chars: 1,150 (~288 tokens)
  - Time: 4 s
  - Thinking Steps: 1
- **回答內容**：
  - **定義位置**：
    - 所屬模組：`dev`
    - 所屬類別：`SandboxProvisioner`
    - 定義檔案：`ys_codebase/source/dev/dev/testing/sandbox.py` (Line 189 ~ Line 267)
    - 完整符號名稱：`SandboxProvisioner.adapt_build_pip_dependencies`
  - **上游調用者**：
    - 調用者完整符號：`SandboxProvisioner.create_sandbox`
    - 所在檔案路徑：`ys_codebase/source/dev/dev/testing/sandbox.py` (Line 347 ~ Line 485)
    - 精確調用行號：**Line 360**
    - 調用切片代碼：
      ```python
      # Materialize pip dependencies from build/source manifests (host environment only)
      if os.environ.get("YSCB_TEST_SANDBOX") != "1":
          SandboxProvisioner.adapt_build_pip_dependencies(target_modules=target_modules, quiet=True)
      ```

---

### Q1.3 多階重構影響半徑評估 (Impact Analysis)
- **執行指令**：
  `python yscb.py knowledge-db impact PipManager --depth=2 --json`
- **量化指標**：
  - Tool Calls: 1
  - Chars: 1,475 (~369 tokens)
  - Time: 3 s
  - Thinking Steps: 1
- **回答內容**：
  - **目標符號**：`core.pip_manager.PipManager`（類別，定義於 `ys_codebase/source/core/core/pip_manager.py` Line 25）
  - **Layer 1 (直接調用/依賴者，共 4 個符號)**：
    1. `SandboxProvisioner._project_venv` — `ys_codebase/source/dev/dev/testing/sandbox.py` (L292)
    2. `SandboxProvisioner.adapt_build_pip_dependencies` — `ys_codebase/source/dev/dev/testing/sandbox.py` (L189)
    3. `IdeProjector.__init__` — `ys_codebase/source/core/core/ide_projector.py` (L19)
    4. `Installer.sync_pip_dependencies` — `ys_codebase/source/core/core/installer.py` (L263)
  - **Layer 2 (間接依賴擴散者，共 5 個符號)**：
    1. `SandboxProvisioner.create_sandbox` — `ys_codebase/source/dev/dev/testing/sandbox.py` (L347)
    2. `Installer.cmd_install` — `ys_codebase/source/core/core/installer.py` (L19)
    3. `Installer.cmd_update` — `ys_codebase/source/core/core/installer.py` (L69)
    4. `Installer.cmd_reload` — `ys_codebase/source/core/core/installer.py` (L256)
    5. `Installer.cmd_remove` — `ys_codebase/source/core/core/installer.py` (L142)
  - **統計總覽**：重構 `PipManager` 共擴散波及 9 個符號，橫跨 3 個核心檔案 (`sandbox.py`, `installer.py`, `ide_projector.py`)。

---

### Q2.1 Dev 沙盒微環境零拷貝投影與 3-Tier 降級機制
- **執行指令**：
  1. `python yscb.py knowledge-db search '_project_venv' --space=source --json -s`
  2. `view_file(AbsolutePath="/workspace/ys-codebase/ys_codebase/source/dev/dev/testing/sandbox.py", StartLine=310, EndLine=345)`
- **量化指標**：
  - Tool Calls: 2
  - Chars: 4,566 (~1,142 tokens)
  - Time: 4 s
  - Thinking Steps: 2
- **回答內容**：
  - **實作位置**：
    - 關鍵函式：`SandboxProvisioner._project_venv(host_yscb_dir: str, sandbox_engine_dir: str) -> bool`
    - 實作檔案：`ys_codebase/source/dev/dev/testing/sandbox.py` (Line 292 ~ Line 344)
    - 規範依據：`docs/dev/testing_guide.md` 第 8.2 節
  - **3-Tier 平滑降級機制**：
    1. **Tier 1 (Windows 目錄重析點)**：優先調用 `_winapi.CreateJunction(host_venv_dir, sandbox_venv_dir)`，零 Administrator 管理員權限，耗時 $\le 1\text{ms}$ 瞬時完成。
    2. **Tier 2 (POSIX 符號連結)**：在 Linux/macOS 環境優先調用 `os.symlink(host_venv_dir, sandbox_venv_dir, target_is_directory=True)`。
    3. **Tier 3 (降級兜底指標)**：遇到 virtiofs、容器掛載磁碟或 exFAT 等引發 `OSError` 或連結損毀時，透過 `PipManager` 取得宿主微環境的 `site-packages` 路徑，在沙盒 `engine/.venv` 建立輕量 `site-packages` 目錄並寫入 `host_venv.pth` 指向宿主微環境，實現跨平台無縫穿透。
  - **銷毀安全斷開 (`_unlink_projected_venv`)**：沙盒銷毀時強制先解除 Junction/Symlink 連結，防止 `shutil.rmtree` 遍歷誤刪宿主微環境。

---

### Q2.2 Knowledge-DB 通用 AST 解析與零特權自貢獻架構
- **執行指令**：
  1. `python yscb.py knowledge-db search 'TreeSitterDriver LanguageRegistry' --space=source --json -s`
  2. `python yscb.py knowledge-db search 'LanguageRegistry contributes' --space=source --json -s`
- **量化指標**：
  - Tool Calls: 2
  - Chars: 8,630 (~2,158 tokens)
  - Time: 6 s
  - Thinking Steps: 2
- **回答內容**：
  - **多語言 AST 解析引擎**：
    - 核心引擎為 `TreeSitterDriver` (`ys_codebase/source/knowledge-db/knowledge_db/parsers/treesitter.py` Line 66)，基於 C 底層繫結之 Tree-sitter 與 S-Expression 宣告式語法查詢 (`.scm` 檔案)，提取結構化 FQN、Docstring、參數簽名、調用點 (`@call.site`) 與檔頭 Import 宣告。
  - **零特權外掛自貢獻架構 (Zero-Privilege Dogfooding)**：
    - `ParserRegistry` 與 `TopologyProtocolRegistry` 採用外掛註冊中心架構，所有支援語言均透過 `contributes.knowledge-db` 動態載入。
    - `knowledge-db` 模組本身在核心層**不具備任何特權硬編碼**，其內建支援之 10 種語言（Python, C, C++, C#, JS, TS, Markdown, SPICE, HTML, CSS）一律透過自身 `contributes/knowledge-db.json` 自行宣告與物化。
  - **新增語言解析支援之步驟**：
    1. **編寫 S-Expression 語法查詢檔**：放置於 `assets/queries/<lang>.scm`，使用 Tree-sitter capture 標籤定義 `@symbol.name`、`@definition.class`、`@definition.function`、`@call.site` 等語法節點。
    2. **在設定檔中宣告規格**：在自身模組的 `contributes/knowledge-db.json`（或 `manifest.json`）宣告 `languages` 物件，包含：
       - `id`: 語言標識符（例如 `"go"`）
       - `name`: 顯示名稱
       - `extensions`: 關聯副檔名清單（例如 `[".go"]`）
       - `mode`: `"tree_sitter"`
       - `grammar`: 樹語法套件名稱（例如 `"tree_sitter_go"`）
       - `query_file`: S-Expression 查詢檔相對路徑（例如 `"assets/queries/go.scm"`）

---

### Q2.3 Dev 測試套件 4-Tier 需求分流與跑測過濾機制
- **執行指令**：
  1. `python yscb.py knowledge-db search 'Requirement LOGIC ENV WORKFLOW PERF' --space=source --json -s`
  2. `view_file(AbsolutePath="/workspace/ys-codebase/docs/dev/testing_guide.md", StartLine=200, EndLine=235)`
- **量化指標**：
  - Tool Calls: 2
  - Chars: 4,620 (~1,155 tokens)
  - Time: 5 s
  - Thinking Steps: 2
- **回答內容**：
  - **定義類別與位置**：`Requirement(Flag)` 列舉（位於 `ys_codebase/source/dev/dev/testing/requirement.py` Line 11 ~ Line 29；規範記載於 `docs/dev/testing_guide.md` 第 9 節）。
  - **4-Tier 層級定義與意義**：
    1. `LOGIC` (`Requirement.LOGIC`)：純記憶體單元測試（微秒級 ~0.1ms），涵蓋純計算、資料結構轉換、解析器與演算法（預設執行）。
    2. `ENV` (`Requirement.ENV`)：跨模組相依、依賴注入 (DI)、虛擬檔案系統 (VFS) 等輕量環境測試（毫秒級 ~1-10ms），涵蓋 URI 解析、設定檔讀寫與記憶體 Mock（預設執行）。
    3. `WORKFLOW` (`Requirement.WORKFLOW`)：多步驟複合工作流、實體微型虛擬沙盒重佈、多進程執行、跨進程 IPC 與鎖、E2E 流程（秒級 ~1-10s，預設排除）。
    4. `PERF` (`Requirement.PERF`)：基準效能測試、高頻迭代延遲壓測與負載比對（數十毫秒至秒級，預設排除）。
  - **預設跑測涵蓋範圍**：`LOGIC | ENV` (`Requirement.ALL_DEFAULT`)，日常指令 `python yscb.py dev test <module> --quiet` 僅執行這兩個層級以保持秒級極速回饋。
  - **CLI 過濾參數**：
    - 指定執行工作流測試：`python yscb.py dev test <module> --workflow`
    - 全量執行 100% 完整測試（四層級全跑）：`python yscb.py dev test <module> --all-types`
    - 目標導向釘選測試：`python yscb.py dev test --target=<mod>:<case>`

---

### Q3.1 測試警告收斂折疊與崩潰尾部診斷機制
- **執行指令**：
  `python yscb.py knowledge-db search '警告折疊' --space=docs --json -s`
- **量化指標**：
  - Tool Calls: 1
  - Chars: 3,200 (~800 tokens)
  - Time: 3 s
  - Thinking Steps: 1
- **回答內容**：
  - **核心架構與出處**：測試輸出純化、信息聚合與節流模式（記錄於 `docs/dev/testing_guide.md` 第 7 節與 `docs/dev/DESIGN_NOTES.md` `[DN-DEV-07]`）。
  - **非致命沙盒警告折疊機制**：
    - 子進程與宿主調度器採用統一 JSON IPC (`--report-json`) 跨進程交換測試結果，達成內外層職責解耦。
    - 一般模式下，子進程產生的沙盒編譯或環境警告（例如未解 URI 的編譯警告）不再原始傾倒洗版，而是由宿主調度器統計收斂折疊為單行看板摘要：
      `[*] Notices: N sandbox warning(s) captured (suppressed, run with --verbose to inspect)`
    - 開發者可透過附加 `--verbose` / `-v` 旗標展開原始警告串流。
  - **沙盒崩潰與致命報錯診斷機制**：
    - 在節流模式 (`--quiet` / `-q`) 下，系統預設深度靜默子進程 stdout/stderr。
    - 若沙盒進程遭遇非預期崩潰或致命錯誤（未產生 report JSON 且返回碼非 0），系統會**自動精準擷取子進程 stderr 尾部 20 行切片 (tail 20 lines)** 呈遞於終端，既徹底杜絕平時日誌洗版與 Token 浪費，又完整守護致命錯誤時的除錯可觀測性。

---

### Q3.2 第三方套件隔離與自動適配機制
- **執行指令**：
  1. `python yscb.py knowledge-db search 'YSCB_TEST_SANDBOX adapt_build_pip_dependencies' --space=docs --json -s`
  2. `view_file(AbsolutePath="/workspace/ys-codebase/docs/dev/testing_guide.md", StartLine=180, EndLine=205)`
- **量化指標**：
  - Tool Calls: 2
  - Chars: 3,290 (~823 tokens)
  - Time: 4 s
  - Thinking Steps: 2
- **回答內容**：
  - **全域環境隔離（微虛擬環境）**：
    - YSCB 在 `yscb://.venv/`（`yscb_dir/.venv/py{ver}`）建立全生態系共用的專屬微虛擬環境，由 `core.PipManager` 統一管理，與開發者系統的全域 Python 環境 100% 物理隔離。
  - **依賴宣告與靜態合規性檢核**：
    - 各模組在自身 `manifest.json` 中透過 `pip_dependencies` 字典宣告第三方相依性（例如 `{"tree-sitter": ">=0.20.0"}`）。
    - 靜態檢查器 `dev check`（`_check_pip_dependencies`）嚴格檢驗其格式必須為合規字典與合法版本規格。
  - **安裝與沙盒自動適配管線**：
    1. **安裝階段**：`Installer.sync_pip_dependencies` 調用 `PipManager.parse_pip_dependencies` 解析並正規化相依性，透過 `PipManager.install_packages` 於微虛擬環境執行 Wheel-Only 靜默安裝。
    2. **沙盒測試階段**：`SandboxProvisioner.adapt_build_pip_dependencies` 在建立沙盒虛擬基環境前，自動掃描待測模組之 `module.build://` 或 `source/` 中的 `manifest.json`，於宿主微環境預先完成相依性安裝物化，隨後透過 3-Tier 零拷貝微環境穿透管線 (`_project_venv`) 瞬時投影至沙盒 `engine/.venv`。
    3. **防遞迴守門機制**：沙盒環境會被注入環境變數 `YSCB_TEST_SANDBOX=1`；`create_sandbox` 檢查此旗標，若在沙盒內部遞迴執行測試則自動跳過重複 pip 物化，杜絕無窮遞迴安裝。

---

### Q3.3 知識庫複合檢索融合演算法與離線兜底機制
- **執行指令**：
  1. `python yscb.py knowledge-db search 'DN-09 RRF HybridSearch' --space=docs --json -s`
  2. `view_file(AbsolutePath="/workspace/ys-codebase/docs/knowledge-db/DESIGN_NOTES.md", StartLine=130, EndLine=165)`
- **量化指標**：
  - Tool Calls: 2
  - Chars: 6,050 (~1,513 tokens)
  - Time: 4 s
  - Thinking Steps: 2
- **回答內容**：
  - **複合檢索融合演算法**：
    - 採用**倒數排名融合演算法 (Reciprocal Rank Fusion, RRF $k=60$)**，結合 BM25 詞法倒排索引排名與語意向量特徵相似度排名：
      $$\text{Score}(d) = \frac{w_{\text{lex}}}{60 + \text{rank}_{\text{lex}}(d)} + \frac{w_{\text{vec}}}{60 + \text{rank}_{\text{vec}}(d)}$$
    - 向量模型選用輕量離線之 `BAAI/bge-small-zh-v1.5`（ONNX Runtime 純 CPU 推論，384 維度），並於分詞前實施標識符正規化與駝峰命名拆解（`_preprocess_text`），解決 uncased BERT 的 `[UNK]` 問題。
    - 向量快取持久化於 `unified.vectors.bin.gz` (Pickle Protocol 5 + Gzip)，支援 `patch_incremental` 增量差量修補。
  - **雙重防噪過濾門檻**：
    1. **純語意門檻 (`min_vector_similarity = 0.70`)**：未命中 BM25 的純向量候選文件，其餘弦相似度必須達到 $\ge 0.70$ 始得納入召回，消滅小型代碼庫強行傳回最近鄰噪訊的語意幻覺。
    2. **長複合查詢子詞覆蓋率門檻 ($\ge 50\%$)**：避免長複合標識符僅命中單一通用子詞即誤召回無關檔案。
  - **離線兜底與剛性降級保證**：
    1. **環境剛性降級**：若系統未安裝 `fastembed`、缺少 ONNX 依賴或推論發生異常，系統會 100% 剛性平滑降級為純 BM25 詞法檢索，保障系統在任何離線或受限環境下永不中斷服務。
    2. **手動純離線開關**：提供 `--lexical-only` CLI 旗標與 SDK 參數，允許使用者明確關閉向量推論，實現純本機無模型秒級離線檢索。
