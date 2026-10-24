# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_04_knowledge_db_pipeline_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash (Medium)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-09 在 API 規格書與架構設計書中有 100% 對應實作介面。
- [x] **邊界防護**：EC-01 ~ EC-05 具體落實向量降級、雙階身分對映、死符號斷邊、多副檔名拆解與基類安全退回。
- [x] **依賴純淨**：符合 NFR-01 (熱修補 <500ms、快取重用) 與 NFR-02 (合規 pass、12 測試檔全綠零殘留) 指標約束。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/knowledge-db/README.md` | Modify | 同步更新 SDK 呼叫範例、移除同義詞說明、校正技能指針為 `yscb-cli-guide` |
| **模組手冊** | `ys_codebase/source/knowledge-db/README.md` | Modify | 同步源碼層手冊之 SDK 介面、CLI 選項與向量複合檢索機制 |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 增補記錄冷啟動向量載入前置分離、雙階入度邊增量保真與同義詞汰除邊界 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 維護 `pipeline.py`、`graph.py`、`hybrid.py`、`engine.py` 之 Docstring 與型別標註 |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄本版本發布摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：當單一檔案修改時，未修改外部檔案的裸調用（如 `from mod import func; func()`）沒有前綴且沒有重解析外部檔案的 import，如何保證入度邊不被 Linker 誤殺？  
> [*] **防護解法**：在熱修補拔除舊符號前，快照舊符號的 `(file_path, name, fqn)`，第一階直接依同檔案身分優先對齊新符號 SHA-1 ID，100% 繞過缺少外部 `file_imports` 的消歧限制。

> [?] **尖銳問題 2**：如果 Worker 啟動時 FastEmbed 模型損毀或缺少相依套件，分離載入條件後會不會導致程序崩潰？  
> [*] **防護解法**：`want_vectors=True` 僅表達「希望嘗試載入」，若 `_ensure_jit_index_ready` 嘗試載入向量失敗，內部會捕獲異常並記錄降級日誌；後續 `can_use_vector` 依然為 `False`，平滑退回純 BM25 檢索。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01**：核心結構純化與死代碼移除 — 刪除 `knowledge_db/protocol.py` 與 `schema.py:CallGraphNode`；徹底清理 `contributes/` 與 Python 檔案中殘留的 `thesaurus / aliases / related` 欄位與定義。
2. **TASK-02**：檢索管線死鎖解除與調用圖譜熱修補保真 — `pipeline.search()` 前置載入條件分離與多副檔名正規化；`graph.py:CallGraphIndex` 新增外部入度邊提取；`hot_patch_unified_index` 實作第一階 Identity Remap 與第二階 Linker 雙階重連；`find_target_symbol` 補齊 `ftypes` 與快取重用。
3. **TASK-03**：常駐背景服務單一託管與路徑純化 — `hook.server.py` 移除私自啟動之第二個 Watcher；`service.py` 移除 `source/server` 注入；`engine.py` 移除無效 events 呼叫；`config.py` 修復以 `core.config` 為最高優先級。
4. **TASK-04**：CLI 契約對齊、SDK 別名補齊與文檔更新 — `contributes/core.json` 補齊選項與 `hooks`；`cli.py` 修復 `-d` 代碼切片與 JSON 欄位輸出；`engine.py` 補齊 `callers/callees/impact` SDK 別名；更新 `README.md`、`DESIGN_NOTES.md` 與 `_manifest.md`。
5. **TASK-05**：測試套件 14 檔 $\to$ 12 檔收斂、去重純化與補盲 — 物理裁撤 2 個歷史碎片檔；合併雙胞胎重複測試；重寫 5 處虛假與條件放行測試；補齊冷啟動向量載入與熱修補入度邊保真回歸測試。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 確認採取雙階入度邊增量重連協定，第一階以同檔案身分重映守護無前綴裸調用，第二階以 `TopologyLinker` 跨檔消歧。
- **[P04:DR-02]** 確認裁撤 `test_benchmark_perf_and_memory.py` 與 `test_cli_ux.py` 兩個碎片檔，收斂為 12 個子系統 1:1 對齊測試檔。
- **[P04:DR-03]** 確認徹底移除已淘汰的同義詞庫與未使用的 `protocol.py` 死代碼。

