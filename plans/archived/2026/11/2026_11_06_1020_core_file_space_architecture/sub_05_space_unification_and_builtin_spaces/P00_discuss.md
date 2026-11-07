# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_05_space_unification_and_builtin_spaces  
> 建立日期：2026-11-07  
> 所屬主計畫：2026_11_06_1020_core_file_space_architecture  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 重新整理並重構 Space 的定義與聚合邏輯：不應區分動態 vs 靜態空間（移除 `is_ephemeral`），建立完整的統一空間體系，同時支援 `contributes` 注入、`on_register_file_spaces` 事件動態注入與 `runtime` 注入；廢除獨立的 `contributes.presets`，全面統一為 Space，並支援 `presets`（拉取規則）與 `compose`（拉取檔案結果）的 `!<target>` 反向引用語法。
  2. 新增兩大核心預設空間：
     - `gitignore`：正向定義不想被版控的檔案（整合原 `contributes.gitignore` 與 runtime `core.gitignore`，預設 `watch: false`）。
     - `workspace`：排除非專案資產（如 `.build`、`.modules`、`.venv`、`__pycache__` 等無統計效益的中間態檔案，`include: ["*"]` 僅設定 `exclude`），對標 VS Code 排除掃描設定，作為 `vfs`、`ast` 與 `core.space` 等任何需接觸檔案之模組的最外層遞迴式掃描空間上限。
- **核心目標**：
  1. 落實 `R01` 定案之 `SpaceConfig` 單一模型（乾淨移除 `PresetConfig`、`contributes.presets`、`fs presets`、`is_ephemeral`、`has_explicit_include`、`GitignoreEvaluator`、`gitignore_dynamic.json`、`@gitignore` 與頂層 `contributes.gitignore`）。
  2. 實作 `on_register_file_spaces` 事件與雙層絕對聯集及 `!<target>` 反向引用引擎：同空間多源注入與 `presets` 規則展開採規則層運算；`compose` 與自動生成之 `/<short-name>`（別名 `<short-name>`）採檔案結果層運算。
  3. 建置內建 `gitignore` 與 `workspace` 空間，並同步對齊全倉模組（`core`、`ast`、`knowledge-db`、`gdrive-support`、`agents-workflow`、`vscode-support`、`file-space`）之 `contributes/core.json`、`scripts/hook.core.py`、SDK 呼叫與單元測試。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 直接於 `ys_codebase/source/core/core/space/`、`ys_codebase/source/core/core/gitignore.py`、`ys_codebase/source/vscode-support/vscode_support/projector.py` 及各模組 `contributes/core.json` / `scripts/hook.core.py` 原地重構，不引入平行冗餘結構。
- **邊界排除 (Explicitly Excluded)**：
  - 暫不實作實體 `project://.gitignore` 中「開發者手寫非受控區塊」逆向解析回流至 `gitignore` 空間（先將 Space 與 `gitignore` 本身的正向定義與物化功能做好）。
  - 不變更 `core.vfs` 單檔物理讀寫鎖（File Guard）職責邊界。
