# 專題調研與分析報告：Space 定義統一與雙層絕對聯集聚合重構 (R01_space_definition_and_aggregation.md)

> 調研主題：全面統一為 Space 結構、`on_register_file_spaces` 事件與 Runtime 注入、雙層絕對聯集與 `!<target>` 反向引用代數、內建 `gitignore` 與 `workspace` 空間  
> 建立日期：2026-11-07  
> 所屬主計畫：2026_11_06_1020_core_file_space_architecture / sub_05_space_unification_and_builtin_spaces  
> 調研狀態：Concluded  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：
  1. **靜態與動態空間二元割裂 (`is_ephemeral`) 與缺乏動態註冊事件**：現行 `SpaceRegistry` 將空間拆分為靜態宣告（`contributes`）與動態暫態空間（`_ephemeral_spaces` / `is_ephemeral=True`），且缺乏在 `SpaceRegistry.reload()` 時供各模組根據組態動態注入空間的生命週期事件（導致 `gdrive-support/cloud` 平時於 `fs spaces` 不可見，且 `core.gitignore` 需額外維護 `gitignore_dynamic.json` 檔案）。
  2. **`Preset` 與 `Space` 雙軌冗餘及 `contributes.gitignore` 分裂**：原本獨立存在 `contributes.presets`、`PresetConfig`、`@gitignore` 魔術字串與頂層 `contributes.gitignore` 清單；當 Space 本身支援空 `entries: []` 且 `presets` 欄位可直接引用其他 Space 拉取規則時，獨立的 `Preset` 型別與 `contributes.presets` 成為多餘歷史包袱。
  3. **`compose` 與母空間過濾規則耦合**：現行 `_evaluate_composite_secondary_filter` 將母空間自身的 `include` 與 `exclude` 回頭二次過濾 `compose` 子空間的檔案結果，導致規則展開（`presets` / 注入）與結果聯集（`compose`）兩種計算模型互相干擾。
  4. **短名稱聯集缺乏一等公民空間實體**：現行短名稱 `<short-name>` 僅在查詢時回傳 `List[SpaceConfig]`，並未在註冊表中自動具現化為一顆可獨立定址與被組合的實體空間（`/<short-name>`）。
- **調研目標與範疇**：
  - 全面統一為 `SpaceConfig` 單一模型（乾淨移除 `PresetConfig`、`contributes.presets`、`fs presets`、`is_ephemeral`、`has_explicit_include`、`GitignoreEvaluator`、`gitignore_dynamic.json` 與頂層 `contributes.gitignore`）。
  - 新增 `on_register_file_spaces` 核心事件，建立「四階段規則注入 + `presets` 規則展開 + `compose` 檔案結果運算」之雙層絕對聯集與 `!<target>` 反向引用模型。
  - 定義內建核心預設空間 `gitignore` 與 `workspace`（排除非專案資產之最外層遞迴掃描上限）。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 全面統一為 `SpaceConfig` 完整 Metadata 定義

廢除獨立的 `PresetConfig`、`contributes.presets`、`is_ephemeral` 與 `has_explicit_include`，所有規則集與檔案空間統一由 `SpaceConfig` 承載（純規則模板即為 `entries: ()` 的 Space）：

| 分類 | 欄位名稱 | 型別 / 預設值 | 職責說明 |
| :--- | :--- | :--- | :--- |
| **識別資訊** | `qualified_name` | `str` | 空間完整名稱：具名空間為 `<owner>/<short-name>`，自動合成之短名聯集空間為 `/<short-name>` |
| | `owner` | `str` | 來源模組名稱；短名自動合成空間為 `""`；Runtime 未指定來源時預設為 `"__unknown__"` |
| | `short_name` | `str` | 空間短名稱 |
| | `description` | `str = ""` | 空間用途描述 |
| **範圍與組合** | `entries` | `Tuple[str, ...] = ()` | 自身掃描根路徑清單（支援相對路徑與 `project://` 等語意 URI；允許與 `compose` 同時為空，此時評估結果為 $\emptyset$） |
| | `compose` | `Tuple[str, ...] = ()` | 組合其他 Space 的檔案結果集合（支援正向聯集 `<space>` 與反向差集 `!<space>`） |
| **過濾規則** | `presets` | `Tuple[str, ...] = ()` | 引用其他 Space 的規則池（僅拉取目標 Space 之規則；支援正向展開 `<space>` 與反向排除 `!<space>`） |
| | `include` | `Tuple[str, ...] = ()` | 僅針對自身 `entries` 的白名單規則（未指定且無正向 preset include 時預設為 `["*"]`） |
| | `exclude` | `Tuple[str, ...] = ()` | 僅針對自身 `entries` 的黑名單排除規則（優先權高於自身 `include`） |
| **掃描與監控** | `hash_policy` | `HashPolicy = "adaptive"` | 指紋策略：`adaptive` / `full_hash` / `stat_only` / `lazy_stabilized` |
| | `large_file_threshold_mb` | `int = 10` | `adaptive` 模式下轉為 `stat_only` 的大檔門檻 (MB) |
| | `follow_symlinks` | `bool = False` | 掃描時是否穿透符號連結 |
| | `watch` | `bool = True` | Server FileWatcher 是否常駐監控此空間（`gitignore` 空間預設為 `False`） |

