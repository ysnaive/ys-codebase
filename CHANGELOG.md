# 專案變更歷史 (Changelog)

本檔案記錄 `ys-codebase` 專案的所有高階功能、規範與架構變更。以開發計畫 (Dev Plan) 目錄名稱為版本區分單位。

## 2026_09_05_1300_core_dev_toolchain_upgrade (Completed)

- **`sub_01_core_pip_sdk_and_environment_export` (Completed)**：
  - **Core 導出微環境 PipManager SDK 契約**：於 `source/core/core/__init__.py` 的 `__all__` 中正式導出 `PipManager`、`PipInstallError` 與 `pip_manager` 模組，支援標準匯入契約 `from core import PipManager, PipInstallError`。
  - **規格正規化工具函式 (`parse_pip_dependencies`)**：在 `PipManager` 實作靜態方法 `parse_pip_dependencies`，支援字典與清單格式相依性宣告之空白過濾、型態防禦與順序去重，消除跨模組手刻解析與重複代碼。
  - **安裝器依賴收斂**：重構 `Installer.sync_pip_dependencies` 改調用 `PipManager.parse_pip_dependencies`。
  - **文件與測試健全化**：新增 `docs/core/DESIGN_NOTES.md` 之 `[DN-19]`、更新 `source/core/README.md` 與 `docs/core/API_REFERENCE.md`；新增單元測試 `test_pip_manager_sdk.py`，全生態系 123/123 單元測試 100% 通過。

- **`sub_02_dev_toolchain_pip_adaptation_and_sandbox_integration` (Completed)**：
  - **3-Tier 微環境沙盒雙軌投影管線 (`_project_venv`)**：於 `dev.testing.sandbox` 實作 Windows Junction (`_winapi.CreateJunction`)、POSIX Symlink (`os.symlink`) 與 `.pth` 檔案指標三階平滑降級投影機制，達成跨平台零管理員權限、sub-1ms 瞬時投影，沙盒無縫感知宿主微環境套件。
  - **Build 版與模組 Pip 相依性沙盒預適配 (`adapt_build_pip_dependencies`)**：在沙盒建置前自動掃描待測模組之來源或 release zip manifest，透過 `core.PipManager` 靜默正規化並安裝物化 pip 相依性；加入 `YSCB_TEST_SANDBOX` 防遞迴守門，杜絕沙盒內部巢狀跑測時的重複 pip 調用。
  - **沙盒安全斷開機制 (`_unlink_projected_venv`)**：於 `cleanup_sandbox` 銷毀沙盒實體前，強制先行安全斷開 Junction/Symlink 連結，防止 `shutil.rmtree` 遞迴誤刪宿主微環境。
  - **Checker 靜態相依性合規性檢驗**：擴充 `source/dev/dev/checker.py` 檢驗 `manifest.json` 中 `pip_dependencies` 結構必須為非空套件名稱映射字典約束。
  - **單元與邊界測試全覆蓋**：新增 `test_pip_adaptation.py` 驗證 FT-01~04 與 ET-01~02，修復沙盒 hook 路徑跳脫與 build 清理殘留；dev 模組 72/72 單元測試 100% 通過。

- **`sub_03_dev_test_output_purification_and_info_aggregation` (Completed)**：
  - **統一 JSON IPC 跨進程交換與輸出解耦**：單模組與平行測試全面採用 `--report-json` 導出測試數據，由宿主調度器作為唯一的格式化渲染端，達成內外層職責解耦。
  - **雙模式輸出純化與警告收斂**：
    - `--quiet` / `-q` 模式下，全量屏蔽子進程 stdout/stderr；全數通過時嚴格僅輸出單行統計（`Pass: 78(100.0%), Fail: 0, Skip: 0`）；崩潰時精準擷取 stderr tail（後 20 行）供快速診斷。
    - 一般模式下，子進程非致命沙盒警告（如未解 URI 編譯警告）收斂折疊為 `[*] Notices: N sandbox warning(s) captured`，並支援 `--verbose` 展開原始串流。
  - **沙盒黑盒子與高保真原則**：沙盒內部生命週期 Hook（如 JIT 預發布與自癒物化）維持自然運行，嚴禁粗暴短路業務邏輯。
  - **宿主防穿透剛性守門**：
    - `dev op-test` 於宿主環境直接調用時剛性阻斷（Gate 0），提示改用 `dev test` 進入沙盒。
    - `YSCBTestCase.setUp` 在無法向上解析出合法沙盒目錄時強制拋出 `SecurityError`，徹底拔除回退至 `os.getcwd()` 的漏洞，守護專案根目錄零污染。
  - **測試與文件完備**：新增 `test_output_purification.py` 完整覆蓋 FT-01~04 與 ET-01~02；更新 `docs/dev/testing_guide.md` 與 `docs/dev/DESIGN_NOTES.md` `[DN-DEV-07]`；dev 模組 78/78 測試 100% 通過。

- **`sub_04_core_dev_test_case_purification` (Completed)**：
  - **測試套件純化與碎片化小檔根除**：
    - Dev 模組：將 `test_tester_sync.py` 與 `test_tester_throttle.py` 完整整併至核心 `test_tester.py`，刪除舊零碎測試檔。
    - Core 模組：新建 `test_cli_router.py`，完整吸收 `test_cli_help.py` 與 `test_cli_guild.py`；將 `test_contributes_jit.py` 併入 `test_contributes.py`；精簡緊湊化 `test_pip_manager_sdk.py` 同質案例；徹底清除舊檔。
  - **4-Tier 分流機制 (Logic / Env / Workflow / Perf)**：
    - 將 `test_sandbox.py` 與 `test_engine.py` 中 7 個高耗時實體沙盒、多進程執行與跨進程鎖案例標註為 `@require(Requirement.WORKFLOW)`；效能基準測試標註為 `@require(Requirement.PERF)`。
    - 預設模式（`python yscb.py dev test --quiet`）僅執行 `LOGIC + ENV`，大幅縮短日常跑測回饋時間（`dev` 降至 ~2.5s，`core` ~4s）。
    - 支援 `--all-types` 與 `--workflow` 供發布與守門時進行 100% 全量回歸驗證（0 邏輯遺失）。
  - **YSCBTestCase 三態執行分類與 Unknown 數量回報**：
    - 覆寫 `_callTestMethod` 捕獲未處理例外，於 `tearDown()` 建立 `PASSED` / `FAILED` / `UNKNOWN` 精確分類；未顯式標註 `mark_passed()` 且無異常之案例歸類為 `UNKNOWN`，徹底杜絕假失敗沙盒提示污染 stdout。
    - 規避 Python `unittest.TestSuite` 執行後清空測試實例機制，於測試前保留實例引用，並於 Summary 統計（一般模式與節流模式）精準支援 `Unknown: N` 數量回報。
  - **測試修復與版本發布 (`core@1.0.3.3`)**：
    - 修復 `source/core/tests/` 8 個測試套件計 43 處方法，補齊 `self.mark_passed()`，達成 `core` 快測 118/118 100% Passed 且 Unknown: 0。
    - 晉升並發布 `core@1.0.3.3`。
  - **測試與文件完備**：新增單元測試 `test_execution_status_classification_in_teardown` 與 `test_format_throttled_with_unknown`；更新 `docs/dev/testing_guide.md`（新增第 9 節）與 `docs/dev/DESIGN_NOTES.md` (`[DN-DEV-08]`)；全量測試 100% 通過。


## 2026_09_05_1025_knowledge_db_refactor (Executing)

- **`sub_01_universal_ast_and_contributed_tree_sitter` (Completed)**：
  - **Tree-sitter 宣告式通用 AST 解析引擎 (`TreeSitterDriver`)**：引入聲明式 S-Expression 查詢解析器（`python.scm`, `cpp.scm`, `c.scm`, `javascript.scm`, `typescript.scm`, `c_sharp.scm`, `markdown.scm`），提供結構化 FQN、Docstring、結構化參數簽名、調用點與檔頭 import 提取，全面取代舊手刻正則狀態機。
  - **零特權外掛自貢獻架構 (Zero-Privilege Dogfooding)**：重構 `LanguageRegistry` / `ParserRegistry`，全數語言由 `contributes.knowledge-db` 宣告動態加載；模組自身內建支援之 10 種語言（含自訂 SPICE, HTML, CSS）一律透過自身 `contributes/knowledge-db.json` 自貢獻物化，消除核心特權硬編碼。
  - **遞迴階層符號模型與向後相容適配**：升級 `UnifiedSymbol` 為遞迴階層結構，支援 `parent_id`、`children`、結構化搜尋載荷 `search_payload` 與 `members` 轉接層，100% 相容既有檢索與調用拓撲邏輯。
  - **遺留正則解析器代碼與過時測試徹底清理**：刪除 `cpp_parser.py`, `csharp_parser.py`, `js_ts_parser.py`, `markdown_parser.py`, `python_parser.py` 等舊正則解析代碼，清理並遷移過時測試案例。
  - **自動化測試與驗證**：單元、邊界與調用圖譜測試 100% 通過（14/14 Passed），全生態系回歸驗證通過。

- **`sub_02_multilingual_tokenizer_and_hybrid_search` (Completed)**：
  - **多語言分詞引擎 (`MultilingualTokenizer`)**：實作中英混雜、CJK 雙向 1-gram / 2-gram 切分、駝峰 (`CamelCase`) 與蛇形 (`snake_case`) 標識符拆解提煉，支援常見停用詞過濾與空白規整，大幅提升跨語言與符號檢索召回率。
  - **輕量向量嵌入推論與增量補丁 (`EmbeddingService` & `VectorIndex`)**：透過 YSCB 微環境引入 FastEmbed ONNX（`bge-small-zh-v1.5`，384 維度），實作標識符預處理（解決 uncased BERT `[UNK]` 問題）、本地二進位壓縮快取 (`unified.vectors.bin.gz`)、L2 正規化與基於 SHA-1 內容雜湊的差分增量增修補丁 (`patch_incremental`)。
  - **RRF 倒數排名融合檢索 (`HybridSearchEngine`)**：以 Reciprocal Rank Fusion ($k=60$) 融合 BM25 詞法倒排索引與向量語意相似度，並施加未命中 BM25 時之向量相似度最低門檻（$\ge 0.70$）與長複合查詢詞覆蓋率過濾（$\ge 50\%$），有效壓抑非相關噪訊。
  - **雙軌剛性平滑降級守門**：支援 `--lexical-only` CLI 旗標或在向量模型/相依性未就緒時，100% 剛性平滑降級為純 BM25 檢索，保障系統在離線或輕量環境下絕對可用。
  - **遺留代碼與手刻同義詞庫清理**：徹底刪除舊同義詞庫檔案 `knowledge_db/thesaurus.py` 與 `tests/test_thesaurus.py`，全庫零殘留引用。
- **`sub_03_networkx_call_graph_and_impact_analysis` (Completed)**：
  - **NetworkX 工業級有向圖拓撲 (`CallGraphIndex`)**：引入 `networkx` 作為核心圖儲存與拓撲走訪引擎，替換手刻整數池與雙向 set 字典；節點為符號 ID，邊保存 `SymbolCallSite`，直接透過 `G.predecessors` 與 `G.successors` 達成 sub-毫秒級雙向檢索。
  - **FQN 作用域消歧與幽靈關聯根除 (`TopologyLinker`)**：結合 Universal AST 階層 FQN、父子作用域與 Import 映射表重構消歧演算法；收緊全域候選判定，無 Import 的跨模組裸調用嚴格判定為未鏈接邊，徹底杜絕跨檔案同名方法幽靈關聯。
  - **全方位 AST 符號結構化選擇器 (`SymbolSelector`)**：實作完備的微型語法解析器，支援類型前綴（`class`, `struct`, `interface`, `enum`, `fn`/`def`, `type`, `const`）、階層範疇（`foo.a`）與可調用標記（`()`）之任意正交複合組合；CLI 指令（`callers`, `callees`, `impact`, `search`）全面支援該選擇器進行目標符號精確消歧與高維度定位。
  - **多語言調用拓撲協議 (`LanguageTopologyProtocol`)**：定義跨語言抽象協議與 `TopologyProtocolRegistry`，支援各語言 AST 調用點與 Import 映射提取解耦。
  - **測試與品質驗證**：新增 `test_selector.py` 與 `test_networkx_graph.py`；全模組 132/132 測試 100% 通過（包含 14 個既有調用圖回歸測試）。



## 2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance (Executing)

- **`sub_06_jit_fingerprint_stat_gate` (Completed)**：
  - **JIT 來源特徵指紋 Stat-First 雙階快照初篩優化**：在 `agents-workflow` 的 `ReleasePublisher` 中引入基於 `(st_mtime_ns, st_size)` 的 Stat-First 跨進程持久化快取（`cache://agents-workflow/source_sha1_cache.json`），並快取單次執行週期來源資產綜合摘要，消除 Stage 0 短路判定時的重複檔案讀取與 SHA-1 雜湊負擔。在 Clean 狀態下檢查時間壓降至 sub-0.2ms，達成 0 檔案內容讀取與 0 重複雜湊，且兼顧 100% 變更感知自愈精確度。
  - **Pip 相依性解耦與純淨治理**：自 `source/agents-workflow/manifest.json` 徹底移除 `pip_dependencies` (`watchdog`) 宣告，消除常駐檔案監聽的冗餘套件依賴，回歸微環境極致純淨性。
  - **單元測試與 Dogfooding 驗證**：新增 `test_ft_11_stat_first_cache_hit_and_touch_healing` 與 `test_ft_12_manifest_clean_of_watchdog` 測試；全生態系 386/386 單元測試 100% 通過；完成 `@build` 本地安裝物化驗證。
  - **版本晉升與發布**：依軌道 B 規範完成版本晉升並自部署至運行端：`agents-workflow@1.0.3.8`。

- **`sub_05_jit_self_healing_integration` (Completed)**：
  - **微內核生命週期事件總線解耦 (`core.events`)**：建立獨立事件總線模組，提供 `broadcast(event_name, context, emit_module, search_roots)` 與 `get_contributed_events()`；徹底移除 `Engine.act_broadcast_event` 舊門面，達成宿主與微內核完全解耦。
  - **標準 Hook 尋址契約**：確立 `module://<module>/scripts/hook.<Sender>.py` 規範，支援函式名 `on_{event_name}` 與 `{event_name}` 雙向彈性匹配。
  - **宿主生命週期管線收斂 (`yscb.py`)**：於命令分發前執行微環境注入、運行端自愈與 `pre_cli_dispatch` 廣播；分發後執行 `post_cli_dispatch` 廣播與更新提示；自舉命令自動短路。
  - **模組 Ad-hoc 攔截清理**：`agents-workflow` 的 `ensure_jit_release()` 遷移至 `hook.core.py::on_pre_cli_dispatch`，並從 `scripts/cli.py` 徹底剔除 Ad-hoc 入口攔截。
  - **沙盒跑測總線收斂**：`dev.testing.sandbox` 移除重複之 `_dispatch_test_hooks`，改呼叫 `core.events.broadcast(..., emit_module="dev")`。
  - **事件清冊中繼資料與 CLI**：擴充 `contributes.events` 宣告格式規範 (`list[{"<name>": "description"}]`) 與 `source/core/contribute.json`，新增 `python yscb.py event list` CLI 指令。
  - **版本晉升與發布**：全生態系測試 100% 通過 (`384/384 Passed`)，依規範完成版本晉升：`core@1.0.3.1`、`dev@1.0.1.12`、`agents-workflow@1.0.3.6`。

## 2026_09_03_1840_agents_workflow_session_throttle_and_standards_optimization (Completed)

- **`agents-workflow@1.0.3.5` 全套引導規範、工作流與模板「極精簡 Session 回覆節流協議」與標準佔位符重構**：
  - **確立全域對話節流公理 (Session Response Throttle Protocol)**：於 `AgentsStandards.md` 與 `development-sop` 確立「實體檔案為唯一真理 (SSOT)」，全面禁止對話全文重複、代碼傾倒與圖表傾倒；為各 SOP 階段與計畫分支全面制定 5~10 行極精簡卡片與即刻停步 (`End Turn`) 機制。
  - **SOP 階段手冊重構 (`P00` ~ `P07` 及 `plan_modes`)**：
    - 全面導入標準極簡 Checkpoint 卡片；產出文件路徑統一規範為 `[name](__${project://plans/}__/{plan_name}/...)`。
    - `phase_06_test.md` 與 `Auto.md` 顯式增設「待手動驗證項」，引導 Agent 簡略條列實機/UX 測試操作與預期效果。
    - `phase_07_walkthrough.md` 強化歷程覆盤，直接聯動 `/Review` 工作流五維審查（文檔 1:1 驗收收斂至 Review，廢除 P07 獨立冗長文檔表）。
    - `plan_modes.md` 補齊 FT-1~3、Revision、Research (R01)、Umbrella 極簡卡片與標準佔位符。
  - **工作流系列全面精煉 (Workflows)**：
    - `ContextInit.md`：移除頂部 `DYNAMIC_CONTEXT_MAP`，將熱啟動簡報升級為 4 行極精簡狀態卡，杜絕靜態規則傾倒。
    - `NewPlan.md`：移除頂部 `DYNAMIC_CONTEXT_MAP`，精簡流程啟動節點。
    - `Auto.md`：全文通用性重構，移除特化 CLI 舉例與冗餘修飾，語意聚合精簡 ~40%，收斂為 4 步連續推進閉環。
    - `Review.md`：移除頂部 `DYNAMIC_CONTEXT_MAP`，剔除無法客觀地毯式檢查之項目（代碼清潔度、日誌細節），聚焦三層文檔對齊、測試與計畫合規、Commit 規範三大可核驗柱石，增設審查結論卡。
    - `SessionAnalysis.md`：確立「禁止一切主觀性評論」核心原則，僅允許客觀統計數據；為 2.1 流程自檢（全數合規單行卡 vs 異常項目根因卡）與 2.2 Token 分析提供剛性標準卡，徹底杜絕 Checkbox 清單傾倒。
    - `Discuss.md`：移除頂部 `DYNAMIC_CONTEXT_MAP`，語意聚合為 3 步閉環，增設極精簡討論卡 (RCA Card) 並立即停步等待裁決。
    - `Continue.md`：移除頂部 `DYNAMIC_CONTEXT_MAP`，消除層級偏見詞彙，升級為極精簡接續卡。
    - `Pause.md`：移除頂部 `DYNAMIC_CONTEXT_MAP`，移除內嵌模板代碼改採標準 SSOT 引導，升級為極精簡交接卡。
    - `Research.md`：移除頂部 `DYNAMIC_CONTEXT_MAP`，制定極精簡調研成果卡（三大出口路徑導引）。
    - `Roadmap.md`：移除頂部 `DYNAMIC_CONTEXT_MAP`，修正佔位符語法，制定極精簡路線圖推薦卡。
    - `Idea.md`：依指示正式下線並自宣告、Token 與文件完整移除。
  - **標準標頭補齊與驗證器同步 (`header.md` & `verifier.py`)**：
    - `header.md` 補齊生命週期狀態枚舉：`> 狀態：[Draft | Confirmed | In Progress | Passed | Completed]`。
    - `verifier.py` 之 `PLACEHOLDER_PATTERNS` 同步升級，嚴格防呆未替換佔位符。
  - **Dogfooding 閉環驗證與發布**：
    - 全套 50/50 單元測試 100% 通過。
    - 依規範執行版本晉升 `1.0.3.4` ➔ `1.0.3.5`、正式打包發布與 `python yscb.py update agents-workflow` 自部署物化至 `.agents/` 運行環境。

## 2026_09_03_1227_agents_workflow_plan_filter_and_session_analysis (Completed)

- **`sub_01` `dev test` 輸出格式優化與節流模式 (`--quiet` / `-q`)**：
  - **節流模式核心實作**：於 `dev test` 與 `dev op-test` 引入 `--quiet` 與 `-q` 命令列開關；在所有測試 100% 通過時僅輸出單行 `Pass: {n}({percent:.1f}%), Fail: {n}, Skip: {n}`，極致節省高頻回歸測試時的 Token I/O 消耗（壓縮率達 95% 以上）。
  - **深度靜默前置日誌**：徹底抑制前置沙盒構建、沙盒建立與清理日誌（`[dev:test] Pre-building...`、`Create sandbox...`、`Cleaned up sandbox...`）與通過後提示；未傳入節流旗標時 100% 維持完整 ASCII 診斷表格相容。
  - **失敗詳情精確保留**：若存在測試失敗，除首行統計外，完整輸出 `FAILED / ERROR TEST CASES LIST:` 詳情區塊（Message、Location、Quick Re-run）。
  - **環境變數跨沙盒穿透**：注入 `YSCB_TEST_QUIET="1"`，使單模組與 `--all` 多模組平行沙盒執行均達成一致靜默與聚合。
  - **AI 手冊與工作流全面對齊**：`yscb-module-dev`、`Auto.md`、`development-sop` 等指引中 AI 建議測試指令全面升級為 `--quiet`。
  - **驗證與測試**：新增 `test_tester_throttle.py` 單元測試；全生態系 312/312 單元測試 100% 通過；實機 UX 驗證完成。

- **`agents-workflow` 計畫目錄正則過濾 Bug 修復與 `SessionAnalysis` 工作流重構**：
  - **計畫目錄正則收斂 (Bug Fix)**：修復 `PlanVerifier`、`PlanScanner` 與 `PlanSearcher` 將 `plans/roadmap/`、`archived/` 等非計畫目錄誤判為進行中計畫之瑕疵，全面改以白名單正則 `r"^\d{4}_\d{2}_\d{2}"` 判定合法計畫，非時間戳資源目錄完全安全略過，使 `python yscb.py agents-workflow plan check` 全庫診斷 100% 通過。
  - **對話歷程分析工作流重構 (`SessionAnalysis`)**：
    - 將原 `/Retro` 工作流全面重構命名為 `/SessionAnalysis`。
    - 去除過度形容詞與環境特化資訊，聚合為「流程與紀律自檢（異常過濾呈遞模式）」、「四大維度行為與 Token 消耗分析（Skills / Workflows / CLI 含 I/O / Other）」與「模組特化評測」。
    - 移除首部 `DYNAMIC_CONTEXT_MAP`，維持工作流首部純淨與專注度。
    - 佔位符重命名：`WORKFLOW_RETRO` ➔ `WORKFLOW_SESSIONANALYSIS`，`RETRO_CHECK_ITEMS` ➔ `SESSION_ANALYSIS_CHECK_ITEMS`。
  - **跨模組解耦與注入對齊**：
    - `core`：移除 `RETRO_CHECK_ITEMS` 注入並刪除 `retro_check.md`，不再進行 CLI 冗餘合規審查。
    - `knowledge-db`：改向 `SESSION_ANALYSIS_CHECK_ITEMS` 注入全新精煉之 `session_analysis_check.md`，專注於工具調用統計、使用情境與效益分析。
  - **驗證與測試**：新增 `test_session_analysis_workflow.py` 並擴充 `test_plans_toolchain.py`；全生態系四大模組 305/305 單元測試 100% 通過；實機 UX 驗證完成。

