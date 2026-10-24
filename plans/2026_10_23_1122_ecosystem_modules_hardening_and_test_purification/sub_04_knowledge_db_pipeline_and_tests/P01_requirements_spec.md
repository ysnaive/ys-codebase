# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_04_knowledge_db_pipeline_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash (Medium)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 冷啟動向量索引載入死鎖解除 | 分離 `pipeline.py:search()` 載入前需求判定（`want_vectors = enable_vector_search and not degraded and not lexical_only`）與載入後可用性判定（`can_use_vector`），確保全新進程冷啟動查詢能正確載入磁碟上的向量索引並走 Hybrid RRF 融合。 | P0 | K-01 |
| **FR-02** | 調用圖譜熱修補跨檔入度邊雙階保真 | 於 `CallGraphIndex` 實作外部入度調用邊提取方法；於 `hot_patch_unified_index` 實作「第一階同檔案身分對映 (`Identity Remap`) ＋ 第二階 `TopologyLinker` 消歧」雙階重連，保證單檔修改後外部未修改檔案指向該檔的 `Callers` 入度邊 100% 不掉邊。 | P0 | K-02, [P00:DR-01] |
| **FR-03** | 常駐背景服務單一託管與路徑純化 | 純化 `scripts/hook.server.py`，移除私自啟動之 `_watcher_instance`，僅保留 `pre_warm()`，背景監聽與熱自癒 100% 由 `server.ServiceManager` 透過 `contributes/server.json` 單一託管；移除 `service.py` 的 `source/server` 路徑注入與 `engine.py` 之無效事件呼叫。 | P0 | K-03, [P00:DR-02] |
| **FR-04** | 複合檢索多副檔名正規化與拓撲快取重用 | 於 `pipeline.search()` 呼叫 `_normalize_ftypes()` 拆解 `--ftype` 逗號；於 `hybrid.py` 支援多副檔名過濾；`act_callers/callees/impact` 傳遞 `ftypes` 給 `find_target_symbol()`；`find_target_symbol()` 改用 `_ensure_jit_index_ready(require_vectors=False)` 記憶體快取。 | P1 | K-04 |
| **FR-05** | 徹底純化移除遺留同義詞庫與死代碼 | 自 `contributes/`、`schema.py`、`space.py`、`bundler.py`、`retrieval.py`、`linker.py`、`engine.py`、`cli.py` 與 `SKILL.md` 移除 `thesaurus / aliases / related` 欄位；物理刪除 0 引用之 `knowledge_db/protocol.py` 與 `schema.py:CallGraphNode`。 | P1 | K-05 |
| **FR-06** | CLI 選項契約對齊與 `-d` 切片修復 | 於 `contributes/core.json` 補齊 `limit`、`kind`、`lang`、`space`、`all`、`json` 選項與 `hooks` 宣告；修復 `scripts/cli.py` 使 `-d` 模式必然擷取代碼切片，且 `search -d --json` 補齊 `id`、`matched_terms` 與 `spaces`。 | P1 | K-06 |
| **FR-07** | 組態優先級修復、常駐熱刷新與 SDK 別名對齊 | 修正 `KnowledgeDBConfig.load()` 以 `core.config` 優先；於 `get_engine()` 同步熱刷新組態；向量降級提示改為 CLI 指令；於 `KnowledgeEngine` 補齊 `callers/callees/impact` SDK 別名並同步 `README.md` 與 `_manifest.md`。 | P1 | K-07, K-08 |
| **FR-08** | 測試套件純化收斂 14 檔 $\to$ 12 檔與去重 | 裁撤 `test_benchmark_perf_and_memory.py` 與 `test_cli_ux.py` 並併入子系統測試檔；合併 `test_graph.py`、`test_hot_reload.py`、`test_engine.py` 重複測試；清除同義詞與墓碑測試。 | P1 | KT-02, KT-03 |
| **FR-09** | 虛假測試修復、單例隔離與高風險路徑補盲 | 重寫 `test_space.py` Provider 測試、`test_cli.py` 實境沙盒檢索斷言（廢除條件式放行）、`test_retrieval.py` 異常捕獲；`tearDown` 隔離全域快取；補齊冷啟動向量載入、熱修補入度邊保真、多副檔名與 Schema 合規測試。 | P0 | KT-01, KT-04, KT-05 |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 磁碟無向量索引或模型載入失敗 | 當 `want_vectors=True` 但磁碟無向量檔或 FastEmbed 載入異常時，`can_use_vector` 判定為 `False`，平滑安全降級為純 BM25 檢索，不中斷查詢流程。 |
| **EC-02** | 外部未修改檔案以無前綴裸函式調用目標檔案 | `from a import bar; bar()` 無前綴裸調用在目標檔案修改時，第一階 `Identity Remap` 藉由同檔案 `(norm_file_path, name)` 身分直接重連，不受缺少外部 `file_imports` 影響。 |
| **EC-03** | 目標符號在熱修補中被徹底刪除或改名 | 第一階身分映射失敗，第二階 `TopologyLinker` 跨檔消歧失敗後自然斷開入度邊，不留幽靈邊（Ghost Edges）。 |
| **EC-04** | 傳入 `--ftype=c,cpp,py` 逗號與空格複合字串 | 詞彙與向量檢索皆正確正規化為 `["c", "cpp", "py"]`，精確過濾相符附檔名之結果，不發生全域誤殺。 |
| **EC-05** | 在受限或未安裝 `server` 模組的環境下調用 | `service.py` 能安全退回內建 `BaseServiceWorker` 抽象基類，`hook.server.py` 容錯略過，不引發致命 `ImportError`。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能 / 資源 | 增量熱修補耗時維持在 500ms 內，入度邊提取與重連複雜度為 O(Dirty + ExternalIncomingEdges)；`find_target_symbol` 重用常駐快取，消除重複解壓反序列化磁碟檔案開銷。 |
| **NFR-02** | 合規 / 純淨 | 全模組 `python yscb.py dev check knowledge-db` 通過（0 Fail, 0 Warn）；12 個測試檔單元測試與全量生態系回歸測試 100% 通過；測試執行後環境零殘留、無檔案與單例狀態污染。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** 外部未修改檔案以無前綴裸調用呼叫函式時，單檔熱修補並未重解析外部檔案之 AST，若直接調用 `TopologyLinker.resolve_call_site` 會因缺少 `file_imports` 遭守門攔截丟邊，故必須以 `Identity Remap` 為第一階優先對齊。
- **`[!CAUTION]`** 嚴禁在 `knowledge_db/service.py` 中向 `sys.path` 插入 `source/server` 路徑；跨模組存取必須嚴格透過 `.modules/` 運行時空間。

