# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：knowledge-db 熱重載新增與修改檔案靜默 no-op 修復 (Hot Reload Silent No-op Fix)  
> 建立日期：2026-09-06  
> 所屬主計畫：無 (獨立標準計畫)  
> 狀態：Confirmed  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-03 在 `P03_api_spec.md` 中皆有明確的方法簽名與契約定義。
- [x] **邊界防護**：EC-01 ~ EC-03 涵蓋二進位損毀、快照缺失與空變更防禦，皆有 `try-except` 與全量重建兜底。
- [x] **依賴純淨**：完全不引入第三方新依賴，符合 NFR-01 指標約束。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 登記 `[DN-18]` 熱重載倒排索引磁碟懶加載與全量自癒兜底架構；登記 `[DN-19]` 物理級 SSOT：廢除 JSON 指紋檔全權收斂至二進位快照 |
| **測試規格** | `plans/.../P06_test_plan.md` | Confirm | 定稿 FT-01~03、ET-01、FT-04~06 與 RT-01 測試規格 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若 `unified.index.bin.gz` 讀取途中剛好遇到並發寫入或損毀怎麼辦？  
> 💡 **防護解法**：`save_binary` 原生採用 `tempfile + os.replace` 原子替換，讀取方不會讀到半截檔案；即便遭遇檔案損毀或解壓異常，外層 `try-except` 捕獲警告並降級回傳 `HotPatchResult(False)`，緊接著由 Daemon 的第二道防線觸發 `build_unified_index(force=True)` 全量自癒重建。

> ❓ **尖銳問題 2**：若檔案很多，全量兜底重建是否會造成 Daemon 卡死？  
> 💡 **防護解法**：全量重建僅在增量熱補丁失敗時作為例外補救路徑單次執行；且 `_execute_debounced_patch` 本身在 Daemon 的獨立背景 Timer 線程中執行，前台 CLI 不會被阻塞。

> ❓ **尖銳問題 3**：廢除 `fingerprints.json` 後，各空間如何取得快取檔案數量？  
> 💡 **防護解法**：`unified.meta.bin` 儲存了全域正規化檔案路徑清冊。`engine.status()` 直接以各空間定義之 `include`/`exclude`/`file_patterns` 動態過濾計算，微秒級完成統計，徹底解決快照時間差問題。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [x] **TASK-01**：在 `source/knowledge-db/knowledge_db/pipeline.py` 實作 `hot_patch_unified_index` 磁碟懶加載（對應 FR-01, EC-01）。
- [x] **TASK-02**：在 `source/knowledge-db/knowledge_db/daemon.py` 實作 `_execute_debounced_patch` 與 `_run_startup_check` 失敗兜底重建與詳細 diff 統計日誌（對應 FR-02, FR-03, EC-02）。
- [x] **TASK-03**：在 `source/knowledge-db/tests/test_hot_reload_server.py` 編寫單元測試覆蓋 FT-01~03 與 ET-01。
- [ ] **TASK-04**：在 `source/knowledge-db/knowledge_db/scanner.py` 與 `engine.py` 徹底廢除 `fingerprints.json`，改以 `unified.meta.bin` 為唯一快照來源（對應 FR-04）。
- [ ] **TASK-05**：在 `source/knowledge-db/tests/test_scanner.py` 清理過時 JSON 指紋測試，更新為二進位快照驗證（對應 FR-04）。
- [ ] **TASK-DOC**：在 `docs/knowledge-db/DESIGN_NOTES.md` 追加記錄 `[DN-18]` 與 `[DN-19]`。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 拍板實作細節，全面對齊架構與規格設計，啟動 Phase 5 實作。
- **[P04:DR-02]** 拍板「路線 2：物理級 SSOT」，擴充 TASK-04/05，全面廢除 JSON 指紋。