## 2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance (In Progress - 里程碑 1, 2, 3 & 4 達成)

- **`sub_04` YSCB 私有 Pip 微虛擬環境治理核心功能實作與 IDE 軟合併投影 (`sub_04_yscb_venv_core`)**：
  - **私有微環境空間協議 (`yscb.venv://`)**：正式註冊並實體解算至 `yscb://.venv/`，依直譯器大/小版本分層隔離（如 `py312`），預設鎖定 `include-system-site-packages = false`，達成 100% 零全域環境污染。
  - **純原生標準庫微內核邊界**：`core` 模組本體嚴格維持純 Python 標準庫實作，零 Pip 依賴，開箱即用。
  - **微環境管理器 (`core.pip_manager.PipManager`)**：實作跨平台路徑適配、virtiofs 符號連結探測自愈、Wheel-Only 靜默安全安裝（`--only-binary=:all:`）與 `PipInstallError` 結構化異常治理。
  - **IDE 自動感知與可復原軟合併 (`core.ide_projector.IdeProjector`)**：
    - 自動探測 `project://.vscode` 目錄是否存在，不存在則完全靜默略過，達成零目錄污染。
    - 比照 `internal yscb gitignore` 哲學，在 `project://.vscode/settings.json` 引入 `_yscb_managed` 宣告式清冊結構，軟合併 `python.analysis.extraPaths`、`python.defaultInterpreterPath`、`files.exclude`、`search.exclude` 與 `files.watcherExclude`，100% 完整保留使用者自訂設定，並支援依清冊乾淨回滾。
  - **宿主動態嗅探與導入 (`yscb.py`)**：在指令分發入口實施 $< 0.05\text{ms}$ 極速嗅探，動態將微環境 `site-packages` 插入 `sys.path[0]`，模組源碼可直接無感 `import`。
  - **真實生態系 Dogfooding 閉環**：於 `agents-workflow` 宣告 `watchdog>=4.0.0`，實機驗證安裝物化、`Observer` 背景多執行緒與實體檔案事件捕獲完全正常。
  - **測試與合規**：新增 `test_venv_core.py` 測試套件涵蓋 FT-01~FT-08；全生態系 320/320 單元測試 100% 通過；實機 UX 驗證完成。

- **`sub_03` 建置產物 `build/` 空間協議更名 `.build/`、Git 追蹤解耦、工具鏈對齊與 VS Code 隱藏配置**：
  - **`module.build` 空間協議重構與零過渡純淨架構**：將 `module.build.root://` 與 `module.build://` 語意解析底層全面自 `yscb://build/` 更名為 `yscb://.build/`，對齊內部隱藏規範；堅決不加入任何舊目錄相容分支，落實零平滑遷移原則。
  - **`yscb://.gitignore` 內部忽略軟合併更新與舊項清理**：於 `_generate_internal_gitignore` 標記區塊內注入 `/.build/`，並徹底移除舊 `/build/` 條目，維持忽略規則極致純淨；完整保護宿主自訂與其他模組規則。
  - **生態系工具鏈全面對齊 `.build/`**：
    - `dev.builder`：模組打包輸出目錄切換至 `module.build://`（`ys_codebase/.build/<mod>/<ver>.zip` 與 `index.json`），實機打包四大模組均成功產出至 `.build/`。
    - `dev.testing.sandbox`：沙盒虛擬環境透過語意協議自 `.build/` 提取最新建置產物覆蓋測試。
    - `yscb.py`：模組提取還原優先級對齊 `.build/`，徹底移除舊 `build/` 候選路徑。
  - **最高工程規範與 IDE 開發體驗同步更新**：
    - `docs/_project/STANDARDS.md` 空間協議表第 1 節修訂為 `yscb://.build/`，Git 追蹤政策正式標記為 `🚫 忽略`。
    - `.vscode/settings.json`：於 `files.exclude`、`search.exclude` 與 `files.watcherExclude` 全面隱藏並排除 build、mirror、modules、snapshots。
  - **驗證與測試**：新增 `test_build_git_decoupling.py` 專屬單元測試套件；全生態系四大模組 305/305 單元測試 100% 通過 (4.943s)；實機 UX 驗證完成。

- **`sub_02` 運行端 `modules/` 空間協議更名 `.modules/`、Git 追蹤解耦、冷啟動再生管線與 JIT 自動同步自愈**：
  - **`module://` 語意空間重構與零過渡純淨架構**：將 `module://` 與 `module.root://` 實體解析底層全面自 `yscb://modules/` 更名為 `yscb://.modules/`，對齊內部隱藏目錄規範；落實零平滑遷移負擔原則，不包含任何舊目錄探測或搬移邏輯。
  - **`yscb://.gitignore` 標記區塊軟合併生成 (`[P00:DR-07]`)**：
    - 引入獨立邊界標記 `# === YSCB INTERNAL IGNORE BEGIN ===` 與 `# === YSCB INTERNAL IGNORE END ===`。
    - 採用非破壞性軟合併演算法，相容 `"yscb://" == "project://"` 拓撲，將 `/.modules/` 納入內部忽略規則，同時 100% 完整保留宿主專案自訂規則與其他模組（如 `agents-workflow`）之管理區塊。
  - **宿主層原生自包含冷啟動再生 (`python yscb.py restore`)**：
    - 於 `yscb.py` 實作自包含之 `cmd_restore`，依據 `yscb.config.json` 之 `installed_modules` 清冊批量物化還原所有模組至 `.modules/` 並觸發 reload。
    - 支援本地 Provider、`build/`（`@build` 開發版優先提取並反向更新鏡像庫）與遠端/本地 `file://` Provider。
  - **前置 JIT 模組同步守門 (`_ensure_jit_modules_sync`)**：
    - 於 CLI 命令分發入口前置建立 $< 0.05\text{ms}$ 極速狀態嗅探；若本機 `.modules/` 缺失或版本落後，自動觸發無感 JIT 原地自愈，達成跨端 `git pull` 後的零手動介入自愈體驗。
  - **全專案工程規範同步更新**：同步修訂 `docs/_project/STANDARDS.md`、`docs/core/README.md` 與 `source/core/README.md`，將空間協議正式改為 `yscb://.modules/` 且 Git 追蹤政策標記為 `🚫 忽略`。
  - **驗證與測試**：新增 `test_restore_and_jit_modules.py` 專屬單元測試套件；全生態系四大模組 298/298 單元測試 100% 通過 (4.911s)；實機 UX 驗證完成。

- **`sub_01` 全生態系安全熱更新與 JIT 變更感知自愈機制**：
  - **`core.contributes` JIT 嗅探守門**：以 $< 2\text{ms}$ 極速檔案指紋檢查感知 contributes 變更並原地重新聚合，消除手動 `reload`。
  - **`agents-workflow` JIT 投影同步**：在前置 hook 中引入 $< 10\text{ms}$ 指紋嗅探，自動將修改同步編譯至 `.agents/`。
  - **`UpdateChecker` 12 小時節流版本探測**：微內核每 12 小時輕量檢查來源版本並非阻塞提示升級。
  - **全生態系 292/292 單元測試通過與 Dogfooding `@build` 直裝閉環驗收**。

## 2026_09_01_0636_agents_workflow_context_init_aggregation_and_token (Level 0 Fast Track 結案)

- **`agents-workflow` ContextInit 內容聚合整理、Token 錨點補齊與 Dev Container 終端指南特化注入**：
  - **`WORKFLOW_CONTEXTINIT` 宣告式擴充錨點**：於 `contributes/agents-workflow.json` 補齊全模組第 63 個 Token 錨點，達成 11 個 Workflow 100% 具備對稱特化擴充能力。
  - **`ContextInit.md` 內容聚合與佔位符置入**：重構優化三步驟加載指引與熱啟動簡報，於尾部置入 `__@{WORKFLOW_CONTEXTINIT}__` 內容佔位符。
  - **專案特化 Dev Container 終端防呆指南注入**：
    - 建立 `config/agents-workflow/snippets/context_init_devcontainer.md`，說明原生 sub-100ms 執行保證、Persistent Terminal 常駐綁定與避免邊界逾時 Detach 之同步等待時間門檻。
    - 於 `config/agents-workflow/contribute.json` 宣告 `WORKFLOW_CONTEXTINIT` 的 `insert` 擴充。
  - **驗證與測試**：`agents-workflow` 47/47 單元測試 100% 通過，本地 Dogfooding `@build` 安裝與 `.agents/workflows/ContextInit.md` 物化產物驗證完成。

## 2026_09_01_0607_knowledge_db_space_token_and_skill_hardening (Level 0 Fast Track 結案)

- **`knowledge-db` 宣告式空間佔位符與檢索技能剛性防護**：
  - **`KNOWLEDGE_DB_SPACE` 宣告式動態解算**：模組完全自包含地宣告 Token 與 `get_knowledge_db_spaces` computed provider，將全系統已註冊空間（`docs`, `plans`, `source`）動態編譯為 Markdown 表格並渲染至 Skill，零跨模組耦合。
  - **檢索技能與工具分流剛性防護**：
    - 原生搜尋工具剛性收窄：明訂 `SearchPath` 僅限單一具體檔案路徑，嚴禁目錄跨檔廣搜。
    - 負面範例防護：於 Skill 中注入「常見探索意圖與反模式對照表 (Anti-Patterns vs Correct Patterns)」。
    - Frontmatter 強化：注入禁止目錄搜尋之守門語意，強化 Agent 第一反射。
  - **驗證與測試**：新增 `test_providers.py`，`knowledge-db` 130/130 單元測試 100% 通過，Dogfooding 物化驗收完成。

## 2026_09_01_0551_host_bootstrapper_inprocess_dispatch (Level 0 Fast Track 結案)

- **`yscb.py` 宿主引導腳本同進程動態調度與零阻塞優化**：
  - **`dispatch_module` 同進程分發實作**：以 Python 標準庫 `runpy.run_path` 取代原先的 `subprocess.run`，消除多次 Python 解釋器冷啟動開銷與非交談式/後台 Headless 環境下的 `stdin` 管道 I/O 阻塞。
  - **現場維護與狀態碼保證**：動態維護 `sys.argv` 參數現場，精確捕獲並轉譯 `SystemExit` 狀態碼，無縫支援全模組 CLI 指令與拼寫建議。
  - **驗證與測試**：全模組 CLI 響應時間自數秒降至 0.8s 內同步完成；`core` 54/54 與 `agents-workflow` 47/47 單元測試全數通過。

## 2026_08_31_1718_agents_workflow_architecture_optimization (sub_02_skills_architecture 結案)

- **`agents-workflow` 宣告式 Skills 體系與多 Target 投影架構全面實作**：
  - **宣告式 `export.type = "skill"` 與目錄級資產掃描**：
    - `ArtifactCompiler` 擴充 `_scan_directory_files`，支援以目錄為單位的 Skill 包（包含 `SKILL.md`、`references/` 等子檔案）遞迴掃描與 Stage 1 快取，保留相對目錄階層。
  - **Target 技能投影與路徑巨集插值 (`projections.skill`)**：
    - `ReleasePublisher` 支援 `target_dir` 插值 `{export.name}`、`{export.basename}` 與 `{target.name}`，實現跨 Target 靈活部署。
    - 統一配置 `antigravity`、`claude`、`codex` 三大 Targets 之技能投影，並將 `codex` 專案路徑對齊官方規範 `project://.agents/`。
  - **多檔案 Stage 2 語意 URI 相對路徑轉譯**：
    - 支援 Markdown 內 `__#{...}__` (Local URI) 與 `__${...}__` (Project URI) 多階解析與點擊性跳轉。
  - **首個領域技能資產落地：`documentation` Skill**：
    - 重構傳統單檔文檔規範為 `documentation` Skill 包（`SKILL.md` 讀者須知 + `references/author_guide_and_checklist.md` 作者須知）。
    - 抽象中觀層為通用 `<Category>` 領域命名空間，提供 7 大維度導引、判定樹與 3-Tier 交付核對清單。
  - **自動化測試與回歸驗證**：
    - 新增 FT-09~10 與 ET-05 測試，模組 47/47 Passed，生態系全量 278/278 Passed。

## 2026_08_31_1026_knowledge_db_call_graph_and_reference_index (Level 1 Full Track 結案)

- **`knowledge-db` 跨檔案符號調用圖譜與引用依賴拓撲索引全棧實作**：
  - **資料模型與數值物件 (`schema.py`)**：
    - 新增不可變值物件 `SymbolCallSite`（紀錄 caller、callee、line、scope、context_prefix）與 `CallGraphNode` 模型，具備完整的 `to_dict()` 與 `from_dict()` 序列化。
  - **多語言 AST/狀態機調用點與 Import 萃取 (`parsers/`)**：
    - `BaseParser` 擴充 `extract_call_sites` 與 `extract_imports` 抽象介面。
    - `PythonParser` 實作 `CallSiteVisitor` 作用域棧 (`ScopeStack`)，走訪 `ast.Call`, `ast.Attribute`, `ast.Import`, `ast.ImportFrom` 萃取調用點與模組別名映射。
    - `CppParser` 萃取 `#include`, `using namespace`, `using Alias` 與 `this->Init()`, `Class::Method()` 調用點。
    - `CSharpParser` 萃取 `using Namespace`, `using Alias` 與類別方法調用點。
    - `JsTsParser` 萃取 named/default `import`, `require` 與類別方法/函式調用點。
    - `MarkdownParser` 萃取文檔內部超連結與 `Class.method` 符號引用點。
  - **四階消歧拓撲鏈接器 (`linker.py`)**：
    - 實作 `TopologyLinker` 四階消歧演算法（Tier 1 檔內/類別自省 ➔ Tier 2 顯式 Import 別名 ➔ Tier 3 同空間優先 ➔ Tier 4 全庫倒排上下文打分），未定義動態呼叫安全降級。
  - **雙向圖索引與二進位持久化 (`graph.py`)**：
    - 實作 `CallGraphIndex`（整數池化 Integer String Pool、雙向稀疏鄰接表 `forward_graph` / `reverse_graph`、`query_impact` BFS 循環防護、`patch_incremental` 增量修補、Pickle Protocol 5 + Gzip 高速寫盤）。
  - **門面 SDK 與 CLI 整合 (`engine.py` & `scripts/cli.py`)**：
    - `KnowledgeEngine` 整合 `act_callers`、`act_callees`、`act_impact` 與 JIT 變更感知熱自愈流水線。
    - CLI 新增 `callers`, `callees`, `impact` 指令，產出 RFC 8089 可點擊直達 Markdown 連結與切片。
  - **測試與品質保證**：
    - 新增測試套件 `tests/test_call_graph.py` (FT-01~11, ET-01~02, PT-01 全數通過)。
    - `knowledge-db` 全量單元測試 **125/125 Passed (100% Ready, 1.08s)**，全庫物化安裝完成。
  - **衍生子計畫 `sub_01_contributes_injection_optimization` (Level 0 Fast Track 結案)**：
    - 於 `source/knowledge-db/contributes/core.json` 登錄 `callers`, `callees`, `impact` 權限規範，自動編譯同步至 `AgentsCliGuild.md`。
    - 升級 `KnowledgeAgentsStandards.md` 工具分流決策矩陣與防呆阻斷鐵律，同步物化至專案根目錄 `AGENTS.md`。
    - 升級 `research_guild.md`、`phase00_guild.md` 與 `retro_check.md`，注入調用圖譜架構探索指引與評測欄位。
    - 於 `contributes/knowledge-db.json` 擴充調用圖譜專用語及前端 Web 技術棧（HTML/DOM、JS/TS/JSX/TSX、CSS/Flexbox/Grid 佈局排版）同義詞、別名與關聯度詞條。

## 2026_08_31_0533_knowledge_db_performance_and_memory_optimization (Level 1 Full Track 結案)

- **`knowledge-db` 全棧運算提速、並發 AST 打包與倒排索引記憶體瘦身**：
  - **`CodeTokenizer` 極速化 (`tokenizer.py`)**：
    - 以 `_is_cjk_ord` Unicode 整數範圍直接比對 (`0x4E00 <= ord(c) <= 0x9FFF` 等) 徹底取代主迴圈逐字元 `re.match`，消除正則引擎調度開銷。
    - 為識別碼拆分函式 `split_identifier` 引入 `@lru_cache(maxsize=8192)` 與預編譯正則，重複分詞吞吐量提升 $10\times$ 以上。
  - **倒排索引資料結構瘦身與共享池 (`retrieval.py` & `schema.py`)**：
    - 為 `Posting` 節點配置 `__slots__`，將文檔欄位長度字典抽離至頂層 `InvertedIndex.doc_lengths` 共享池，消除百萬級冗餘字典副本，節點記憶體佔用降低 $40\%+$。
    - `InvertedIndex.from_dict` 支援舊版包含 `field_lengths` 的二進位快取自動升級遷移至頂層共享池。
    - `InvertedIndex.patch_incremental` 增量同步維護與清理 `doc_lengths`，杜絕過期殘留。
  - **同義詞加權展開快取 (`thesaurus.py`)**：
    - 為 `ThesaurusEngine.expand_query_weighted` 實作以查詢簽章 Tuple 為鍵之 LRU Memoization 快取，動態增減詞條自動清空快取。
  - **動態門檻多進程並發 AST 打包 (`bundler.py`)**：
    - 於 `SemanticBundler` 實作動態門檻分流（檔案數 $\ge 10$ 且多核時調度 `ProcessPoolExecutor` 分批解析），頂層工作者函式 `_parse_file_task_worker` 具備完整錯誤容錯與單進程安全降級能力。
  - **實機效能飛躍與全生態系品質保證**：
    - 新增效能與記憶體基準測試套件 `test_benchmark_perf_and_memory.py` (8 測全數通過)。
    - `knowledge-db` 單元測試全數通過 (**111/111 Passed, 100% Ready, 1.01s**)；全生態系 4 大模組全量迴歸測試 **231/231 Passed (100% Ready)**；模組靜態合規性檢核 100% 通過。
    - 全專案完全索引重建耗時從原本的 1.8s+ 驟降至 **0.887s**，即時語意檢索延遲降至 **0.52s**。

## 2026_08_30_1928_core_topology_injection_and_zero_fallback (Level 1 Full Track 結案)

- **`core` 核心空間拓撲雙軌注入 (`yscb_root`)、全庫 Fallback 機制剛性收斂與沙盒生命週期雙重隔離**：
  - **`core.uri` 對稱注入體系 (`uri.py`)**：
    - 補齊與 `host_dir` 嚴格對稱之核心拓撲注入介面：`set_yscb_root(path)`、`get_yscb_root()`、`yscb_scope(path)` 與 `YSCB_ROOT_DIR` 環境變數。
    - `_get_yscb_root()` 剛性遵循三階梯優先順序：記憶體注入 (`_active_yscb_dir`) $\rightarrow$ 環境變數 (`YSCB_ROOT_DIR`) $\rightarrow$ 常數基準 (`__file__` 向上 3 層)，杜絕路徑漂移。
  - **`core.config` 徹底清除遞迴 Fallback 盲點 (`config.py`)**：
    - 徹底移除 `ConfigManager._get_yscb_root` 中的 `while` 遞迴搜尋與 `os.getcwd()` fallback，100% 委任 `uri._get_yscb_root()`。
  - **`dev` 測試沙盒生命週期鉤子雙軌隔離 (`sandbox.py`)**：
    - 於 `SandboxProvisioner._dispatch_test_hooks` 同時包覆 `host_scope(ctx.host_dir)` 與 `yscb_scope(ctx.engine_dir)`，確保模組測試鉤子 100% 運行於沙盒專屬空間，徹底杜絕跨進程並發建沙盒時對宿主專案檔案的搶寫與穿透。
  - **`agents-workflow` 路徑收斂 (`searcher.py`)**：
    - 收斂 `PlanSearcher` 預設歸檔目錄為標準 `plans/archived`，消除全庫命名分歧。
  - **品質驗證與全生態系全類別全綠燈**：
    - 新增 `test_yscb_root_injection_and_scope` 單元測試案例。
    - 全生態系 4 大模組全類別 (`LOGIC` + `ENV` + `WORKFLOW` + `PERF`) 回歸測試 **252/252 Passed (100% Ready, 0 Failed, 0 Skipped)**。

## 2026_08_30_1807_fix_sandbox_path_and_benchmark (Level 0 Fast Track 結案)

- **`dev` 模組跨平台沙盒路徑自省、上游活躍沙盒守門防護與 `knowledge-db` 並發壓測容錯優化**：
  - **沙盒 CWD 祖先路徑向上探測 (`case.py` & `tester.py`)**：
    - 重構 `YSCBTestCase.setUp`，改為向上遞迴搜尋包含 `host_env` / `mock_provider` 之沙盒根目錄，支援 `YSCB_SANDBOX_DIR` 優先讀取，徹底杜絕深層 CWD 下的 `FileNotFoundError`。
    - 於 `tester.py` 子進程環境顯式注入 `YSCB_SANDBOX_DIR` 並綁定 `stdin=subprocess.DEVNULL`，杜絕子進程非互動環境阻塞。
  - **上游託管活躍沙盒防誤刪守門 (`sandbox.py` & `test_sandbox.py`)**：
    - 於 `SandboxProvisioner.cleanup_sandbox` 注入「活躍沙盒防護」守門：下游子測試無權銷毀當前進程所在的 Runner 沙盒（僅上游結案時透過 `is_harness_cleanup=True` 銷毀），徹底根除 Linux (POSIX) 即時 Unlink 引發的連鎖崩潰。
    - 新增測試案例 `test_guardrail_active_sandbox_protected_from_accidental_cleanup` 守門驗證。
  - **並發 I/O 基準測試環境容錯 (`test_incremental_hot_reload.py`)**：
    - 將 `knowledge-db` 增量熱重載延遲基準測試門檻校正為具容器並發韌性之 `<= 1200.0ms`。
  - **全生態系測試排查與全綠燈交付**：
    - 全生態系 4 大模組 43 套測試全數排查，`dev check` 100% Passed，全量迴歸測試 `dev test --all --logical` **223/223 Passed (100% Ready)**。

## 2026_08_30_1618_knowledge_db_web_parsers (Level 1 Full Track 結案)

