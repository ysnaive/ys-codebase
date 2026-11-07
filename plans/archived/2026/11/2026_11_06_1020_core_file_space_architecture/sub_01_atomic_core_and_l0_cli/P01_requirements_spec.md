# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_01_atomic_core_and_l0_cli  
> 建立日期：2026-11-06  
> 所屬主計畫：2026_11_06_1020_core_file_space_architecture  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `core` 空間與預設集 Contributes Schema 擴充及原子資料模型 | 1. 於 `ys_codebase/source/core/contributes/_format.json` 新增 `PresetDef`（含 `description: str?`, `include: list[str]?`, `exclude: list[str]?`）與 `SpaceDef`（含 `description: str?`, `entries: list[uri]! | extend`, `presets: list[str]? | extend`, `include: list[str]? | extend`, `exclude: list[str]? | extend`, `hash_policy: enum(adaptive, full_hash, stat_only, lazy_stabilized)? = adaptive`, `large_file_threshold_mb: int? = 10`, `follow_symlinks: bool? = false`）型別契約與頂層 `presets`、`spaces` 擴充點。<br/>2. 於 `core/space/schema.py` 實作 `PresetConfig`、`SpaceConfig` 與 `HashPolicy` 不可變/預編譯資料結構；當 `include` 未指定或為空清單時，預設為全納入 `["*"]`；`exclude` 優先級恆高於 `include` (`[P01:DR-01]`)。<br/>3. 驗收條件：執行 `python yscb.py contributes check` 與 `dev check core` 100% 通過。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-02** | `<owner>/<name>` 命名空間隔離載入與 `<name>` 短名自動聯集尋址 | 1. 實作 `SpaceRegistry`（或 `CoreSpaceManager`），掃描已安裝模組 `module://*/contributes/core.json`（及相容過渡讀取或顯式傳入之空間/預設集資料）與專案 `config://core/contribute.json`。<br/>2. 模組定義之空間與預設集自動註冊為完整限定名 `<module>/<name>`（`owner="<module>"`, `short_name="<name>"`）；專案定義者自動註冊為 `project/<name>`（`owner="project"`, `short_name="<name>"`），各來源定義獨立保存、互不覆蓋，徹底消除模組載入順序相依性。<br/>3. 查詢介面支援雙粒度尋址：傳入 `<owner>/<name>`（含 `/`）時精準返回單一 `SpaceConfig` / `PresetConfig`；傳入不含 `/` 之短名 `<name>` 時，返回所有 `short_name == <name>` 之定義清單（按 `core` -> 字母序模組 -> `project` 確定性排序），並於列舉與匹配時自動執行結果集聯集（Union）。<br/>4. 驗收條件：當模組 `mod_a` 與 `project` 同時定義同名空間 `docs` 時，`get_spaces("mod_a/docs")` 與 `get_spaces("project/docs")` 各自返回獨立定義，而查詢短名 `"docs"` 則涵蓋兩者之聯集且無規則互相污染。 | P0 | [P00:DR-03] |
| **FR-03** | 顯式預設集 (`presets`) 展開與內建 `@gitignore` 動態預設集 | 1. 每個 `SpaceConfig` 僅展開其 `presets` 欄位顯式列出之預設集（無隱式全域 `default_presets`）。<br/>2. 當 `presets` 引用 `<owner>/<preset>` 時精準展開該來源預設集；引用短名 `<preset>` 時聯集展開所有同名預設集之 `include` 與 `exclude`。<br/>3. 內建特殊預設集 `"@gitignore"`：當且僅當某 Space 之 `presets` 包含 `"@gitignore"` 時，讀取 `project://.gitignore`（忽略 `#` 註解與空白行，支援 `!` 負向豁免或標準忽略規則轉譯）並合入該空間之排除過濾器。<br/>4. 驗收條件：未宣告 `presets: ["@gitignore"]` 之空間完全不受 `.gitignore` 影響；宣告者自動排除 `.gitignore` 命中之檔案與目錄。 | P0 | [P00:DR-02], [P00:DR-03] |
| **FR-04** | 三座標相容預編譯規則引擎與單點路徑判定原語 (`match`) | 1. 實作規則預編譯器，對 `include` 與 `exclude` 中之每條規則自動識別並支援三種座標系：<br/>   - **座標 ① 語意 URI 前綴**（含 `://`，如 `yscb://.venv/**`、`project://plans/archived/**`）：透過 `core.uri.resolve` 解析為正規化絕對路徑後進行精確或 glob/前綴匹配。<br/>   - **座標 ② 含 `/` 之相對路徑**（如 `plans/archived/**`、`core/**/*.py`）：同時比對目標相對於 `project://` 之 `project_rel` 以及相對於所屬 `entry` 之 `entry_rel`，任一命中即視為匹配。<br/>   - **座標 ③ 不含 `/` 之單純名稱**（如 `*.py`、`__pycache__`、`.DS_Store`）：匹配目標路徑之檔名（basename）或任意層級之目錄區段名（path segment）。<br/>2. 實作單點判定與解釋原語 `match_path(path, space_query=None)`：不進行全磁碟掃描，直接對目標路徑（檔案或目錄）判定其命中的 `entry`、是否被某條 `exclude`（含規則字串與來源 preset/space）排除、是否命中某條 `include`，並返回結構化 `MatchExplainResult`。<br/>3. 驗收條件：針對三種座標格式之正向納入與負向排除判定 100% 精確，且能明確回報決策原因（如命中的 entry 與觸發排除的具體規則）。 | P0 | [P00:DR-01], [P00:DR-04] |
| **FR-05** | 零冗餘目錄剪枝走訪原語 (`ls`) | 1. 實作 `iter_space_files(space_query, *, pattern=None)` 原子走訪器：支援單一限定空間 `<owner>/<space>`、短名聯集 `<space>` 或全空間（`space_query=None`）。<br/>2. 針對每個 `SpaceConfig` 之每個 `entry`：若 `entry` 為單一檔案則直接套用 `exclude`/`include` 判定並取得 `stat`；若為目錄則使用 `os.scandir` 遞迴走訪，在進入子目錄前先執行目錄級 `exclude` 剪枝（命中排除規則之子目錄直接略過不進入），並直接複用 `DirEntry.stat(follow_symlinks=...)` 取得 `(mtime_ns, ctime_ns, size)`，杜絕重複 `Path.stat()` / `Path.resolve()`。<br/>3. 跨多個 `entries` 或短名 `<space>` 多來源空間聯集時，以實體檔案規範路徑去重，產出確定性排序之 `SpaceFileEntry(rel_path, abs_path, entry_path, matched_spaces, size, mtime_ns, ctime_ns)`。<br/>4. 驗收條件：目錄剪枝能跳過被排除之目錄子樹（0 次內部 `scandir`），且短名聯集空間對重疊檔案僅輸出一次並完整標註所屬限定空間清單。 | P0 | [P00:DR-01], [P00:DR-03], [P00:DR-04] |
| **FR-06** | 單檔與空間級原子指紋計算原語 (`hash`) | 1. 於 `core/space/hasher.py` 實作純標準庫指紋計算原語：支援單一檔案或指定空間（`<space>` / `<owner>/<space>`）之指紋計算。<br/>2. 支援三種計算策略：`stat_only`（基於 `size` 與 `mtime_ns`）、`full_hash`（完整 Blake2b 16-byte hex digest）、`adaptive`（小於 `large_file_threshold_mb` 算完整 Blake2b，大檔採頭中尾稀疏取樣 Blake2b），並對空間計算決定性之整體 `merkle_root`。<br/>3. 驗收條件：相同內容與集合之空間計算出 100% 一致之 `merkle_root`，且不強制寫入或污染任何持久化快照檔。 | P0 | [P00:DR-04] |
| **FR-07** | L0 CLI 雙路由暴露 (`yscb.py core file-space` / `yscb.py fs`) | 1. 於 `core/contributes/core.json` 註冊命令 `file-space` 與別名命令 `fs`（共用同一組 L0 子命令樹：`spaces`、`presets`、`match`、`ls`、`hash`），並於 `core/commands/dispatcher.py` 確保當外部模組同名存在時（如 `sub_04` 退役前之舊 `module:file-space`），頂層未帶 `core` 前綴之 `yscb.py file-space` 不截胡既有外部模組路由，而 `yscb.py core file-space <subcmd>` 與 `yscb.py fs <subcmd>`（及 `yscb.py core fs <subcmd>`）100% 路由至 `core` 新 L0 CLI (`[P01:DR-02]`)。<br/>2. 五大 L0 子命令均為 `tier: "safe"`，支援人類可讀輸出與 `--json` 結構化輸出。<br/>3. 驗收條件：透過 `yscb.py core file-space <subcmd> -h` 與 `yscb.py fs <subcmd> --json` 執行五大子命令均返回 exit code 0 與符合規格之結構化結果，同時舊 `yscb.py file-space status` 在 `sub_04` 前維持原行為不中斷。 | P0 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `entries` 中包含磁碟上不存在之目錄或檔案，或無法解析之未知語意 URI | 走訪 (`ls`/`hash`) 時對尚不存在之物理路徑安全靜默略過（不拋出 `FileNotFoundError` 中斷其他有效入口），並於 `spaces` / `match` 診斷資訊中標註 `exists: false`；若為語意 URI 語法錯誤或未知 scheme，則捕獲並記錄明確警告或於嚴格檢查時報錯。 |
| **EC-02** | `entries` 指向 `project://` 根目錄以外之外部路徑（如 `yscb://` 於獨立宿主或臨時沙盒目錄） | 計算檔案顯示用邏輯路徑 `rel_path` 時，優先嘗試相對於 `project://`；若該檔案不在 `project://` 子路徑下（`ValueError`），自動退回以相對於所屬 `entry`（冠上 entry 識別前綴或規範相對路徑）表示，絕不拋出未捕獲之 `ValueError: is not in the subpath`。 |
| **EC-03** | `presets` 引用不存在之預設集名稱 | 載入展開時不崩潰，保留未解析之 preset 名稱於警告清單（`unresolved_presets`）供 `spaces` / `presets` CLI 與診斷檢視，其餘有效規則照常生效。 |
| **EC-04** | `follow_symlinks: true` 時遭遇符號連結循環（Symlink Loop）或懸空連結（Broken Symlink） | 走訪時以已造訪目錄之 `(st_dev, st_ino)` 集合偵測並阻斷無限遞迴循環；遭遇懸空連結或讀取權限拒絕（`PermissionError` / `OSError`）時安全略過該項目，不中斷整體空間掃描。 |
| **EC-05** | 查詢不存在之空間名稱（如 `fs ls unknown_space` 或 `fs ls bad_mod/docs`） | 拋出結構化 `SpaceNotFoundError`，CLI 於人類模式與 `--json` 模式均輸出清晰錯誤訊息並返回非零退出碼 (`exit code 1`)。 |
| **EC-06** | `@gitignore` 預設集在專案根目錄無 `.gitignore` 檔案，或 `.gitignore` 含有註解、`!` 負向豁免規則 | 無 `.gitignore` 時視為空規則集；有 `.gitignore` 時正確忽略 `#` 開頭註解與空行，並支援 `!` 負向規則豁免被前序 `.gitignore` 規則排除之路徑（但不覆蓋 Space 自身顯式宣告之 `exclude`）。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零第三方依賴 | `core/space/` 必須 100% 使用 Python 標準庫實作（`os`, `pathlib`, `re`, `hashlib`, `dataclasses`, `json` 等），嚴禁引入 `watchdog` 或任何第三方套件，堅守 `module:core` Zero-Prerequisite 微內核鐵律。 |
| **NFR-02** | 過濾與走訪效能 | 規則於 `SpaceConfig` 初始化時完成一次性預編譯（常數集合 $O(1)$ 查找 + 合併正規表示式）；`ls` 走訪全專案源碼空間（約 300~500 檔）本機耗時 $\le 50\text{ms}$。 |
| **NFR-03** | 跨平台路徑正規化 | 所有內部路徑比對統一正規化為 POSIX 正斜線 `/`（Windows 下兼容大小寫不敏感或 `normcase` 比對），確保在 Windows 與 Linux 下產出 100% 一致之匹配結果與 `merkle_root`。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 執行緒本地 URI 上下文隔離 (`core/uri.py`)**：`core.uri` 採用 `threading.local()` 管理 `active_host_dir` 與 `active_yscb_dir`；`core.space` 解析語意 URI 時必須直接調用 `core.uri.resolve()`，嚴禁在模組載入期將動態解析路徑硬編碼快取為全域常數，以確保平行沙盒測試隔離。
- **`[!WARNING]` 頂層命令路由碰撞防呆 (`core/commands/dispatcher.py`)**：`dispatcher.py` 目前將 `core_mod.commands.keys()` 視為頂層快捷指令（優先於 `registry.resolve_module_name`）。在 `sub_04` 移除舊 `module:file-space` 前，若 `core` 註冊了命令 `file-space`，必須在 `dispatcher.py` 讓「與已安裝非 `core` 模組同名之頂層 token（即 `file-space`）」在未加 `core` 前綴時優先路由給外部模組 `module:file-space`，而 `yscb.py core file-space ...` 與 `yscb.py fs ...` 則路由至 `core`，確保過渡期 100% 零衝突 (`[P01:DR-02]`)。
- **`[!NOTE]` 僅從 `.modules/` 載入 Contributes 之剛性約束**：遵循 `core` 既有設計，正式環境下跨模組 `contributes/core.json` 統一由 `yscb_dir/.modules/*/contributes/core.json` 聚合，同時於單元測試與 Manager 初始化介面支援顯式傳入字典或指定根目錄以便沙盒測試。
