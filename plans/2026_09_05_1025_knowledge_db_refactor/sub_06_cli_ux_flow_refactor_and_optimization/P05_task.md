# 實作任務清單 (Task Breakdown)

> 功能名稱：knowledge_db_cli_ux_flow_refactor_and_optimization  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `source/knowledge-db/knowledge_db/config.py`，支援 Local / Project 級 4 大組態讀取與執行緒解析
- [x] **TASK-02**：重構 `source/knowledge-db/knowledge_db/embedding.py`，整合 `max_threads`、HF Hub 警告屏蔽、`VectorIndex` 檔頭元資料與維度防呆
- [x] **TASK-03**：重構 `source/knowledge-db/knowledge_db/pipeline.py`，實作 JIT 10 符號動態探針、熔斷降級、雙軌進度呈現
- [x] **TASK-04**：更新 `source/knowledge-db/knowledge_db/engine.py`，整合 Config 注入流水線
- [x] **TASK-05**：重構 `source/knowledge-db/scripts/cli.py`，導入 `TerminalStyler` 色彩階層、修復 `status` 判定與 `--help`、保障 `--json` 純淨
- [x] **TASK-06**：編寫 `source/knowledge-db/tests/test_cli_ux.py` 單元測試套件，覆蓋 FT-01~09 與全生態系回歸驗證
- [x] **TASK-DOC**：更新 `source/knowledge-db/README.md` 與 `docs/knowledge-db/DESIGN_NOTES.md` (`[DN-KDB-09]`)

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **DEV-01** | `Minor` | **跨模組相容性修復 (`yscb.py` / `dev/sandbox.py`)**：在 Linux/virtiofs 容器環境下，`os.symlink` 產生斷鏈（dangling symlink）致沙盒啟動崩潰；於 `sandbox.py` 增設斷鏈檢核並清理以退回 `.pth` 機制，並於 `yscb.py` 增設 `host_venv.pth` 解析。 | **方案 B（核准保留）**：經開發者指示保留修復並補登偏差記錄；後續建議獨立追蹤基礎設施跨平台規範。 |
| **DEV-02** | `Info` | **IDE 開發環境配置調整 (`.vscode/settings.json`)**：Python 直譯器與 site-packages 路徑調整為本機容器環境。 | **方案 B（核准保留）**：依開發者指示保留，不影響 production 與發布套件。 |
| **DEV-03** | `Opt` | **測試環境自動化向量 Mock 降級機制 (`engine.py` / `hook.dev.py`)**：因歷史測試反覆實例化 ONNX 致時長膨脹至 210s；依開發者裁定採「解法 A」，於測試環境自動切換為確定性 Mock 向量，全套件測試時長由 210s 劇降回 8.99s (<10s)。 | **解法 A（核准實施）**：已實裝並驗證，全套件 133 個測試 100% 通過且僅需 9.00s。 |