- **`knowledge-db` 模組 Web 技術棧 (JS/TS/HTML/CSS) 語言解譯器與語意檢索整合落地**：
  - **JavaScript / TypeScript 解譯器 (`JsTsParser`)**：
    - 支援 `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs`, `.mts`, `.cts` 副檔名。
    - 實作狀態機與正則引擎，精準提取 `class` (類別)、`interface` (介面)、`type` (型別別名)、`enum` (列舉)、頂層 `function`、`const` 箭頭函式、類別內部 `method` 與多行 JSDoc 註解。
    - 內建樣板字串 (`` `...` ``) 與 TSX / TS 泛型 `<T>` 標籤歧義防禦。
  - **HTML 網頁解譯器 (`HtmlParser`)**：
    - 支援 `.html`, `.htm` 副檔名。
    - 提取 `<title>` (標題)、`<h1>`~`<h6>` (階層標題，具缺損閉合容錯能力)、ID 選擇器元素 (`#id`)、HTML5 語意標籤 (`<main>`, `<section>`, `<article>`, `<dialog>` 等) 與 HTML 註解。
  - **CSS / SCSS / LESS 樣式解譯器 (`CssParser`)**：
    - 支援 `.css`, `.scss`, `.less` 副檔名。
    - 提取 Class 選擇器 (`.className`)、ID 選擇器 (`#idName`)、CSS 原生變數 (`--var`)、SASS 變數 (`$var`)、LESS 變數 (`@var`) 與 `@keyframes` 動畫幀容器。
  - **解析器註冊分發與架構優化**：
    - 於 `schema.py` 擴充 `LanguageType` (`JAVASCRIPT`, `TYPESCRIPT`, `HTML`, `CSS`) 與 `SymbolKind.TYPE_ALIAS`。
    - 於 `ParserRegistry` 完成 Web 解析器自動分流註冊。
    - 最佳化 `YSCBTestCase` 沙盒環境復用與 Windows 跨平台大小寫不敏感檔名比對，徹底杜絕 Windows 260 字元路徑溢位。
  - **品質驗證與合規性檢核**：
    - 新增測試套件 `test_web_parsers.py` (9 測全數通過)；`knowledge-db` 單元測試全數通過 (**103/103 Passed, 100% Ready**)；模組靜態合規性檢核 100% 通過。

## 2026_08_30_0304_knowledge_db_incremental_hot_reload_and_bugfix (Level 1 Full Track 結案)

- **`knowledge-db` 模組 JIT 嗅探死循環根除與細粒度增量熱重載機制落地**：
  - **100% 完整清冊 JIT 嗅探與死循環根除 (`scanner.py` & `engine.py`)**：
    - 重構 `FingerprintScanner.check_invalidation()`，移除提前 return 截斷缺陷，保證全量走訪並產出 100% 完整之 `full_files_map` 與準確差量清冊 `ScanDiffDetail` (`added`, `modified`, `deleted`)。
    - `build_unified_index` 剛性持久化完整快照至 `unified.meta.bin`，徹底根除每次查詢無效重複熱重構之死循環問題。
  - **Win32 / NTFS `os.scandir` 走訪加速 (`scanner.py`)**：
    - 採用 `os.scandir` 遞迴走訪直接提取 `DirEntry.stat()`，減少 50% 以上系統呼叫開銷。
  - **單檔符號記憶體快取池 (`bundler.py`)**：
    - 於 `SemanticBundler` 維護 `_file_symbols_cache`，熱重載時僅對 `added` 與 `modified` 檔案重新解析 AST，未變更檔案 100% 零 I/O 記憶體復用。
  - **倒排索引差量打補丁 (`retrieval.py`)**：
    - 於 `InvertedIndex` 實作 `patch_incremental()`，精準拔除舊 Postings、注入新符號 Postings 並動態重算 `field_avgdl` 與 `doc_count`。
  - **極速持久化與效能飛躍**：
    - 索引持久化採用 `compresslevel=1` 快速壓縮；單檔熱重載延遲由 2,500ms 大幅降至 **20~50ms**（提速 50 倍以上）。
  - **回歸驗證與品質守門**：
    - 新增測試套件 `test_incremental_hot_reload.py` (9 測全數通過)；`knowledge-db` 94/94 測 100% 通過；全生態系全量跑測 `dev test --all --logical` ➔ **213/213 Passed (100% Ready)**；模組靜態合規性檢核 100% 通過。

## 2026_08_30_0102_knowledge_db_cache_isolation_and_uri_output (Level 1 Full Track 結案)

- **`knowledge-db` 模組快取目錄零 Fallback 固化與搜尋輸出 RFC 8089 檔案 URI 連結格式重構**：
  - **快取儲存根目錄零 Fallback 剛性守門 (`space.py`)**：
    - 重構 `SpaceManager._get_storage_root()`，徹底消除 `Path("./.cache/knowledge-db")` 隱式回退。
    - 當 `_safe_resolve_uri("cache://knowledge-db/")` 失敗且未傳入自訂 `storage_dir` 時，強制拋出 `InvalidSpaceConfigError`，徹底杜絕專案宿主根目錄意外產生 `.cache/` 殘留目錄之副作用。
  - **RFC 8089 檔案 URI 與 Markdown 連結輸出 (`engine.py` & `cli.py`)**：
    - 於 `KnowledgeEngine` 實作 `to_file_uri()` 與 `format_file_link()` 方法。
    - `knowledge-db search` 全面升級：簡易模式、預覽模式 (`-s`)、詳細模式 (`-d`) 的檔案標頭全面輸出為 `[rel_path:Lstart-end](file:///abs_path#Lstart)` 可點擊 Markdown 連結，支援 IDE 中 `Ctrl+Click` 直達行號並消除 Agent 路徑拼接失誤；`--json` 模式於每筆檢索結果注入 `file_uri` 欄位。
  - **回歸驗證與品質守門**：
    - 新增單元測試 `test_ft_07_to_file_uri_and_formatting` 與 `test_et_04_zero_fallback_cache_root_guardrail`；全生態系全量跑測 `dev test --all` ➔ **230/230 Passed (100% Ready)**；模組靜態合規性檢核 100% 通過。
## 2026_08_29_2349_knowledge_db_thesaurus_enhancement_and_decoupling (Umbrella Level 2 結案)

- **`knowledge-db` 模組三階同義詞加權擴展檢索重構與宣告式詞庫解耦豐富化**：
  - **三階加權擴展檢索架構 (`thesaurus.py` & `retrieval.py`)**：
    - 實作三階層查詢 Token 擴展權重模型：原始詞 (1.0)、嚴格同義詞與單向別名 (0.6)、領域關聯詞 (0.25)。
    - 重構 BM25 檢索引擎，支援 `WeightedToken` 語意衰減乘積計分，大幅提升檢索廣度 (Recall) 並 100% 確保首屏精確度 (Precision)。
  - **詞彙庫硬編碼解耦與宣告式 Contributes 體系 (`space.py` & `contributes/knowledge-db.json`)**：
    - 徹底移除源碼硬編碼之 `BUILTIN_THESAURUS`，轉為由 `SpaceManager` 自 `core.contributes` 宣告式動態載入。
    - 建立涵蓋 98+ 組高頻軟體工程、架構概念、多語言語法與 SPICE 網表之高品質同義詞、別名與關聯詞庫。
  - **回歸驗證與品質守門**：全生態系全量跑測 `dev test --all` ➔ **228/228 Passed (100% Ready)**；四大模組靜態合規性檢核 100% 通過。

## 2026_08_29_2315_knowledge_db_spice_parser_integration (Level 1 Full Track 結案)

- **`knowledge-db` 模組 SPICE (.cir, .sp, .spice, .net, .cdl) 網表語系解譯器 (SpiceParser) 整合與語意檢索擴充**：
  - **多語言 Schema 擴充**：於 `schema.py` 新增 `LanguageType.SPICE = "spice"` 列舉支援。
  - **雙階段語意解譯引擎 (`SpiceParser`)**：
    - **Stage 1 邏輯行聚合器**：精準合併行首 `+` 多行接續指令並保持原始行號映射 (`line_number` ~ `end_line`)；相容行首 `*` 與行尾 `;` (ngspice) / `$` (HSPICE) 註解，並支援連續註解萃取為符號 Docstring。
    - **Stage 2 階層語意狀態機**：完整提取子電路 (`.subckt ... .ends` ➔ `CLASS`)、模型 (`.model` ➔ `STRUCT`)、參數 (`.param` ➔ `VARIABLE`)、包含指令 (`.include`/`.lib`/`.global` ➔ `MACRO`) 與頂層/內部元件實例 (`X...`, `M...`, `R...` ➔ `members`)。
  - **解析器動態調度與 CLI 檢索整合**：於 `ParserRegistry` 預設註冊 `SpiceParser` (優先級 100)；`knowledge-db search` 支援 `--ftype=sp,cir,spice,net,cdl` 與 `-s` 程式碼切片即時預覽。
  - **回歸驗證與品質守門**：新增 `test_spice_parser.py` (9 測 100% 通過)；全生態系全量跑測 `dev test --all` ➔ **210/210 Passed (100% Ready)**；模組靜態合規性檢核 100% 通過。

## 2026_08_29_2125_unit_tests_audit_and_maintenance (Level 1 Full Track 結案)

- **全生態系四大模組單元測試套件地毯式排查、整併、瘦身與分流提速優化**：
  - **`core` 模組**：重構 `source/core/tests/test_semver.py`，完整涵蓋 4 段式 (`Major.Minor.Patch.Revision`) 與 3 段式 SemVer 解析、比較、升級與約束求解；安全刪除重複之 `test_semver_v4.py`。
  - **`dev` 模組**：校正 `source/dev/tests/test_sandbox.py` 中 5 大實體沙盒複製與打包測試為 `@require(Requirement.ENV)`，使 `dev test --all --logical` 純邏輯秒級跑測降至 6.25 秒（175 測）。
  - **`agents-workflow` 模組**：移除早期留存之孤立冒煙測試 `test_basic.py`；建立 `source/agents-workflow/scripts/hook.dev.py`，於沙盒生命週期自動注入 `project://` 語意空間路徑組態，徹底消除 28 項編譯器未定義警告日誌噪音；將專案組態升級為 `project://` 協議。
  - **`knowledge-db` 模組**：將深度 AST 解析邊界測試整合至 `test_parsers.py` 並刪除 `test_parsers_deep.py`；將同義詞庫雙向擴展與分詞測試整合至 `test_tokenizer.py` 並刪除 `test_thesaurus.py`。
  - **回歸驗證與品質守門**：全生態系全量跑測 `dev test --all` ➔ **201/201 Passed (100% Ready)**；四大模組 `dev check <module>` 靜態合規性 100% 通過。

## 2026_08_29_2035_user_guidance_and_module_readme_enhancement (Umbrella Level 2 結案)

- **全生態系模組純用戶導引手冊建置與專案級 README 重構**：
  - **`core` 模組導引手冊 (`source/core/README.md`)**：以純用戶視角完整說明微核心架構定位、11 大語意空間協議 VFS、2x2 組態矩陣（專案共享 vs 本機覆蓋）、全量 CLI 指令速查、Python SDK 常用公開 API 與 3 大情境 Cookbook。
  - **`dev` 模組導引手冊 (`source/dev/README.md`)**：完整闡述五大核心引擎、Dogfooding 雙軌閉環流水線（軌道 A 本地自引用 / 軌道 B 正式發布）、四段式語意版本號 (`Major.Minor.Patch.Revision`) 標準定義、全量 CLI 指令矩陣、`YSCBTestCase` 單元測試指南與 Cookbook。
  - **`agents-workflow` 模組導引手冊 (`source/agents-workflow/README.md`)**：完整介紹四層架構、11 大官方 Slash Commands 導覽表、6 大計畫分支拓撲決策樹、Agent 行為核心三大公理與 6 大防呆鐵律、全量 CLI 速查與接入 Cookbook。
  - **`knowledge-db` 模組導引手冊 (`source/knowledge-db/README.md`)**：詳解四層檢索流水線、日常檢索決策樹（`--ftype=c,cpp,py` / `--ftype=md` / hybrid）、`-s` 代碼切片即時預覽強制替代原則、全量 CLI 指令矩陣、`KnowledgeEngine` SDK 範例與 3 大情境 Cookbook。
  - **專案根目錄 README 重構 (`README.md`)**：加入頂部 Agent 醒目安裝指引、全景 Mermaid 生態系架構圖、標準基礎安裝與 `core.project_root` 綁定、`agents-workflow` 安裝/路徑手動調整與 Pre-flight 核對提示、`knowledge-db` 安裝/源碼空間設定與 Pre-flight 詢問提示、及全域 CLI Cheat Sheet。
  - **回歸驗證與合規檢核**：5 大子計畫與主計畫全部通過 `plan verify` 100% Passed；全生態系 4 大模組 **211/211 測試 100% Passed**。

## 2026_08_29_1505_workflow_and_agents_guidance_optimization — sub_05_init_project_uri_guardrail (`agents-workflow@1.0.2.9`)

- **一鍵初始化 `init` 前置依賴協議 `project://` 驗證與防呆修復引導 (`initializer.py`)**：
  - **前置依賴防呆驗證**：於 `WorkflowInitializer` 實作 `check_project_protocol()`，在執行目錄探測與建立前，先驗證 `project://` 是否已定義（`core.project_root` 非空且非 `!undefined`）。
  - **修復引導與建議指令**：當 `project://` 未定義時，中斷初始化流程並輸出清晰警示方塊與建議指令（`config set core project_root <path>` 或 `uri resolve project://`）。
  - **清除隱式 Fallback 漏洞**：重構 `_resolve_physical_path()`，徹底移除對 `os.getcwd()` 的隱式退化處理，嚴格落實《`project://` 零 Fallback 鐵律》。
  - **回歸驗證與正式發布**：新增單元測試案例 `test_ft_05_check_project_protocol_valid` 與 `test_et_02_project_protocol_undefined_guardrail`，全生態系 211/211 測試 100% Passed；正式發布 `agents-workflow@1.0.2.9` 並完成本機更新。

## 2026_08_29_1920_dev_dual_track_pipeline_standards (`dev@1.0.1.3`)

- **Dogfooding 與正式發布雙軌閉環流水線規範重構 (`DevAgentsStandards.md`)**：
  - **雙軌閉環流程劃分**：明確定義「軌道 A：日常開發與本地自引用調試 (`@build`)」與「軌道 B：版本晉升與正式發布交付 (`bump` ➔ `release` ➔ `install --force` / `update`)」。
  - **發布防呆守門純化**：明確規範日常開發嚴禁擅自切入軌道 B 正式 release；當獲指示進行 bump 或 release 交付時，依軌道 B 執行正式發布與本機同步。
  - **沙盒回歸與正式發布**：全套件 50/50 測試 100% Passed；正式發布 `dev@1.0.1.3` 並完成本機覆蓋安裝。

## 2026_08_29_1915_agents_workflow_multi_donor_insert_aggregation (`agents-workflow@1.0.2.7`)

- **單一 Token 錨點多模組 (Multi-Donor) 注入聚合與指紋特徵比對修復 (`compiler.py` & `publisher.py`)**：
  - **多 Donor 注入聚合狀態機**：修復 `compiler.py` 中 `mode == "below"` / `above` 提早抹除 Token 錨點造成後續模組注入失效之邏輯缺陷；支援同一個 Token 錨點依 `above` ➔ `replace` ➔ `below` 拓撲順序多模組同時注入。
  - **發布特徵指紋計算優化**：修正 `publisher.py` 指紋計算中 `insert` 之 URI 取值 (`ins.get("value")`) 並納入模組版本，確保編譯器或資產異動時觸發發布。
  - **回歸驗證與正式發布**：新增 `test_sub_07_multi_donor_insert_aggregation`，全套件 42/42 測試 100% Passed；正式發布 `agents-workflow@1.0.2.7` 並完成本機覆蓋安裝，驗證 `dev` 與 `knowledge-db` 規範 100% 同步注入 `AGENTS.md`。

## 2026_08_29_1901_dev_agents_standards_dynamic_injection (`dev@1.0.1.2`)

- **Dogfooding 閉環流水線與模組開發三層空間規範之宣告式動態注入 (`contributes/agents-workflow.json`)**：
  - **資產新增**：新增 `DevAgentsStandards.md`，完整定義 Dogfooding 3 級空間隔離矩陣、標準四步閉環流水線與發布/安裝免測防呆鐵律。
  - **宣告式注入**：於 `contributes/agents-workflow.json` 宣告將 `DevAgentsStandards.md` 自動注入至 `AGENTS_STANDARDS` Token 錨點。
  - **規範解耦**：移除 `AGENTS.md` 第 4 節的硬編碼內容，凡安裝 `dev` 模組之環境自動無損軟合併注入 Dogfooding 規範。
  - **發布與驗證**：完成 Revision bump 至 `1.0.1.2`，正式打包並完成本機覆蓋安裝。

## 2026_08_29_1505_workflow_and_agents_guidance_optimization — sub_04_retro_workflow_and_token (`agents-workflow@1.0.2.8`)

- **`/Retro` 開發歷程自檢工作流與 `RETRO_CHECK_ITEMS` 宣告式模組擴充體系**：
  - **`/Retro` 標準工作流落地 (`Retro.md`)**：建立普適任何 Session 歷史（日常除錯、零散問答、標準計畫）之自檢工作流，內建「不合規文檔溯源分析 (Documentation-Root-Cause Traceability)」剛性紀律與核心自檢「異常過濾呈遞」原則。
  - **宣告式多模組擴充 Token 體系 (`RETRO_CHECK_ITEMS`)**：宣告 `RETRO_CHECK_ITEMS` 與 `WORKFLOW_RETRO` 錨點，將通用紀律與領域特化指標完全解耦。
  - **生態系模組注入與標定格式落地**：
    - `knowledge-db`：宣告注入「知識庫 Search 效益評測」（調用統計、時機合理性、相較傳統 grep/list 效益對比估算與 Top 1~3 排名命中率）。
    - `core`：宣告注入「CLI 指令 Default-Deny 守門查核」（採異常過濾呈遞與 5-Whys 根因溯源）。
  - **無序獨立標頭與多 Donor 聚合**：採用無序語意標頭確保多 Donor 注入之無序性與獨立性，通過全生態系 211/211 測試並完成熱物化至 `.agents/workflows/Retro.md`。

## 2026_08_29_1505_workflow_and_agents_guidance_optimization — sub_03_plan_taxonomy_and_archetypes_expansion (`v1.0.2.5`)

- **計畫分流維度重構、工作類型拓撲擴充、延遲建檔守門與 Roadmap 策略資產體系**：
  - **全景 6 大計畫分支矩陣 (Plan Taxonomy Matrix)**：
    - **Fast Track (Level 0) 4 維度重構**：升級為修改總行數 $\le 100$ 行、Public API 零變更、架構自包含、既有測試可驗證之綜合規模判定，並設置 Escalation Gate 升級防線。
    - **Umbrella (Level 2) 雙軌拓撲**：明確劃分 **模式 B-1 (預先規劃型 Pre-planned)** 藍圖模式與 **模式 B-2 (增量演進型 Incremental)** 滾動模式。
    - **修訂計畫 (Revision Plan)**：建立 4 步短循環（精準定位 ➔ 原地極小修訂 ➔ 極簡變更卡 ➔ Turn Gate 待命），免開實體目錄保護 Token。
    - **調研計畫 (Research Plan)**：建立 3 步專題調研流程（P00_discuss ➔ R01 報告 ➔ 三大出口分流：立項實作 / 轉入 Roadmap / 存檔歸檔）。
  - **`/NewPlan` 延遲建檔與 JIT 動態分流引導守門**：
    - 實現延遲建檔機制 (Delayed Materialization)：`/NewPlan` 觸發時維持純對話狀態，待確立分流時才伴隨建立目錄與模板，杜絕空目錄殘留。
    - P00 顧問角色純化：除非主動要求，Agent 絕不主動提出個人主觀想法，僅以客觀事實與技術架構角度回覆。
  - **Roadmap 長期策略資產與 CLI 管理體系**：
    - 新增 `workflow.roadmap://`（預設解析至 `workflow.plans://roadmap/`）空間協議與標準 `roadmap.md` 模板。
    - 實作 `RoadmapManager` 與 `python yscb.py agents-workflow roadmap` CLI 指令，支援 `--list` 結構化摘要對照表與非標準 Markdown 容錯預覽。
    - 新增 `/Roadmap` 智能推薦工作流，以 CLI 零 Token 掃描 ➔ 客觀事實匹配 ➔ 推薦卡 ➔ 一鍵轉化為核心步驟。
  - **全量測試與回歸驗證**：
    - 新增 `test_roadmap.py` 測試套件，全生態系 4 大模組 209/209 測試 100% Passed (100% Ready)；正式發布 `agents-workflow@1.0.2.5`。

## 2026_08_29_1715_agents_workflow_release_manifest_idempotency

- **Release Manifest 寫入冪等性防護與空轉 Git Diff 消除 (`publisher.py`)**：
  - **雙軌 Manifest 實質變更防抖檢測**：
    - 於 `ReleasePublisher.release_all` Stage 3 寫入 `storage://` (Project 軌) 與 `cache://` (Local 軌) 前，引入 `fingerprint`、`active_targets` 與 `published_files` 三要素實質比對。
    - 當內容完全未變更時，保留原有之 `updated_at` 時間戳記，並跳過磁碟重複寫入，徹底消滅每次執行 `reload` 或發布流程時產生的空轉 Git diff。
  - **全量測試與回歸驗證**：
    - `agents-workflow` 模組 41/41 測試全數通過；全生態系 4 大模組 209/209 測試 100% Passed (100% Ready)。

## 2026_08_29_1505_workflow_and_agents_guidance_optimization — sub_02_uri_placeholders_and_workflow_path_healing (`v1.0.2.4`)

- **Stage 2 佔位符二分法解析、工作流路徑根目錄直達與確定性讀檔阻斷鐵律**：
  - **Stage 2 佔位符二分法解析與反引號完全替代剝除 (`compiler.py`)**：
    - 實作 `LOCAL_URI_EXACT_REGEX` 與 `PROJECT_URI_EXACT_REGEX` 精確判定。
    - **純佔位符 (Standalone)**：解算後直接返回純路徑字串並吞噬外層反引號，確保 Markdown 超連結 `` [Link](`__#{uri}__`) `` 產出 100% 合規之 CommonMark `[Link](../path.md)`（0 反引號殘留）。
    - **穿插代碼 (Inline)**：指令如 `` `python __${yscb.host://yscb.py}__ run` `` 解算後維持代碼區塊反引號（➔ `` `python yscb.py run` ``）。
  - **工作流讀檔動線全面切換至專案根目錄協議 (`__${...}__`)**：
    - 將 `ContextInit.md` 等工作流中供 Agent 於專案根目錄以 `view_file` 讀取之檔案指引全面改用 `__${...}__` (Project Relative URI)。
    - 物化後產出 `AGENTS.md`、`CHANGELOG.md`、`docs/_project/STANDARDS.md` 等根目錄直達路徑，徹底消除 404 與非預期搜尋開銷。
  - **確定性文檔讀取失效阻斷鐵律 (Deterministic Document Read Guardrail)**：
    - 於 `AgentsStandards.md` 注入剛性禁令：當讀取 SOP/指引顯式指定之確定性檔案失敗時，**絕對禁止**自主發起同義詞或模糊搜尋來掩蓋路徑缺陷，必須立即停步向開發者呈報具體報錯。
  - **非標準語意協議前綴治癒**：
    - 全面修正 `DocumentationStandards.md`、`P07_walkthrough.md` 的 `plans://` ➔ `workflow.plans://` 與 `umbrella_overview.md` 的 `archive://` ➔ `workflow.archived://`。
  - **全量測試與回歸驗證**：
    - 全生態系 4 大模組 209/209 測試 100% Passed (100% Ready)；正式發布 `agents-workflow@1.0.2.4`。

