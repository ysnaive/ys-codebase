# 專題調研與分析報告：`module:space` 生態系前置介面與 Contributes / CLI 契約設計 (R03_ecosystem_contracts_and_cli_design.md)

> 調研主題：`module:space` 在 `ys-codebase` 生態系中需提前定案之 Contributes 結構、CLI 樹、組態矩陣與跨模組遷移契約  
> 建立日期：2026-11-02  
> 所屬主計畫：2026_11_02_0339_module_space_feasibility_research  
> 調研狀態：Concluded  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：
  在完成 `R01`（可行性與分級雜湊、`watchdog` 依賴拍板）與 `R02`（單調世代游標、三級雜湊與核心 SDK 簽名）後，啟動 `module:space` 開發立項前，必須先針對 **`ys-codebase` 生態系的跨模組對接契約** 進行一次性定案。因為一旦 `module:space` 成為 Layer 1 基礎設施底座，其 `contributes/_format.json`、`contributes/core.json`、`config/space/` 2x2 組態結構，以及既有 `knowledge-db` / `agents-workflow` 的空間宣告遷移方式，將直接決定全倉 `dev check` 合規檢核與向下相容性。
- **調研目標與範疇**：
  精確盤點並提前定案以下 6 大生態系層級契約：
  1. **`module:space` 的 `manifest.json` 與依賴邊界**（含 `watchdog>=4.0.0` 承接與 `server` optional 宣告）。
  2. **`space` 對外開放的擴充契約 `contributes/_format.json`**（統一 `SpaceDef` 欄位命名，相容既有 `include` / `exclude` / `file_patterns` 語法並擴充 `hash_policy`）。
  3. **既有模組（`knowledge-db` 與 `agents-workflow`）之空間宣告解耦與零斷裂雙軌相容策略**（如何將 `weight` 留在 `knowledge-db` 而把空間幾何移交 `space`）。
  4. **`module:space` 向 `core`、`server`、`agents-workflow` 注入的 `contributes/*.json` 完整規格**（URI Schemes、CLI 指令樹、`space-watcher` 服務、工作流指南與 Token 錨點）。
  5. **專案級 2x2 組態模板（`config/space/`）與多語系 `locales/` 契約**。
  6. **分階段落地與平滑遷移策略（Umbrella Plan 子計畫切分建議）**。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 契約一：`module:space/manifest.json` 依賴與套件邊界定案

`module:space` 定位為 Layer 1 基礎設施模組，直接承接原 `knowledge-db` 的 `watchdog>=4.0.0` 依賴，使 `knowledge-db` 可從自身 `pip_dependencies` 中移除 `watchdog`（改由依賴 `"space": ">=1.0.0"` 自動傳遞）：

```json
{
  "name": "space",
  "version": "1.0.0.0",
  "description": "YS-Codebase Unified File Space, Tiered Fingerprinting & Background Watcher Subsystem",
  "entry": "scripts/cli.py",
  "dependencies": {
    "core": ">=1.2.1"
  },
  "optional": {
    "server": {
      "version": ">=1.0.0",
      "hint": "提供常駐 space-watcher 背景檔案變更監聽與零延遲快取預熱"
    }
  },
  "pip_dependencies": {
    "watchdog": ">=4.0.0"
  },
  "onboarding": [
    "[Pre-flight] Configure project file spaces in config/space/contribute.json (spaces.source.include)",
    "Inspect registered spaces & fingerprint cache health: python yscb.py space status",
    "Scan spaces and compute Merkle roots: python yscb.py space scan"
  ]
}
```

---

### 2.2 契約二：`space/contributes/_format.json` 空間定義 Schema 定案（向後相容既有語法）

- **關鍵相容性設計**：
  在 `R02` 盲眼設計中曾使用 `roots / include_globs / exclude_globs` 命名；但對照目前母倉與下游專案（`uitk.net`、`GC_VEX_V5`）已經廣泛部署的 `config/knowledge-db/contribute.json` 與 `agents-workflow/contributes/knowledge-db.json`，全生態系現行標準欄位名稱為 **`include`（語意 URI 或目錄/檔案路徑清單）、`exclude`（排除 Glob 清單）、`file_patterns`（檔案名稱/副檔名 Glob 清單，如 `["*.py", "*.md"]`）**。
  - **定案裁決**：**100% 沿用既有 `include`、`exclude`、`file_patterns` 欄位名稱，且頂層 `spaces` 維持 `dict[space_name, SpaceDef]` 字典映射結構**（而非 List）！如此可讓 `core.contributes` 的 `_deep_merge` 自動按 `space_name` 實現「專案級 `config/space/contribute.json` 覆蓋模組預設空間」，且既有配置遷移成本為零！