---

### 2.2 雙層絕對聯集、`on_register_file_spaces` 事件與 `!<target>` 反向引用代數模型

核心代數公理：**絕對聯集目標取決於操作目標——「多源注入與 `presets` 規則引用」操作的是規則 (Rule Set)，「`compose` 與短名空間合成」操作的是檔案結果 (File Set)，兩者正交不耦合，完全禁止其他合併策略。**

#### 第一層：同一個 `<owner>/<short-name>` 的四階段兩趟編譯與 `presets` 規則層運算
1. **四階段收集與兩趟編譯管線 (`SpaceRegistry.reload()`)**：
   $$\text{Pass 1 (Raw Collection): } \text{1. Module Contributes} \longrightarrow \text{2. Project Config} \longrightarrow \text{3. Event: \texttt{on\_register\_file\_spaces}} \longrightarrow \text{4. Runtime Injection}$$
   $$\text{Pass 2 (Topological Compilation): } \text{合成 \texttt{/<short-name>} 節點} \longrightarrow \text{DFS 展開 \texttt{presets} 與 \texttt{!presets}} \longrightarrow \text{對稱編譯 \texttt{CompiledRuleSet}}$$
   - **為什麼必須兩趟編譯 (Two-Pass Compilation)**：避免 Stage 1 (`core`) 的空間先展開 `presets` 時，漏掉 Stage 2~4 才注入到目標空間的規則；且當 Stage 4 執行期呼叫 `register_space()` 時，更新原始規則表並重新觸發 Pass 2 編譯。
   - **`on_register_file_spaces` 事件重入防護與沙盒隔離**：
     - 當 `SpaceRegistry` 以顯式 `raw_spaces` 測試資料初始化時，不廣播全域事件。
     - 廣播 `on_register_file_spaces` 時設有 `_in_reload_broadcast` 重入鎖防護，並顯式傳入 `search_roots=[self._yscb_dir / ".modules"]` 確保沙盒隔離；`gdrive-support` 於 hook 中僅讀取輕量 `repo_sync` 組態，不重複實例化 `SpaceRegistry`。
   - **預設來源歸屬**：Runtime 注入若未指定 `<owner>/`（僅傳入 `<short-name>`），預設 `owner` 為 `"__unknown__"`（即 `__unknown__/<short-name>`）；若傳入前導斜線 `"/<short-name>"`，`_parse_qualified_key` 保留前導斜線代表無來源合成空間（`owner=""`）。
2. **`CompiledRuleSet` 正反向編譯語意 100% 對稱化**：
   - 修正既有 `schema.py` 中 `allow_dir_prefix=is_exclude` 與 `match_any_seg=self.is_exclude` 的非對稱限制：無論規則置於 `include`（如正向 `gitignore` 的 `"yscb://.venv/"`、`"__pycache__"`）或 `exclude`，統一啟用目錄前綴匹配（`allow_dir_prefix=True`，且移除 `dir_only` 對目錄內子檔案前綴匹配之阻擋）與路徑片段匹配（`match_any_seg=True`），確保同一條規則在 `include` 與 `exclude` 下命中的檔案集合 100% 一致。