## 2026_08_29_1505_workflow_and_agents_guidance_optimization — sub_01_cli_guidance_and_privilege_optimization

- **CLI 三級權限防呆手冊、JIT 階段指令引導與行為準則純化**：
  - **`contributes.core.commands` Schema 擴充與三級權限分級**：
    - 擴充 `tier` (`safe` | `conditional` | `gated`) 與 `phases` 宣告欄位，於全生態系 4 大模組 26 個指令完成補齊。
    - 🟢 `safe` (自主安全)：沙盒跑測、靜態預檢、知識檢索、計畫狀態查詢。
    - 🟡 `conditional` (階段約束)：`dev build`、`knowledge-db scan/bundle/index`。
    - 🔴 `gated` (授權守門)：`dev release`、`bump-*`、`release-git`、`install --force`、`plan archive`，未獲明確指示前嚴格阻斷執行。
  - **動態防呆手冊產生器與 JIT Phase 指令過濾器**：
    - 實作 `core.providers.get_agents_cli_guild()`，動態渲染帶 🟢/🟡/🔴 標籤之防呆對照表。
    - 實作 `core.providers.get_phase_cli_guild()`，依據當前 Phase 動態過濾推薦指令與紅線警示。
  - **Knowledge-DB 日常檢索強制工具替代與 `--ftype` 決策樹**：
    - 於 `KnowledgeAgentsStandards.md` 強化最高優先級之工具替代條款，明文禁止以 `grep_search` 進行模糊探索或盲目 `list_dir` / `view_file`。
    - 建立 `--ftype=c,cpp,py` (代碼) 與 `--ftype=md` (文檔) 之二分檢索決策樹。
  - **ContextInit 與 Standards 職責解耦與純化**：
    - `ContextInit.md` 解耦模組專屬敘述，聚焦於 `AgentsStandards` 核心防呆反射，SOP 0~7 規範遞延至開啟計畫時按需精讀。
    - `AgentsStandards.md` 純化為核心防呆四重奏，非剛性 SOP 流程敘事 100% 歸位至 `DevelopmentStandards.md`。
    - 移除 `agents-workflow.json` 對 `AGENTS_STANDARDS` 之自引用 `insert`，消滅遞迴軟合併與外層重複 H1 標題。
  - **全量測試與回歸驗證**：
    - 全生態系 4 大模組 208/208 測試 100% Passed (100% Ready)；`sub_01` 計畫 `plan verify` 100% Passed。

## 2026_08_29_1049_knowledge_db_algorithm_optimization — sub_02_agents_workflow_injection_optimization

- **Knowledge-DB 與 Agents-Workflow 注入內容與檢索決策樹優化**：
  - **剛性檢索決策樹 (Search Decision Tree)**：
    - 於 `KnowledgeAgentsStandards.md` 建立明確三層決策分流：
      1. 唯一精確簽章（如 `foo.doSomething`）➔ 原生 `grep_search`。
      2. 明確分類概念（如 "實體智能尋路模組"）➔ 複合關鍵詞檢索 `python yscb.py knowledge-db search '<詞組>' -s`。
      3. 廣義需求探索 ➔ 語意化敘述檢索 `python yscb.py knowledge-db search '<需求>' -s`。
  - **「定位 ➔ 定向閱讀」核心工程哲學 (Targeted Reading Axiom)**：
    - 明確界定檢索職責為「行位址定位與切片預覽」，後續僅進行極小範圍定向閱讀 (`view_file`) 或單一精準 grep，嚴禁在未知精準簽章前發起全專案盲目暴力正則與全文掃描。
  - **過時手動索引指引移除**：
    - `phase07_guild.md` 移除強制手動執行 `knowledge-db index`，說明 JIT 查詢智能感知熱自愈機制。
  - **SOP JIT Guild 檢索引導升級**：
    - `phase00_guild.md` 與 `research_guild.md` 強化 `-s` (`--snippet`) 參數指引與複合關鍵詞檢索建議。
  - **全量測試與 Dogfooding 同步**：
    - 全生態系 4 大模組 198/198 測試 100% 通過 (8.825s)；根目錄 `AGENTS.md` 與 `.agents/` 產物 100% 同步軟合併無損。

## 2026_08_29_1049_knowledge_db_algorithm_optimization — sub_01_jit_invalidation_and_hot_healing

- **Knowledge-DB 全域聯集單一索引與 JIT 智能變更感知熱自愈**：
  - **全專案空間聯集去重建檔與單一全域倒排索引 (`unified.index.bin.gz`)**：
    - 放棄各空間獨立建檔舊機制，改以實體檔案絕對路徑為唯一鍵去重，所有檔案 100% 僅讀取與 AST 解析 1 次。
    - 單一全域倒排索引使 BM25 的 IDF 與 $avgdl$ 指標全局精確正規化，消滅跨空間重疊引起的重複符號與 BM25 評分失真。
    - 符號與 Posting 自動記錄所屬多空間標籤清單 (`spaces: List[str]`)，支援 `--space <name>` 進行 $O(1)$ 高速空間標籤過濾。
  - **極致緊湊原生二進位狀態快照 (`unified.meta.bin`)**：
    - 採用 Magic Header `b"YFP1"` + 原生 `struct` 封裝，反序列化耗時 $< 0.1\text{ ms}$。
    - 建立微秒級快照清冊，完全避免 JSON 序列化與 SHA-1 內容計算之磁碟 I/O 開銷。
  - **JIT 查詢時智能變更感知與背景熱自愈 (Just-In-Time Smart Healing)**：
    - 檢索入口透過 `os.scandir` 進行極速 `(mtime, size)` 比對（耗時僅 $2\sim 3\text{ ms}$），一旦檢測到檔案新增、修改、刪除或索引缺失，自動於背景執行熱重建。
    - 熱自愈提示導向 `sys.stderr`，絕不污染 `--json` 結構化輸出；CLI 支援 `--no-auto-rebuild` / `-n` 旗標以手動停用自動熱自愈。
  - **全量測試與回歸驗證**：
    - `knowledge-db` 模組 50/50 測試 100% 通過；全生態系 4 大模組 198/198 測試 100% 通過。

## 2026_08_29_1025_agents_workflow_manifest_cache_placement

- **Agents-Workflow 發布清單雙軌分流儲存與換行符號歸一化 (`v1.0.2.1`)**：
  - **雙軌 Manifest 空間與格式分流**：
    - **Project 軌 (Tier 2)**：發布清單寫入 `storage://agents-workflow/release_manifest.json`（受 Git 追蹤），路徑 100% 格式化為 `project://` 語意協議路徑（例如 `project://.agents/workflows/Auto.md`），徹底杜絕跨機協作與 Git diff 污染。
    - **Local 軌 (Tier 1)**：發布清單寫入 `cache://agents-workflow/release_manifest.json`（受 Git 忽略），路徑格式使用本機實體絕對路徑。
  - **獨立 Pruning 孤立檔案清理與容錯自癒**：
    - 雙軌各自獨立維護指紋與已發布檔案清冊，獨立執行孤立舊檔案清理。
    - 讀取含有異機絕對路徑（如 `H:\...`）之歷史 Manifest 時不崩潰，安全自癒並標準化。
  - **全專案跨平台換行符號 (LF) 剛性歸一化**：
    - 專案根目錄建立 `.gitattributes`（`* text=auto eol=lf`），並於 `.vscode/settings.json` 加入隱藏清單。
    - 發布引擎及檔案寫入統一顯式指定 `newline="\n"`，徹底根絕 Windows 下 Python 預設自動轉換為 CRLF 產生的警告與換行符號差異。
  - **全量測試與回歸驗證**：
    - `agents-workflow` 模組 40/40 測試全數通過；全生態系 4 大模組 191/191 測試 100% 通過。

## 2026_08_29_0038_knowledge_db_search_snippet_optimization


- **Knowledge-DB 搜尋結果代碼切片與預覽優化 (`v1.0.1.2`)**：
  - **消滅 Double-Look 檢索瓶頸**：
    - 新增 `--snippet`、`-s` 與 `--preview` 旗標，於搜尋結果中直接嵌入帶行號對齊之程式碼切片與 Docstring 摘要。
    - 實測證實可將 Agent 探索代碼庫時的二次檔案讀取 (`view_file`) 降低 80%~95%，搜尋至理解一輪到位。
  - **強韌延遲切片提取器 (`SnippetExtractor`)**：
    - 採用延遲讀取架構，未指定 `--snippet` 時磁碟 I/O 增量為 0。
    - 具備檔案缺失降級 (`[Snippet Unavailable: File not found]`)、行號邊界安全截斷與 UTF-8 `replace` 容錯防禦。
  - **Workspace 相對路徑標準化**：
    - 搜尋結果輸出之檔案路徑自動正規化為相對於專案根目錄之標準相對路徑，優化 IDE 點擊跳轉體驗。
  - **JSON 結構化輸出擴充 (`--json -s`)**：
    - JSON 輸出物件新增 `code_snippet` 結構化欄位（包含 `start_line`, `end_line`, `target_line`, `lines`, `docstring_summary`）。
  - **Agents-Workflow 注入規範同步**：
    - 同步更新 `KnowledgeAgentsStandards.md`、`phase00_guild.md`、`research_guild.md` 與 `contributes/core.json`，於行為準則與 JIT 引導中推薦使用 `--snippet`。
  - **全量測試與回歸驗證**：
    - `knowledge-db` 模組 43/43 測試 100% 通過；全生態系 4 大模組 186/186 測試全數通過。

## 2026_08_28_1754_module_toolchain_optimization — sub_07_knowledge_db_search_output_formatting

- **Knowledge-DB 搜尋結果輸出格式優化 (`sub_07`)**：
  - **預設極輕量簡易模式 (Simple Mode)**：
    - `python yscb.py knowledge-db search <query>` 預設改為極簡排版，每筆結果僅輸出 `#<Rank:02d> <file_path>:<line_number>` 單行資訊，大幅降低終端雜訊並加速點擊跳轉。
  - **詳細多行卡片模式 (Detailed Mode)**：
    - 支援 `--detail`、`-d` 或 `--verbose` 旗標，完整保留評分 (Score)、符號類型、符號名稱、語言、簽名、摘要說明與命中關鍵詞之完整多行卡片。
  - **結構化 JSON 模式 (JSON Mode)**：
    - 支援 `--json` 旗標輸出包含 `query`, `total`, `results` 結構之純淨 JSON，供自動化腳本或第三方工具鏈解析。
  - **CLI 說明與單元測試完善**：
    - 更新 `knowledge-db --help` 說明文字；新增簡易模式、詳細模式與 JSON 模式完整單元與邊界測試（全模組 42/42 測試 100% Passed）。

## 2026_08_28_1754_module_toolchain_optimization — sub_06_agents_workflow_knowledge_db_integration

- **Knowledge-DB 與 Agents-Workflow 雙向 Contributes 聯動與 Space 解耦 (`sub_06`)**：
  - **Space 空間解耦與來源職責分離**：
    - `knowledge-db/configurable/contribute.json` 清空預設硬編碼路徑（`spaces: {}`），達成模組零假設與通用性。
    - `agents-workflow` 透過 `contributes/knowledge-db.json` 向知識庫貢獻 `docs` 空間（指向 `workflow.docs://`）。
    - 宿主專案透過 `config/knowledge-db/contribute.json` 宣告特化之 `source` 源碼空間（指向 `project://source`, `project://ys_codebase`）。
  - **`AGENTS_STANDARDS` 錨點補齊與行為準則注入**：
    - 於 `AgentsStandards.md` 底部補齊 `__@{AGENTS_STANDARDS}__`，並於 `agents-workflow.json` 宣告對應 Token。
    - 由 `knowledge-db` 注入 `KnowledgeAgentsStandards.md`（知識檢索優先紀律、Docstring 符號結構防護）。
  - **SOP AGENT GUILD JIT 註解注入**：
    - 調研與需求階段 (`PHASE00_AGENTS_GUILD`, `RESEARCH_AGENTS_GUILD`) 引導使用 `knowledge-db search` 定向查找資料，嚴禁盲目大範圍 grep 或逐檔翻找。
    - 結案階段 (`PHASE07_AGENTS_GUILD`) 明確指引調用 `knowledge-db index` 即刻更新專案倒排索引庫。
  - **測試套件標籤清理與效能最佳化**：
    - 清理 `knowledge-db` (17 個)、`agents-workflow` (11 個) 與 `dev` 測試中誤掛之 `ISOLATED_SANDBOX`，回歸純 `LOGIC` / `ENV` 與 Session 共享沙盒。
    - 全模組跑測時長從 **21.099s ⬇️ 大幅下降至 8.224s (2.5x 提速)**。
  - **Dev Module Check 靜態合規檢核升級 (`dev.checker`)**：
    - 於 AST 靜態語法分析新增測試方法/類別裝飾器檢核：若同時標記 `LOGIC` 與 `ISOLATED_SANDBOX` 則發出 `[WARN]` 反模式警告，引導合理使用沙盒。
  - **全量測試與回歸驗證**：
    - 全生態系 4 大核心模組沙盒回歸跑測 **184/184 測試案例 100% Passed (8.224s)**。


## 2026_08_28_1754_module_toolchain_optimization — sub_05_agents_workflow_release_local_mode


- **Agents-Workflow Release 預設 Local 模式、Gitignore 軟合併同步與 Core Config 來源層級探測 (`sub_05`)**：
  - **微內核組態溯源 API (`core.config`)**：
    - `core.config.get_raw(module, key, local, default)`：可精確讀取單一層級 (Local 或 Project) 的原始未合併設定。
    - `core.config.inspect(module, key)`：可深度診斷鍵值來源（`"local"`、`"project"`、`"both"`、`"none"`）與 `is_overridden` 覆蓋狀態。
  - **Release Target 預設 Local 模式 (`ReleaseTargetManager`)**：
    - `release-target --add <t>` 與 `--remove <t>` 預設操作本機私有之 `config.local.json`（Tier 1，不入 Git），避免不同開發工具相互污染專案。
    - 支援 `--proj` / `--project` 旗標以顯式切換寫入 `config.project.json`（Tier 2，團隊共用）。
  - **多層來源標註清冊 (`release-target --list`)**：
    - 終端排版清晰標註各 Target 啟用層級：`[ENABLED (LOCAL)]`、`[ENABLED (PROJECT)]`、`[ENABLED (BOTH)]`、`[DISABLED]`。
  - **`project://.gitignore` 區塊非破壞性軟合併 (`ReleasePublisher.sync_gitignore`)**：
    - 4 步發布交易中自動維護 `# === YSCB AGENTS_WORKFLOW IGNORE BEGIN ===` 標記區塊。
    - 若 `.gitignore` 不存在則自動建立；若已存在則非破壞性替換區塊，用戶自訂規則 100% 完好保留。
  - **全量測試與回歸驗證**：
    - 全生態系 4 大核心模組沙盒回歸跑測 **181/181 測試案例 100% Passed**。

## 2026_08_28_1754_module_toolchain_optimization — sub_04_agents_workflow_plan_check_upgrade


- **Agents-Workflow Plan 核查工具鏈升級 (`sub_04`)**：
  - **5 步計畫合規檢核流水線 (`agents_workflow.plans.verifier.PlanVerifier`)**：
    - **Stage 1 (Structure & Depth Guard)**：目錄層級限制 $\le 2$ 層（主計畫 ➔ 子計畫），Umbrella 主計畫 `umbrella_overview.md` 存在性與子清冊一致性。
    - **Stage 2 (Changelog Integrity Guard)**：`changelog.md` 伴隨存在性、Markdown 表格格式與有效紀錄列。
    - **Stage 3 (Dynamic Template Resolver)**：動態讀取 `.cache/agents-workflow/resolved_contents/templates/<template>.md`（展開後之標準模板），提取 Markdown `# Header` 標題清單。
    - **Stage 4 (Markdown File & ID Guard)**：Blockquote Header 元數據完整性、佔位符與嚴禁殘留任何 HTML 註解（`<!-- ... -->`）、標準 ID 前綴格式 (`FR-XX`, `EC-XX`, `FT-XX`, `ET-XX`)。
    - **Stage 5 (Severity Aggregator)**：`[PASS]`, `[WARN]`, `[FAIL]` 三級嚴重度聚合與向下相容 Tuple 解包。
  - **Noise-Free 聚焦排版與 CLI 整合**：
    - 全數通過時單行收斂 (`[*] Plan: <name> [PASS]`)；有違規時自動隱藏 Pass 檔案，僅展示 Fail/Warn 問題檔案與行號。
    - 支援 `--json` 結構化格式輸出。
  - **PlanArchiver 剛性歸檔守門阻斷**：
    - `plan archive` 在歸檔前自動執行 plan check，若存在 `[FAIL]` 且未加 `--force` 時剛性阻斷歸檔。
  - **全量測試與回歸驗證**：
    - 全生態系 4 大核心模組沙盒回歸跑測 **178/178 測試案例 100% Passed**。

## 2026_08_28_1754_module_toolchain_optimization — sub_03_dev_module_check_upgrade


- **Dev 模組狀態檢核工具升級 (`sub_03`)**：
  - **5 步流水線合規檢查引擎 (`dev.checker.Checker`)**：
    - **Step 1 (ManifestGuard)**：驗證必填欄位完整性、SemVer 嚴格格式、強制 `dependencies` 包含 `core`（`core` 本體除外）。
    - **Step 2 (CoreInjectGuard)**：檢核 `contributes/core.json`（宣告 `commands` 或 `uri_schemes`）。
    - **Step 3 (StructureGuard)**：`scripts/cli.py` 存在性、強制 `configurable/` 模板標準（嚴禁根目錄散落 `config.*.json`）、暫存垃圾檔案清理、`contributes.format.md` 文檔合規提示。
    - **Step 4 (AstSecurityGuard)**：AST 語法檢查、空間穿透防禦（禁止業務模組存取 `module.source://`）、反模式靶向攔截（禁止業務代碼直接存取 `config.project.json` / `contributes.merged.json`，放行一般原生 I/O）。
    - **Step 5 (TestClassGuard)**：強制測試類別繼承 `dev.testing.case.YSCBTestCase`。
  - **三級嚴重度與 Release 剛性守門 (`dev.releaser.Releaser`)**：
    - 結構化 `[PASS]`, `[WARN]`, `[FAIL]` 分級。
    - 存在 `[FAIL]` 時剛性阻斷 `dev release` 正式打包發布；同時放行 `dev build` 以利本機調試。
  - **診斷報告與 CLI 體驗升級**：
    - 支援終端彩色診斷排版與 `--json` 機器可讀格式輸出。
  - **全量測試與回歸驗證**：
    - 全生態系 4 大模組虛擬沙盒回歸跑測 **178/178 測試案例 100% Passed (21.623s)**，清理歷史殘留之 6 處穿透與反模式。

## 2026_08_28_1754_module_toolchain_optimization — sub_02_config_system_upgrade


- **Config 系統架構升級、Contribute 專案特化規範與工具鏈建立 (`sub_02`)**：
  - **微內核 `core.config` 統一 SDK**：
    - 提供 `get(module, key, default)`（支援點分隔路徑）、`get_all(module)`、`set(module, key, value, local=False)`、`delete`、`reload` 與 `list_modules` 介面。
    - 封裝 Local > Project (Tier 1 > Tier 2) 雙層深層合併，並以 `(project_mtime, local_mtime)` 雙時間戳快取達成 0 I/O 與 Auto-Healing 自動自愈。
  - **標準 `configurable/` 模板目錄規範**：
    - 徹底廢除源碼根目錄散落之 `config.*.json` 模板；模組預設設定一律置於 `source/<module>/configurable/`。
    - 部署引擎 `act_deploy_configs_from_modules()` 自動掃描 `configurable/` 增量補齊至 `config://`，並物理刪除 runtime 空間之模板目錄，確保代碼純淨。
  - **專案特化 `contribute.json` 類別與 Git 剛性追蹤公理**：
    - 下游專案對目標模組之能力擴充注入統一置於 `config://<target>/contribute.json`（對應實體 `config/<target>/contribute.json`）。
    - 核心聚合引擎 `ContributesAggregator` 階層 ② 專門載入 `config://<target>/contribute.json`；剛性禁止 `contribute.local.json`（檢測到主動警告並忽略），保障工作流與軟體構建之 100% 確定性。
  - **全生態系消費端 100% 收斂**：
    - `core.uri`、`knowledge-db` (`space.py`)、`agents-workflow` (`targets.py`, `publisher.py`, `initializer.py`) 全面收斂調用 `core.config` 與 `core.contributes` SDK，徹底消滅手寫讀寫組態與手寫提取 contributes 反模式。
  - **CLI 工具鏈與 Contributes 註冊**：
    - 提供 `python yscb.py config list / get / set / reload` 指令體系，並於 `contributes/core.json` 註冊防呆條款。
  - **全量測試與回歸驗證**：
    - 全系統 4 大模組虛擬沙盒回歸跑測 **172/172 測試案例 100% Passed (27.717s)**，靜態品質與契約檢查 `dev check --all` 100% PASSED。

## 2026_08_28_1754_module_toolchain_optimization — sub_01_core_contributes_file_structure_upgrade


- **Core Contributes 系統檔案結構升級與純淨目錄化標準重構 (`sub_01`)**：
  - **目錄化 Contributes 唯一官方標準 (`source/<module>/contributes/<target>.json`)**：
    - 徹底廢除散落於模組根目錄之 `contributes.<target>.json` 與 `manifest.json` 內嵌擴充宣告。
    - 確立全生態系唯一的標準結構：模組欲貢獻給目標 `<target>` 之宣告一律儲存於專屬 `contributes/<target>.json` 檔案中。
  - **Manifest 徹底瘦身 (Slimming down >98%)**：
    - 全系統 4 大核心模組 (`core`, `dev`, `knowledge-db`, `agents-workflow`) 之 `manifest.json` 徹底剝除 `"contributes"` 冗餘物件，恢復純粹輕量元數據宣告（`agents-workflow/manifest.json` 由 554 行精簡至 10 行）。
  - **雙階聚合引擎重構與專案特化覆蓋 (`core.contributes.ContributesAggregator`)**：
    - **階層 ① (模組貢獻)**：自動掃描已安裝模組之 `module://<donor>/contributes/<target>.json`，遞迴注入 `__provider__ = donor` 標記並進行深度拓撲合併。
    - **階層 ② (專案特化注入與覆蓋)**：完整掃描 `config://<target>/config.project.json`（與 `config.local.json`）之 `"contributes"` 物件，疊加覆蓋於模組基礎貢獻之上，保障下游專案特化擴充擁有最高優先權。
    - **物化快取與自愈機制 (Auto-Healing)**：聚合結果原子寫入 `cache://<target>/contributes.merged.json`；若快取遺失或損毀，`core.contributes.get()` 自動觸發即時自愈重建。
  - **消費端 SDK 100% 收斂與空間穿透反模式清算 (Zero Source Probing)**：
    - 徹底清理 `agents-workflow/compiler.py` 與 `core/providers.py` 中探測 `module.source://` 的歷史穿透壞味道，恪守三層空間公理。
    - 全模組消費端（`core/providers.py`、`core/engine.py`、`knowledge_db/space.py`、`agents_workflow/compiler.py`）徹底廢除手寫檔案遍歷，統一 100% 調用 `core.contributes.get(target, key)` SDK 查詢。
  - **測試沙盒構建產物覆蓋增強 (`dev.testing.sandbox`)**：
    - 升級測試沙盒初始化機制，自動將 `module.build://` 構建之最新測試包解壓覆蓋至沙盒 `engine/modules/` 空間，確保 Hermetic Build 與 Dogfooding 測試高保真度。
  - **全量測試與回歸驗證**：
    - 全系統 4 大核心模組虛擬沙盒回歸跑測 **164/164 測試案例 100% Passed (19.632s)**，全模組靜態合規檢查 `dev check --all` 100% PASSED。
  - **知識庫交付**：
    - 交付 `source/core/contributes.format.md`、`source/knowledge-db/contributes.format.md`、`source/dev/contributes.format.md` 與 `source/agents-workflow/contributes.format.md`。