```json
{
  "_types": {
    "SpaceDef": {
      "description": "str?",
      "include": "list[str]!",
      "exclude": "list[str]?",
      "file_patterns": "list[str]?",
      "hash_policy": "enum(adaptive, full_hash, stat_only, lazy_stabilized)? = adaptive",
      "large_file_threshold_mb": "int? = 10",
      "follow_symlinks": "bool? = false",
      "watch": "bool? = true"
    }
  },
  "spaces": {
    "description": "向 space 模組註冊通用檔案空間幾何範圍、過濾規則與分級雜湊策略",
    "format": {
      "*": "$SpaceDef"
    }
  }
}
```

- **四種 `hash_policy` 明確定義**：
  - `adaptive`（**預設**）：檔案 `< large_file_threshold_mb`（預設 10MB）時計算全檔 `blake2b`；`>= 10MB` 時自動切換「頭 64KB + 中 64KB + 尾 64KB + 檔案大小」稀疏取樣 `blake2b`（單檔 `< 1ms`）。
  - `full_hash`：不論檔案大小一律串流計算全檔 `blake2b`。
  - `lazy_stabilized`：背景 Watcher 偵測到變動時先檢查檔案穩定度（距離最後修改 `>= 2.0s` 且無獨佔寫入鎖）後再計算雜湊，適用於外部工具持續寫入之大檔空間。
  - `stat_only`：不開啟檔案，僅以 `(relpath, size, mtime_ns)` 合成指紋，適用於龐大唯讀外部依賴目錄。

---

### 2.3 契約三：`knowledge-db` 與 `agents-workflow` 空間宣告解耦與 `Mode A` 單一正統收斂

經開發者拍板，由於引入全新 `module:space` 基礎設施依賴必然屬於 Minor 以上之版本迭代（`knowledge-db@1.2.0.0`、`agents-workflow@1.3.0.0`），空間遷移契約全面遵循 **`/code-optimizer` 之 `Mode A：收斂期 / 允許破壞性清理 (Convergence Mode)`** 原則，強制建立**單一正統入口（Single Canonical Entry）**，零容忍物理刪除過渡轉發層、相容別名與重複代碼：

1. **空間幾何歸 `space`、檢索權重歸 `knowledge-db`（零雙軌 Fallback 殘留）**：
   - **`module:space` 成為全系統空間定義唯一真理來源（SSOT）**：
     - 專案級空間配置統一收斂至 `config/space/contribute.json`（移除原 `config/knowledge-db/contribute.json` 中的 `spaces` 幾何定義）。
     - `agents-workflow` 新增 `ys_codebase/source/agents-workflow/contributes/space.json` 宣告 `"docs"` 與 `"plans"` 空間幾何；原 `agents-workflow/contributes/knowledge-db.json` 僅保留檢索專屬權重 `space_weights: {"docs": 1.2, "plans": 0.85}`。
     - `knowledge-db/contributes/_format.json` 移除舊版 `SpaceDef` 幾何定義，改為簡潔的 `"space_weights": {"format": {"*": "float!"}}`。
2. **`knowledge-db` 內部執行 `Mode A` 徹底拔除與收斂（零薄轉發殼層）**：
   - **物理刪除** `ys_codebase/source/knowledge-db/knowledge_db/{space.py,scanner.py,service.py}` 及 `knowledge-db/contributes/server.json`，絕不保留 `knowledge_db.space` 轉發 Adapter 殼層。
   - 同步更新 `knowledge-db` 內部所有調用點（`engine.py`、`pipeline.py`、`bundler.py`、`providers.py`、`retrieval.py`）與 `tests/` 測試套件，直接 import 並調用 `space` 公開 SDK（`space.SpaceManager`、`space.consume_diff`、`space.merkle_root`），並新增 `knowledge-db/scripts/hook.space.py` 訂閱 `on_space_changed` 事件執行增量熱修補。

---

### 2.4 契約四：`module:space` 向核心生態系注入之 `contributes/*.json` 規格

#### 2.4.1 `contributes/core.json`（URI 協議、CLI 指令樹、事件與多語系）

1. **自訂語意 URI 協議 (`uri_schemes`)**：
   - `space.cache://` $\rightarrow$ `"value": "cache://space/"`（指向 `module:space` 的二進位/SQLite 快取與游標資料庫目錄）。
