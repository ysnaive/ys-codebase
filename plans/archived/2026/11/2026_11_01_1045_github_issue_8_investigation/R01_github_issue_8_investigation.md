# 專題調研與分析報告：GitHub Issue #8 四大跨模組問題根因剖析與架構修復方案 (R01_github_issue_8_investigation.md)

> 調研主題：GitHub Issue #8 (`server` 狀態偵測失效、自訂解析器載入不一致、錯誤可觀測性與 `plan verify` 動態 Target 路徑)  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1045_github_issue_8_investigation  
> 調研狀態：Concluded  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：
  外部開發者 (`coachnian`) 於 Windows 11 Pro / Python 3.13.16 環境將 YS-Codebase (`yscb.py` 1.1.0.6, `core` 1.2.0.2, `agents-workflow` 1.2.2.1, `knowledge-db` 1.1.2.2, `server` 1.0.1.2) 導入 Astro 靜態網站專案時，回報了 [GitHub Issue #8](https://github.com/ysnaive/ys-codebase/issues/8) 共 4 項問題：
  1. **問題一**：`server status` 與 `server stop` 永遠偵測不到運作中的 Daemon（回報 `Status: Stopped` / `Daemon is not running.`），且 `server stop` 會誤刪 `daemon.json` 導致孤兒程序無法透過 CLI 關閉。
  2. **問題二**：`server` 啟用時，專案於 `config/knowledge-db/contribute.json` 註冊之 `custom` 解析器（`yscb_parsers.site_parsers:AstroParser` / `JsonParser`）載入失敗（`No module named 'yscb_parsers'`），而關閉 `server`（Cold Run）則正常載入，造成兩種執行模式的索引符號數不一致（80 vs. 28）；此外，使用者亦指出第三方 YSCB 模組貢獻之解析器與內建 `HtmlParser` 的 `can_parse()` 副檔名硬編碼限制。
  3. **問題三**：自訂解析器載入失敗時，以 `--console` 啟動 Server 並在另一終端執行 `knowledge-db index` 或 `status` 時，客戶端終端機沒有任何警告，僅表現為搜尋結果變少，極難排查。
  4. **問題四**：專案僅啟用 `claude` 目標並移除 `antigravity` 時，`plan verify` 的 `[NEXT PHASE GATE]` 提示仍顯示 `.agents/.yscb/templates/fast_track_plan.md`，而非實際物化路徑 `.claude/.yscb/templates/`。
- **調研目標與範疇**：
  1. 逐一針對上述 4 項問題進行第一手源碼定錨與 5-Whys 根因解剖，確認所有連帶影響面（Blast Radius）。
  2. 針對設計與架構層面的多重解法（特別是問題二之跨進程解析器載入協議、內建 Parser 副檔名配置化、以及問題四之動態 Target 路徑解析）進行候選方案優劣權衡（Trade-offs）。
  3. 提出具體、符合 YSCB 架構規範（如 `Zero Source Path Injection` 護欄、`Single-Writer` 與 `VFS` 契約）的推薦修復藍圖。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 問題一：`server status` / `server stop` 偵測不到運作中 Daemon 與誤刪 `daemon.json`

#### 2.1.1 第一手源碼證據與 5-Whys 根因
- **問題座標**：
  - `ys_codebase/source/server/server/master.py` 第 `67~78` 行 (`read_daemon_state`)
  - `ys_codebase/source/core/core/vfs/vfs.py` 第 `120~124` 行 (`VFS.read_json`)
  - `ys_codebase/source/server/scripts/cli.py` 第 `101~135` 行 (`start`)、第 `137~153` 行 (`stop`)、第 `218~230` 行 (`status`)、第 `240~248` 行 (`reload`)
- **根因鏈 (5-Whys)**：
  1. **現象**：Daemon 正常運行且 `.cache/server/daemon.json` 存在且內容合法，但 `server status` 永遠顯示 `Stopped`，`server stop` 顯示 `Daemon is not running.` 並刪掉 `daemon.json`。
  2. **Why 1**：因為 `status()`、`stop()`、`start()`、`reload()` 皆依賴 `read_daemon_state(yscb_root)` 讀取 `daemon.json`，而 `read_daemon_state()` 永遠回傳 `None`。（反觀 `core/commands/dispatcher.py` 的 `_try_hot_dispatch` 第 `114~116` 行是直接用 `json.load(f)` 讀取 `daemon.json`，所以一般 CLI 指令熱派發完全正常！）
  3. **Why 2**：為什麼 `read_daemon_state()` 永遠回傳 `None`？因為第 `73` 行寫了：
     ```python
     data = vfs.read_json(state_file, default=None)
     ```
     但檢視 `core/vfs/vfs.py:120`：
     ```python
     def read_json(self, path_or_uri: Union[str, Any], encoding: str = "utf-8") -> Any:
     ```
     `VFS.read_json` **根本不接受 `default` 關鍵字參數**！每次呼叫必拋出 `TypeError: VFS.read_json() got an unexpected keyword argument 'default'`。
  4. **Why 3**：為什麼這個 `TypeError` 在測試與執行時沒暴雷？因為第 `76~77` 行寫了 `except Exception: pass`（標準的異常掩蓋反模式），把程式簽名錯誤當成檔案讀取失敗吞掉了。
  5. **Why 4**：為什麼 `test_server.py` 沒抓到？因為 `test_server.py` 測試的是 `MasterSupervisor` 的 `/api/status` HTTP 端點，並未針對 `read_daemon_state()` 或 CLI `start` / `status` / `stop` 撰寫端到端整合測試；且在 `start()` 背景啟動迴圈（`cli.py:125~133`）中，因為 `read_daemon_state()` 回傳 `None`，`start` 每次都會等滿 3 秒並印出 `Daemon started but readiness probe timed out.`。
- **連帶副作用分析**：
  - **副作用 A (`server start`)**：背景啟動必定傻等 3.0 秒 timeout，且若再次執行 `server start`，因 `cli.py:101` `read_daemon_state` 為 `None`，無法在 CLI 層攔截「已在運行」（幸好 `MasterSupervisor.start()` 內部有 `InterProcessLock("daemon.lock")` 擋住第二個實例）。
  - **副作用 B (`server stop` 誤刪 `daemon.json`)**：當 `read_daemon_state()` 回傳 `None`（例如 JSON 正在寫入或解析失敗），`cli.py:146~151` 卻直接執行 `os.remove(state_file)`！一旦 `daemon.json` 被誤刪，正在運行的 Master 與 Worker 就失去狀態檔（連 `_try_hot_dispatch` 也找不到 Port 與 Token），徹底變成無法透過 CLI 關閉的孤兒程序。
  - **全倉同類隱患清查**：經 `knowledge-db search "read_json default="` 全倉掃描，全倉 5 大模組中**僅有 `server/master.py:73` 這一處**誤傳了 `default=None` 給 `vfs.read_json`。

#### 2.1.2 修復處方
1. **修正 `read_daemon_state()`**：移除無效參數 `default=None`，改為 `data = vfs.read_json(state_file)`；將異常捕獲精確收斂為 `except (OSError, ValueError, TypeError, KeyError):`（僅容忍檔案不存在/競爭讀取半截 JSON 或 `ServerDaemonState(**data)` 結構不符）。
2. **加固 `cli.py:stop()` 防誤刪 `daemon.json`**：若 `state` 為 `None` 或 `!is_process_alive(state.pid)`，在刪除 `daemon.json` 前應先以非阻塞方式探測 `daemon.lock`（或確認 `state is not None and not is_process_alive(state.pid)`）——唯有確認鎖未被持有（代表 Daemon 確實已死），才清理殘留的 `daemon.json`。

---

### 2.2 問題二：`server` 啟用時無法載入專案自訂解析器（與內建解析器副檔名限制）

#### 2.2.1 全景執行路徑與 `sys.path` 差異深度剖析
在 YSCB 生態系中，`ParserRegistry._load_from_contributes()` 會在 **3 種不同執行上下文**中被調用，目前這 3 種上下文的 `sys.path` 與工作目錄 (`cwd`) 存在嚴重不對稱：

| 執行模式 | 啟動入口與 `cwd` | `sys.path` 現況 | 專案自訂 Parser (`project://`) | 第三方模組 Parser (`module://<donor>`) |
| :--- | :--- | :--- | :---: | :---: |
| **模式 A：Cold Run（一般執行）** | `python yscb.py ...`<br/>`cwd` = 專案根目錄 (`project://`) | `sys.path[0]` 為 `yscb.py` 所在目錄（通常即 `project://` / `yscb.host://`）；`dispatcher.py` 注入 `.modules/core` 與 `.modules/knowledge-db` | ✅ 可載入（因 `sys.path[0]` 碰巧含 `yscb.py` 目錄） | ❌ **失敗**（`dispatcher.py` 未將 Donor 模組 `.modules/<donor>` 加入 `sys.path`） |
| **模式 B：Warm Worker（常駐 Server）** | `master.py:_spawn_worker_locked` 啟動 `worker.py`<br/>`cwd` = `self.yscb_root` (`ys_codebase/`) | `PYTHONPATH` 僅含 `.venv/.../site-packages`、`ys_codebase/`、`ys_codebase/.modules`、`.modules/core`、`.modules/server`。<br/>**完全不包含 `project://` 或 `yscb.host://`！** | ❌ **失敗**（`No module named 'yscb_parsers'`） | ❌ **部分失敗**（除非該 Donor 模組剛好也註冊了 `server.services` 被 `ServiceManager` 注入 `sys.path`） |
| **模式 C：`ProcessPoolExecutor` 平行打包子進程** | `bundler.py:bundle_union`（當檔案數 $\ge 80$ 時啟動子進程池） | Windows `spawn` 模式下子進程繼承父進程的 `sys.path` / `PYTHONPATH` 與 `cwd`；若父進程是 Warm Worker（且 `execute_task` 在 `finally` 還原了 `cwd` 或在 `pre_warm` 階段），子進程新建 `_get_worker_registry()` 時同樣找不到路徑 | ❌ 在 Server 模式下失敗 | ❌ 失敗（子進程未重新注入動態 `sys.path`） |

此外，還有兩個深層機制問題：
1. **`WarmWorker.pre_warm()` 時序陷阱**：
   當 Server 啟動時，`worker.py:pre_warm()` 會觸發 `hook.server.py:on_worker_warming` $\to$ `KnowledgeEngine.pre_warm()` $\to$ `get_engine()` $\to$ `KnowledgeEngine.__init__()` $\to$ `ParserRegistry()`！
   請注意：**`ParserRegistry` 是在 Worker 剛啟動的 `pre_warm()` 階段就被實例化並快取在 `_GLOBAL_ENGINE_INSTANCE` 單例中**！此時還沒收到任何 CLI `execute_task(cwd=...)` 請求。因此，如果只在 `execute_task` 依賴 `cwd`，`pre_warm()` 階段建立的 `_GLOBAL_ENGINE_INSTANCE.parser_registry` 依然會載入失敗，且之後所有 CLI 請求都會沿用這個已經漏載 Parser 的單例！
2. **內建 Parser（`HtmlParser` / `CssParser` / `SpiceParser`）`can_parse()` 寫死副檔名**：
   如使用者在 Issue #8 中敏銳觀察到的：
   - `TreeSitterDriver(cfg)` 會將 `LanguageConfig` 存入 `self.config`，並在 `can_parse()` 中使用 `ext in self.config.extensions`（完全受 `contributes` 控制）。
   - 但 `mode: "custom"` 在 `ParserRegistry._load_from_contributes`（`registry.py:90~91`）實例化時寫的是：
     ```python
     parser_cls = getattr(mod, cls_name)
     parser_inst = parser_cls()
     ```
     完全沒有把 `cfg` (`LanguageConfig`) 或 `cfg.extensions` 傳給 `parser_inst`！且 `HtmlParser.can_parse` 直接寫死 `ext in self.SUPPORTED_EXTENSIONS` (`{".html", ".htm"}`)。這導致使用者就算想在 `config/knowledge-db/contribute.json` 覆寫 `"html"` 的 `extensions: [".html", ".htm", ".astro"]`，或新增 `"astro"` 複用 `knowledge_db.parsers.html_parser:HtmlParser`，`HtmlParser.can_parse("index.astro")` 依然會回傳 `False`！

#### 2.2.2 候選架構方案對比矩陣

針對「如何讓專案與第三方模組的自訂解析器在 Cold Run、Warm Worker (`pre_warm` & `execute_task`) 與 `ProcessPoolExecutor` 子進程下 100% 一致載入，並支援副檔名動態綁定」，評估以下三個方案：

| 評估維度 | 方案 A：僅於 `worker.py` 將 `yscb.host://` 加入 `sys.path` | 方案 B：`ParserRegistry` 原生支援語意 URI / 模組路徑動態解析 ＋ `BaseParser` 綁定 `LanguageConfig.extensions`（推薦） | 方案 C：強制要求所有自訂解析器打包為獨立 YSCB Module 安裝至 `.modules/` |
| :--- | :--- | :--- | :--- |
| **設計機制** | 於 `master.py` / `worker.py` 將 `os.path.dirname(yscb_root)` 加入 `PYTHONPATH` | 1. **雙層路徑保障**：`worker.py` (`pre_warm` 與 `PYTHONPATH`) 將 `yscb.host://` 與 `project://` 加入安全路徑；`ParserRegistry` 解析 `parser_entry` 時，支援：<br/>  • 語意 URI：`project://yscb_parsers/site_parsers.py:AstroParser` 或 `module://<donor>/...:Cls`<br/>  • 套件路徑：`yscb_parsers.site_parsers:AstroParser`（自動將 `project://`、`yscb.host://` 及該語言之 `module://<__provider__>` 納入查找路徑）。<br/>2. **副檔名動態賦予**：`ParserRegistry` 實例化 `custom` Parser 後，將 `cfg.extensions` 合併/綁定至實例（如 `SUPPORTED_EXTENSIONS` 或 `_configured_extensions`），使內建 `HtmlParser` 等可直接透過 `contribute.json` 擴充 `.astro` 等副檔名。<br/>3. **熱自癒同步**：當 `contributes` 更新或配置變更時，`get_engine()` 同步刷新若曾失敗或變更之 `ParserRegistry`。 | 禁止專案直接放 `.py`，要求必須走 `dev build` + `install @build` |
| **優點 (Pros)** | 改動最少（僅改 `master.py` / `worker.py`） | • **100% 相容使用者現有寫法**（`"yscb_parsers.site_parsers:AstroParser"` 免改設定即可在 Cold / Server / Multiprocessing 全通）<br/>• **同時支援語意 URI**（如 `"project://..."`），當 `project_root` 與 `yscb.host://` 不同目錄時依然精準定位<br/>• **徹底解決第三方 YSCB 模組貢獻 Parser 的 `sys.path` 問題**（透過 `__provider__` 自動定位 `.modules/<donor>`）<br/>• **零代碼複用內建 Parser**：使用者可直接將 `.astro` 綁定至 `HtmlParser` | 符合純模組化形式 |
| **缺點 (Cons)** | • 若 `project_root` 與 `yscb.host` 不同目錄會失效<br/>• 無法解決第三方 YSCB 模組 (`module://<donor>`) 貢獻 Parser 的問題<br/>• 無法解決 `HtmlParser` 副檔名硬編碼問題 | 需協調更新 `server/master.py`、`knowledge-db/parsers/registry.py`、`base.py` 與文檔 `docs/knowledge-db/contributes_guide.md` | 對輕量前端/網站專案門檻過高，違背 Issue #8 使用者直覺體驗 |
| **對 `Zero Source Injection` 護欄影響** | 安全 | **100% 安全**（僅解析 `project://`、`yscb.host://` 與 `.modules/<provider>`，絕不注入 `ys_codebase/source/`） | 安全 |

---

### 2.3 問題三：解析器載入失敗缺乏顯式警告與可觀測性

#### 2.3.1 根因解剖
為什麼使用者在 `--console` 模式下執行 `python yscb.py knowledge-db index` 完全看不到任何警告？
1. **原因 1（單例快取時序）**：當使用者啟動 `python yscb.py server start --console` 時，`WarmWorker.pre_warm()` 在背景執行緒建立 `_GLOBAL_ENGINE_INSTANCE` 並實例化 `ParserRegistry()`。此時 `ParserRegistry._load_from_contributes()` 發生 `ModuleNotFoundError` 並呼叫 `logger.warning(...)`。
2. **原因 2（Worker 背景 Logger 未串流至客戶端）**：在 `pre_warm()` 期間，Python 標準 `logging` 寫入 Worker 的 `sys.stderr`（即被 Master 的 `_drain_stderr` 轉寫入 `.cache/server/log`），並不會出現在之後執行 `knowledge-db index` 的那個客戶端終端機上！
3. **原因 3（二次呼叫不重試）**：當使用者在另一個終端機執行 `python yscb.py knowledge-db index` 時，Warm Worker 呼叫 `get_engine()`，直接拿到已經建好的 `_GLOBAL_ENGINE_INSTANCE`（其 `self.parser_registry` 早就跳過了失敗的語言，且不會再次執行 `_load_from_contributes()`），因此 `index` 執行過程完全無聲無息，只看到符號數從 80 變成 28！

#### 2.3.2 修復處方
1. **結構化保存載入狀態與錯誤 (`ParserRegistry.load_errors`)**：
   於 `ParserRegistry` 新增 `self.load_errors: Dict[str, str] = {}`（記錄 `lang_id -> error_message`，同時涵蓋 `tree_sitter` grammar/query 載入失敗與 `custom` `parser_entry` 載入失敗）。
2. **重試與自癒機制**：
   在 `get_engine()` 或 `build_index()` 時，若發現 `parser_registry.load_errors` 非空（或 `contributes` 快照更新），可嘗試重新載入；若仍有 `load_errors`：
   - **`knowledge-db index`**：於終端機 `stderr` 顯式印出 `[knowledge-db] [WARN] 偵測到 N 個語言解析器載入失敗:` 與各語言失敗原因，讓開發者在跑 `index` 的終端機一眼看見。
   - **`knowledge-db status`（含 `--json`）**：在狀態面板與 JSON 輸出中新增已載入語言清單與 `parser_load_errors` 區塊，提供 100% 透明的診斷可觀測性。

---

### 2.4 問題四：`plan verify` 與 `plan status` 提示路徑硬編碼 `.agents/`

#### 2.4.1 全倉硬編碼盤點
經檢索 `ys_codebase/source/agents-workflow/` 全模組 Python 源碼，發現以下 2 個檔案共 4 處將物化參考路徑硬編碼為 `.agents/`（即假設 `antigravity` / `codex` 目標永遠啟用）：
1. **`agents_workflow/plans/verifier.py` 第 `750~754` 行 (`_build_next_phase_hint`)**：
   ```python
   return (
       f"下一階段 {p_code} ({tmpl_name}) -> "
       f"請先讀取 `.agents/.yscb/templates/{tmpl_name}` | "
       f"必備章節: {raw_titles_str}"
   )
   ```
2. **`agents_workflow/plans/status.py` 第 `432` 行與第 `504~505` 行 (`resolve_next_action`)**：
   ```python
   # L432:
   "required_reference_path": ".agents/skills/research/SKILL.md",
   # L504-505:
   ref_base = ".agents/skills/development-sop/references"
   sop_skill_path = ".agents/skills/development-sop/SKILL.md"
   ```
   當使用者在專案中執行 `release-target --add claude --proj` 並 `release-target --remove antigravity --proj` 後，專案根目錄下只有 `.claude/.yscb/templates/` 與 `.claude/skills/`，完全沒有 `.agents/` 目錄。此時 `plan verify` 與 `plan status --resume` 卻指示 Agent 去讀 `.agents/...`，導致 Agent 讀檔失敗或困惑。

#### 2.4.2 候選方案與動態解析設計
在 `agents_workflow/plans/_common.py`（或 `targets.py`）提煉共用輔助函式 `resolve_active_target_projected_path(artifact_type: str, artifact_name: str = "", subpath: str = "") -> str`：
1. **查詢當前活躍 Target**：透過 `ReleaseTargetManager.get_classified_targets()["union"]` 取得專案與本機啟用的 Target 清單（例如 `["claude"]`），並對照 `ArtifactCompiler().get_release_targets()` 的 `projections` 定義：
   - 當 `artifact_type == "template"`：讀取 `projections["template"]["target_dir"]`（例如 `"project://.claude/.yscb/templates"`），轉為專案相對路徑 `.claude/.yscb/templates/{subpath}`。
   - 當 `artifact_type == "skill"`：讀取 `projections["skill"]["target_dir"]`（例如 `"project://.claude/skills/{export.name}"`），代入 `artifact_name`（如 `"development-sop"` 或 `"research"`）與 `subpath`（如 `"references/phase_01_requirements.md"` 或 `"SKILL.md"`），轉為專案相對路徑 `.claude/skills/development-sop/references/...`。
2. **多 Target 並存與 Fallback 策略**：
   - 若當前啟用了多個不同目錄的 Target（例如同時啟用 `antigravity` 與 `claude`），可優先採用主動嗅探到的當前宿主環境（`core.locale.detect_active_host_dialect()` 對應之 Target，例如 `CLAUDECODE=1` $\to$ `claude`），若未命中則取 `union` 清單中的第一個有效 Target（或去重並聯）。
   - 若 `union` 為空或無法讀取組態（如獨立沙盒單元測試環境），安全退回預設值 `.agents/.yscb/templates/...` 與 `.agents/skills/...`，確保既有 138 個單元測試 100% 向後相容。

---

## 3. 結論 (Conclusion)

- **核心結論**：
  GitHub Issue #8 回報的 4 項問題均已 100% 透過第一手源碼定錨確認根因：
  1. **`server` 狀態與停機失效**：源於 `server/master.py:read_daemon_state` 誤傳 `default=None` 給不支援該參數的 `VFS.read_json()`，且被 `except Exception: pass` 靜默吞掉；連帶導致 `cli.py:stop()` 誤判 Daemon 未運行而刪除活體 Daemon 的 `daemon.json`。
  2. **`server` 啟用時自訂解析器載入失敗**：源於 `WarmWorker` 啟動與 `pre_warm` 時 `sys.path` 未包含 `project://` / `yscb.host://` 與語言貢獻者 `module://<__provider__>` 路徑，且 `ParserRegistry` 對 `mode: "custom"` 未支援語意 URI 亦未將 `LanguageConfig.extensions` 注入 `BaseParser` 實例（導致內建 `HtmlParser` 無法透過組態擴充 `.astro` 副檔名）。
  3. **解析器載入失敗無警告**：源於 `ParserRegistry` 在背景 `pre_warm` 階段初始化單例，錯誤僅寫入背景日誌而未保存於 `ParserRegistry.load_errors`，導致前景執行 `knowledge-db index` / `status` 時毫無提示。
  4. **`plan verify` 提示路徑錯誤**：源於 `verifier.py` 與 `status.py` 硬編碼 `.agents/` 前綴，未隨當前啟用之 `release_targets`（如 `claude` $\to$ `.claude/`）動態映射。
- **後續建議**：
  - 本次變更橫跨 `server`、`knowledge-db` 與 `agents-workflow` 三個模組（預計修改約 120~180 行業務與測試代碼，無破壞性 Public API 變更），推薦選擇 **出口 ①：原地升級為標準實作計畫（Full Track）**（可搭配 `/auto` 自動推進 `P01-05_auto.md` 至 `P06` 實機驗證），一次性完成四項問題修復、補齊回歸測試並更新 `docs/knowledge-db/contributes_guide.md` 自訂解析器放置規範。