3. **同空間多源注入合成律**：
   - **`entries` / `compose` / `presets`**：依注入順序執行去重聯集 (`Union`)。
   - **`include`（對自身 `entries` 的檔案覆蓋絕對聯集）**：若任一次宣告/注入已包含全域萬用字元 `"*"`（或 `"**"`、`**/*`），則 `[*] ∪ [任何規則]` 在檔案角度恆為 `[*]`，後續再添加任何選項皆維持 `["*"]` 不變；若某次注入未顯式提供 `include`，則不覆蓋既有顯式 `include`；若全部注入與正向 `presets` 均未提供 `include`，最終預設為 `["*"]`。
   - **`exclude`（黑名單規則聯集）**：將各次注入之 `exclude` 規則執行去重聯集 (`exclude_1 ∪ exclude_2`)，共同排除自身 `entries` 下匹配的檔案。
   - **純量屬性**：後續注入若有顯式指定則更新，未指定則保留既有值。
4. **`presets` 欄位（引用其他 Space 的規則池）與局部子樹目錄剪枝不變量**：
   - **DAG 環路檢測與合成空間展開**：`presets` 展開與 `compose` 統一納入 DFS 循環依賴檢測（遇環拋出 `SpaceCycleError`）。當 `presets`（或 `!presets`）指向合成空間 `/<short-name>` 時，自動遞迴收集其所有正向 `compose` 子空間（`<owner>/<short-name>`）的規則。
   - **正向引用 `<space>`**：遞迴拉取目標 Space 的 `include` 與 `exclude` 規則並展開聯集至當前空間的規則池。
   - **反向引用 `!<space>` 與局部子樹剪枝不變量**：
     - 語意：凡「符合目標 Space 規則條件（命中目標 `include` **且未命中**目標 `exclude`）」的路徑，即視為命中當前空間的 **`exclude` 排除條件**（絕不將目標的 `exclude` 混入當前空間的 `include`）。
     - **局部子樹目錄剪枝不變量**：在 `os.scandir` 走訪目錄 `D` 時，針對反向引用 `!T`，當 `D` 明確命中 `T` 之 `include` 規則，且 **`T.effective_exclude` 中沒有任何可能匹配 `D` 或 `D` 子樹的豁免規則**（即無非錨定萬用規則、且無以 `D` 為前綴或祖先之豁免規則）時，直接安全剪枝跳過 `D`（避免因單一無關檔案豁免而導致 `.venv/`、`.modules/` 喪失剪枝能力）；唯有當 `D` 子樹內可能存在豁免規則時才進入 `D` 於檔案層級精確判定。

#### 第二層：`compose` 與自動短名空間 `/<short-name>` 的結果層運算
1. **`compose` 檔案結果運算（正向絕對聯集 + 反向差集）**：
   - 每個空間的 `presets` / `include` / `exclude` **100% 只作用於該空間自己的 `entries`**（移除母空間對 `compose` 子空間的二次過濾）。
   - 當空間 $S$ 宣告正向 `compose` 集合 $C^+$ 與反向 `compose` 集合 $C^-$（以 `!<space>` 表示）時：
     $$\text{Files}(S) = \left(\text{EvalOwnEntries}(S) \;\cup\; \bigcup_{P \in C^+} \text{Files}(P)\right) \;\setminus\; \bigcup_{N \in C^-} \text{Files}(N)$$
   - **路徑收集 vs. 組態雜湊分流**：
     - `collect_all_entry_paths`（供 Watcher 監聽根目錄與 `gdrive-support` 解析空間根目錄）**僅展開正向 `compose` ($C^+$)**，忽略負向 `!<space>` ($C^-$)。
     - `compute_config_hash` 則將**正向 $C^+$、負向 $C^-$ 及 `presets` / `!presets` 依賴之所有空間**全數納入雜湊計算，確保 `!B` 規則異動時快照能正確失效重算。
     - `scanner.py:patch_files` 與 `SpaceWatcher` 增量變更判定統一調用 `registry.match_path` 完整評估（含 `!compose` 差集），而非僅用單層 `matches`。
