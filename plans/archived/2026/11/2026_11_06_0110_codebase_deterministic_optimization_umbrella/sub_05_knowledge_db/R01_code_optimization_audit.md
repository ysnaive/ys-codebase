# 技術調研與程式碼優化診斷報告 (Research & Code Optimization Audit)

> 調研主題：sub_05_knowledge_db 確定性代碼優化、實作邏輯/併發問題修復與測試套件純化 雙盲審計報告 (OPT-01 ~ OPT-12 & AUD-01 ~ AUD-24)  
> 建立日期：2026-11-06  
> 所屬主計畫：2026_11_06_0110_codebase_deterministic_optimization_umbrella  
> 狀態：Concluded  
> 模型：Gemini 3.1 Pro  
> 模板版本：v1.1  

---

## 1. 背景與調研目標 (Background & Objectives)

- **檢視範圍**：`ys_codebase/source/knowledge-db/` 模組之 21 個業務程式碼檔案與 10 個測試程式碼檔案。
- **審計與驗證基準**：業務程式碼依據 `/code-optimizer` (`D1~D5` & `S1~S6`) 及實作邏輯/併發/邊界防禦基準；測試程式碼依據 `testing-sop` (`T-01~T-06`)。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

- 完成 `knowledge-db` 模組 14 個業務與腳本檔案（`OPT-01 ~ OPT-12`）之確定性重構與併發/邏輯修復：將 `EmbeddingService._init_lock` 升級為 `threading.RLock()` 消除 `download_model()` 重入死鎖、於本地模型缺失時同步重置 `_init_attempted = False`、修正 `InvertedIndex.add_symbol` 同 `doc_id` 重複寫入時之 postings 累積、為 `SnippetExtractor._file_lines_cache`、`KnowledgeDBEngine.get_engine()`、`ServiceWorker.start()` 與 `Pipeline.clean()` 補齊執行緒鎖、以及移除 3 支 `hook.*.py` 頂層 `logger = ...` 執行語句。
- 完成 10 個測試檔案（`AUD-01 ~ AUD-24`）之全面純化：移除全部 15 處 `time.sleep`（改用 `write_text_and_advance_mtime` 確定性推進時間戳），清零工單編號標籤，補齊 `1.2.1.x.py` 遷移腳本與動態探針超時熔斷測試，達成 112/112 測試 100% 通過（`0 ResourceWarning`）。

---

## 3. 結論 (Conclusion)

- 經盲測子代理 D 驗收與盲測子代理 E 零錨定二次審計，確認業務碼與測試碼皆達成 `P0 = 0, P1 = 0, P2 = 0`（觸發融斷 `CIRCUIT BREAKER TRIGGERED`），全數 `112 / 112` 測試通過（耗時 `2.27s`，`0 ResourceWarning`），`Checker().check_module("knowledge-db")` 為 `0 FAIL, 0 WARN`。