2. **生命周期事件宣告 (`events`)**：
   - `on_space_changed`：`"當 space-watcher 偵測到空間內檔案實質變更並推進世代號 (generation) 時廣播"`。
3. **CLI 指令樹 (`commands.cmd`)**：
   為對齊 `core/contributes/_format.json` 的嚴格檢核規範（`tier`、`server_compatible`、`args`、`options`、`usage`），提前定案 5 個高內聚子命令：

| CLI 指令 | `tier` | `server_compatible` | 參數與選項 (`args` / `options`) | 核心用途 |
| :--- | :---: | :---: | :--- | :--- |
| `yscb.py space status [<space>]` | `safe` | `true` | `args.space (optional)`<br>`options`: `--all/-a`, `--scan/--diff`, `--json` | 檢視所有（或指定）空間之有效檔案數、當前 `generation`、`merkle_root`、各消費者 (`consumer_id`) 游標水位與 Watcher 狀態 |
| `yscb.py space scan [<space>]` | `safe` | `true` | `args.space (optional)`<br>`options`: `--force/-f`, `--json` | 立即觸發空間增量掃描（`--force` 強制重算內容雜湊），更新快取並輸出耗時、Stat 命中數、雜湊重算數與最新 `merkle_root` |
| `yscb.py space files <space>` | `safe` | `true` | `args.space (required)`<br>`options`: `--pattern/-p <glob>`, `--json` | 列出指定空間內匹配之檔案清單及其 `(rel_path, size, content_hash, updated_gen)` |
| `yscb.py space diff <space>` | `safe` | `true` | `args.space (required)`<br>`options`: `--consumer/-c <id>`, `--ack`, `--json` | 查詢指定消費者游標（或省略 `--consumer` 時對比當前磁碟與快取）之 `added / modified / deleted` 差量明細；帶 `--ack` 時同步推進游標 |
| `yscb.py space clean [<space>]` | `conditional` | `true` | `args.space (optional)`<br>`options`: `--reset-cursors`, `--json` | 清除指定（或全部）空間之指紋快取與過期墓碑；帶 `--reset-cursors` 時一併重置所有消費者游標 |

#### 2.4.2 `contributes/server.json`（常駐背景監聽服務）

取代原本位於 `knowledge-db/contributes/server.json` 的 `knowledge-db-watcher`，改由 `module:space` 註冊全系統唯一的 `space-watcher`（或保留 `knowledge-db` 內部透過 `hook.space.py` / 訂閱回呼響應 `space-watcher`）：

```json
{
  "services": [
    {
      "name": "space-watcher",
      "worker_class": "space.service:SpaceWatcherServiceWorker",
      "description": "全域檔案空間變更監聽、分級指紋預熱與差量事件廣播服務",
      "auto_start": true
    }
  ]
}
```

> **與 `knowledge-db` 的熱自癒銜接方式**：
> 當 `space-watcher` 在 `server` 的 `WarmWorker` 內偵測到檔案變更並更新空間快取後，會呼叫 `core.events.broadcast("on_space_changed", payload, emit_module="space")` 並觸發進程內 `space.subscribe()` 回呼。`knowledge-db` 只需提供 `scripts/hook.space.py`（或在 `WarmWorker` 內註冊回呼），在收到 `on_space_changed` 時呼叫 `with space.consume_diff(..., consumer_id="knowledge-db")` 執行 `pipeline.hot_patch_unified_index()` 即可！全系統永遠只有 **1 個 `watchdog.Observer` 執行緒**！

#### 2.4.3 `contributes/agents-workflow.json`（工作流與教練技能注入）

- 向 `HOW_TO_CONFIG_MODULES` 注入 `module://space/assets/config_guide.md`（引導 `/how-to-config-yscb` 檢查 `config/space/contribute.json` 與 `yscb.py space status`）。
- 向 `HOW_TO_YSCB_MODULES` 注入 `module://space/assets/usage_guide.md`（引導 `/how-to-yscb` 介紹 `space status / scan / files / diff`）。
- 提供 `SPACE_REGISTRY_TABLE` 動態 Token Provider（`code.func://space/space/providers:get_registered_spaces_table`），並讓原 `knowledge-db` 的 `KNOWLEDGE_DB_SPACE` 直接複用或串接。

---

### 2.5 契約五：專案組態模板（`templates/config/`）與儲存格式選型

