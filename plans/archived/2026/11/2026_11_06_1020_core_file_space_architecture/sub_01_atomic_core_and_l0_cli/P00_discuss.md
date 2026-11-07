# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_01_atomic_core_and_l0_cli  
> 建立日期：2026-11-06  
> 所屬主計畫：2026_11_06_1020_core_file_space_architecture  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：將 `file-space` 核心能力直接內聚併入 `module:core`，第一步建立核心原子功能（所有後續複合功能皆應能藉由這些原子操作達成），並輸出成 L0 CLI（掛載於 `core` 命令 `file-space`、別名 `fs`，可透過 `yscb.py core file-space` 或 `yscb.py fs` 呼叫）。
- **核心目標**：
  1. **空間與預設集原子定義模型 (`SpaceDef` / `PresetDef`)**：於 `core` 建立支援 `entries`（多入口：資料夾或單一檔案，支援語意 URI）、`presets`（顯式引用 `{include, exclude}` 規則包，含內建動態 `@gitignore`，無隱式全域 `default_presets`）、`include`（預設 `["*"]`）與 `exclude`（優先級高於 `include`）之結構化資料模型與 `contributes/core.json`（`_format.json`）Schema 定義。
  2. **命名空間隔離與聯集尋址 (`<owner>/<name>` vs `<name>`)**：模組於 `contributes/core.json` 定義之空間與預設集自動冠上 `<module>/<name>`，專案於 `config/core/contribute.json` 定義者自動冠上 `project/<name>`，互不覆蓋、零載入順序衝突；查詢或引用時指定 `<owner>/<name>` 為精準定位，指定短名 `<name>` 則自動代表所有同名定義之聯集。
  3. **三座標相容預編譯匹配與零冗餘剪枝走訪 (`match` / `ls` / `hash`)**：
     - 實作三座標相容規則編譯與單點判定原語 (`match`)：① 語意 URI 前綴、② 含 `/` 之相對路徑（同時相容相對於 `project://` 之 `project_rel` 與相對於所屬 `entry` 之 `entry_rel`）、③ 不含 `/` 之任意層級檔名或目錄名。
     - 實作基於 `os.scandir` / `DirEntry.stat()` 之目錄級剪枝與檔案過濾原子走訪原語 (`ls`)，對跨入口或短名聯集空間自動依實體路徑去重。
     - 實作純標準庫單檔與空間級指紋計算原語 (`hash`，支援 `adaptive`、`full_hash`、`stat_only` 策略與空間 Merkle Root 聚合）。
  4. **L0 CLI 暴露 (`core file-space` / `fs`)**：於 `core` 註冊命令 `file-space`（別名 `fs`），提供 `spaces`、`presets`、`match`、`ls`、`hash` 五大 L0 原子子命令（均支援 `--json` 結構化輸出）。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 經調研既有 `ys_codebase/source/file-space/file_space/{schema.py,manager.py,scanner.py}`，復用並重構其 `_compile_glob_pattern` 預編譯思想、`os.scandir` `DirEntry.stat()` 零冗餘走訪與 `compute_file_hash`（Blake2b 全量/稀疏取樣雜湊）演算法，遷移至 `ys_codebase/source/core/core/space/`，並結合 `core.uri` 與 `core.contributes` 原生解析能力。
- **邊界排除 (Explicitly Excluded)**：
  - `compose` 複合空間展開、YFP2 持久化快照帳本、跨世代 `diff` 與多消費者游標 (`CursorStore`) 歸屬 `sub_02_composite_capabilities`，不在 `sub_01` 實作。
  - `module:server` 常駐監控 (`FileSpaceWatcherServiceWorker`) 與事件廣播歸屬 `sub_03_server_hook_integration`，不在 `sub_01` 實作。
  - 既有下游模組 (`ast`、`knowledge-db`、`gdrive-support`、`agents-workflow`) SDK 遷移與舊 `ys_codebase/source/file-space/` 實體移除歸屬 `sub_04_ecosystem_migration_and_legacy_removal`，`sub_01` 不改動既有模組亦不刪除舊 `file-space` 模組。
  - 單點式防誤改物理鎖（File Guard）獨立歸屬未來 `core.vfs` 專項計畫，不在本子計畫實作。
- **架構影響範圍**：
  - `ys_codebase/source/core/core/space/`（新建核心空間原子引擎子套件）
  - `ys_codebase/source/core/contributes/_format.json`、`ys_codebase/source/core/contributes/core.json`（擴充 `presets`、`spaces` 貢獻點與 `file-space` / `fs` L0 CLI 宣告）
  - `ys_codebase/source/core/core/commands/`（掛載 `file-space` / `fs` L0 CLI 處理器）
  - `ys_codebase/source/core/tests/`（新增 `sub_01` 完整單元與邊界測試）

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 拓撲與過濾三核心欄位及三座標相容匹配**：
  - 廢棄舊版語意錯位之 `include`（舊版代表入口）與 `file_patterns`，確立正交三欄位：`entries`（多入口：支援資料夾或單一檔案、支援語意 URI；不存在之入口於走訪時安全略過並可於診斷標示）、`include`（包含樣式，未填預設為 `["*"]`）、`exclude`（排除樣式，優先級永遠高於 `include`，支援於 `scandir` 階段直接對匹配之目錄子樹剪枝）。
  - 規則匹配支援三座標無縫相容：① 若帶語意 URI 前綴（如 `yscb://...`、`project://...`），先解析為目標絕對路徑/前綴比對；② 若含 `/`（如 `plans/archived/**` 或 `core/**/*.py`），同時比對相對於 `project://` 之 `project_rel` 與相對於所屬 `entry` 之 `entry_rel`（任一命中即成立）；③ 若不含 `/`（如 `*.py`、`__pycache__`），直接匹配任意層級之檔案或目錄名稱（basename / segment）。
- **[P00:DR-02] 顯式預設集 (`presets`) 與內建 `@gitignore`**：
  - 支援定義具名預設集 `presets: { "<name>": { "description": "...", "include": [...], "exclude": [...] } }`，Space 透過 `"presets": [...]` 顯式引用並將規則聯集展開至自身 `include` / `exclude`。
  - 不設隱式 `default_presets`（拒絕黑盒過濾）；提供內建特殊動態預設集 `"@gitignore"`（解析 `project://.gitignore` 有效忽略規則轉換為排除條件，僅在 Space 顯式將 `"@gitignore"` 列入 `presets` 時生效）。
- **[P00:DR-03] `<owner>/<name>` 命名空間隔離與短名 `<name>` 自動聯集尋址**：
  - 禁止複雜且具載入順序風險的跨模組覆寫語法；所有模組於 `contributes/core.json` 宣告之空間/預設集自動命名為 `<module>/<name>`，專案於 `config/core/contribute.json` 宣告者自動命名為 `project/<name>`。
  - 當透過 SDK 或 CLI 以完整限定名 `<owner>/<name>`（如 `agents-workflow/docs` 或 `project/docs`）存取時，僅精準定位該單一來源定義；當以短名 `<name>`（如 `docs`）存取時，自動代表所有定義了 `<name>` 之來源的結果集聯集（Union）。
- **[P00:DR-04] L0 原子操作與 CLI 雙路由 (`yscb.py core file-space` / `yscb.py fs`)**：
  - 在 `sub_04` 正式退役舊 `module:file-space` 前，透過將命令註冊於 `core` 之 `file-space`（並配置命令別名 `fs`），使開發者與測試可透過 `python yscb.py core file-space <subcmd>` 或 `python yscb.py fs <subcmd>` 零衝突調用新引擎之五大 L0 原子子命令：`spaces`（列舉空間定義）、`presets`（列舉預設集定義）、`match`（單點路徑規則判定與解釋）、`ls`（零冗餘剪枝走訪列舉）、`hash`（單檔或空間級內容指紋與 Merkle Root 計算）。

---

## 3. 開放議題與確認紀錄

- [x] **空間定義三要素 (`entries` / `include` / `exclude`) 與三座標基準**：已確認相容語意 URI、`project://` 相對路徑、`entry` 相對路徑與單純檔名/目錄名。
- [x] **預設集 (`presets`) 策略**：已確認採用顯式引用、支援 `@gitignore`，不設全域隱式 `default_presets`。
- [x] **跨模組與專案定義衝突處理**：已確認採用 `<module>/<space>`、`project/<space>` 精準定位與 `<space>` 短名自動聯集機制。
- [x] **L0 CLI 掛載與舊模組過渡策略**：已確認掛載為 `file-space`（別名 `fs`），支援 `yscb.py core file-space` 全名呼叫，舊模組待 `sub_03` 後完成全倉 SDK 遷移（`sub_04`）再移除。