2. **自動生成短名合成空間 `/<short-name>` 與列舉隔離**：
   - 只要系統中出現任何短名稱為 `<short-name>` 的空間，註冊表自動生成並維護一個無來源名的對應空間：`qualified_name = "/<short-name>"`（查詢時輸入 `"/<short-name>"` 或 `"<short-name>"` 皆解析至此空間）、`owner = ""`、`short_name = "<short-name>"`、`entries = ()`、`compose = (<owner_1>/<short-name>, ...)`。
   - 快照鍵值正規化 (`_sanitize_target_key`) 明確區分 `/<short-name>`（轉為 `synthetic__<short-name>`）與 `<owner>/<short-name>`（轉為 `<owner>__<short-name>`），杜絕檔名碰撞。
   - `resolve_spaces(None)` / `scan(None)` 未指定目標時預設解析為 `["/workspace"]`；萬用查詢 `"*"` 與 `SpaceWatcher` 預設監控清單自動排除 `watch=False` 之空間（如 `gitignore`）與無入口之純規則空間；`gdrive_support/config.py` 改以 `collect_all_entry_paths` 取得空間根目錄，避免被 `/<short-name>` 之 `entries=()` 覆寫。

---

### 2.3 內建核心預設空間：`gitignore` 與 `workspace`

| 空間短名 | 預設宣告 (`core/<name>`) | 設計語意與跨模組契約 |
| :--- | :--- | :--- |
| **`gitignore`** | `entries: ["project://"]`<br/>`include: [各模組不想被版控之規則...]`<br/>`exclude: [特例保留規則...]`<br/>`watch: False` | 1. **正向定義**：空間內容即為「不想被版控的檔案集合」，廢除頂層 `contributes.gitignore`。<br/>2. **`.gitignore` 物化轉譯**：`core.gitignore` 讀取所有 `<owner>/gitignore` 的規則按 `# [<owner>]` 分組物化寫入 `project://.gitignore` 受控區塊，其中 `include` 輸出為正向忽略行、`exclude` 自動加上 `!` 前綴輸出為 `!<pattern>` 豁免行。<br/>3. **常駐隔離**：預設 `watch: False`，避免 Server FileWatcher 監控 `.venv/`、`.modules/` 等龐大忽略目錄。<br/>4. **反向排除引用**：其他空間可透過 `presets: ["!gitignore"]` 或 `compose: ["!gitignore"]` 排除版控忽略檔案。 |
| **`workspace`** | `entries: ["project://"]`<br/>`include: ["*"]`<br/>`exclude: [非專案資產與中間態黑名單...]`<br/>`watch: True` | 1. **最外層遞迴掃描上限**：排除 `.modules`、`.build`、`.mirror`、`.temp`、`.snapshots`、`.cache`、`.config.local`、`.storage.local`、`.venv`、`.git`、`__pycache__`、`*.pyc` 等無統計與分析效益的中間態檔案。<br/>2. **全倉預設掃描目標**：作為 `core.space`、`vfs`、`ast` 等模組未指定特定子空間時的預設最大遞迴掃描範圍上限。<br/>3. **基底規則繼承與 IDE 投影**：其他業務空間可透過 `presets: ["workspace"]` 繼承排除黑名單；`vscode-support` 讀取 `workspace` 的排除規則並正規化轉譯為 VS Code `**/...` Glob 投影至 `.vscode/settings.json`（保留 `extraPaths` 含 `.modules` 時對 `**/.modules/**` 之豁免防護）。 |

---

## 3. 結論 (Conclusion)

- **核心結論**：
  1. 全面統一為 `SpaceConfig`，乾淨移除 `PresetConfig`、`contributes.presets`、`fs presets`、`is_ephemeral`、`has_explicit_include`、`GitignoreEvaluator`、`gitignore_dynamic.json`、`@gitignore` 與頂層 `contributes.gitignore`。
  2. 新增 `on_register_file_spaces` 事件驅動跨模組動態空間注入，確立「四階段規則注入 + `presets` 操作規則、`compose` 與 `/<short-name>` 操作檔案結果」的雙層絕對聯集與 `!<target>` 反向引用代數模型，並通過盲眼審查修補剪枝與列舉隔離邊界。
  3. 建立 `gitignore`（正向定義不想被版控的檔案，`watch: False`）與 `workspace`（排除非專案資產之最外層遞迴掃描空間上限，作為預設全倉掃描目標）兩大內建核心空間。
- **後續建議（選填）**：
  - 採出口 ① 立即轉入 `sub_05` 實作計畫推進。
