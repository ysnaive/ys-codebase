# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_04_knowledge_db_pipeline_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Completed  
> 模型：Gemini 3.8 Flash (Medium)  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：核心結構純化與死代碼移除 — 刪除 `knowledge_db/protocol.py` 與 `schema.py:CallGraphNode`；徹底清理 `contributes/` 與 Python 檔案中殘留的 `thesaurus / aliases / related` 欄位與定義 (`K-05`, `FR-05`)
- [x] **TASK-02**：檢索管線死鎖解除與調用圖譜熱修補保真 — `pipeline.search()` 前置載入條件分離與多副檔名正規化；`graph.py:CallGraphIndex` 新增外部入度邊提取；`hot_patch_unified_index` 實作第一階 Identity Remap 與第二階 Linker 雙階重連；`find_target_symbol` 補齊 `ftypes` 與快取重用 (`K-01`, `K-02`, `K-04`, `FR-01`, `FR-02`, `FR-04`)
- [x] **TASK-03**：常駐背景服務單一託管與路徑純化 — `hook.server.py` 移除私自啟動之第二個 Watcher；`service.py` 移除 `source/server` 注入；`engine.py` 移除無效 events 呼叫；`config.py` 修復以 `core.config` 為最高優先級 (`K-03`, `K-07`, `FR-03`, `FR-07`)
- [x] **TASK-04**：CLI 契約對齊、SDK 別名補齊與文檔更新 — `contributes/core.json` 補齊選項與 `hooks`；`cli.py` 修復 `-d` 代碼切片與 JSON 欄位輸出；`engine.py` 補齊 `callers/callees/impact` SDK 別名；更新 `README.md`、`DESIGN_NOTES.md` 與 `_manifest.md` (`K-06`, `K-08`, `FR-06`, `FR-07`)
- [x] **TASK-05**：測試套件 14 檔 $\to$ 12 檔收斂、去重純化與補盲 — 物理裁撤 2 個歷史碎片檔；合併雙胞胎重複測試；重寫 5 處虛假與條件放行測試；補齊冷啟動向量載入與熱修補入度邊保真回歸測試 (`KT-01` ~ `KT-05`, `FR-08`, `FR-09`)
- [x] **TASK-DOC**：三層文檔與手冊同步 — 更新 `docs/knowledge-db/README.md`、`docs/knowledge-db/DESIGN_NOTES.md`、`ys_codebase/source/knowledge-db/README.md` 與 `CHANGELOG.md`

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | 依 P04 規劃之拓撲順序進行實作 |
