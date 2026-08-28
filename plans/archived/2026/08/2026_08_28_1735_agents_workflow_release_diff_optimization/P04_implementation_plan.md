# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：agents-workflow 發布引擎來源 Diff 檢測與無效 File IO 優化 (agents-workflow Release Diff Optimization)  
> 建立日期：2026-08-28  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 (指紋短路) ➔ `compute_source_fingerprint`、FR-02 (落地 Diff) ➔ `release_all` Stage 4、FR-03 (軟合併 Diff) ➔ `_soft_merge_agents_md`、FR-04 (`--force`) ➔ `cli.py` & `release_all(force=True)`、FR-05 (結構化指標) ➔ `release_all` 回傳值。
- [x] **邊界防護**：EC-01 (檔案遺失失效短路) ➔ 存在性校驗；EC-02 (Target 變更) ➔ 指紋涵蓋 Target 規則；EC-03 (Manifest 損毀) ➔ 安全降級；EC-04 (AGENTS.md 自定義章節) ➔ 正則替換前後精準比對。
- [x] **指標約束**：NFR-01 達成 Reload 0 I/O；NFR-02 短路耗時 $< 5\text{ms}$；NFR-03 100% Python 標準庫；NFR-04 回歸 100% Passed。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 1** | `docs/agents-workflow/README.md` | Modify | 補充 `release --force` 指令說明與 reload 雙階 Diff 檢測機制說明。 |
| **維度 2** | `docs/agents-workflow/architecture.md` | Modify | 更新發布引擎四步流水線圖解，納入 Stage 0 來源指紋與 Stage 4 內容比對。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若開發者在磁碟上手動刪除某個已發布的 `.agents/workflows/Auto.md`，但未修改任何 `source/` 檔案，系統是否會因為來源指紋命中而永遠不補齊該檔案？  
> 💡 **防護解法**：在 Stage 0 指紋比對命中時，會逐一檢查 manifest 中 `published_files` 及 `AGENTS.md` 的實體檔案存在性 (`os.path.isfile(f)`)。若任一檔案缺失，短路自動失效並降級為標準 Stage 1~4 發布，即時修復補齊缺失檔案 (EC-01)。

> ❓ **尖銳問題 2**：若開發者在 `AGENTS.md` 底部手動編輯了自定義章節（`## 4. 專案特化工程規範`），在 Diff 檢測時是否會因為不是純標準內容而反覆覆寫或損壞使用者內容？  
> 💡 **防護解法**：`_soft_merge_agents_md` 在記憶體中先讀取現存 `AGENTS.md` 並進行正則標籤區塊替換（完整保留自定義內容），然後比對替換後的新字串與現存字串 `new_content == existing`。若標準內容未變且自定義內容未變，兩者字串完全一致，跳過寫入；若使用者修改了自定義內容，合併後完整保留自定義內容並正確覆寫 (EC-04)。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：在 `source/agents-workflow/agents_workflow/publisher.py` 中實作 `compute_source_fingerprint()`。
- [ ] **TASK-02**：在 `publisher.py` 中重構 `_soft_merge_agents_md()` 支援 Diff 檢測與 `(success, written)` 回傳。
- [ ] **TASK-03**：在 `publisher.py` 中重構 `release_all()` 支援 Stage 0 短路、Stage 4 內容比對、`force` 旗標與完整指標回傳。
- [ ] **TASK-04**：在 `source/agents-workflow/scripts/cli.py` 中擴充 `release` 指令支援 `--force` 參數。
- [ ] **TASK-05**：在 `source/agents-workflow/scripts/hook.core.py` 中更新 `on_reload` 日誌輸出。
- [ ] **TASK-06**：撰寫 `source/agents-workflow/tests/test_publisher.py` 完整覆蓋 FT-01~06 與 ET-01~03。
- [ ] **TASK-07**：實機執行全模組測試 `python yscb.py dev test agents-workflow`，確保全量 Passed。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 剛性定稿 P04 實作計畫與 P06 測試計畫**：完成交叉審查與靈魂拷問防護，全面啟動 Phase 5 依序編碼實作。
