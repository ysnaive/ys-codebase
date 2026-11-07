# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：sub_05_space_unification_and_builtin_spaces  
> 建立日期：2026-11-07  
> 所屬主計畫：2026_11_06_1020_core_file_space_architecture  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 全面統一為 `SpaceConfig` 與對稱化 `CompiledRuleSet` | 移除 `PresetConfig`、`contributes.presets`、CLI `yscb fs presets`、SDK `list_presets`/`resolve_presets`、`is_ephemeral`、`has_explicit_include`、`GitignoreEvaluator` 與 `@gitignore`；允許 `SpaceConfig` 之 `entries` 與 `compose` 同時為空（評估結果為 $\emptyset$）；對稱化 `CompiledRuleSet` 之 `include` 與 `exclude` 編譯語意（統一啟用 `allow_dir_prefix=True` 與 `match_any_seg=True`）。 | P0 | [P00:DR-01] |
| **FR-02** | 四階段兩趟編譯規則注入與 `on_register_file_spaces` 事件 | `SpaceRegistry.reload()` 分兩趟執行：Pass 1 依序收集 `1. Module Contributes -> 2. Project Config -> 3. on_register_file_spaces 事件廣播 -> 4. In-Process Runtime Injection` 並對同一個 `<owner>/<short-name>` 執行規則層絕對聯集（`include` 含 `*` 恆為 `*`，`exclude` 規則聯集共同排除，未帶 `<owner>/` 預設歸屬 `__unknown__/<short-name>`）；Pass 2 生成 `/<short-name>` 節點並以 DFS 拓撲展開 `presets` 與編譯 `SpaceConfig`；廢除 `gitignore_dynamic.json`。 | P0 | [P00:DR-02] |
| **FR-03** | `presets` 規則引用、`!<space>` 規則反轉排除與局部子樹剪枝 | `presets` 欄位直接引用其他 Space 拉取規則池（含 DFS 環路檢測 `SpaceCycleError`；指向 `/<short-name>` 時遞迴拉取所有同名 `<owner>/<short-name>` 規則）；支援 `!<space>` 反向規則排除（命中目標 `include` 且未命中目標 `exclude` 視為當前空間之 `exclude`），並於 `os.scandir` 實作局部子樹剪枝不變量（目錄 `D` 命中目標 `include` 且目標 `effective_exclude` 無匹配 `D` 子樹之豁免規則時直接剪枝 `D`）。 | P0 | [P00:DR-03] |
| **FR-04** | `compose` 檔案結果絕對聯集、`!<space>` 結果差集與自動生成 `/<short-name>` | 移除母空間對 `compose` 子空間的二次過濾（`include`/`exclude` 僅過濾自身 `entries`）；正向 `compose` 採檔案結果絕對聯集，反向 `!<space>` 採檔案結果差集（$\text{Positive} \setminus \text{Negative}$）；自動為每個 `<short-name>` 生成 `qualified_name="/<short-name>"`（`owner=""`）合成空間（快照鍵轉為 `synthetic__<short-name>`）；`collect_all_entry_paths` 僅展開正向 `compose`，`compute_config_hash` 納入正反向 `compose` 與 `presets` 全依賴。 | P0 | [P00:DR-04] |
| **FR-05** | 內建 `gitignore` 正向空間與 `.gitignore` 物化收斂 | 廢除 `contributes/core.json` 頂層 `"gitignore"` 陣列，各模組統一於 `spaces.gitignore` 正向定義不想被版控的檔案（`entries: ["project://"]`, `include: [...]`, `watch: false`）；`core.gitignore` 讀取所有 `<owner>/gitignore` 並將 `yscb://`/`project://` 正規化為專案根相對路徑後，按 `# [<owner>]` 分組物化至 `project://.gitignore` 受控區塊（先輸出 `include`，再將 `exclude` 冠上 `!` 輸出）。 | P0 | [P00:DR-05] |
| **FR-06** | 內建 `workspace` 最外層遞迴掃描上限空間與跨模組對齊 | 於 `core` 定義 `spaces.workspace`（`entries: ["project://"]`, `include: ["*"]`, `exclude: [...]`）作為 `resolve_spaces(None)` / `scan(None)` 預設掃描天花板（`"*"` 與 `SpaceWatcher` 排除 `watch=False` 空間）；`vscode-support` 讀取 `workspace.exclude` 經 Glob 正規化層投影至 `.vscode/settings.json`（保留 `extraPaths` 含 `.modules` 時對 `**/.modules/**` 之豁免防護）；同步對齊 `agents-workflow`、`gdrive-support`、`ast`、`knowledge-db`、`server` 與 `file-space`。 | P0 | [P00:DR-06] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `presets` 或 `compose` 存在直接或間接循環引用（含透過 `/<short-name>` 或 `!<space>` 形成環路） | Pass 2 DFS 展開或評估時立即偵測並拋出 `SpaceCycleError`，附帶完整循環鏈路徑。 |
| **EC-02** | `on_register_file_spaces` 事件處理器內部再次觸發 `SpaceRegistry` 初始化或處於 `raw_spaces` 沙盒模式 | `_in_reload_broadcast` 執行緒局部/實例重入鎖阻斷遞迴廣播；`raw_spaces` 顯式模式下跳過事件廣播；廣播時帶入 `search_roots=[yscb_dir / ".modules"]` 隔離沙盒。 |
| **EC-03** | 被反向引用的空間 `!T` 含有單一檔案 `exclude` 豁免規則（如 `include: [".venv/**", "build/**"], exclude: ["build/keep.txt"]`） | `os.scandir` 對 `.venv/` 判定無子樹豁免規則直接高速剪枝；對 `build/` 判定存在子樹豁免則進入目錄於檔案級保留 `build/keep.txt` 並排除其餘檔案。 |
| **EC-04** | Space 的 `entries` 與 `compose` 同時為空（純規則模板空間） | 不拋出異常，合法建立 `SpaceConfig`，直接對其執行 `iter_space_files` 或 `match_path` 時回傳空集合 / `matched=False` (`reason="outside_entries"`)。 |
| **EC-05** | 同名合成空間 `/<short-name>`（`entries=()`）與具名空間 `<owner>/<short-name>` 在 `gdrive_support/config.py` 或 `_sanitize_target_key` 中並存 | `_sanitize_target_key("/<short>")` 轉為 `synthetic__<short>` 避免與 `<owner>__<short>` 碰撞；`gdrive_support/config.py` 以 `collect_all_entry_paths` 取得根目錄，不被 `entries=()` 覆寫。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 依賴與相容性 | `core.space` 與 `core.gitignore` 維持 100% Python 標準庫零第三方依賴；跨平台（Windows/Linux/macOS）路徑正規化一致。 |
| **NFR-02** | 掃描與剪枝效能 | `workspace` 或引用 `presets: ["!gitignore"]` 之空間走訪時，對 `.venv`、`.modules`、`.git` 等目錄於 `os.scandir` 第一層即完成 O(1) 目錄剪枝，不深入遍歷內部子檔案。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** 修改各模組 `contributes/core.json` 與 `core/contributes/_format.json` 後，須同步透過 `dev build` 與 `install <mod>@build --force` 更新運行空間，確保跨模組測試與 CLI 驗證讀取最新 Schema。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[Stage 1: Module Contributes (spaces)]
       │
       ▼
