# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：post_abstraction_audit_and_update_deps  
> 建立日期：2026-11-02  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 解決第一波抽象化重構（`file-space` & `ast` 解耦）後檢出之 4 項同步缺口與邊界隱患反饋單（`ISS-01` ~ `ISS-04`）。
  2. 另外當下游使用 `update` 指令更新的時候，沒有根據更新後的組態（`manifest.json` / `index.json`）驗證相依性，導致已安裝模組若在新版有新增或升級相依性（例如 `knowledge-db` 1.1 $\to$ 1.2 新增 `file-space` 與 `ast` 相依）會因未解析安裝或版本不符而無法運作。
- **核心目標**：
  1. **`core` `cmd_update` 聯合拓撲相依解析與自動拉取 (`Update Dependency Resolution`)**：升級 `Installer.cmd_update`，先置優先處理 `core` 候選版號評估（使同批次下游模組能匹配新 `core` 相依要求），再將待更新模組目標版本交由 `AtomicEngine.act_solve_deps` 執行聯合拓撲相依解析，自動驗證並拉取/註冊新版引入之缺失相依模組（如 `file-space`、`ast`）或需連帶升級之相依模組，並對全部實際變更模組執行遷移階梯 (`act_migrate`) 與 Onboarding 提示。
  2. **`ISS-01` & `ISS-04` 零第三方依賴保證與空間表格 Provider 收斂**：在 `file_space/providers.py` 統一提供已註冊空間 Markdown 表格渲染（包含 `get_registered_file_spaces_table` 與 `get_knowledge_db_spaces`），使 `knowledge_db/providers.py` 僅以純標準庫路徑掛載委派至 `file_space.providers`（零頂層 `import knowledge_db` / `networkx`）；同步將 `knowledge_db/__init__.py` 與 `ast_engine/__init__.py` 升級為 PEP 562 `__getattr__` 延遲匯入，根治初次 `restore` / `install` 在 `sync_pip_dependencies()` 前執行 `act_reload` 時 `KNOWLEDGE_DB_SPACE` 崩潰洗空問題。
  3. **`ISS-02` `knowledge-db` 版號對齊與 `dev check` 守門**：將 `knowledge_db/__init__.py` 之 `__version__` 與 `CHANGELOG.md` 對齊為 `1.2.0.0`（與 `manifest.json` 一致），並於 `dev/checker.py` 增設套件 `__init__.py` 之 `__version__` 與 `manifest.json["version"]` 一致性靜態檢核。
  4. **`ISS-03` 根目錄 `README.md` 與 `docs/README.md` 七大模組三階 DAG 同步**：將根目錄 `README.md` 與 `docs/README.md` 全面更新為七大核心模組（納入 `file-space` $\to$ `ast` $\to$ `knowledge-db` 三階 DAG），修正 `README.md` §3.3 空間設定教學為 `config/file-space/contribute.json` 與 `config/knowledge-db/contribute.json` (`space_weights`)，並補齊 `yscb.py file-space` 與 `yscb.py ast` CLI 速查表。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `AtomicEngine.act_solve_deps` 多根批次拓撲解析引擎（已支援 `Sequence[Tuple[str, Optional[str]]]` 與跨依賴約束校驗）。
  - 復用 `file_space/providers.py` 既有 `FileSpaceManager` 空間載入邏輯，收斂 `knowledge_db/providers.py` 重複之表格生成實作。
  - 復用 `agents_workflow/plans/__init__.py` 既有之 PEP 562 `_LAZY_EXPORTS` + `__getattr__` 延遲載入範式於 `knowledge_db/__init__.py` 與 `ast_engine/__init__.py`。
- **邊界排除 (Explicitly Excluded)**：
  - 不變更 `yscb update` 預設之同主版號鎖定（`^Major.Minor.Patch` Major Lock）語意。
  - 不變更 `file-space`、`ast` 或 `knowledge-db` 的索引二進位格式（`YFP2` / `ASTSnapshot`）。
- **架構影響範圍**：
  - `ys_codebase/source/core/core/{installer.py,engine.py}` 及 `ys_codebase/source/core/tests/`
  - `ys_codebase/source/file-space/file_space/providers.py` 及 `ys_codebase/source/file-space/tests/`
  - `ys_codebase/source/ast/ast_engine/__init__.py` 及 `ys_codebase/source/ast/tests/`
  - `ys_codebase/source/knowledge-db/knowledge_db/{__init__.py,providers.py}` 及 `ys_codebase/source/knowledge-db/tests/`
  - `ys_codebase/source/dev/dev/checker.py` 及 `ys_codebase/source/dev/tests/`
  - `README.md`、`docs/README.md`、`CHANGELOG.md`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `cmd_update` 聯合拓撲相依解析與自動拉取策略**：
  - 當執行 `yscb.py update [modules...]` 時，先將待檢核清單中的 `core` 排至首位評估最新相容版號（若 `core` 也在更新集合內，預先將候選 `core` 版號提供給相容性探針，避免其他模組的新版因要求新 `core` 而被 `_discover_available_versions_for_module` 誤過濾）。
  - 針對所有已安裝模組（無論版號是否上升，皆須確保其當前或新版相依完整性）或待更新目標模組，將 `(mod, target_ver)` 送入 `self.engine.act_solve_deps(update_requests, None, provider_url)` 執行聯合拓撲解析。
  - 若 `act_solve_deps` 解析出尚未安裝的新相依模組（如 `knowledge-db@1.2.0.0` 新增之 `file-space`、`ast`）或需連帶升級的已安裝相依模組，於同一原子交易內自動執行 `act_prepare`、`act_register`、`act_reload`、`act_migrate` 與 `sync_pip_dependencies()`；若相依約束衝突或無法滿足則拋出明確錯誤並由 `act_restore_snapshot` 全量回滾。
