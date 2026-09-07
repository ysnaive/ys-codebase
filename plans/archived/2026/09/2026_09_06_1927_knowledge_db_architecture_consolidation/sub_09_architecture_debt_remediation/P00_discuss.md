# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_09_architecture_debt_remediation  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：全數規劃修復，開啟 sub 09
- **核心目標**：基於主計畫架構深度審查報告（`architecture_review.md`），全面規劃並消除 sub_01~sub_08 重構期間累積之 14 項架構技術債、過度設計、競態窗口與隱性缺陷（2 項 High、5 項 Medium、5 項 Low、2 項 Design Omission），全面恢復與提升代碼純度與模組邊界清晰度。
- **邊界排除 (Explicitly Excluded)**：
  - 嚴禁打破重構凍結管制（嚴禁在修復期間執行本地 `@build` 自部署）。
  - 不引入全新領域模組，不修改已定案之對外 Public CLI 介面協議。
  - 不進行無關之代碼大翻修，僅精準針對 14 項識別問題進行架構債收斂與標準化。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 14 項架構債問題全數納入修復範疇與分級治理**：
  - **Tier 1 (High - 核心穩定性/行為矛盾)**：
    - **H-01**：`core.engine.AtomicEngine.act_lock/act_unlock` 廢棄自製 JSON 檔案鎖，全面遷移至 `core.platform.InterProcessLock`，消除雙軌並存與競態窗口。
    - **H-02**：`knowledge_db.service.KnowledgeDBServiceWorker.is_path_watched` 徹底移除 L159~163 寬鬆之 `workspace_root` 兜底邏輯，對齊 sub_08 規格與 CHANGELOG 宣告。
  - **Tier 2 (Medium - 資源洩漏/原子性/代碼重複/單例共享)**：
    - **M-01**：消除 `_ensure_venv` 於 `yscb.py`、`server/master.py`、`server/worker.py` 三處重複，下沉至 `core.platform` 提供標準實作並統一支援 `host_venv.pth` 解析。
    - **M-02**：`server.master._write_state()` 廢除裸 `open("w")`，改採 `core.vfs.write_json(..., atomic=True)` 確保守護進程狀態原子寫入。
    - **M-03**：`yscb.py.dispatch_module` 冷啟動路徑引入進程級模組快取（`_MODULE_CACHE`），避免重複 `spec.loader.exec_module`。
    - **M-04**：`yscb.py._is_modules_dirty` 修復推導式中裸 `open()` 未關閉之 FD 洩漏問題。
    - **M-05**：`knowledge_db.service.KnowledgeDBServiceWorker._get_pipeline()` 與 CLI `get_engine()` 統一共享 `knowledge_db.engine.get_engine()` 單例，消除 Worker 進程內雙重 Engine 實例。
  - **Tier 3 (Low & Design Omission - 代碼品質/常態防護/契約健全)**：
    - **L-01**：`core.guard.py` Docstring 補齊 Guard Token 語意邊界文件（防直接終端繞道之標識，非密碼學抗篡改密鑰）。
    - **L-02**：`knowledge_db.pipeline._GLOBAL_INDEX_CACHE` 引入 `threading.RLock` 保護，防範 CLI 主線程與 Watcher 背景線程並發讀寫競態。
    - **L-03**：`yscb.py._try_hot_dispatch` 支援透過環境變數 `YSCB_DISPATCH_TIMEOUT` 覆蓋 120s 逾時設定。
    - **L-04**：`knowledge_db.engine` 移除未使用的 7 個 Formatter 內部常數導入，維持純淨 Facade 介面。
    - **L-05**：`yscb.py.main()` 拆解四層三元運算符嵌套，改寫為標準 if-elif-else 結構。
    - **D-01**：`server.service.BaseServiceWorker.start()` 補齊 `context` 參數契約文件（`yscb_root`, `workspace_root`, `config` 等）。
    - **D-02**：`core.vfs.VFS.copy()/move()` 針對跨 Backend 操作補齊明確校驗與錯誤拋出（`NotImplementedError`）。

- **[P00:DR-02] 實作順序與驗證策略**：
  - 採分 Phase 階梯式修復：
    1. Phase 1: Tier 1 (H-01, H-02) 關鍵路徑修復與單元驗證。
    2. Phase 2: Tier 2 (M-01 ~ M-05) 基礎設施與進程單例整合。
    3. Phase 3: Tier 3 (L-01 ~ L-05, D-01 ~ D-02) 代碼品質、並發保護與契約文檔。
  - 每階段均執行針對性測試，全部完成後執行全生態系回歸測試（`core`, `dev`, `server`, `knowledge-db`, `agents-workflow`）。

---

## 3. 開放議題與確認紀錄

- [x] 是否全數修復 14 項審查問題：確認全數納入。
- [x] 是否遵守重構凍結管制：確認不執行 `@build` 本地自部署。
- [ ] 待開發者確認 P00/實作規劃後推進至 Phase 1。
