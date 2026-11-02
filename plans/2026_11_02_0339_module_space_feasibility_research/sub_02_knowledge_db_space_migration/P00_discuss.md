# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：`knowledge-db` 空間與指紋底座遷移重構（`/code-optimizer` `Mode A` 單一正統入口收斂）  
> 建立日期：2026-11-02  
> 所屬主計畫：2026_11_02_0339_module_space_feasibility_research / sub_02_knowledge_db_space_migration  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Full Track  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：針對主計畫 `R03` 契約三（`knowledge-db` 遷移至 `module:space`），採用 `/code-optimizer` **`Mode A（收斂期 / 允許破壞性清理）`** 與 **`[軌道 3B / 2B：主代理 + 盲眼子代理協同]`** 進行五維度靜態診斷與單一正統入口無損重構。
- **核心目標**：
  1. **前置三維度定錨 (`/code-optimizer` Step 1)**：
     - **檢視範圍**：`單一模組 (Module Scope: ys_codebase/source/knowledge-db/)`（並涵蓋宿主組態 `ys_codebase/config/space/contribute.json` 與 `ys_codebase/config/knowledge-db/contribute.json` 對齊）。
     - **生命週期與相容性模式**：`Mode A：收斂期 / 允許破壞性清理 (Convergence Mode)`——因引入全新模組依賴 `"space": ">=1.0.0"` 屬 minor 以上版本迭代，強制收斂為 `from space import ...` 單一正統入口，物理刪除 `knowledge_db/space.py`、`knowledge_db/scanner.py`、`knowledge_db/service.py` 與 `contributes/server.json`，零容忍保留薄轉發殼層或相容別名。
     - **代理執行與審查軌道**：`[軌道 3B / 2B：主代理 + 盲眼子代理協同]`——委派盲眼子代理執行 `D1~D5` 靜態診斷與調用點盤點，落檔 `R01_code_optimization_audit.md`。
  2. **事件驅動增量同步與游標對齊**：
     - 新增 `ys_codebase/source/knowledge-db/scripts/hook.space.py`（訂閱 `on_space_changed` 事件），於收到 `code_space` / `docs_space` 變更時觸發 `engine.sync_incremental(consumer_id="knowledge-db")`。
     - 將 `KnowledgeDBEngine` 內部之檔案掃描與差異比對改為調用 `module:space` 之 `consume_diff(space_name, consumer_id="knowledge-db")`（或 `diff()` + SQLite commit 後 `ack()`），確保 SQLite 索引與 `space` 游標滿足最終一致性。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 全面復用 `sub_01` 建置之 `module:space`（`SpaceManager`、`FingerprintScanner`、`BinarySnapshotManager`、`SpaceWatcherServiceWorker`）。
- **邊界排除 (Explicitly Excluded)**：
  - `agents-workflow` 不納入本子計畫（已依開發者指示列為 `sub_03` 後續再討論）。
  - SQLite FTS5 / AST Graph Schema 與查詢 CLI（`search`、`callers`、`callees`、`impact`、`index`、`status`、`clean`）之對外契約保持 100% 行為等價。
- **架構影響範圍**：`ys_codebase/source/knowledge-db/`（生产碼与 `tests/`）、`ys_codebase/config/space/contribute.json`、`ys_codebase/config/knowledge-db/contribute.json`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 採納 `/code-optimizer` `Mode A` 單一正統入口收斂**：
  - 物理移除 `ys_codebase/source/knowledge-db/knowledge_db/{space.py,scanner.py,service.py}` 與 `ys_codebase/source/knowledge-db/contributes/server.json`。
  - 於 `knowledge_db/__init__.py` 與內部模組移除所有舊有空間/掃描匯出別名，統一改由 `from space import ...` 匯入，並同步更新 `ys_codebase/source/knowledge-db/tests/` 下所有測試案例。
- **[P00:DR-02] 盲眼子代理 (`軌道 2B/3B`) 產出 `R01_code_optimization_audit.md`**：
  - 由盲眼子代理對 `ys_codebase/source/knowledge-db/` 全模組執行 `D1~D5` 診斷與 `Mode A` 調用點盤點，產出 `R01_code_optimization_audit.md` 作為重構處方箋。

---

## 3. 開放議題與確認紀錄

- 待盲眼子代理完成 `R01_code_optimization_audit.md` 後，呈遞診斷卡由開發者確認推進實作。