- **架構影響範圍**：
  - `module:core` (`core/space/{schema.py,registry.py,scanner.py,cli.py,watcher.py,providers.py,__init__.py}`, `core/gitignore.py`, `contributes/_format.json`, `contributes/core.json`)
  - `module:vscode-support` (`vscode_support/projector.py`, `scripts/hook.core.py`, `contributes/core.json`)
  - `module:agents-workflow`, `module:gdrive-support`, `module:ast`, `module:knowledge-db`, `module:server`, `module:file-space` (`contributes/core.json`、`scripts/hook.core.py` 與空間引用對齊)

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 全面統一為 `SpaceConfig`、對稱化 `CompiledRuleSet` 並乾淨移除歷史包袱**：廢除獨立的 `PresetConfig`、`contributes.presets`、CLI `yscb fs presets`、SDK `list_presets`/`resolve_presets`、`is_ephemeral`、`has_explicit_include`、`GitignoreEvaluator` 與 `@gitignore` 魔術字串（並同步清理 `scanner.py` 之 `_ephemeral_snapshots` 與 `file-space` 轉發匯出）；對稱化 `CompiledRuleSet` 的 `include` 與 `exclude` 編譯語意（統一啟用 `allow_dir_prefix=True` 與 `match_any_seg=True`），使正向定義之目錄與片段規則在 `include` 下同樣能匹配目錄內所有檔案。
- **[P00:DR-02] 四階段兩趟編譯規則注入與 `on_register_file_spaces` 事件**：`SpaceRegistry.reload()` 拆為兩趟：Pass 1 依序執行 `1. Module Contributes -> 2. Project Config -> 3. on_register_file_spaces 事件廣播（帶重入防護與沙盒 search_roots 隔離） -> 4. In-Process Runtime Injection` 收集並以規則層絕對聯集合併各 `<owner>/<short-name>`；Pass 2 生成 `/<short-name>` 節點並以 DFS 拓撲展開 `presets` 與編譯 `SpaceConfig`。Runtime 注入未帶 `<owner>/` 時預設歸屬為 `__unknown__/<short-name>`，徹底廢除 `gitignore_dynamic.json`。
- **[P00:DR-03] `presets` 規則引用、`!<space>` 規則反轉排除與局部子樹剪枝不變量**：Space 的 `presets` 欄位直接填入其他 Space 名稱以拉取其規則池（含 DFS 環路檢測 `SpaceCycleError`；若指向 `/<short-name>` 則遞迴拉取所有同名 `<owner>/<short-name>` 規則）；當填入反向語法 `!<space>` 時，凡「符合目標 Space 規則條件（命中目標 `include` 且未命中目標 `exclude`）」的路徑即視為命中當前空間的 `exclude` 排除條件。於 `os.scandir` 目錄走訪時，只要目錄 `D` 命中目標 `include` 且目標 `effective_exclude` 中無任何可能匹配 `D` 子樹之豁免規則，即直接剪枝 `D`。
- **[P00:DR-04] `compose` 檔案結果絕對聯集、`!<space>` 結果差集與自動生成 `/<short-name>`**：每個空間的 `include` / `exclude` 僅過濾自身的 `entries`；正向 `compose` 採檔案結果絕對聯集，反向 `!<space>` 採檔案結果差集（$\text{Positive} \setminus \text{Negative}$）。`collect_all_entry_paths` 僅展開正向 `compose`（且 `gdrive_support/config.py` 改用 `collect_all_entry_paths` 避免被合成空間 `entries=()` 覆寫），而 `compute_config_hash` 則納入正反向 `compose` 與 `presets` 全依賴；`patch_files` 與 `SpaceWatcher` 統一以 `match_path` 評估差集。
- **[P00:DR-05] 內建 `gitignore` 正向空間與 `.gitignore` 物化收斂**：廢除 `contributes/core.json` 頂層 `"gitignore"` 陣列，各模組統一於 `spaces.gitignore` 正向定義不想被版控的檔案（`entries: ["project://"]`, `include: [...]`, `watch: false`）；`core.gitignore` 直接讀取所有 `<owner>/gitignore` 的規則並將 `yscb://` / `project://` 正規化為專案根相對路徑後，按 `# [<owner>]` 分組物化至 `project://.gitignore` 受控區塊（先輸出 `include` 正向忽略行，再將 `exclude` 冠上 `!` 輸出為 `!<pattern>` 豁免行）。
- **[P00:DR-06] 內建 `workspace` 最外層遞迴掃描上限空間與 VS Code Glob 轉譯**：於 `core` 定義 `spaces.workspace`（`entries: ["project://"]`, `include: ["*"]`, `exclude: [YSCB 執行期/建置中間態與 VCS/Python/OS 快取黑名單]`），作為 `resolve_spaces(None)` / `scan(None)` 等未指定特定空間時的預設全倉遞迴掃描上限（且 `"*"` 與 `SpaceWatcher` 預設排除 `watch=False` 之 `gitignore`）；`vscode-support` 讀取 `workspace.exclude` 並經語意 URI / 裸名轉 `**/...` Glob 正規化層投影至 `.vscode/settings.json`（保留 `extraPaths` 含 `.modules` 時對 `**/.modules/**` 之豁免防護）。

---

## 3. 開放議題與確認紀錄

- 所有架構設計、`on_register_file_spaces` 事件與盲眼審查邊界修補處方均已拍板確認，無開放議題。