1. **隨包組態模板 (`ys_codebase/source/space/templates/config/`)**：
   - `contribute.json`：預置 `"source"` 空間骨架（`include: ["module.source://"]`、標準 `exclude` 與 `"hash_policy": "adaptive"`）。
   - `config.project.json`：預置全域預設參數（`default_hash_policy: "adaptive"`、`large_file_threshold_mb: 10`、`debounce_ms: 500`）。
   - `config.local.json`：預置本機覆寫參數（`force_polling: false`）。
2. **底層快取持久化格式定案（`YFP2` 二進位快照 vs. SQLite WAL）**：
   - 對比 `R01`（`YFP2` C-struct 二進位檔）與 `R02`（`sqlite3` WAL 模式）：
   - 在 `knowledge-db` 現有測試中，`BinarySnapshotManager (YFP1)` 反序列化 1,000 個檔案僅需 `< 0.1ms`，且對跨平台容器檔案系統（如 `virtiofs` / Windows 網路掛載磁碟，SQLite WAL 的 `shm` 共享記憶體鎖有時在 `virtiofs` 會遇到相容性問題）具有 **100% 絕對的檔案系統可攜性與原子替換 (`os.replace`) 韌性**！
   - **最佳融合定案**：採用 **`YFP2` 擴充二進位格式（搭配輕量 JSON 消費者游標帳本 `cursors.json`）**！
     - `cache://space/snapshots/<space_name>.yfp2.bin`（或 `unified.yfp2.bin`）：使用緊湊 `struct` 打包 `(path_len, size, mtime_ns, created_gen, updated_gen, flags, hash_bytes)` 與檔頭 `(magic="YFP2", version=2, head_generation, merkle_root_bytes)`，兼具 `< 0.1ms` 載入速度、`os.replace` 原子寫入與 100% `virtiofs`/Windows 零鎖定問題。
     - `cache://space/cursors/<consumer_id>.json`：每個消費者獨立一個極小 JSON 檔記錄 `{space_name: {"acked_gen": 11, "merkle_root": "..."}}`，透過 `vfs.write_json(..., atomic=True)` 各自獨立原子寫入，連跨消費者之間的寫入鎖競爭都徹底歸零！

---

## 3. 結論與實作立項藍圖 (Conclusion & Implementation Blueprint)

- **核心結論**：
  透過 `R01`、`R02` 與本篇 `R03` 的三階收斂，`module:space` 的所有內外部契約已 100% 明確且與現有生態系完美對齊：
  1. **高內聚職責邊界**：專注於「宣告式空間聚合 (`SpaceManager`)」、「二階段短路 + 四模分級雜湊 (`adaptive` / `full_hash` / `lazy_stabilized` / `stat_only`) + `merkle_root`」、「單調世代水位 + 多消費者獨立游標 (`cursors/<consumer_id>.json` + `with consume_diff()`)」與「基於 `watchdog` 的單一 `space-watcher` 常駐服務」。
  2. **`Mode A` 單一正統入口收斂（零過渡相容包袱）**：依 Minor 以上版本迭代標準，將空間幾何定義 100% 收斂至 `module:space`，物理刪除 `knowledge-db` 內部的 `space.py`、`scanner.py` 與 `service.py`（不留薄轉發殼層），並將檢索權重精簡為 `knowledge-db` 的 `space_weights`，以每消費者獨立游標檔結合 `YFP2` 二進位快照實現全倉單一 Watcher 與零寫入鎖競爭。
- **後續立項建議（建議採用 Umbrella Plan 雙子計畫或 Full Track 推進）**：
  - **`sub_01_space_module_core`**：建立 `ys_codebase/source/space/` 模組（含 `manifest.json`、`contributes/{_format,core,server,agents-workflow}.json`、`YFP2` 二進位快照與分級雜湊引擎、世代游標 `diff/ack/consume_diff` SDK、`SpaceWatcherServiceWorker` 與 5 大 CLI 子命令），通過 `dev check space` 與完整沙盒單元測試。
  - **`sub_02_ecosystem_space_migration`**：以 `/code-optimizer` `Mode A（收斂期 / 允許破壞性清理）` 將 `knowledge-db` 與 `agents-workflow` 徹底遷移至 `module:space`（物理拔除 `knowledge-db/{space,scanner,service}.py`，直接調用 `space` SDK 並透過 `hook.space.py` 響應增量熱修補；更新母倉 `config/space/contribute.json` 與全套測試），實現全倉單一正統入口。

