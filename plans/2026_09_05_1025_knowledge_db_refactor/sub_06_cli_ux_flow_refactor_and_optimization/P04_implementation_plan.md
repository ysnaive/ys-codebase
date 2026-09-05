# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：knowledge_db_cli_ux_flow_refactor_and_optimization  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-08 在 `P03_api_spec.md` 中均有對應的介面與類別定義
- [x] **邊界防護**：EC-01 ~ EC-07（模型拼錯、維度衝突、JIT 熔斷、非 TTY 去色、JSON stdout 純淨度）均具體落實於各模組
- [x] **依賴純淨**：符合 NFR-01~03 指標約束，無引入任何未宣告之外部 pip 套件

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `source/knowledge-db/README.md` | Modify | 增補 4 大 Local/Project Config 設定項與使用範例 |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 新增 `[DN-KDB-09]`：記錄 JIT 10 符號動態探針、向量熔斷退回與 CPU 執行緒自適應防飢餓機制 |
| **發布日誌** | `plans/<plan>/changelog.md` | Modify | 完整追蹤 Phase 流轉與任務完成狀態 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若動態探針（前 10 個符號）在推論時因某些特殊字元拋出例外，是否會導致整次搜尋崩潰？  
> 💡 **防護解法**：探針執行區塊包覆 `try...except`。一旦探針推論發生任何未預期例外，立即安全降級回退至純 BM25 檢索，並記錄警告日誌，絕對不阻斷使用者的核心代碼搜尋。

> ❓ **尖銳問題 2**：若使用者設定 `NO_COLOR=1` 或輸出導向管道 (`| grep`)，ANSI 彩色跳脫序列是否會污染文字？  
> 💡 **防護解法**：`TerminalStyler` 嚴格遵循 `sys.stdout.isatty()` 與 `os.getenv("NO_COLOR")` 雙重守門，任何非 TTY 或禁用情境下自動回傳原生文字。

> ❓ **尖銳問題 3**：若向量索引快取格式為舊版無 JSON 檔頭時，是否會引發相容性崩潰？  
> 💡 **防護解法**：`VectorIndex.load_binary` 實作向下相容探測；若未包含元資料檔頭，自動回退為舊版直接反序列化，若維度不符則平滑重建，保證舊快取零崩潰。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：實作 `knowledge_db/config.py`，支援 Local / Project 級 4 大組態讀取與執行緒解析。
- [ ] **TASK-02**：重構 `knowledge_db/embedding.py`，整合 `max_threads`、HF Hub 警告屏蔽、`VectorIndex` 檔頭元資料與相容性檢查。
- [ ] **TASK-03**：重構 `knowledge_db/pipeline.py`，實作 JIT 10 符號動態探針、熔斷降級、雙軌進度呈現。
- [ ] **TASK-04**：更新 `knowledge_db/engine.py`，將 Config 注入 Pipeline 與各子組件。
- [ ] **TASK-05**：重構 `scripts/cli.py`，導入 `TerminalStyler` 色彩排版、修復 `status` 與 `--help`、保障 `--json` 純淨。
- [ ] **TASK-06**：編寫 `tests/test_cli_ux.py` 單元測試套件，100% 覆蓋 FT-01~09 與全生態系回歸驗證。
- [ ] **TASK-DOC**：更新 `source/knowledge-db/README.md` 與 `docs/knowledge-db/DESIGN_NOTES.md` (`[DN-KDB-09]`)。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 定稿動態探針與可配置熔斷、雙軌進度呈現、ANSI 階層美化與 Config 整合方案，准予啟動代碼編寫。
