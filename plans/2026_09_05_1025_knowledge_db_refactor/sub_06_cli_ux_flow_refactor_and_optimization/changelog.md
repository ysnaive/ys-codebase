# 計畫變更紀錄 (Changelog)

> 功能名稱：knowledge_db_cli_ux_flow_refactor_and_optimization  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Completed  
> 模板版本：v1.1  

---

> 按時間倒序排列。每條記錄包含日期時間、類型標籤、摘要。

## 變更紀錄

| 日期時間 | 類型 | 摘要 |
| :--- | :---: | :--- |
| 2026-09-05 10:52 | `PHASE` | 完成 Phase 7 成果展示與結案報告 (產出 P07_walkthrough.md，同步全域 CHANGELOG.md，子計畫圓滿結案！) |
| 2026-09-05 10:50 | `PHASE` | 完成 Phase 6 人工/UX 驗收 (UX-01~04 全數經開發者確認標定為 [測試通過])，通過 Review Gate 審查，準備推進 Phase 7 |
| 2026-09-05 10:48 | `FIX` | 在 `dev/testing/sandbox.py` 補強懸空軟連結刪除防禦，徹底消除 `Failed to unlink projected venv: [Errno 2]` 警告並重打 `dev@build` |
| 2026-09-05 10:41 | `OPTIMIZE` | 實裝「解法 A」：`engine.py` 與 `hook.dev.py` 支援沙盒/測試環境自動切換確定性 Mock 向量，全套件測試時長由 210s 壓降回 8.99s (<10s) |
| 2026-09-05 10:22 | `DEVIATION` | 開發者裁定採「方案 B」：保留 `yscb.py`、`dev/sandbox.py` 之 Linux/virtiofs 斷鏈修復與 `.pth` 穿透邏輯，並於 P05 補登 DEV-01/02 偏差記錄 |
| 2026-09-05 10:05 | `PHASE` | 完成 Phase 5 代碼實作 (TASK-01~06, TASK-DOC)，執行 133/133 全套件測試 100% 通過，物化安裝 @build 產物，抵達 Phase 6 驗證 Checkpoint |
| 2026-09-05 09:29 | `PHASE` | 推進至 Phase 5 任務實作，產出 P05_task.md 並開始各項代碼撰寫 |
| 2026-09-05 09:29 | `PHASE` | 完成 Phase 4 定稿審查，產出 P04_implementation_plan.md 並定稿 P06_test_plan.md (Confirmed) |
| 2026-09-05 09:28 | `PHASE` | 完成 Phase 3 API 規格，產出 P03_api_spec.md (含 KnowledgeDBConfig, TerminalStyler, ProbeBreaker 介面簽名) |
| 2026-09-05 09:28 | `PHASE` | 完成 Phase 2 架構設計，產出 P02_architecture_plan.md 並初始化 P06_test_plan.md (Draft) |
| 2026-09-05 09:27 | `DECISION` | 定錨 [P00:DR-06] 與 FR-08：支援 Local Config `knowledge-db.max_threads`（預設 auto=cpu//2），解除硬編碼 2 執行緒瓶頸 |
| 2026-09-05 09:25 | `DECISION` | 昇華 [P00:DR-02]：導入 10 符號動態探針推估，並開放 Local Config 支援 `knowledge-db.jit_vector_timeout_seconds` 自訂熔斷臨界值 |
| 2026-09-05 09:23 | `PHASE` | 完成 Phase 1 規格轉譯，產出 P01_requirements_spec.md (含 FR-01~07, EC-01~06, NFR-01~03) |
| 2026-09-05 09:21 | `DECISION` | 定錨 [P00:DR-05]：支援 Project/Local 級模型名稱自訂配置 (embedding_model) 與向量維度/快取失效防呆機制 |
| 2026-09-05 09:16 | `DECISION` | 定錨 [P00:DR-01]~[DR-04]：定義 local config 向量開關、JIT 5秒臨界值熔斷、雙軌進度呈現與 HF Hub 雜訊屏蔽機制 |
| 2026-09-05 09:16 | `PHASE` | 開立計畫目錄，伴隨建立 P00 與本變更日誌 (狀態：`Discussing` $\rightarrow$ `Confirmed`) |