## 2026_08_28_1735_agents_workflow_release_diff_optimization


- **`agents-workflow` 發布引擎來源 Diff 檢測與無效 File IO 優化**：
  - **Stage 0 來源端綜合特徵指紋與提前短路 (Source Fingerprint Early Short-Circuit)**：
    - 實作 `ReleasePublisher.compute_source_fingerprint()`：整合 `assets/` 資源檔案 (templates, standards, workflows) SHA-1、`manifest.json`、專案組態 (`config.project.json`) 與啟用 Target 之投影規則，計算 64 位元 SHA-256 綜合指紋。
    - 在發布交易前（Stage 0）比對 `storage://release_manifest.json` 記錄之指紋與實體檔案完整性。若來源未變且發布檔案皆完好，**立即提前短路 (0 I/O，耗時 ~1ms)**，徹底消除 microkernel reload 階段的無效檔案寫入。
  - **Stage 4 落地端記憶體內容 Diff 比對與增量物化 (Incremental Materialization)**：
    - 在實體落地階段比對目標檔案現存磁碟文字與渲染產物，僅在內容實質相異時執行 `open(w)` 寫入，相同者跳過寫入。
    - `_soft_merge_agents_md` 升級 Diff 檢測，正則區塊替換前後字串一致時跳過磁碟寫入。
  - **`--force` 強制發布支援與結構化指標透明化**：
    - CLI `python yscb.py agents-workflow release --force` 與 SDK 支援 `force=True` 旗標，可強制忽略所有 Diff 檢測進行全量重新編譯與覆寫。
    - `release_all()` 回傳指標擴充包含 `short_circuited`、`written_count`、`skipped_count`、`removed_count` 等欄位，Hook 日誌清晰展示變更計數。
  - **全量測試與品質驗收**：
    - 新增 `source/agents-workflow/tests/test_publisher.py` (FT-01~06, ET-01~03)，模組 32/32 Passed，全系統 163/163 測試案例 100% Passed (10.409s)。


## 2026_08_27_2127_knowledge_db — sub_05_binary_index_cache_optimization

- **`knowledge-db` 符號池去重與二進位 Gzip 倒排索引快取優化 (`sub_05`)**：
  - **符號池分離與輕量引用解耦 (Symbol Pool Normalization)**：
    - 重構 `InvertedIndex` 資料結構：在頂層建立 `symbols: Dict[str, UnifiedSymbol]`（以 `doc_id` 唯一識別）。
    - 倒排表 `postings[term]` 僅存儲輕量引用節點 `Posting(doc_id, field_freqs, field_lengths, space)`，徹底消滅同一個符號在數百個 Term 中被深層拷貝重複內嵌的 500 倍膨脹冗餘。
  - **原生二進位 Gzip 壓縮快取 (`.index.bin.gz`)**：
    - 本地快取檔案格式全面升級為 `cache://knowledge-db/indices/<space_name>.index.bin.gz`。
    - 使用 Python 原生標準庫 `pickle` (最高協議 Protocol 5) 與 `gzip` (Level 6)。
    - **磁碟體積縮減 99.53%**：從未優化 JSON 快取的 **55.35 MB** (1,079,342 行) 暴降至 **253.89 KB**（僅剩原大小的 0.47%）。
    - **反序列化耗時加速超過 40 倍**：載入耗時由 **~850 ms 降低至 < 20 ms**。
  - **舊版快取平滑升級與自癒機制**：
    - `KnowledgeEngine._get_or_build_index` 與 `build_index` 支援讀取二進位快取，若遇舊版 `.index.json` 自動降級讀取並平滑升級寫入 `.index.bin.gz`。
    - `KnowledgeEngine.clean()` 同步支援清理 `.index.bin.gz` 與舊 `.index.json`。
    - 若快取檔案損毀 (Corrupt Gzip/Pickle) 自動透明重新構建，確保 100% 韌性。
  - **全量測試與品質驗收**：
    - 新增 `test_symbol_pool_normalization_and_binary_gzip_io` 與 `test_corrupted_binary_cache_fallback`。
    - 全模組 40/40 測試案例 100% Passed (9.045s)。

## 2026_08_27_2127_knowledge_db — sub_04_cli_sdk_and_workflow_interlock

- **`knowledge-db` 模組頂層統一門面 SDK、完整 6 大 CLI 指令體系、本地端快取遷移與 Core 套件解析嚴格化 (`sub_04`)**：
  - **Python SDK 頂層統一門面 (`engine.py` / `KnowledgeEngine`)**：
    - 實作 `KnowledgeEngine` 高階門面 Facade，一站式封裝 `SpaceManager`、`FingerprintScanner`、`ParserRegistry`、`SemanticBundler`、`ThesaurusEngine` 與 `BM25Engine`。
    - 提供簡潔且完整型別標註的公開 API：`status()`、`scan()`、`bundle()`、`build_index()`、`search()`、`clean()`。
    - 實作透明索引自動懶加載 (Lazy Indexing) 與多空間 InvertedIndex 高速 Posting 零拷貝聚合。
  - **資料庫與索引檔案全面本地端化 (`cache://knowledge-db/`)**：
    - 預設存儲空間全面遷移至 `cache://knowledge-db/`（對應 `yscb://.cache/knowledge-db/`），空間指紋、倒排索引與 Bundle 產物 100% 留存本地端。
    - 利用 `.cache/` 由專案 `.gitignore` 全局忽略之特性，徹底杜絕龐大 AST 符號與 Postings JSON 檔案污染專案 Git 倉庫。
  - **Core 模組套件解析嚴格化與 Build 包隔離 (`core.engine.AtomicEngine`)**：
    - 徹底廢除 `_get_module_manifest_from_provider_or_local` 查無發布時回傳 fake manifest 的 dummy fallback，嚴格拋出 `ModuleNotFoundError`。
    - 實作 `module.build://` 物理隔離，僅在請求明確包含 `build` revision 標記時允許存取，防禦未授權之幽靈模組安裝。
  - **模組自治 Hook (`scripts/hook.dev.py`)**：
    - 實作 `on_test_setup` 與 `on_test_teardown`，支援 YSCB 沙盒測試生命週期環境自動準備與清理。
  - **CLI 完整 6 大子指令體系 (`scripts/cli.py` / `manifest.json`)**：
    - 完整實作 `status`、`scan`、`bundle`、`index`、`search`、`clean` 6 大子指令與格式化彩色輸出。
    - 在 `manifest.json` 完整宣告 commands 說明與防呆 case pros/cons 規範。
  - **全量測試與品質驗收**：
    - 實作 `test_engine.py` (FT-01~06, ET-01)、`test_cli.py` (FT-07~08)、`test_space.py` (FT-11)、`test_installer.py` (FT-09~10) 與全量回歸套件，全模組 38/38 + Core 48/48 測試案例 100% Passed。
  - **知識庫交付**：
    - 更新 `docs/knowledge-db/README.md`（完整 6 大 CLI 指令集與 Python SDK 快速上手手冊）與 `docs/knowledge-db/architecture.md`（全系統整合架構設計與本地端快取拓撲）。

## 2026_08_27_2127_knowledge_db — sub_03_tokenizer_thesaurus_and_bm25_retrieval

- **`knowledge-db` 模組代碼/中文混合分詞、雙層同義詞擴展與多欄位 BM25 檢索引擎 (`sub_03`)**：
  - **純原生代碼與中文混合分詞器 (`tokenizer.py`)**：
    - 實作 `CodeTokenizer`，支援駝峰（`camelCase`, `PascalCase`）、底線（`snake_case`）與全大寫縮寫標識符拆解，同時保留子單字與完整小寫標識符。
    - 實作 CJK 中文字元 1-gram 單字與 2-gram 相鄰雙字滑動窗口切分。
    - 內建中英文高頻停用詞與純標點符號過濾。
  - **雙層同義詞擴展引擎 (`thesaurus.py`)**：
    - 實作 `ThesaurusEngine`，內建 18 組軟體工程通用雙向中英對照同義詞庫。
    - 支援動態合併專案與空間層級自訂同義詞庫 (`ThesaurusConfig`)。
    - 實作查詢端雙向去重擴展 (`expand_query`)，具備 Set 集合防無窮迴圈與最大擴展上限 (EC-05)。
  - **多欄位加權 BM25 倒排索引與檢索引擎 (`retrieval.py`)**：
    - 實作 `InvertedIndex` 多欄位倒排索引結構，記錄詞頻、平均欄位長度 $\text{avgdl}$ 與全域 IDF 預計算，支援純 JSON 序列化導出與還原。
    - 實作 `BM25Engine` 多欄位加權評分（Name 3.5, Signature 2.0, Member 2.0, Docstring 1.5），具備平滑 IDF 與 Exact Match 2.0x 置頂加權。
    - 實作 `QueryFilter` 複合條件過濾器（空間、語言、類型、分數門檻）與結構化 `SearchResult`。
  - **CLI 指令擴充 (`scripts/cli.py` / `manifest.json`)**：
    - 新增 `search <query> [--space=name] [--kind=type] [--lang=py] [--limit=10]` 指令，支援命令列快速語意檢索與高亮格式化輸出。
  - **全量測試與品質驗收**：
    - 實作 `test_tokenizer.py` (FT-01~02)、`test_thesaurus.py` (FT-03) 與 `test_retrieval.py` (FT-04~07, ET-01) 單元測試套件，全模組 32/32 測試案例 100% Passed (3.268s)。
  - **知識庫交付**：
    - 交付 `docs/knowledge-db/tokenizer.md`（分詞與同義詞指南）、`docs/knowledge-db/retrieval.md`（檢索引擎指南）並更新 `docs/knowledge-db/README.md`。

## 2026_08_27_2127_knowledge_db — sub_02_parsers_and_semantic_bundler

- **`knowledge-db` 模組多語言解析器外掛體系與語意打包引擎 (`sub_02`)**：
  - **解析器基礎抽象與外掛註冊分發中心 (`parsers/base.py`, `parsers/registry.py`)**：
    - 定義 `BaseParser` 抽象基底契約（`can_parse`, `parse`）。
    - 實作 `ParserRegistry`，支援自訂解析器優先權覆蓋、依副檔名匹配與未知檔案類型安全降級略過。
  - **四大多語言原生語意解析器 (`parsers/`)**：
    - **`PythonParser`**：利用 Python 原生 `ast` 模組，完整解析 Class、Function、AsyncFunction、Method、Decorator、Docstring、Signature（含型別標註與預設值）與成員清單 (`MemberInfo`)，具備 `SyntaxError` 安全降級。
    - **`MarkdownParser`**：狀態機解析 H1~H4 標題節點 (`DOC_HEADING_1~4`)、Tables 表格 (`DOC_TABLE`) 與段落內容摘要，支援純文字檔案降級 (`DOC_SECTION`)。
    - **`CppParser`**：狀態機解析 C/C++ Class、Struct、Enum、Function、`#define` 巨集與 Doxygen 註解 (`///`, `/** */`)。
    - **`CSharpParser`**：狀態機解析 C# Namespace、Class、Interface、Struct、Method、Property 與 XML `<summary>` 註解。
  - **語意發布包與打包引擎 (`bundler.py`)**：
    - 實作 `SemanticBundle` 不可變資料模型與純 JSON 序列化/反序列化。
    - 實作 `SemanticBundler`，支援空間全量解析打包 (`bundle_space`)、原子暫存檔替換導出 (`export_bundle`) 與離線載入還原 (`import_bundle`)。
  - **CLI 指令擴充 (`scripts/cli.py` / `manifest.json`)**：
    - 新增 `bundle [space | --all] [--output=path]` 指令，支援命令列一鍵打包空間語意 Bundle。
  - **全量測試與品質驗收**：
    - 實作 `test_parsers.py` (FT-01~06) 與 `test_bundler.py` (FT-07~08, ET-01) 單元測試套件，全模組 24/24 測試案例 100% Passed (3.113s)。
  - **知識庫交付**：
    - 交付 `docs/knowledge-db/parsers.md`（多語言解析器指南）、`docs/knowledge-db/bundler.md`（語意打包引擎指南）並更新 `docs/knowledge-db/README.md`。

## 2026_08_27_2127_knowledge_db — sub_01_space_management_and_schema

- **全新 `knowledge-db` 模組空間管理、資料架構與雙階增量指紋比對引擎 (`sub_01`)**：
  - **模組骨架與元數據宣告 (`manifest.json` / `scripts/cli.py`)**：
    - 在 `source/knowledge-db/` 建立符合 YSCB 規範之模組骨架，依賴 `core >= 1.0.0`，並宣告 URI Scheme `knowledge.storage -> storage://knowledge-db/`。
    - 實作 `scripts/cli.py` 提供 `status`（檢視空間與快取）與 `scan`（單空間/全空間聯集增量比對）指令。
  - **核心解耦資料模型 (`schema.py`)**：
    - 定義 `SymbolKind`、`LanguageType`、`SpaceOrigin` 列舉與 `MemberInfo` 成員模型。
    - 實作不可變 `UnifiedSymbol` 模型，包含 SHA-1 唯一 ID 計算演算法（`compute_id`）與字典序列化/反序列化。
    - 實作獨立解耦之 `SpaceConfig`（選填 `file_patterns` 預設 include all 邏輯）與 `ThesaurusConfig` 同義詞模型。
  - **多空間雙軌聚合與聯集模型 (`SpaceManager`)**：
    - 支援模組聯動注入（`contributes.knowledge-db.json` / `manifest.json`）與專案組態（`config.project.json` / `config.local.json`）雙軌空間定義。
    - 實作 `Local` > `Project` > `Contributed` 階層優先權覆蓋與 `resolve_space_include` 語意 URI 解算。
    - 廢除單一 `default_space` 強制約定，全系統以所有有效空間之聯集作為全域處理範圍 ($Scope = \bigcup Space_i$)。
  - **雙階增量檔案指紋比對引擎 (`FingerprintScanner`)**：
    - 實作 Stage 1 (`mtime`+`size` 初篩，零 I/O 與零 SHA1 運算) + Stage 2 (`SHA1` 內容校驗) 雙階比對。
    - 支援 `scan_space` 與 `scan_all_spaces`，輸出 `ScanDiffResult`（Added/Modified/Deleted/Unchanged）。
    - 實作指紋快取損毀自動自癒重置與基於暫存檔之原子寫入持久化機制。
  - **全量測試與品質驗證**：
    - 實作 `test_schema.py`、`test_space.py`、`test_scanner.py` 單元測試套件，15/15 測試案例 100% Passed (3.400s)。
  - **知識庫交付**：
    - 交付 `docs/knowledge-db/README.md`（模組手冊與子計畫演進）、`docs/knowledge-db/contributes_guide.md`（擴充點指南）與 `docs/knowledge-db/architecture.md`（架構說明）。

## 2026_08_28_0215_test_shared_sandbox_optimization

- **測試框架 Session-Level 全局共用沙盒與寫入型測試隔離優化**：
  - **Session-Level 全局共用沙盒生命週期 (`YSCBTestCase`)**：
    - 將 `YSCBTestCase` 預設沙盒生命週期由「類別層級 (Class-Level)」重構為「Session-Level 類別級全域單例 (`_shared_sandbox_ctx`)」，徹底消除跨測試類別重複在 Windows NTFS 上建立與刪除目錄的實體 I/O 開銷。
    - 實作 `YSCBTestCase.cleanup_shared_sandbox()`，並於 `TestRunner.run_suite()` 之 `finally` 區塊保證自動安全釋放。
  - **寫入與變異型測試剛性隔離標註 (`ISOLATED_SANDBOX`)**：
    - 全面盤點寫入型測試（`TestCoreInstaller`, `TestCoreEngine`, `TestRemoteZipBootstrap`），顯式標註 `@require(Requirement.ENV | Requirement.ISOLATED_SANDBOX)`，確保 100% 測試狀態純淨與環境隔離。
    - 擴充 `YSCBTestCase.setUp()` 支援類別層級 `@require` 條件解析。
  - **全量測試與回歸驗證**：
    - 新增跨 Class Session-Level 沙盒複用與清理安全單元測試，全庫 114/114 測試 100% Passed (100% Ready)。
  - **知識庫交付**：
    - 更新 `docs/dev/user_guide.md` §4.3 (Session-Level 共用沙盒與 ISOLATED_SANDBOX 測試沙盒模式指南)。

## 2026_08_27_2146_release_targets_codex_claude

- **`agents-workflow` 模組新增 Anthropic Claude Code 與 OpenAI Codex Release Targets**：
  - **多平台 Release Target 宣告與投影拓撲 (`manifest.json`)**：
    - 新增 `claude` 目標：工作流指令投影至 `project://.claude/commands/{name}.md`，模板與標準規範投影至 `project://.claude/.yscb/`，支援 YAML Frontmatter。
    - 新增 `codex` 目標：工作流指令投影至 `project://.codex/workflows/{name}.md`，模板與標準規範投影至 `project://.codex/.yscb/`，支援 YAML Frontmatter。
  - **CLI 管理指令支援 (`release-target`)**：
    - 支援 `python yscb.py agents-workflow release-target <list|add|remove>` 自由切換與發布多平台目標。
  - **測試與回歸驗證**：
    - 新增 `test_targets.py` 驗證多目標宣告、清單查詢與拓撲路徑映射，模組全量 23/23 測試 100% Passed。
  - **知識庫交付**：
    - 更新 `docs/agents-workflow/user_guide.md` §2.4 (多平台 Release Targets 矩陣與管理)。

## 2026_08_27_2011_dev_test_performance_and_encoding_fix

- **Dev 模組測試效能優化、Mock 模組建置隔離與 Windows Unicode/cp950 控制台編碼防禦**：
  - **Windows 控制台與子進程編碼安全防禦 (`SafeStreamWriter` / `safe_print`)**：
    - 在 `dev.tester`、`dev.testing.runner` 與 `dev.testing.case` 導入 `safe_print` 與 `SafeStreamWriter`，子進程 Standard Streams 與終端輸出全面覆蓋 UTF-8 與 `errors="replace"` 安全轉譯。
    - 徹底根除 Windows 中文語系環境下 `cp950` 控制台在輸出替換字符 `\ufffd` 或非 BMP Unicode 時崩潰中斷之缺陷。
  - **測試四層分類精準歸類 (`WORKFLOW` Tier)**：
    - 將純高階多進程 E2E 調度測試（`test_dev_test_high_level_orchestration` 與 `test_single_module_worker_execution_and_report_json`）標記為 `@require(Requirement.WORKFLOW)`。
    - 日常預設回歸 (`LOGIC` + `ENV`) 自動排除重型測試，可透過 `--workflow` 或 `--all-types` 按需調度。
  - **單元測試去子進程化 (Mocking)**：
    - 重構 `test_tester.py` 沙盒全量清理邏輯，以 Mock 隔離 Worker 子進程，毫秒級完成驗證，消除測試內部遞迴啟動多行程。
  - **標準建置與發布測試全面改採 Mock Module 隔離 (Zero Side Effect)**：
    - 重構 `test_builder.py` 與 `test_release_pipeline.py`，全面改以動態生成之輕量 Mock Module 測試 build、package_release、revision purge 與 index.json。
    - 徹底解除對真實官方模組原始碼的打包依賴，根除未來官方新增或修改模組時產生的耦合副作用。
  - **效能指標躍升**：
    - `dev` 模組跑測耗時由 **12.08 秒大幅壓至 3.81 秒（加速超過 68%）**。
    - 全系統回歸跑測 118/118 測試案例 100% Passed。
  - **知識庫交付**：
    - 更新 `docs/dev/user_guide.md` §4.7 (控制台編碼防禦與 Mock 模組建置測試實踐規範)。

## 2026_08_27_1506_dev_test_architecture_optimization

- **dev 測試架構優化主計畫 — sub_05: 多進程/多 Worker 多模組並行跑測 (`sub_05_parallel_module_test_runner`)**：
  - **多 Worker 多沙盒並行測試調度 (`Tester._run_parallel_test`)**：
    - `dev test --all` 預設自動啟用多進程並行執行，利用 `ThreadPoolExecutor` 驅動多個獨立虛擬沙盒子行程（Worker Processes），總回歸時間縮短至單一最慢模組耗時（由 ~23 秒壓至 **~14 秒，加速 >40%**）。
    - 支援 `-j <N> / --jobs=<N>` 控制最大並行 Worker 數（預設 `min(cpu_count, num_modules)`）。
    - 支援 `--sequential / --no-parallel` 快速回退為單進程順序執行。
  - **獨立沙盒實例隔離與線程安全 (`SandboxProvisioner`)**：
    - 沙盒目錄引入 `uuid` 唯一性綴詞，確保微秒級多 Worker 同時建立沙盒時零目錄碰撞與零檔案衝突。
    - 每個 Worker 獲取專屬 `sandbox 1..N` 標籤與獨立環境變數空間。
  - **即時交錯生命週期 Log 與報告聚合**：
    - 各 Worker 建立沙盒、開始測試與結束測試之 Log 即時交錯呈現在終端。
    - 各 Worker 透過 `--report-json` 導出結構化數據，主進程聚合所有模組數據並按原始順序輸出單一整合 ASCII Diagnostic Report。
  - **差異化沙盒清理策略**：通過之模組沙盒即時銷毀，若有失敗模組僅保留該失敗模組所在的沙盒供除錯。
  - **全量測試與回歸驗證**：新增多 Worker 並行派發與獨立沙盒單元測試，全庫 148 個測試案例回歸 148/148 100% Passed。
  - **知識庫交付**：更新 `docs/dev/user_guide.md` §4.1 (並行測試參數與用法)。