[Stage 2: Project Config (config/core/contribute.json)]
       │
       ▼
[Stage 3: Event Broadcast `on_register_file_spaces(ctx)`]
  ├─► agents-workflow/scripts/hook.core.py -> register_space("agents-workflow/gitignore", ...)
  ├─► gdrive-support/scripts/hook.core.py  -> register_space("gdrive-support/cloud", ...)
  └─► vscode-support/scripts/hook.core.py  -> register_space("vscode-support/gitignore", ...)
       │
       ▼
[Stage 4: In-Process Runtime Injection (`register_space`)]
       │
       ▼  (Pass 1: Rule-Level Absolute Union per `<owner>/<short-name>`)
[Pass 2: Synthesize `/<short-name>` + DFS Expand `presets`/`!presets` + Symmetric `CompiledRuleSet`]
       │
       ├─► `core.gitignore.sync()` ──► Read all `<owner>/gitignore` (include -> rule, exclude -> !rule) ──► `project://.gitignore`
       ├─► `vscode-support`        ──► Read `workspace.exclude` -> Glob normalizer ──► `.vscode/settings.json`
       └─► `iter_space_files` / `match_path` / `scan` (Default query `None` -> `/workspace`)
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/contributes/_format.json` | Modify | 移除頂層 `presets` 與 `gitignore` 格式定義，更新 `spaces` 欄位與描述契約 |
| `ys_codebase/source/core/contributes/core.json` | Modify | 移除頂層 `presets`、`gitignore` 與 `fs presets` CLI，新增 `spaces.workspace`、`spaces.gitignore` 與 `on_register_file_spaces` 事件 |
| `ys_codebase/source/core/core/space/schema.py` | Modify | 移除 `PresetConfig`、`GitignoreEvaluator`、`is_ephemeral`、`has_explicit_include`；允許空 `entries`/`compose`；對稱化 `CompiledRuleSet` 並新增反轉規則排除與局部子樹剪枝判定 |
| `ys_codebase/source/core/core/space/registry.py` | Modify | 實作四階段兩趟編譯、`on_register_file_spaces` 廣播、`register_space`/`unregister_space`、自動生成 `/<short-name>`、`presets`/`!presets` 與 `compose`/`!compose` 差集運算 |
| `ys_codebase/source/core/core/space/scanner.py` | Modify | 移除 `_ephemeral_snapshots` 分支；`_sanitize_target_key` 區分 `/<short>` 為 `synthetic__<short>`；`scan(None)` 預設 `/workspace`；`patch_files` 改用 `match_path` |
| `ys_codebase/source/core/core/space/watcher.py` | Modify | 將 `notify_ephemeral_space_registered` 更新為 `notify_space_registered` |
| `ys_codebase/source/core/core/space/providers.py` | Modify | 移除 `PresetConfig` / `is_ephemeral` 依賴，更新空間診斷表欄位 |
| `ys_codebase/source/core/core/space/__init__.py` | Modify | 移除 `PresetConfig`、`GitignoreEvaluator` 匯出，新增 `register_space`、`unregister_space`（保留 `define_ephemeral_space` 相容轉發至 `register_space`） |
| `ys_codebase/source/core/core/gitignore.py` | Modify | 移除 `gitignore_dynamic.json`，改由 `SpaceRegistry` 讀取 `<owner>/gitignore` 的 `include` 與 `exclude` (`!<pattern>`) 物化 `.gitignore`，`register`/`unregister` 直接橋接 `core.space` |
| `ys_codebase/source/core/scripts/cli.py` | Modify | 移除 `file_space_presets` / `fs_presets` 子命令與對應處理函式 |
| `ys_codebase/source/core/tests/test_space.py` | Modify | 更新並擴充雙層絕對聯集、`!<preset>`/`!<compose>`、局部剪枝、`on_register_file_spaces`、`gitignore` 與 `workspace` 測試 |
| `ys_codebase/source/core/tests/test_gitignore.py` | Modify | 對齊 `spaces.gitignore` 驅動之 `.gitignore` 物化與 `exclude -> !<pattern>` 測試 |
| `ys_codebase/source/file-space/file_space/__init__.py` | Modify | 移除已廢除之 `PresetConfig` 與 `GitignoreEvaluator` 轉發匯出 |
| `ys_codebase/source/vscode-support/contributes/core.json` | Modify | 將頂層 `gitignore` 遷移至 `spaces.gitignore` |
| `ys_codebase/source/vscode-support/vscode_support/projector.py` | Modify | 讀取 `workspace` 空間排除規則並正規化轉譯為 VS Code `**/...` Glob（保留 `.modules` extraPaths 豁免） |
| `ys_codebase/source/vscode-support/scripts/hook.core.py` | Modify | 實作 `on_register_file_spaces` 動態注入 `vscode-support/gitignore` |
| `ys_codebase/source/agents-workflow/contributes/core.json` | Modify | 對齊 `spaces.docs`、`spaces.plans` 與 `spaces.gitignore` |
| `ys_codebase/source/agents-workflow/scripts/hook.core.py` | Modify | 實作 `on_register_file_spaces` 依活躍 `release_target` 動態注入 `agents-workflow/gitignore` 與 `agents-workflow/workspace` |
| `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` | Modify | 對齊 `core.gitignore` / `core.space` 同步機制 |
| `ys_codebase/source/gdrive-support/contributes/core.json` | Modify | 將頂層 `gitignore` 遷移至 `spaces.gitignore` |
| `ys_codebase/source/gdrive-support/gdrive_support/config.py` | Modify | `_load_space_include_roots` 改用 `reg.collect_all_entry_paths(s_cfg.qualified_name)` |
| `ys_codebase/source/gdrive-support/gdrive_support/sync_engine.py` | Modify | 改用 `core.space.register_space` |
| `ys_codebase/source/gdrive-support/scripts/hook.core.py` | Modify | 實作 `on_register_file_spaces` 依輕量 `repo_sync` 組態動態註冊 `gdrive-support/cloud` |
| `ys_codebase/source/ast/contributes/core.json` | Modify | 將 `presets` 引用更新為 `["workspace"]` |
| `ys_codebase/source/ast/ast_engine/bundler.py` | Modify | `_resolve_target_spaces(None)` 排除 `gitignore`、無入口空間與重複合成空間 |
| `ys_codebase/source/knowledge-db/contributes/core.json` | Modify | 將 `presets` 引用更新為 `["workspace"]` |
| `ys_codebase/source/server/server/space_watcher.py` | Modify | 排除 `watch=False` 與無入口空間，增量變更評估統一使用 `match_path` |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 兩趟編譯與規則合成封裝 (`_RawSpaceAccumulator`)**：在 `SpaceRegistry` 內部以 `_RawSpaceAccumulator` 保存四階段收集之原始欄位並執行規則層絕對聯集，待四階段收集完畢後統一建立 `/<short-name>` 節點並執行 DFS 展開與 `SpaceConfig` 實例化。
- **[P02:DR-02] 反向 Preset 排除規則組 (`negated_preset_matchers`)**：當空間 `S` 宣告 `presets: ["!T"]` 時，將 `T` 編譯後之 `(include_matcher, exclude_matcher)` 掛載於 `S.negated_presets`；檔案判定時若 `T.include_matcher` 命中且 `T.exclude_matcher` 未命中則視為被 `S` 排除；目錄剪枝時若目錄 `D` 命中 `T.include_matcher` 且 `T.exclude_matcher` 無可能匹配 `D` 子樹之規則，直接剪枝 `D`。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
@dataclass
class SpaceConfig:
    qualified_name: str
    owner: str
    short_name: str
    description: str = ""
    entries: Tuple[str, ...] = ()
    compose: Tuple[str, ...] = ()
    presets: Tuple[str, ...] = ()
    include: Tuple[str, ...] = ()
    exclude: Tuple[str, ...] = ()
    hash_policy: HashPolicy = HashPolicy.ADAPTIVE
    large_file_threshold_mb: int = 10
    follow_symlinks: bool = False
    watch: bool = True
    effective_include: Tuple[RuleItem, ...] = ()
    effective_exclude: Tuple[RuleItem, ...] = ()
    negated_presets: Tuple["SpaceConfig", ...] = ()
    unresolved_presets: Tuple[str, ...] = ()
    unresolved_compose: Tuple[str, ...] = ()
    uri_warnings: Tuple[str, ...] = ()

class SpaceRegistry:
    def reload(self) -> None: ...
    def register_space(
        self,
        name: str,
        config: Union[SpaceConfig, Mapping[str, Any]],
        *,
        watch: Optional[bool] = None,
    ) -> SpaceConfig: ...
    def unregister_space(self, name: str) -> bool: ...
    def list_spaces(
        self,
        owner: Optional[str] = None,
        *,
        include_synthetic: bool = True,
    ) -> List[SpaceConfig]: ...
    def resolve_spaces(self, query: Optional[str] = None) -> List[SpaceConfig]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `SpaceCycleError`：當 `presets` 或 `compose`（含正向與 `!` 反向引用及 `/<short-name>` 合成節點）存在環路時拋出。
  - `SpaceNotFoundError`：當 `resolve_spaces(query)` 查詢不存在之空間名稱時拋出。
  - `SpaceError`：當 `hash_policy`、`large_file_threshold_mb` 或 `register_space` 名稱/型別非法時拋出。
- **階段決策紀錄**：`[P03:DR-01]` 保留 `define_ephemeral_space` 作為 `register_space` 之相容別名函式，確保任何外部呼叫零斷裂。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-06 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-05 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  - *問：若 `core/workspace` 在 `exclude` 中排除了 `.modules/**`，而某個專案在 `.modules` 內執行模組測試或 IDE 分析時是否會衝突？*
  - *答*：`workspace` 僅管轄專案層級廣域掃描上限，`vscode-support` 在投影 `python.analysis.exclude` 時保留 `has_modules_extra` 檢查，當 `.modules` 位於 `extraPaths` 時自動豁免 `**/.modules/**`。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md` | Modify | 同步更新 `core.space` 統一模型、`on_register_file_spaces`、`gitignore` 與 `workspace` 空間說明 |
| **專題手冊** | `docs/core/file_space.md` | Modify / N/A | 於 Phase 07 結案時同步更新空間雙層絕對聯集與反向引用契約 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | Modify | 登記 `CompiledRuleSet` 正反向對稱化與 `!preset` 局部子樹剪枝不變量 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `SpaceConfig`、`SpaceRegistry` 與 `core.gitignore` Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 07 記錄 `sub_05` 架構升級摘要 |

- **決策定稿**：**[P04:DR-01]** 通過動刀前 `Pre-Code Analyze Gate`（核對 `[P00:DR-01]` ~ `[P00:DR-06]` 全數映射至 `FR-01` ~ `FR-06` 與 `EC-01` ~ `EC-05`，無違反 `AGENTS.md` 與 `CodeQualityStandards.md` 紅線）。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：重構 `module:core` (`contributes/_format.json`, `contributes/core.json`, `core/space/{schema,registry,scanner,watcher,providers,__init__}.py`, `core/gitignore.py`, `scripts/cli.py`) 及 `module:file-space` 空殼匯出
- [x] **TASK-02**：重構下游模組 (`vscode-support`, `agents-workflow`, `gdrive-support`, `ast`, `knowledge-db`, `server`) 之 `contributes/core.json`、`on_register_file_spaces` hooks 與空間對接邏輯
- [x] **TASK-03**：更新與擴充 `core` 及下游模組之單元測試，通過全模組 `dev check` 與 `dev test` 沙盒回歸驗證
- [x] **TASK-DOC**：同步更新關鍵模組與公開 API Docstrings

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
