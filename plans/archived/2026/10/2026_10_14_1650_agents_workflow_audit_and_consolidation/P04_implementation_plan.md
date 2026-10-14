# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：2026_10_14_1650_agents_workflow_audit_and_consolidation  
> 建立日期：2026-10-14  
> 所屬主計畫：N/A (獨立計畫)  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-07 在 API 規格書（P03）與架構設計（P02）中均有明確實作定位與介面簽名。
- [x] **邊界防護**：EC-01 ~ EC-05 均定義了確定性防禦策略（佔位符攔截、活躍計畫強校驗、歸檔計畫不掃描、未勾選 Checkbox 阻斷）。
- [x] **依賴純淨**：100% Python 標準庫，零新增第三方依賴，清理死代碼提升系統健康度。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/agents-workflow/README.md` | Modify | 同步更新純 Skill 架構、P07 內化審查流程與模板 Header 規範 |
| **設計決策** | `docs/agents-workflow/DESIGN_NOTES.md` | Modify | 登記 `[DN-AW-15]`（模板模型溯源、P07 審查三道防線與 Token 拓撲收斂） |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄本計畫高階成果與架構重構歷程 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：將 Review Gate 併回 P07 後，Agent 是否會因為少了中間 Checkpoint 停頓，而草率填寫 P07 甚至跳過三層文檔核驗？  
> [*] **防護解法**：實施「三重剛性防線」：指引層（`phase_07_walkthrough.md` 強制 3-Step，未完成審查修改前禁止產出 P07）、模板層（必填結構化三層文檔審查表）、驗證器層（`PlanVerifier` 強制檢查狀態為 `Completed` 時若有 `- [ ]` 未勾選 Checkbox 立即判定 `FAIL`，結案自檢無法通過）。
>
> [?] **尖銳問題 2**：`contributes/agents-workflow.json` 大量刪減 40+ 個 Token，是否會破壞其他生態系模組？  
> [*] **防護解法**：事前全量審計確認：被刪減的 41 個 `PHASE00~07_*` 與 `*_AGENTS_GUILD` Token 在全專案中 **0 個引用**；保留核心通用擴充點（`PHASEXX_HEADER`、`WORKFLOW_SOP_STANDARDS`、`AGENTS_SKILL_ROUTING`、`AGENTS_CLI_GUILD`、`SESSION_ANALYSIS_CHECK_ITEMS`），並在測試沙盒中執行全生態系 5 大模組回歸驗證。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：基礎建設與 Token 清理（刪除 `providers.py`，更新 `contributes/agents-workflow.json` 與 `contributes/_manifest.md`）
- [ ] **TASK-02**：共用模組提取與 CLI 修正（於 `plans/__init__.py` 抽取 `_resolve_uri_path`，統一 fallback，修正 `cli.py`）
- [ ] **TASK-03**：模板標頭新增 `> 模型：[模型名稱]` 與 6 大非 Phase 模板 HTML 註解清除純淨化
- [ ] **TASK-04**：`new-plan/SKILL.md` 輕量化重構，廢除 `DEVELOPMENT_STANDARDS` 雙重注入並修復 15 處超連結斷鏈
- [ ] **TASK-05**：Review 內化併回 P07（刪除 `review_gate.md`，重構 `phase_07_walkthrough.md`、`P07_walkthrough.md`、`phase_06_test.md`、`auto/SKILL.md` 等）
- [ ] **TASK-06**：`PlanVerifier` 與核心工具鏈代碼升級（`has_model` 檢查、佔位符攔截、移除歸檔計畫掃描、未勾選 Checkbox 阻斷）
- [ ] **TASK-07**：單元測試更新與驗證（更新 `test_plans_toolchain.py`、`test_compiler.py`，跑通全量測試）

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 確立 7 步有序實作順序，並於 TASK-06 達成 PlanVerifier 活躍/封存邊界解耦。