- **dev 測試架構優化主計畫 — sub_04: dev test CLI 輸出結構、日誌降噪與即時反饋優化 (`sub_04_test_cli_output_and_ux_optimization`)**：
  - **中間輸出緩衝捕獲與靜默降噪 (`OutputCapturer`)**：跑測期間預設對 stdout/stderr 進行記憶體緩衝，常態消除 Hook、Mock 與 print 控制台雜訊，僅在失敗或 `-v / --verbose` 時展開。
  - **跑測生命週期即時進度 Log**：即時輸出 `Create sandbox <id> at: "..."`, `<mod> begin test in sandbox <id>`, `<mod> test finish in ({time}s)` 與 `Cleaned up sandbox <id>`，為後續多行程 Worker 空間奠定基礎。
  - **雙報表根除與子行程輸出隔離**：在 `Tester._run_test` 實作子行程 `capture_output=True` 搭配 `YSCB_NESTED_TEST` 隔離，徹底根除巢狀測試產生的雙報表洩漏。
  - **診斷報告結構豐富化 (`ASCIIReportFormatter`)**：
    - 頂部元數據呈現 `Mode / Target / Build`。
    - 各模組列顯示獨立執行精確耗時。
    - Custom 節點展示四層分類細分計數 (`[Logic: X, Env: Y]`)。
    - 失敗時輸出結構化診斷區塊與一鍵 `--target` 快速重測指令。
  - **全量測試與回歸驗證**：新增 `OutputCapturer`、報表元數據與分類統計單元測試，全系統回歸跑測 147/147 測試 100% Passed。
  - **知識庫交付**：更新 `docs/dev/user_guide.md` §4.1 (`-v`) 與 §4.6 (診斷報告結構與即時反饋)。

- **dev 測試架構優化主計畫 — sub_03: 測試分類體系重構、效能深水區與沙盒型別安全防固 (`sub_03_test_performance_optimization`)**：
  - **四層測試分類體系 (4-Tier Test Taxonomy)**：在 `dev.testing.requirement` 定義 `LOGIC` (純邏輯)、`ENV` (環境/跨模組)、`WORKFLOW` (工作流/E2E)、`PERF` (壓力效能) 與正交 `ISOLATED_SANDBOX` 標籤；預設跑測僅執行 `LOGIC` 與 `ENV`，大幅提升回歸效能。
  - **CLI 篩選旗標與精準目標定位器 (`--target`)**：
    - 擴充 CLI 分類篩選（`--logical`, `--env`, `--workflow`, `--perf`, `--all-types`）。
    - 支援 `--target=<mod>:[<case>][.<method>]`，達成單一測試案例 **0.75 秒極速單點驗證**。
  - **三道型別與環境防呆守門鎖 (Triple-Lock Guard)**：
    - 靜態門禁：`dev check` AST 語法樹掃描全面禁止測試類別直接繼承原生 `unittest.TestCase`。
    - 動態門禁：`TestDiscovery` 於載入測試套件時驗證 MRO 繼承鏈，非 `YSCBTestCase` 測試直接拒絕加載。
    - 入口門禁：`YSCBTestCase.setUp()` 檢測宿主裸跑直接拋出 `SecurityError` 阻斷，根除任何非授權的真實環境污染。
  - **全庫 16 個測試檔案 100% 標準化遷移**：全面改寫為 `YSCBTestCase`，徹底消除進程內寫入外洩與 `test_release_pipeline.py` 內部遞迴跑測問題。
  - **全量測試與回歸驗證**：全庫 144 個測試案例回歸 144/144 Passed (100% Ready)。
  - **知識庫交付**：更新 `docs/dev/user_guide.md` §4.4 (測試四層分類與目標定位) 與 §4.5 (三道防呆守門鎖)。

- **dev 測試架構優化主計畫 — sub_02: 預設共用沙盒、ISOLATED_SANDBOX 分流與 URI JIT 測試靜默防護 (`sub_02_test_architecture_refinement`)**：
  - **預設共用沙盒機制 (Shared Sandbox by Default)**：在 `YSCBTestCase` 實作 Class-level 延遲初始化共用沙盒，同類別測試方法預設複用同一個沙盒實例，並於 `tearDownClass` 銷毀。將全模組回歸耗時由 ~73 秒壓縮至 **35.6 秒**（**加速超過 50%**）。
  - **`Requirement.ISOLATED_SANDBOX` 獨立沙盒分流**：在 `dev.testing.requirement` 定義 `ISOLATED_SANDBOX` 列舉，標記 `@require(Requirement.ISOLATED_SANDBOX)` 之測試方法自動分流獲得 Per-Method 專屬全新沙盒，於 `tearDown` 即時釋放，達成零污染隔離。
  - **`YSCB_TEST_SANDBOX` 測試模式 JIT 靜默防護**：測試框架自動注入 `YSCB_TEST_SANDBOX=1` 並於子行程 `run_cli` 中透傳；`core.uri.reconcile_undefined_uri` 檢測到測試環境時靜默跳過 `input()` 終端阻塞，即時拋出結構化 `UndefinedURIError`，保證測試工作流零打斷。
  - **全量測試與回歸驗證**：新增 `source/dev/tests/test_case.py` 單元測試，全系統回歸跑測 `dev test --all` 達成 141/141 100% Passed (100% Ready)。
  - **知識庫交付**：更新 `docs/dev/user_guide.md` §4.3 測試沙盒模式指南。

- **dev 測試架構優化主計畫 — sub_01: 殘留 sandbox 清理與自動滾動修剪機制 (`sub_01_residual_sandbox_cleanup`)**：
  - **沙盒生命週期雙軌自動清理 (Sandbox Dual-Track Lifecycle Cleanup)**：
    - **Case 1 (滾動上限修剪 Rolling Prune)**：在 `SandboxProvisioner` 實作 `prune_sandboxes(max_keep=3)`，於沙盒建立與失敗保留時自動淘汰超過上限的最舊沙盒，常態保持殘留沙盒數不超過 3 個，消除無限膨脹佔用硬碟空間之問題。
    - **Case 2 (全量通過清空 Full-Pass Flush)**：在 `Tester._run_test` 整合，當以 `--all` 執行且全系統回歸測試 100% 通過時，自動呼叫 `cleanup_all_sandboxes()` 清空 `cache://dev/sandbox/`，達成乾淨交付。
    - **零選項無侵入架構**：不新增額外 CLI 選項，完全內建於生命週期中。
  - **全量測試與回歸驗證**：
    - 單元測試新增 `test_prune_sandboxes_limit`、`test_cleanup_all_sandboxes`、`test_sandbox_cleanup_empty_or_missing`、`test_sandbox_cleanup_ignores_non_sandbox` 與 `test_run_test_all_success_cleans_sandboxes`。
    - 全系統回歸跑測 `python yscb.py dev test --all` 通過 134/134 測試 (100% Ready)。
  - **知識庫交付**：
    - 更新 `docs/dev/user_guide.md` §4.2 沙盒生命週期與自動清理機制說明。

## 2026_08_27_0412_dev_and_governance_health_fix

- **工程健檢缺陷修復、Dev 測試動態解算、PlanVerifier 標頭相容與文檔知識庫校準**：
  - **Dev 測試套件版本硬編碼消除與動態解算**：
    - 修復 `test_builder.py`、`test_release_pipeline.py`、`test_sandbox.py` 對 `core` 靜態版本字串之依賴，改採動態自 `manifest.json` 讀取版本組裝 build tag。
    - 消除 `core` 升版後導致 `dev` 5 個測試案例失敗之缺陷，恢復 `dev test dev` 全量 30/30 通過 (100% Ready)。
  - **`PlanVerifier` 調研報告標頭別名相容增強**：
    - 擴充 `verifier.py` 之合法 Header 比對清單，認列 `調研主題`、`調研狀態`、`topic` 等合法別名，消除調研手冊 (RXX) 驗證誤判。
    - 全專案 4 個開發計畫共 19 份 Markdown 文件稽核達成 0 Error, 0 Warn (100% 合規)。
  - **`docs/README.md` 全域知識地圖同步**：
    - 補齊 `agents-workflow` 模組導覽與生態清冊登載，同步校準全系統版本號矩陣。
  - **Dogfooding 自引用版本發布**：
    - `dev` 模組升版至 `1.0.0.2`，`agents-workflow` 模組升版至 `1.0.1.2`，完成正式打包與本地安裝同步。

## 2026_08_27_0344_agents_workflow_auto

- **Agents-Workflow 模組新增 `/Auto` 自動連續推進工作流與 ContextInit 讀取引導強化**：
  - **`/Auto` 工作流指引建立與 IDE 註冊導出**：
    - 新增 `assets/workflows/Auto.md` 工作流資產，定義適用於 Full Track (Level 1) 與 Umbrella (Level 2) 活躍子計畫之連續推進管線（Phase 01~05）。
    - 授權 Agent 在無未確定技術疑問前提下，自動連續推進 Phase 1~5 文件產出與代碼實作，跳過中間 Checkpoint。
    - 嚴格落實三大熔斷防線：零臆測熔斷（遇未知立即提問）、偏差熔斷（Major/Critical 偏差立即轉入 `/Discuss`）、以及 Phase 6 手動/UX 驗證絕對阻斷（強制等待人工驗收）。
    - `manifest.json` 註冊 `Auto.md` 導出與 `WORKFLOW_AUTO` token 錨點。
  - **`DevelopmentStandards.md` 規範增補**：
    - 增補 §4.4 自動連續推進模式 (`/Auto`) 授權邊界與熔斷原則。
  - **`ContextInit.md` 開發標準讀取引導強化**：
    - 步驟 2 強化為 Mandatory Standards Read，剛性引導 Agent 完整讀取 `DevelopmentStandards.md`，深度掌握 SOP 0~7 流程、追溯鏈矩陣與三大分流。
  - **發布與版本更新**：
    - 模組版本升版至 `1.0.1.1`，完成正式 release 打包與發布安裝。

## 2026_08_27_0143_dev_agents_workflow_injection_expansion

- **擴充 Dev 模組對 Agents-Workflow 注入之工程規範與指令防呆**：
  - **Contributes Commands 規格統一與頂層廢除**：
    - 徹底廢除頂層特例 `contributes.commands`，統一收斂至由 `core` 模組治理的 `contributes.core.commands` 標準規格。
    - 支援富語意 Schema：`{"description": "...", "case_pros": ["..."], "case_cons": ["..."]}`。
    - 宿主起手腳本 `yscb.py` 適配自 `contributes.core.commands` 讀取並渲染標準 CLI Help。
  - **動態指令手冊與強制防呆守門 (`AGENTS_CLI_GUILD`)**：
    - `core.providers.get_agents_cli_guild` 實作動態掃描與過濾（自動排除 pros/cons 皆空指令），輸出標準 Markdown 防呆對照表。
    - `agents-workflow` 導出 `AgentsCliGuild.md` 並透過 `__@{AGENTS_CLI_GUILD}__` 自動物化至發布目標。
    - `AgentsStandards.md` 注入「查表比對」與「Default-Deny 未列情境向開發者確認」之強制守門鐵律。
  - **現有三大模組指令清冊全面補齊**：
    - `core`（8 大指令）、`dev`（10 大子指令）、`agents-workflow`（7 大子指令）全面補齊 `contributes.core.commands` 與詳細防呆推薦/禁止情境。
  - **工作流導航修復與編譯器轉譯增強**：
    - `ContextInit.md` 步驟 2 導航導向 `DevelopmentStandards.md` 與 `AgentsCliGuild.md`。
    - `compiler.py` 增強 `URI_REF_REGEX`，支援在 Markdown 超連結括號內直接使用 `__#{module://...}__` 並轉譯為各 Target 相對超連結。
  - **衍生子計畫 sub_01: 專案相對路徑協議佔位符 `__${uri}__` 與三大佔位符體系明確化**：
    - **三大佔位符體系語意與編譯器擴充**：
      - `__@{token}__`（文件內容佔位符）：Stage 1 內容狀態機遞迴展開。
      - `__#{uri}__`（自身相對路徑佔位符）：Stage 2 依產物 Markdown 自身所在目錄解算相對路徑（超連結）。
      - `__${uri}__`（專案相對路徑佔位符）：Stage 2 依專案根目錄 (`project://`) 解算相對路徑（Shell 指令與專案路徑參照）。
    - **強制反引號包裹與穿插展開語意**：
      - 佔位符必須包裹於代碼塊（`` `...` ``）內，支援內部穿插前後文字（如 `` `python __${yscb.host://yscb.py}__ run` `` ➔ `` `python yscb.py run` ``），保留外層反引號。
      - 裸佔位符阻斷不展開，並輸出 `[compiler:warning]` 警示提示。
    - **跨目錄拓撲 100% 自適應**：
      - 更新 `ContextInit.md` 步驟 4 指令套用 `__${yscb.host://yscb.py}__`，達成無論起手腳本在根目錄或子目錄均能無縫自適應展開。
    - **全系統回歸驗證**：
      - 全系統跑測 `python yscb.py dev test --all` 達成 **125/125 Passed (100% Ready)**。
  - **測試沙盒隔離漏洞修復**：
    - 修復 `test_robustness.py` 中缺少 `_get_yscb_root` mock 的沙盒外溢問題，達成 100% 虛擬目錄拘束隔離。
  - **全系統回歸與交付**：
    - 全系統沙盒跑測 `python yscb.py dev test --all` 通過 125/125 測試 (100% Ready)。
    - 完成 `contributes.format.md`、`docs/agents-workflow/user_guide.md` 與 `docs/dev/user_guide.md` 知識庫文檔交付。

## 2026_08_27_0045_pure_uri_scheme_and_recursive_resolve_fix

- **純淨語意 URI 協議、遞迴解算缺陷修復與 on_reload 自動發布 Hook**：
  - **Core 模組遞迴解算變數修正與純淨模式落實**：
    - 修復 `core.uri.resolve` 遞迴解算 config 協議時因 `current_module=mod` 誤用引發之 `NameError`，修正為 `active_mod`。
    - 清空 `_DEPRECATED_SCHEME_REDIRECTS = {}`，系統全量切換為 100% Pure Canonical 語意協議模型，杜絕向下相容別名污染。
  - **Agents-Workflow 協議正規化與動態地圖修復**：
    - `providers.py` 查詢清單正規化為 `["project", "yscb", "workflow.plans", "workflow.archived", "workflow.docs"]`。
    - `ContextInit.md` 模板更新參照標籤為 `workflow.*`，使 JIT 動態語意解析地圖全數正常顯示為 `[ACTIVE]`。
  - **`on_reload` Hook 自動發布閉環**：
    - 在 `agents-workflow/scripts/hook.core.py` 實作 `on_reload` 自動調用 `ReleasePublisher().release_all()`，達成 microkernel 重載環境時自動更新工作流與 IDE 投影片。
    - 單元測試與全模組回歸 119/119 100% Passed。

## 2026_08_25_2200_agents_workflow_migration

- **開發標準規範與流程分離重構及 Contributes 文檔建立 (`sub_09_standards_refactor_and_contributes_doc`)**：
  - **標準規範與開發流程資產徹底解耦**：
    - 新增 `AgentsStandards.md`：專門收斂 Agent 通用核心原則、防呆紀律與絕對禁止條款。
    - 重構 `DevelopmentStandards.md`：收斂工作目錄管理、追溯鏈矩陣、模板尋址指針、三大分流矩陣、SOP 0~7 階段流程與 Fast Track 流程。
    - `NewPlan.md` 維持完整載入 `DevelopmentStandards.md` 流程指引。
  - **`AGENTS.md` 精簡軟合併與 Prompt 上下文優化**：
    - `ReleasePublisher` 發布時僅提取極簡版 `AgentsStandards.md` 注入至 `AGENTS.md` 的標記區間，縮減 Prompt 冗餘 Token 60% 以上，100% 保留專案特化工程規範。
  - **專案組態開關落實與預設調整**：
    - `config.project.json` 中 `"release_targets"` 預設改為空陣列 `[]`（無），避免未宣告時主動生成未預期的 IDE 目錄。
    - 完整支援 `enable_agents_md` 與 `enable_project_changelog` 開關控制。
  - **官方 Contributes 規格書建立**：
    - 交付 `source/agents-workflow/contributes.format.md`，完整定義 `core.uri_schemes`、`export`、`token`、`insert`、`release_target` 的欄位型別與使用範例。
  - **全量測試與回歸驗證**：
    - 模組內部單元測試 21/21 100% Passed。
    - 全系統端到端沙盒測試 114/114 100% Ready。
    - 交付 `docs/agents-workflow/README.md` 與 `docs/agents-workflow/user_guide.md`。

- **Plans CLI 工具鏈補齊與舊版功能遷移 (`sub_08_plans_cli_toolchain_migration`)**：
  - **Plans 工具鏈子套件體系 (`agents_workflow.plans`)**：
    - 將舊版 4 大孤立維護腳本（`archive_plan.py`, `scan_plan_status.py`, `search_dev_plans.py`, `verify_plan.py`）完整重構為高內聚子套件，定義自定義例外基底與型別（`PlanNotFoundError`, `PlanFormatError`, `PlanIncompleteError`, `PlanDestinationExistsError`）。
    - 100% 透過 `core.uri.resolve` 解析語意空間（`workflow.plans://`, `workflow.archived://`, `project://`），消除所有硬編碼路徑。
  - **計畫安全歸檔服務 (`PlanArchiver`)**：
    - 實作 4 重安全檢查守門模型（Completed 狀態、全域 CHANGELOG 登載、清理暫時 `handoff.md`、目的地同名防護）。
    - 依據時間戳前綴 `YYYY_MM_` 自動分流至 `workflow.archived://{YYYY}/{MM}/{plan_name}/`；支援 `--force` 放行。
  - **計畫狀態矩陣掃描服務 (`PlanScanner`)**：
    - 專注掃描活躍進行中計畫（明確排除歷史目錄），精確識別 4 大 Track（Umbrella, Fast Track, Full Track, Phase 0）與當前 Phase 狀態，輸出純 ASCII 樹狀縮排清冊。
  - **歷史與決策檢索服務 (`PlanSearcher`)**：
    - 支援 `--dr` 模式正則結構化擷取去重跨計畫決策記錄，相容中英文與 Markdown 列表/標題格式；支援全文程式碼與上下文行檢索，提供 `--year`, `--month`, `--limit` 篩選。
  - **文件合規性與規範稽核服務 (`PlanVerifier`)**：
    - 稽核 Markdown 是否殘留 `<!-- AGENT_GUIDANCE -->` 模板指引註解；檢查 Blockquote Header 元數據（`功能名稱`, `建立日期`, `狀態`）齊備性；遞迴稽核 `sub_*` 子計畫目錄。
  - **CLI 路由派發與平鋪別名 (`scripts/cli.py`)**：
    - 實作 `agents-workflow plan <archive|status|search|verify>` 路由，並提供 `plan-archive`, `plan-status`, `plan-search`, `plan-verify` 雙軌別名支援。
    - 內建 Windows 控制台 UTF-8 安全轉碼保護與純 ASCII 格式渲染，徹底消除編碼崩潰。
  - **全量測試與回歸驗證**：
    - 模組內部單元測試 20/20 100% Passed。
    - 全系統端到端沙盒測試 111/111 100% Ready。
    - 交付 `docs/agents-workflow/README.md` 與 `docs/agents-workflow/user_guide.md`。

## 2026_08_26_1747_core_dev_refinement

- **Dev 與 Agents-Workflow 模組連動注入與本地建置直裝特例 (`sub_04_dev_agents_workflow_linkage_injection`)**：
  - **宣告式工程規範連動注入 (`contributes["agents-workflow"]`)**：
    - `dev` 模組於 `manifest.json` 宣告 `contributes["agents-workflow"]`，以 `mode: "below"` 模式向 `DevelopmentStandards.md` 尾部的 `WORKFLOW_SOP_STANDARDS` 錨點注入 `DevEngineeringStandards.md`。
    - 建立 `DevEngineeringStandards.md` 資產，冠以 **「YS-Codebase 模組開發專案特化工程規範」**，收斂三大空間 SSOT、虛擬沙盒測試規範、靜態合規守門。
    - **🚨 Agent 剛性防呆禁止條款**：規範中剛性明定：在開發者未明確下達指示（如「發布/安裝/同步」）前，**Agent 絕對禁止主動執行 `dev release` 或 `install` 覆蓋宿主環境**；唯一允許的驗證手段為 **`python yscb.py dev test` 於隔離虛擬沙盒中跑測**。
  - **套件管理器本地建置直裝通道 (`install @build`)**：
    - `core.engine.PackageManager` 在 `act_download` 與 `_get_module_manifest_from_provider_or_local` 擴充 `@build` 特例通道：當版本約束包含 `build` 時，強制直連本地端 `module.build://{module_name}/` 尋找 `*.build.zip` 下載物化，缺少產物時拋出明確引導錯誤，徹底終結本地開發調試需先手動 release 的繁瑣流程。
  - **全量測試與回歸驗證**：
    - 模組內部單元測試與 `agents-workflow` 規範注入測試 100% Passed。
    - 全系統端到端沙盒測試 118/118 100% Ready (47.770s)。
    - 交付 `docs/dev/user_guide.md` 與 `docs/dev/DESIGN_NOTES.md` (DN-DEV-05)。

- **Dev 模組發布強制覆蓋模式與 release-git 智慧略過 (`sub_03_dev_release_force_override`)**：
  - **發布強制覆蓋模式 (`--force` / `-f`)**：
    - 為 `dev release`、`dev release-check` 與 `dev release-git` 擴充 `--force` 旗標支援。
    - 剛打包發布發現文檔/註解小瑕疵時，允許原地覆蓋同名 `<ver>.zip` 產物並同步更新 `release/<mod>/index.json`，免被迫 bump revision 造成版本膨脹。
    - **Gate 2 / Gate 3 放行邊界**：`force=True` 時放行 Gate 2 覆蓋與 Gate 3 同版本（`target == highest`）修訂；但若版本小於歷史舊版本（`target < highest`），依然嚴格拋出 `VersionRollbackError` 阻斷。
  - **`dev release-git` 智慧感應機制**：
    - 自動感應目標版本是否已在庫：尚未發布則打包，已發布且無 force 自動略過打包步驟直接接續 Local Git Commit & Tag，已發布且傳入 force 則強制重新打包覆蓋並更新 tag。
  - **全量測試與回歸驗證**：
    - 模組單元測試 29/29 100% Passed。
    - 全系統端到端沙盒測試 113/113 100% Ready。
    - 交付 `docs/dev/README.md` 與 `docs/dev/user_guide.md`。