- **[P00:DR-02] `ISS-01` & `ISS-04` 空間表渲染收斂與 PEP 562 延遲匯入**：
  - 將 `get_knowledge_db_spaces` 實作收斂至 `file_space/providers.py`（與 `get_registered_file_spaces_table` 同源共管），`knowledge_db/providers.py` 移除頂層 `import knowledge_db`，改以純標準庫掛載 `file_space` 後轉發呼叫 `file_space.providers.get_knowledge_db_spaces`，100% 杜絕載入 `networkx` / `fastembed`。
  - 於 `knowledge_db/__init__.py` 與 `ast_engine/__init__.py` 導入 PEP 562 `__getattr__` 延遲匯入，確保匯入頂層套件或輕量屬性（如 `__version__`、例外與 Schema）時零第三方 C-extension / `networkx` / `fastembed` 載入開銷。
- **[P00:DR-03] `ISS-02` 版號單一真理對齊與 `dev check` 靜態防呆**：
  - 對齊 `knowledge_db/__init__.py` 之 `__version__ = "1.2.0.0"` 與 `CHANGELOG.md` 紀錄；於 `dev/checker.py` 新增靜態 AST 檢查，當模組頂層套件 `__init__.py` 定義字串常數 `__version__` 時，強制校驗其與 `manifest.json["version"]` 完全一致。
- **[P00:DR-04] `ISS-03` 根目錄 `README.md` 與 `docs/README.md` 七大模組三階 DAG 對齊**：
  - 同步更新根目錄 `README.md` 與 `docs/README.md` 為七大核心模組（`core`, `dev`, `server`, `file-space`, `ast`, `knowledge-db`, `agents-workflow`），修正空間註冊教學與 CLI 速查表。
- **[P00:DR-05] 標準重載與自癒管線相依交集自檢機制 (`Dependency Reconciliation & Conflict Guard`)**：
  - 於 `AtomicEngine` 實作 `reconcile_installed_dependencies(provider_url: str = "")` 標準自檢與自癒原語，並嵌入 `cmd_update`、`cmd_restore` 與 `act_reload` Stage 1.5（於 Stage 2 物化及 Stage 4 `on_reload` 廣播前執行）：
    1. **本地未安裝相依模組 ($D \notin \text{installed\_modules}$)**：自動彙整所有上游模組對 $D$ 的相依約束交集，若存在相容版本則全自動下載、註冊並物化補裝；若多個上游模組對 $D$ 的約束不存在版號交集，立即拋出結構化衝突錯誤並阻斷。
    2. **本地已安裝相依模組 ($D \in \text{installed\_modules}$)**：若已安裝版號已滿足所有上游約束交集則維持不變；若已安裝版號不滿足上游新增約束，則將所有上游對 $D$ 的約束（及 $D$ 自身鎖定約束）求交集，若在可用版本池中存在滿足交集之版號則全自動升級自癒，若兩模組對 $D$ 之約束不存在版號交集則剛性阻斷升級並回滾。

---

## 3. 開放議題與確認紀錄

- **Q1：當 `update` 發現新版引入新相依模組或提高相依版本要求時，應自動透過 `act_solve_deps` 拉取安裝或僅報錯攔截？**
  - **決策**：採選項 A（自動透過 `act_solve_deps` 聯合解析並拉取/升級新版所宣告的所有新增與更新相依模組，含 `core` 先行判定或聯合升級）。
- **Q2：本次 5 個項目（`ISS-01` ~ `ISS-04` + `update` 相依解析）如何組織開發計畫？**
  - **決策**：採選項 A（全部收斂至同一份 Full Track 計畫一併推進修復與測試驗收）。
- **Q3：是否應在標準 Hook 自檢 & 自癒流程中加入相依性判定與交集自癒機制？**
  - **決策**：是，納入 `[P00:DR-05]`。未安裝相依模組直接補裝，已安裝模組求約束交集判定：無交集（衝突）時剛性阻斷升級，有交集時全數自動自癒。

