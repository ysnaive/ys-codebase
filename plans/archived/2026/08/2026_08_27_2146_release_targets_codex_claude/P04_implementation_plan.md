<!--

Phase 4 執行指引：
1. 目標：對 Phase 1~3 進行嚴密交叉驗證、預排知識庫文檔衝擊 (docs/)、進行架構靈魂拷問、將 P06 測試計畫一併剛性定稿，並產出有序實作任務清單。
2. 交叉驗證：核對所有 FR/EC/NFR 在 API 規格書與架構中均有具體承接。
3. 文檔預排：依據知識庫 7 大抽象維度，預排本次交付必須建立或更新的 docs/ 文件（Phase 7 將 1:1 核對交付）。
4. 架構靈魂拷問：提出 2~3 個極端破壞性或邊界情境，給出明確防護解法。
5. Test-First 剛性定稿：同步審查並將 P06_test_plan.md 定稿為 Confirmed。
6. 實作任務拆解：將實作任務依依賴拓撲拆解為有序的 TASK 清單。
7. Checkpoint 等待關卡：等待開發者明確確認 P04 與 P06 內容（狀態更新為 Confirmed）後推進至 Phase 5。

-->

# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：agents-workflow 添加 codex 與 claude code release targets  
> 建立日期：2026-08-27  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-04 在 API 規格書與 `manifest.json` 宣告中有 1:1 承接。
- [x] **邊界防護**：EC-01 ~ EC-03 有具體的目錄自動建立與孤立檔案自動清理機制。
- [x] **依賴純淨**：符合 NFR-01 (100% Python 標準庫) 與 NFR-02 (毫秒級發布) 約束。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 4 (使用手冊)** | `docs/agents-workflow/user_guide.md` | Modify | 增補 `claude` 與 `codex` Release Targets 的啟用與路徑投影說明。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：當同時啟用 `antigravity`、`claude`、`codex` 三大目標時，發布引擎是否會產生路徑衝突或彼此覆蓋？  
> 💡 **防護解法**：三大 Target 之投影目錄完全隔離（分別為 `.agents/`、`.claude/`、`.codex/`），`ReleasePublisher` 採迭代式拓撲建構，各 Target 具備獨立的 Deployment Map 與 Header 規則，互不干擾。

> ❓ **尖銳問題 2**：若使用者先啟用 `claude` Target 後又透過 CLI `release-target remove claude` 停用，`.claude/` 目錄中是否會殘留無用舊檔？  
> 💡 **防護解法**：`ReleasePublisher` 在每次發布交易的第 1 步會讀取 `storage://agents-workflow/release_manifest.json` 歷史發布清冊，自動比對並安全移除已不在當前 active targets 中的歷史檔案。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：在 `ys_codebase/source/agents-workflow/manifest.json` 宣告 `claude` 與 `codex` 的 release_target 與投影規則。
- [ ] **TASK-02**：在 `ys_codebase/source/agents-workflow/tests/test_targets.py` 編寫單元測試，驗證 targets 列表與發布產物目錄結構。
- [ ] **TASK-03**：執行虛擬沙盒跑測 `python yscb.py dev test agents-workflow`，確保 100% Passed。
- [ ] **TASK-04**：更新 `docs/agents-workflow/user_guide.md` 交付文檔。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 確認 P01~P03 規格無任何未解技術疑慮，P06 測試計畫同步剛性定稿為 Confirmed。