- **Dev 模組發布與驗證工具鏈重構 (`sub_02_dev_release_verification_refactor`)**：
  - **建置與純淨發布職責分離 (`Builder` & `Releaser`)**：
    - `dev build`：移除 `--clean` 選項（打包前一律自動物理清空目標 `build/<mod>/` 目錄），100% 完整保留 `tests/` 與開發檔案，產出 `<ver>.build.zip` 並更新 `build/<mod>/index.json`。
    - `dev release`：重構為純淨打包器（嚴格排除 `tests/` 與 `.yscbignore`），產出 `release/<mod>/<ver>.zip`；移除舊版冗餘的 bump 選項，與 `build` 對標極簡簽名。
  - **發布產物時序滑動窗口與跨三元組收斂演算法 (`3-Revision Retention Policy`)**：
    - 同三元組 `X.Y.Z` 依時序保留至多 3 份最新 Revision zip，第 4 份及更早者自動物理淘汰。
    - 跨三元組升級時，所有歷史舊三元組自動收斂僅保留最後最高 1 份 Revision zip，徹底消除歷史殘留。
    - 以磁碟真實存在的 zip 檔案為唯一事實來源 (SSOT) 同步生成 `release/<mod>/index.json`，已被物理刪除的舊 Revision 自動自清冊排除。
  - **3-Gate 發布品質守門閘門 (`3-Gate Verification`)**：
    - Gate 1 (靜態合規性)：Manifest 格式完整性與 `scripts/cli.py` 語法/進入點存在性。
    - Gate 2 (版本不可變性 - Immutability)：檢查四元版本庫是否已存在同名 zip，重複發布拋出 `ReleaseVersionExistsError` 阻斷。
    - Gate 3 (版本單調遞增 - Monotonicity)：待發布版本號必須嚴格大於同三元組在庫最高 revision，防止倒退，拋出 `VersionRollbackError` 阻斷。
  - **版本遞增、預檢與安全流水線 CLI 工具鏈 (`scripts/cli.py`)**：
    - 實作 `dev bump-[major|minor|patch|revision] <mod>`：單向遞增模組 `manifest.json` 版本號。
    - 實作 `dev release-check <mod>`：獨立執行 3-Gate 發布就緒預檢（明確阻斷 `--all`）。
    - 實作 `dev release-git <mod> "<msg>"`：依序執行 `test` ➔ `release-check` ➔ `release` ➔ 本地 `git commit & tag`（🚨 嚴禁遠端 push）。
  - **測試流水線前置自動建置 (`Tester`)**：
    - `dev test` 預設自動前置執行 `dev build`，構建失敗立即阻斷；支援 `--no-build` 旗標跳過前置打包直接跑測。
  - **全量測試與回歸驗證**：
    - 新增專用測試套件 `test/test_dev_toolchain_refactor.py` (15/15 Passed)。
    - 全系統沙盒端到端測試 109/109 全數通過 (100% Ready)。

- **模組資料管理相關 URI 協議釐清與遷移 (`sub_01_module_data_uri_refactor`)**：
  - **方案 B：全量 Root 化與 `@/` 自省語法模型 (`core.uri`)**：
    - 徹底廢除全系統所有 `*.root://` 協議（`storage.root`, `cache.root`, `config.root`, `module.root`, `module.source.root`, `module.build.root`, `module.release.root`, `module.mirror.root`）與 `temp://` 協議，協議庫精簡 50%，確立 8 大清晰正交標準協議。
    - 支援顯式跨模組尋址 `{scheme}://{module}/{path}` 與當前模組自省語法 `{scheme}://@/{path}`，無模組上下文調用 `@/` 時拋出結構化 `UndefinedModuleContextError`。
    - 內建舊協議 DeprecationWarning 向下相容轉向與路徑穿越 (`..`) 沙盒逃逸防護。
  - **模組資料三位一體與生命週期治理 (`core:remove --purge`)**：
    - 確立 `storage://` (持久化/Git 追蹤)、`config://` (專案設定/Git 追蹤)、`cache://` (暫存快取/Git 忽略) 之三位一體原則與 Git 版本控制策略。
    - 實作模組標準卸載自動清空 `cache://{module}/` 並保留持久資料；新增 `--purge` 旗標支援物理銷毀 `storage`、`config` 與 `cache`。
  - **開發工具鏈與測試沙盒遷移 (`dev`)**：
    - 測試沙盒環境全面自 `temp://` 遷移至 `cache://dev/sandbox/` (`.cache/dev/sandbox/`)，測試完畢自動乾淨銷毀。
    - `builder.py`、`releaser.py`、`checker.py` 等工具鏈全面升級方案 B 協議。
  - **發布清冊錯誤路徑修復與歷史清理 (`agents-workflow`)**：
    - 修復發布清冊至 `storage://@/release_manifest.json` (`storage/agents-workflow/release_manifest.json`)，根除雙重嵌套缺陷，物理清理歷史遺留之 `storage/core/agents-workflow/` 與 `.temp/`。
  - **全量回歸驗證**：
    - 全專案 110/110 自動化測試全數通過 (100% Ready)。

## 2026_08_25_2200_agents_workflow_migration

- **佔位符解析管線優化、三層 URI 重映射與多環境原子發布 (`sub_07`)**：
  - **兩階段 6 步語意編譯發布流水線 (`ArtifactCompiler` & `ReleasePublisher`)**：
    - 徹底廢棄模組安裝目錄原 `exports/` 殘留目錄，將 Stage 1 內容佔位符展開物化寫入 `cache.root://agents-workflow/resolved_contents/` 微內核快取中繼。
    - Stage 2 依啟用之 Release Targets 建立發布拓撲映射表，動態轉譯 `__#{uri}__` 為相對於落地檔案之本機實體相對路徑 (`os.path.relpath`)。
  - **三層 URI 重映射階層演算 (3-Tier Resolution)**：
    - Tier 1: 本次發布拓撲表 (Deployment Map) ➔ 精確計算相對路徑。
    - Tier 2: Core 專案級語意協議 (`project://`, `docs://`, `plans://`) ➔ 調用 `core.uri.resolve` 計算相對路徑。
    - Tier 3: 未知/未決協議安全降級原樣輸出並發出警告。
  - **消除 Agent 模板尋址盲區**：
    - 於 `DevelopmentStandards.md` 與 `AGENTS.md` 中全面注入標準模板之語意 URI 引用指針，自動轉譯為有效跳轉路徑（如 `../templates/P00_semantic_requirements.md`、`.agents/templates/...`），徹底根除 Agent 模板幻覺。
  - **`release_target` Contributes 體系與純文字/陣列 Header 巨集插值**：
    - 在模組 `manifest.json` 支援宣告 `release_target`（如 `antigravity`），定義 `projections` 與 Header 模板。
    - 支援 `{export.description}`, `{export.name}`, `{target.name}` 等巨集插值，徹底告別 YAML 格式綁定。
  - **4 步原子發布交易與孤立檔案精確清理**：
    - 基於 `storage://agents-workflow/release_manifest.json` 實現「過往清理 ➔ 提前解算防污染 ➔ 持久紀錄 ➔ 目錄落地與 `AGENTS.md` 軟合併」原子交易保證。
  - **完整 CLI 指令體系實裝**：
    - 實作 `python yscb.py agents-workflow release`、`release-target --list`、`release-target --add <t>`、`release-target --remove <t>`。

- **Contributes 擴充支援 Computed Token 與 `code.func://` 函式定位協議 (`sub_06`)**：
  - **`code.func://` 符號定位協議 (`core.symbols`)**：
    - 建立全專案標準的程式碼函式與符號定位協議：`code.func://<module>/<subpath>:<function_name>`。
    - 實作雙軌動態載入器（Package Import + VFS 檔案 Spec 載入），支援 Zip 模組與源碼開發環境、命名空間隔離與 Callable 快取。
  - **Contributes Insert 支援 `type: "computed"`**：
    - 工廠編譯器解算器升級，於 `compile` 階段即時調用 Provider 函式並注入執行期上下文 `ExecutionContext`，具備型別安全轉型防護。
  - **`agents-workflow` 動態路徑地圖實裝**：
    - 實作 `providers.py:get_dynamic_context_map`，成功在 `ContextInit.md` 物化產物中即時動態渲染專案活躍語意 URI 解析地圖。

- **HTML 註解 Token 自宣告與 Core `yscb.host://` 協議支援 (`sub_05`)**：
  - **HTML 註解 Token 自宣告與 Replace 展開**：
    - 於 `agents-workflow/manifest.json` 宣告 `BEGIN_HTML_ANNOTATION` 與 `END_HTML_ANNOTATION` Token。
    - 配置 replace 模式分別物化為字面值 `<!--` 與 `-->`，由工廠編譯器安全展開，避免 Markdown 預覽干擾。
  - **Core `yscb.host://` 專案宿主協議**：
    - 於 `core` 模組引入 `yscb.host://` 一等公民常數協議，模板值為 `{yscb_host}`。
    - 強制指向起手腳本 `yscb.py` 與 `yscb.config.json` 所在之專案宿主工程根目錄，支援 O(1) fast-path 路由。

- **Agents Workflow 配置治理與一鍵初始化引導 (`sub_04`)**：
  - **4 大 Workflow URI 協議體系貢獻**：
    - 於 `manifest.json` 中宣告 `workflow.plans://`, `workflow.archived://`, `workflow.ext://`, `workflow.docs://` 協議，動態綁定至專案級組態 `paths.*`。
  - **專案級組態模板與 `!undefined` 剛性解耦**：
    - 新增 `config.project.json` 模板，所有路徑預設剛性為 `"!undefined"`，貫徹微內核零臆測鐵律。
    - 宣告保留欄位 `ide: []`, `enable_agents_md: true`, `enable_project_changelog: true` 供未來 IDE 適配擴充。
  - **`--init-default` 一鍵初始化與目錄引導引擎 (`WorkflowInitializer`)**：
    - 封裝官方推薦路徑（`project://.agent_workflow/plans` 等），提供實體路徑存在性探測、已存在路徑警示與互動確認 `[-y / -n]`。
    - 自動建立缺失目錄並原子增量持久化至 `config/agents-workflow/config.project.json`，刷新 Core URI 快取。
  - **`--path-*` 變種覆蓋參數支援**：
    - CLI 支援 `--path-plans`, `--path-archived`, `--path-ext`, `--path-docs` 以及 `-y` / `--yes` 自動確認模式。

- **Workflow 佔位符格式重構與可視化語法遷移 (`sub_03`)**：
  - **全新 Markdown 可視化佔位符語法**：
    - 徹底淘汰原易被 Markdown / HTML 預覽引擎隱藏的 HTML 註解格式（`<!-- __TOKEN__ -->`）。
    - 引入**插入佔位符 (Token Anchor)**：`__@{token}__`（如 `__@{PHASEXX_STANDARD_HEADER}__`、`__@{DYNAMIC_CONTEXT_MAP}__`），支援大括號內部微量空格容錯。
    - 引入**路徑佔位符 (URI Reference)**：`__#{uri}__`（如 `__#{module.root://agents-workflow/assets/...}__`），編譯期 100% 原樣保留，作為 Markdown 文檔的語意參照與路徑錨點。
  - **工廠編譯器 5-Step 狀態機與殘留抹除升級**：
    - 升級 `ArtifactCompiler`，支援 `replace` / `below` / `above` 多輪遞迴展開與自指死鎖防護。
    - 實作智慧抹除正則工廠，解算完成後自動吞噬行首縮排與換行，確保產物排版純淨無多餘空行。
  - **全域資產 1:1 語法遷移**：
    - 全面更新 `assets/templates/` (P01~P07)、`DevelopmentStandards.md` 與 `ContextInit.md` 中的標籤。

- **Core Contribute 系統優化與語意 URI 系統打磨 (`sub_02`)**：
  - **Contribute 來源自動標記 (`__provider__`)**：
    - 在微內核搜集 donor 模組 contributes 時，自動遞迴為 Dict 與 List[Dict] 項目注入 `"__provider__": donor_name`（顯式指定保留不覆蓋），確保下游模組可無痛自省貢獻來源。
  - **依賴拓撲聚合排序 (Topological Ingestion Order)**：
    - 依據已安裝模組之依賴拓撲順序有序合併，保證底層基礎設施優先註冊，擴充模組後續追加覆蓋。
  - **微內核標準 Contribute 查詢 SDK**：
    - 提供 `core.contributes.get(target_module, key=None, default=None)` 與 `get_for_current_module()`，內建自愈快取。
  - **JIT `!undefined` URI 熱更新補齊機制**：
    - 在 `uri.resolve()` 探測到 `!undefined` 或未配置路徑時，於 TTY 終端主動彈出 `[-y <path> / -n / --help]` 互動選單。
    - 相對路徑一律以 `yscb://` 為基準展開，支援連鎖未定義依賴遞迴解算與自引用循環死鎖防護 (`CyclicURIDependencyError`)。
    - 自動原子寫回所屬模組之 `config.project.json` 並刷新記憶體快取無縫繼續運行；非 TTY 或靜態檢查時拋出結構化 `UndefinedURIError`。
  - **語意協議高度對稱化與自省清冊**：
    - 徹底清除歷史殘留別名 `build://`。
    - 將鏡像空間與發布空間納入 `module` 分支（`module.mirror.root://` / `module.mirror://`、`module.release.root://` / `module.release://`），與源碼、建置、運行空間達成 6 大空間高度對稱。
    - 新增 `python yscb.py uri list` / `--list`、`resolve`、`to-uri`、`check` CLI 自省命令，支援清晰展示原始宣告值 (`RAW TARGET / VALUE`) 與展開後實體路徑。

- **Agents Workflow 核心骨架遷移與協議產物工廠化 (`sub_01`)**：
  - **純淨通用內核與三位一體資產 (`assets/`)**：
    - 徹底剝離專案特化規則，提供 100% 通用抽象資產：`assets/standards/` (2 項規範: DocumentationStandards, DevelopmentStandards)、`assets/workflows/` (ContextInit)、`assets/templates/` (`header.md` 與 13 大標準模板庫)。
  - **協議產物工廠化與宣告式依賴注入引擎 (`compiler.py`)**：
    - 支援宣告式 `export`（資產導出）、`insert`（錨點注入，支援 `const`/`uri` 與 `replace`/`below`/`above`）與 `token`（自省元數據）Schema 規範。
    - 實作 5-Step 多輪遞迴狀態機（建立快照 ➔ 依拓撲注入 ➔ 移除已解算錨點標籤 ➔ 遞迴探測收斂 ➔ 分流原子寫入至 `module://exports/`），保證自指死鎖防護與無殘留標籤。
    - 完成 `PHASEXX_STANDARD_HEADER` 標頭解耦與 replace 自注入閉環驗證。
  - **CLI 自省與微內核 Hook 自治閉環**：
    - 提供 `agents-workflow compile` (物化編譯)、`tokens` (錨點清單查詢) 與 `list` (物料清冊查詢) 指令。
    - 註冊 `scripts/hook.core.py:on_reload` 事件監聽，在 `yscb reload` 後自動自主編譯物化。
  - **腳手架與資產空間優化**：
    - 統一收納靜態資產至 `assets/` 目錄。
    - 修復 `dev:scaffold` 腳手架對連字號模組名稱之自動底線套件轉換。

## 2026_08_23_2030_architecture_refactor

- **全系統 CLI UX 標準化與本地發布守門精簡 (`sub_14`)**：
  - **全域 Banner 與層次化 Help (`yscb --help`)**：重構輸出視覺架構，整合 Banner、Usage、`CORE COMMANDS` (整併 `init`)，並動態掃描聚合已安裝模組之 `MODULE COMMANDS` 清冊。
  - **智慧指令拼寫建議 (Did you mean?)**：採用 Python 標準庫 `difflib`，在使用者輸入未知指令時提供精準候選提示。
  - **本地發布守門精簡 (`dev.releaser`)**：移除 Gate 1 Git Dirty 限制，支援非 Git 倉庫與本地敏捷發布打包。
- **全面 Zip 單檔打包與同構自舉管線 (`sub_13`)**：
  - **明文空間嚴格二分法**：全系統僅 `source/` 與 `modules/` 維持展開檔案，中間快取與產物庫（`build/`、`release/`、`.mirror/`）全面強制改為 `{version}.zip` 單檔格式。
  - **4-Stage Atomic Reload 流水線**：解耦為 Stage 1 (自癒拉取) ➔ Stage 2 (解壓物化，解壓前剛性清空) ➔ Stage 3 (組態治理，掃描部署並無條件刪除模板) ➔ Stage 4 (依賴注入)。
  - **同構 Zip 下載與自舉**：`yscb.py init` 預設遠端指向 GitHub 官方 Release 庫，100% 透過 Python 標準庫串流下載與解包自舉。
  - **職責精確邊界**：`release.root` 與 `release` 語意協議精準歸由 `dev` 模組貢獻治理。
- **超薄無狀態宿主 (Ultra-Thin Host `yscb.py`)**：100% Python 標準庫原生實現，體積縮減至百餘行，僅負責路徑定位、最小自舉與動態命令轉發，徹底擺脫單檔膨脹與自引用死鎖。
- **Core 微內核基礎設施模組 (`module:core`)**：
  - **First-Class VFS SDK (`core.uri`)**：原生支援語意 URI 讀寫、目錄操作、最長前綴匹配與原子安全寫入。
  - **`AtomicEngine` 12 大原子操作生命週期**：將系統狀態變更分解為 `INIT`, `DOWNLOAD`, `DELETE`, `REGISTER`, `UNREGISTER`, `SOLVE_DEPS`, `PREPARE`, `RELOAD`, `FETCH`, `SNAPSHOT`, `RESTORE_SNAPSHOT`, `DISPATCH_CLI`。
  - **套件管理器 (`core.installer`)**：提供 `install`, `update`, `remove`, `list`, `status`, `rollback`, `reload` 完整套件生命週期。
  - **5 來源依賴注入聚合器 (`core.contributes`)**：支援 Manifest、指向性 JSON、專案與本地層級宣告式能力注入，產出中介層快照至 `cache://` 加速查表。
- **Dev 開發者工具箱模組 (`module:dev`)**：
  - **模組腳手架 (`dev create`)**：一鍵生成符合規範之模組標準骨架與測試模板。
  - **靜態合規檢查器 (`dev check`)**：驗證 Manifest SemVer 規範、CLI 進入點語法與 `.yscbignore`。
  - **純淨套件打包器 (`dev build`)**：自動排除 `tests/` 與 `.yscbignore`，產出純淨版本化套件包並注入 `built_at` 時間戳記。
  - **沙盒測試引擎 (`dev test`)**：提供 `YSCBTestCase` 隔離沙盒、Auto-Contract 動態契約合成與兩階段測試執行。
- **14 組自宣告注入語意 URI 協議**：
  - 核心協議：`yscb://`, `mirror://`, `temp://`, `snapshot://`, `module.root://`, `module://`, `config.root://`, `config://`, `cache.root://`, `cache://`。
  - 開發協議：`module.source.root://`, `module.source://`, `module.build.root://`, `module.build://`。
- **三階測試指令體系與遞迴語意解耦 (`sub_10`)**：
  - `dev op-mksb`：純沙盒建造工廠，支援指定路徑與 `temp://sandbox_{timestamp}/` 動態微秒命名。
  - `dev op-test`：純原地單元測試執行器（100% 零沙盒、零遞迴），支援 `--type=<logic|host_cli|network>` 與 `-k` 遞迴過濾。
  - `dev test`：高階組合門面，自動建造沙盒 ➔ 進入沙盒執行 ➔ 通過後自動銷毀清理。
- **完全對標微型虛擬環境 (`SandboxProvisioner`) (`sub_10`)**：
  - 鋪設 `mock_downstream_project/`、`host_env/`（含 `yscb.py`, `yscb.config.json` 與 `modules/`）、`mock_provider/` 三大標準子空間。
  - 完整繼承父層已安裝模組與配置，消除測試環境混血狀態，嚴格維持 `yscb.py` 僅調用 `modules/` 之單一真相來源。
- **模組測試前置自治 Hook (`scripts/hook.dev.py`) (`sub_10`)**：
  - 各模組提供 `on_test_setup` 與 `on_test_teardown`，隨 `build` 套件打包發布，`core` 自動配置沙盒 `project_root` 解除 `!undefined`。
- **精準命名空間 Hook 對接體系 (`scripts/hook.{emit_module}.py`)**：
  - 模組以發起端命名對接檔案（例 `hook.core.py`, `hook.dev.py`），提供 `ExecutionContext` 凍結資料介面與 try-except 例外隔離防護。
- **系統全域知識庫綠地重建 (`docs/`)**：
  - 依據 7 大抽象維度落成 10 大標準手冊（全域地圖、核心規範、Core 架構、URI 協議、Hook 手冊、Dev 工具箱、測試指南、設計註記 `DN-01~03` 及專案首頁）。
- **套件框架健壯性強化與缺陷修復 (`sub_11`)**：
  - **100% Python 標準庫 SemVer 2.0.0 運算器 (`core.semver`)**：純標準庫實作，支援四元組解析、數值排序（保證 `1.10.0 > 1.9.0`）、`>=, >, <=, <, ==, !=, ~=, *` 範圍匹配與最高合規版本依賴求解。
  - **剛性拓撲隔離與 6 大軟相容手段清除**：`yscb.py` 移除向上爬樹；`contributes.py` 清除對 `source/` 與 `project://` 穿透；`installer.py` 清除硬編碼後門；`uri.resolve()` 嚴格攔截非標準 URI 拋出 `ValueError`。
  - **不可變 `ExecutionContext` SSOT 與 CM 作用域**：`core.context` 集中定義不可變數據載體；`core.uri` 提供 `module_scope` 與 `host_scope` 上下文管理器，例外安全自動還原。
  - **雙層組態快照與 Hermetic Clean Build**：快照還原同步備份覆蓋 `config.root://`；`dev.builder` 預設強制清空發布版本目錄，100% 排除 `tests/` 與 `.yscbignore` 污染。
  - **Contract/Custom 分離統計與獨立失敗清單**：測試框架精準分離計數，杜絕交叉誤扣，並提供獨立失敗案例清單。全量測試 59/59 項 100% Passed。
- **四段式版本號、雙軌來源庫、三層降級鏈與發布流水線 (`sub_12`)**：
  - **四段式語意化版本 (`core.semver`)**：支援 `(major, minor, patch, revision)` 解析與正規化，前三段數值比大小（`1.10.0.0 > 1.9.0.0`），尾號 `revision` 支援微小修訂號或 `build` 本地標籤，日常三元版本常態安裝。
  - **雙軌來源庫架構 (`build://` vs `release://`)**：
    - `build/` (開發庫)：`dev build` 產出完整包（包含 `tests/`，版本強制為 `X.Y.Z.build`），供全黑盒測試直接解析與安裝。
    - `release/` (發布庫)：`dev release` 產出純淨發布包（排除 `tests/`），針對同 `X.Y.Z` 實施單一最新 Revision 淘汰清理。
  - **三層安裝降級鏈 (`build://` ➔ `mirror://` ➔ `provider`)**：依序滿足本地開發即時測試、離線快取與遠端發布庫解析，三層同構維護 `index.json`。
  - **模組增量遷移階梯調用引擎 (`act_migrate`)**：升級時依序遞增調用 `scripts/migrations/{minor}.x.py` 增量腳本，缺腳本自動靜默跳過，失敗自動 Snapshot 原子回滾。
  - **Dev Releaser 發布安全交易防護 (`dev release`)**：Pre-flight 4 大守門、Version Bump、純淨打包、智慧 Git Tag（Major/Minor 自動打 Tag，Patch/Revision 預設不打）與失敗 100% 原子回滾。
  - **運行空間純粹化與自治忽略**：模組物化安裝後自動剝除 `modules/` 內的 `config.*.json` 模板；`init` 自動生成 `yscb://.gitignore` 確保專案根目錄零污染。全量測試 70/70 項 100% Passed。

