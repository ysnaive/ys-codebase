# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：Plans CLI 工具鏈補齊與舊版功能遷移 (Plans CLI Toolchain Migration)  
> 建立日期：2026-08-26  
> 所屬主計畫：[agents-workflow 模組全面遷移與升級 (2026_08_25_2200_agents_workflow_migration)](../umbrella_overview.md)  
> 狀態：Confirmed  
> 依據 P01~P03：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md), [P03_api_spec.md](./P03_api_spec.md)  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 (歸檔), FR-02 (掃描), FR-03 (檢索), FR-04 (稽核) 在 API 規格書中均由獨立類別與方法 1:1 承接。
- [x] **邊界防護**：EC-01~06 均具備專屬自定義例外（`PlanNotFoundError`, `PlanFormatError`, `PlanIncompleteError`, `PlanDestinationExistsError`）與優雅容錯防禦。
- [x] **依賴純淨**：NFR-01~03 100% 透過 `core.uri.resolve` 動態解算、採用純 Python 標準庫，串流搜尋時間 $< 500\text{ms}$。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度一** | `docs/agents-workflow/README.md` | Modify | 更新 CLI 指令清冊矩陣，新增 `plan archive/status/search/verify` 快速索引 |
| **維度三** | `docs/agents-workflow/user_guide.md` | Modify / New | 撰寫 Plans CLI 工具鏈完整操作手冊（語法、參數、安全防護與範例） |
| **發布日誌** | `CHANGELOG.md` | Modify | 追加本次 sub_08 Plans CLI 工具鏈遷移之高階發布摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1（跨磁碟與路徑協議解析一致性）**：  
> 若開發者自訂了 `workflow.plans://` 或 `workflow.archived://` 協議指向不同磁碟分區，`PlanArchiver` 的跨磁碟搬移是否會因 `os.rename` 失敗？  
> 💡 **防護解法**：  
> `PlanArchiver` 統一透過 `core.uri.resolve` 解算為標準 `pathlib.Path` 物件，目錄搬移採用 Python 標準庫之 `shutil.move()`（支援自動處理跨磁碟分區的複製與刪除），並在搬移前後進行目錄父級自動遞迴建立（`mkdir(parents=True, exist_ok=True)`）與衝突防護，確保跨平台跨磁碟 100% 穩健。

> ❓ **尖銳問題 2（超大型專案 Markdown 檢索記憶體與效能約束）**：  
> 當歷史歸檔累積上百個計畫、數千個 Markdown 檔案時，`plan search` 全文檢索是否會因記憶體膨脹或全量掃描而卡頓？  
> 💡 **防護解法**：  
> `PlanSearcher` 採用逐檔串流式讀取（`open(..., errors="ignore")` 逐行掃描），不將全量檔案內容常駐記憶體（記憶體複雜度 $O(1)$）；同時具備 `--limit`（預設 20/25）提早短路（Short-Circuit）跳出機制，保證單次檢索時間維持在毫秒級。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01 (基礎型別與套件進入點)**：建立 `source/agents-workflow/agents_workflow/plans/__init__.py`，定義自定義例外與套件導出。
- [ ] **TASK-02 (狀態矩陣掃描引擎)**：實作 `agents_workflow/plans/scanner.py` (`PlanScanner`)，解析 4 大 Track 與 Phase 狀態並渲染 ASCII 矩陣。
- [ ] **TASK-03 (計畫安全歸檔引擎)**：實作 `agents_workflow/plans/archiver.py` (`PlanArchiver`)，實施 4 重安全檢查、清理 `handoff.md` 與時間戳目錄搬移。
- [ ] **TASK-04 (歷史檢索與規範稽核引擎)**：實作 `agents_workflow/plans/searcher.py` (`PlanSearcher`) 與 `verifier.py` (`PlanVerifier`)。
- [ ] **TASK-05 (CLI 路由派發與別名整合)**：重構 `source/agents-workflow/scripts/cli.py`，新增 `cmd_plan` 與 `plan-archive`, `plan-status`, `plan-search`, `plan-verify` 別名支援。
- [ ] **TASK-06 (專用測試套件與驗證)**：編寫 `test/test_agents_workflow_plans_toolchain.py`，覆蓋 FT-01~04 與 ET-01~06 (11 個測試)。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 零硬編碼與可注入設計**：Plans 子套件所有類別預設調用 `core.uri.resolve`，同時允許建構子注入自定義路徑，保障單元測試極致隔離。
- **[P04:DR-02] Test-First 測試計畫定稿**：同步將 `P06_test_plan.md` 狀態更新為 `Confirmed`，實作階段嚴格依據 11 個測試案例進行驗證。