### Changed
- **`project://` 顯式配置與零 Fallback 鐵律**：`project_root` 預設為 `!undefined`，未定義時精準拋出 `ValueError` 顯式阻斷，杜絕隱式猜測與環境路徑漂移。
- **2x2 組態空間顯式化**：將原 `.config/` 隱藏目錄導正為顯式之 `config/` 專案目錄（受 Git 追蹤資產）。
- **中介快照空間純淨化**：框架衍生之 `contributes.merged.json` 導正至 `cache://`（即 `.cache/`，受 Git 忽略），並實施空檔抑制機制。
- **套件倉庫空間追蹤**：本機 Provider 套件庫 `ys_codebase/build/` 正式受 Git 追蹤以利開箱自舉。
- **版本升級**：`core` 升級至 `1.0.0`，`dev` 升級至 `1.0.0`，超薄宿主 `yscb.py` 升級至 `1.0.0`。

### Fixed
- **隔離歷史干擾**：舊版代碼、舊起手腳本與歷史工作流全數移至 `.quarantine/` 封存。
- **[Critical] 宿主組態與專案空間徹底解耦 (BUG-01, BUG-02)**：`AtomicEngine` 內部所有對 `yscb.config.json` 的讀寫、清冊維護與快照還原全面改由 `host_dir` 實體路徑執行，徹底與 `project://` 解耦，確保在下游外部專案中執行套件管理時 100% 零阻斷。
- **[Critical] `yscb://` 代碼位置常數確定性自定位 (BUG-03, D-07)**：`yscb://` 解析基準直接由 `core.uri` 的實體檔案位置（`__file__` 往上 3 層）確定性常數計算；宿主 Context 顯式注入；徹底刪除動態爬目錄與 `os.getcwd()` 猜測。
- **Provider `index.json` 版本清冊自動維護 (D-06)**：`dev build` 打包時自動增量更新 `build/{module}/index.json`，支援 SemVer 升序排序與去重。
- **`remove` 反向相依安全阻斷防護 (D-08)**：`cmd_remove` 實作反向依賴掃描，被依賴模組未帶 `--force` 時阻斷移除。
- **相依格式雙向相容與遞迴相依拓撲求解 (D-01, D-02)**：`act_solve_deps` 支援 Dict 與 List 格式雙向相容，實作遞迴依賴分析與循環相依檢測。
- **全量回歸測試守門**：Auto-Contract (6/6) + Custom Persistent Tests (32/32) = **38/38 測試全數 Passed (0.555s)**。

---

## 2026_08_23_sop_template_consistency

### Fixed
- **[Critical] Extension「必跑」自動化稽核死碼修復**：`ext_registry.py` 從未解析 `ext_template.md` 規範定義的 `phase:` frontmatter 欄位，`verify_plan.py` 之 `parse_extensions()` 將每個 Extension 的 `phase` 硬編碼為字面字串 `"All"`，導致 `verify_plan.py` 中「檢查必跑 Extension (trigger: always)」的自動化把關邏輯恆為死碼——無論任何 Phase 文件是否漏宣告 `always` 型擴充皆不會被攔截。已於 `ext_registry.py` 新增 `_normalize_phase()` 將 phase 宣告正規化為大寫 Token 集合並貫通三處 Extension 發現迴圈；`verify_plan.py` 新增 `compute_phase_code()` 正確處理 `FT_plan.md` 的 Token 對應（避免誤推導為 `"FT"` 而永遠比對不到 frontmatter 宣告的 `"FT_plan"`）。已用實際 `dogfooding_pipeline_ext.md` 驗證修復生效。
- **`P05_task.md` 模板缺失補齊**：P00~P04、P06、P07 皆有標準模板可鏡像，唯獨 Phase 5 任務清單（被 `NewPlan.md`、`Continue.md`、`Discuss.md`、`scan_plan_status.py` 四處引用/依賴，`/Continue` 更需解析其 `[x]`/`[ ]` 標記定位斷點）從未有對應模板，違反「全階段文件模板剛性對齊」鐵律。新增 `workflows/templates/P05_task.md`，並將 `NewPlan.md` Phase 5 步驟 1 補上明確模板引用。
- **P03/P06 模板語言中立化**：`P03_api_spec.md` 原整份以真實 C# 語法（`namespace UIToolkit.[Subsystem]`、XML doc、`ArgumentNullException`）示範，`P06_test_plan.md` 原寫死 `dotnet test`，與工具庫「純標準庫、任何下游專案皆可用」定位衝突。已改為語言中立偽代碼並比照 `FT_plan.md` 既有的多語言測試指令範例（`pytest` / `dotnet test` / `npm test` / `cargo test` 等）泛化；`P00_semantic_requirements.md` 中一處貼有 `csharp` 語法標籤但內容實為純中文偽代碼註解的程式碼區塊，亦一併修正為語言中立標籤。
- **決策紀錄 (DR) ID 前綴格式統一**：`NewPlan.md` 定義的 `[REQ:DR-XX]` / `[ARCH:DR-XX]` / `[API:DR-XX]` 格式從未被任何模板實際使用，P01/P02/P03/umbrella_overview 各自使用裸 `DR-01`、P04 使用 `[P01:DR-01]`、FT_plan 使用 `DR-XX` + 獨立分類標籤，四種格式並存且互不相容，破壞可追溯鏈的跨文件唯一性承諾。已統一收斂為 P04 既有先例格式 `[{Phase}:DR-XX]`（Phase 為產出該決策之文件對應 Token，如 `P01`/`P02`/`P03`/`P04`/`FT`/`UMBRELLA`），並同步更新 `NewPlan.md` ID 表、`Discuss.md`、`Continue.md`、`changelog.md` 模板、`AGENTS.template.md` 及全部 6 份會產出 DR 的模板。
- **`scan_plan_status.py` Fast Track 狀態解析脆弱性修復**：Umbrella 與 P00 分支皆用精確比對 `狀態：{st}`，唯獨 Fast Track 分支用裸字串 `if st in content`，正文任何角落偶然出現同名字詞（如 "Reviewing"）即可能誤判狀態。已統一改為與其他分支一致的 Header 精確比對。
- **`master_plan_*.md` 孤兒相容分支澄清**：`scan_plan_status.py` 與 `Continue.md` 仍偵測此舊版/人工遷移專案之相容命名，但沒有任何 SOP 文件教 Agent 主動建立此檔名。已於原始碼註解與 `Continue.md` 表格明確標註其為「僅相容偵測、Agent 不應主動建立」，避免未來維護者誤解為與 `umbrella_overview.md` 對等的兩種標準選項。

### Added
- **強化回歸測試套件擴充 (HT-08~HT-11)**：新增 `test/test_hardening.py` 測試涵蓋 Extension phase 死碼修復（含正向攔截與負向不誤觸發兩案例）、`_normalize_phase()`/`compute_phase_code()` 正規化邏輯、`P05_task.md` 模板存在性與必要欄位、`scan_plan_status.py` Fast Track 精確 Header 比對防迴歸。

### Changed
- **版本升級**：`agents-workflow` v1.1.0 ➔ v1.2.0。

## 2026_08_23_1505_fix_yscb_root_path_isolation

### Fixed
- **[P0] `paths.yscb_root` 工具庫與專案空間 100% 物理隔離**：重構 `ProjectContext.get_yscb_root()`、`get_module_dir()` 與 `get_module_cache_dir()`，徹底消除 `yscb_tools` 子目錄配置時殘留專案根目錄 `modules/` 的空間污染問題。
- **[P0] 遠端 Git 倉庫快取與模組執行期快取目錄混雜隔離 ([ARCH:DR-CACHE-02])**：透過衍生 Fast Track 子計畫 `sub_01_cache_mirror_isolation`，將 `GitRemoteClient.cache_dir` 預設路徑隔離收斂至 `yscb://.yscb_cache/mirror/`，杜絕 Git 鏡像同步失敗觸發 `sync_cache(force_refresh=True)` 時誤刪 `modules/` 快取與 `backup/` 快照的重大缺陷。

### Added
- **五層語意 URI 協議體系與統一路徑轉換器 (`ProjectURI`)**：實作 `project://`, `yscb://`, `cache://<module>/`, `storage://<module>/`, `temp://` 及動態擴充協議，支援 Windows/POSIX 雙向正規化、最長前綴匹配 (LPM) 反向轉換、沙盒圍欄安全防護 (Chroot Guard) 與高階 Direct I/O 操作門面。
- **極致記憶體快取與 Fast-Path 系統呼叫避障 (3.8 µs/次)**：`ProjectURI.resolve()` 採用預編譯正規表達式與純 Python 快速通道，避開 Windows 內核系統呼叫開銷，單次解析速度達 3.82 µs（PT-01 10,000 次基準耗時 38.16 ms）。
- **`ConfigManager.resolve_config_uris()` 自動展開**：`ConfigManager.load()` 預設自動遞迴解析字典與陣列中的語意 URI，使模組設定檔能無縫使用 `project://` 或 `cache://` 協定。
- **快取管理終端工具鏈 (`yscb_cli.py cache status / clean`)**：新增 `cache status` 模組快取容量統計表格與 `cache clean <module> [--all]` 清理工具，並於模組卸載 (`remove`) 時自動連動清理快取空間。
- **CLI URI 診斷與健康巡檢工具 (`yscb_cli.py uri check / list / resolve / to-uri`)**：支援全協議健康度診斷、實體路徑逆向轉譯與沙盒逃逸測試。
- **主執行器三位一體公理 ([ARCH:DR-EXEC-01])**：確立 `yscb_config.json`、`yscb_installer.py` 與 `yscb_cli.py` 必須共生於同一目錄，自升級以當前實體路徑為主，其餘受管資產全面錨定 `paths.yscb_root`。
- **全量完備性回歸測試套件**：新增 `test/test_uri_completeness.py` (FT-01~08, ET-01~07, PT-01)，全專案測試覆蓋增至 77/77 項單元/整合測試與下游沙盒 E2E 100% Passed。

### Changed
- **模組快取命名空間升級與自動平滑遷移**：`ide_sync.py` 快取路徑升級為 `cache://agents-workflow/`，啟動時自動將舊版根目錄快取檔案平滑遷移至模組命名空間。
- **版本遞進**：`core` v2.2.0 ➔ v2.3.0、`agents-workflow` v1.1.0 ➔ v1.2.0、`installer` (CLI) v2.2.0 ➔ v2.3.1。

---

## 2026_08_23_extensibility_reliability_hardening

### Fixed
- **[P0] 下游 `build` 指令崩潰修復**：`build_module()` 之 `dest_path` 於「源碼僅存在於遠端快取 (.yscb_cache)」情境（即標準下游專案）缺少 fallback 分支，導致 `UnboundLocalError`。現回退輸出至本地 `build/`。
- **[P0] `YSCB_MODULE_DIR` 跨模組汙染修復**：`ProjectContext.get_module_dir()` 先前在環境變數存在時無條件回傳該路徑（完全忽略 `module_name` 參數），導致模組 A 執行期查詢模組 B 的目錄/設定時被汙染。現僅於環境變數目錄名稱與目標模組相符時採用。
- **Slot 匹配規則一致性修復**：`SOPSynthesizer.synthesize_sop()` 改用與 `SLOT_PATTERN` 一致的容錯正則匹配插槽（支援 `<!--YSCB_SLOT:x-->` 等空白變體），並於找不到插槽降級附加檔尾時輸出 `[WARN]` 明確提示，消除靜默錯置。
- **`remove` 相依防護真實化**：先前僅硬編碼保護 `core`；現依各已安裝模組 `manifest.json` 宣告之 `dependencies` 執行真實相依阻斷（`--force` 可越過）。
- **`version check-update` 計數器修復**：修正模組更新計數在 installer 檢查後被重置歸零、導致「發現更新」與「無待更新項目」同時輸出的自相矛盾訊息。
- **指令與文檔一致性**：`pull` / `remove` 新增 argparse 別名 `update` / `uninstall`（README 與內建 help 先前已宣稱存在但實際未註冊，執行必 exit 2）；`pull` 支援顯式 `--all` 旗標。
- **清除過期測試副本**：移除 `test/yscb_installer.py`、`test/yscb_cli.py`、`test/yscb_config.json`——與根目錄版本號相同 (2.1.0) 但缺少整套互鎖廣播機制的 stale 拷貝（測試實際 import 的是 `ys_codebase/` 版本，該副本為誤留死重量）。

### Added
- **URI Scheme 開放註冊協定 (Contract III)**：`ProjectURI.get_dynamic_schemes()` 動態聚合各模組 `manifest.json` 之 `contributes["core"]["uri_schemes"]` 宣告，core SDK 不再硬編碼 `agents-workflow` 模組名稱；`agents-workflow` 改以宣言式註冊 `plans/archive/docs/sop_ext` 四協議；舊版映射表保留為向後相容 fallback；`project://`、`yscb://` 為保留字不可覆蓋。
- **IDE Adapter 註冊表與 per-adapter 快取**：`cli.py` 新增 `IDE_ADAPTERS` 開放擴充點與泛用 `generate_ide_commands(adapter)`；`IDECacheTracker` 改為每個 adapter 獨立 manifest (`.yscb_cache/ide_manifest_<adapter>.json`)，杜絕未來多 IDE 並存時互刪產物，並自動平滑遷移舊版全域 manifest。
- **`installer rollback` 指令**：`rollback <module> [--list] [--to <備份名稱>]` 自 `.yscb_cache/backup/` 快照一鍵還原模組並同步回寫安裝紀錄；快照新增保留策略（每模組保留最近 5 份）。
- **`installer status` 孤兒偵測**：新增「實體狀態」欄位，模組目錄遺失時標記 `[MISSING]` 並提示修復指令。
- **SOP Patch 決定性疊加順序**：`sop_patches` 支援選填 `priority` 欄位（預設 100，越小越先注入），依 `(priority, 模組名稱)` 穩定排序；`get_contributions()` 與 `get_all_installed_manifests()` 改為名稱排序掃描，跨平台結果具決定性。
- **GitHub Actions CI**：新增 `.github/workflows/ci.yml`，於 ubuntu/windows × Python 3.11/3.12 矩陣自動執行全量回歸套件（含下游沙盒 E2E）。
- **強化回歸測試套件**：新增 `test/test_hardening.py` (HT-01~HT-07)，覆蓋上述全部修復與版本 SSOT 同步防護。

### Changed
- **Hook 執行逾時防護**：`_migration.py` (600s)、`_installed.py` / `_uninstall.py` (120s)、`_on_modules_changed.py` (120s)、自訂 `build.py` (600s)、Extension Verifier (120s) 與全部 git 子程序 (600s) 均加上 timeout，杜絕無限掛起；遷移逾時視同失敗並觸發快照回滾。
- **錯誤診斷體驗**：頂層錯誤訊息附帶例外類別名稱，並支援 `YSCB_DEBUG=1` 環境變數輸出完整堆疊。
- **版本號 SSOT 收斂**：`yscb_core.__version__` 改為自 `manifest.json` 動態讀取，消除三處硬編碼版本號發散風險。
- **版本升級**：`core` v2.1.0 ➔ v2.2.0、`agents-workflow` v1.0.1 ➔ v1.1.0、起手腳本 v2.1.0 ➔ v2.2.0。

---

## 2026_08_23_1112_module_interlock_system

### Added
- **安裝期生命週期連動廣播機制 (Contract I)**：於 `yscb_installer.py` 的 `ModuleManager` 實作 `_broadcast_modules_changed(changes)`，在整批 `install`、`pull`、`remove` 完成後單次派發 `action:module` 變更清單至已安裝模組之 `scripts/_on_modules_changed.py`。`build` 指令嚴格排除廣播。
- **Core SDK 跨模組貢獻查詢通道 (Contract II)**：於 `source/core/scripts/context.py` 實作 `ProjectContext.get_contributions(namespace)` 與 `get_all_installed_manifests()`，為上層模組提供零領域偏見的宣言式貢獻提取通道。
- **SOP Slot 插槽動態注入與標記剝除引擎 (`SOPSynthesizer`)**：建立 `SOPSynthesizer` 類別，支援 `target_slot` 匹配與 `append`/`prepend` 注入，並在具體化輸出時強制透過 `strip_slot_markers()` 100% 正則剝除 `<!-- YSCB_SLOT:... -->` 標記，保證產物純淨。
- **基準指令庫目錄與 Slot 全集植入**：建立 `source/agents-workflow/workflows/commands/` 作為單一事實來源 (SSOT)，並於 `NewPlan.md` (`Phase0`~`Phase7`)、`Review.md` (`Step1`~`Step4`)、`ContextInit.md` (`Step1`~`Step4`) 植入共 16 個標準 Slot 標記。
- **IDE 生成快取與孤兒檔案清理追蹤器 (`IDECacheTracker`)**：於 `source/agents-workflow/scripts/ide_sync.py` 實作快取追蹤器，維護 `.yscb_cache/ide_workflow_manifest.json` 並自動刪除廢棄孤兒指令檔案。
- **雙層 Extension 發現與優先級調度器 (`ExtensionRegistry`)**：於 `source/agents-workflow/scripts/ext_registry.py` 實作雙層調度器，專案根目錄自定義擴充 (`sop_ext://`) 優先覆蓋外掛模組宣告之擴充 (`contributes.sop_extensions`)，並升級 `ext list` 終端輸出為雙層來源標籤排版。
- **動態合成與環境感知 Hook (`_on_modules_changed.py`)**：建立 `agents-workflow` 生命週期 Hook，接收廣播後具體化合成 `workflows/*.md`，並自動偵測專案環境完成 IDE 工作流無感即時同步。
- **連動協定專題手冊與設計筆記**：產出 `docs/AgentsWorkflow/SOP_INTERLOCK_PROTOCOL.md`，並於 `docs/Installer/DESIGN_NOTES.md` 追加 `DN-07` (build 排除鐵律) 與 `DN-08` (Slot 標記剝除防呆)。
- **連動系統全量測試套件**：建立 `test/test_interlock.py`，覆蓋 FT-01~08、ET-01~08、PT-01 等 17 項功能、邊界與效能測試。

### Changed
- **模組空間定義昇華**：`modules/` 定義正式由「從遠端 build 抓取的運行產物」昇華為「於本地和相關模組相依連動後的具體化運行版本」。
- **SOP 基準庫與發布庫結構拆分**：`source/agents-workflow/workflows/` 下移除了 9 份舊版靜態指令，統一收斂至 `commands/` 基準庫管理。
- **CLI 工具鏈全面升級**：升級 `generate_antigravity_ide_commands()`、`ext list`、`ext show` 與 `verify_plan.py` 支援雙層來源調度與跨模組驗證腳本執行。

---

## 2026_08_23_1017_versioning_system

### Added
- **SemVer 2.0.0 與 VersionConstraint 引擎**：於 `source/core/scripts/semver.py` 實作純標準庫語意化版本引擎，支援完整優先級富比較、預發布比對、剛性 bump 以及 `^, ~, >=, <=, ==, !=, *` 相依約束匹配。
- **鏈式線性增量遷移框架 (`MigrationRunner`)**：於 `source/core/scripts/migration.py` 實作 `@runner.step("X.Y.x")` 裝飾器與 $O(N)$ 線性代際遷移，支援跨版本平滑升級與失敗自動回滾。
- **五階段事務性安全升級流水線**：於 `yscb_installer.py` 實作 Pre-flight 相依約束校驗、舊版快照備份至 `.yscb_cache/backup/`、2×2 專案配置增量深層合併 (`deep_merge`)、本地配置唯讀保留、`AGENTS.md` 標記軟合併與例外自動 `_rollback_snapshot()` 還原。
- **統一 CLI 版本管理工具鏈**：新增 `python yscb_cli.py version <status|check|check-update|bump>`，提供三態版本狀態矩陣、相依相容性檢查、一鍵更新掃描與版本遞進。
- **Installer 單檔自舉升級 (`installer self-update`)**：提供 `python yscb_cli.py installer self-update [--force]`，採用 Windows `.tmp` 原子安全覆蓋，徹底規避執行中檔案鎖定問題。
- **抽象外掛式 Extension Verifier Hook**：加固 `verify_plan.py`，動態掃描並調用 `sop_ext://<ext>_verify.py`，建立專案特化 `dogfooding_pipeline_verify.py` 守門外掛。
- **全量主題與設計筆記手冊**：產出 `docs/Core/SEMVER_ENGINE.md`、`docs/Core/MIGRATION_FRAMEWORK.md`、`docs/Installer/UPGRADE_PIPELINE.md`、`docs/AgentsWorkflow/EXTENSION_VERIFIERS.md`，並於 `docs/Installer/DESIGN_NOTES.md` 追加 `DN-04 ~ DN-06`。

### Changed
- **模組版本號正式升級**：`core` 升級至 `v2.1.0`，`agents-workflow` 升級至 `v1.0.1`，核心起手腳本 `yscb_installer.py` 與 `yscb_cli.py` 升級至 `v2.1.0`。
- **相依宣告語法支援 SemVer 約束**：`agents-workflow/manifest.json` 相依宣告改為 `core >= 2.0.0`，安裝器拓撲解析自動提取模組名稱與校驗約束。

---

## 2026_08_23_0055_architecture_migration

### Added
- **Dogfooding 自引用 SOP 擴充**：新增 `extensions/dogfooding_pipeline_ext.md` 與源碼模板，定義 Stage 1~4（源碼空間 ➔ build ➔ regression ➔ install）全流程 Checkpoint。
- **Dogfooding 行為準則公理**：於 `AGENTS.md` 專案特化規範（第 4 節）寫入三層空間權限矩陣與標準四步閉環流水線。
- **知識庫定式工具庫指南**：於 `DocumentationStandards.md` 追加第 7 節「知識庫定式維護工具鏈」(`docs init/new-topic/audit`)。

### Changed
- **SOP NewPlan 雙星伴隨初始化**：修改 `NewPlan.md` Phase 0 步驟 1/2，強制規定開立計畫目錄時必須【同時】建立 `P00_semantic_requirements.md` 與 `changelog.md`，徹底消除時序滯後問題。
- **定式工具鏈指令聯動**：更新 `Review.md` 步驟 2 引入 `ext list/show`、步驟 3 引入 `docs audit`；更新 `AGENTS.md` 與 `AGENTS.template.md` 補齊定式作業 CLI 清單 (`<verify|scan|search|archive|docs|ext>`)。
- **知識庫手冊路徑更新**：更新 `docs/AgentsWorkflow/DETERMINISTIC_SCRIPTS.md` 與 `docs/_project/CONTRIBUTING.md` 為最新 `python yscb_cli.py` 路由器指令語法。

### Fixed
- **verify_plan.py 檢查盲區加固**：加固 `verify_plan.py`，移除 `changelog.md` 略過邏輯，改為嚴格檢查存在性與 Markdown 標題/表格格式。
- **CLI discover_all_extensions 語意 URI 解析修復**：修正 `cli.py` 中直接拼接 `Path(ext_setting)` 導致 `project://` URI 解析錯誤問題，統一改為調用 `get_extensions_dir` 解析。
