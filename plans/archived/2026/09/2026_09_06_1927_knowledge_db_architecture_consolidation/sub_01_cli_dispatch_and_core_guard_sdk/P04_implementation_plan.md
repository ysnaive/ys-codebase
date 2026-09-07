# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：cli_dispatch_and_core_guard_sdk  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-08 在 P03 規格書中皆具備精確簽名與實作契約
- [x] **邊界防護**：EC-01 ~ EC-05 均定義了專屬錯誤判定、AST 捕捉與 126 熔斷策略
- [x] **依賴純淨**：完全遵循 NFR-02，全鏈路維持 100% Python 標準庫零第三方依賴

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md` | Modify | 補充 `core.guard` 守門機制與 `guard_dispatch` 使用說明 |
| **模組手冊** | `docs/dev/user_guide.md` | Modify | 更新 `scripts/cli.py` 進入點規範（`process` 宣告、禁 `main`、禁頂層裸代碼） |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | Modify | 登記 `[DN-16]` CLI 進入點去腳本化與防繞道守門架構決策 |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄 CLI 串接系統改造與 Core 守門 SDK 成果摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：如果既有測試或開發者寫 `import scripts.cli`，是否會因為頂層無 `main` 而導致匯入失敗？  
> 💡 **防護解法**：不會。因為 `cli.py` 本身僅提供函式定義 `def process(args)`，任何外部程式以模組方式 `import` 它都是安全的純定義加載；而內部執行邏輯全部封閉在 `process` 函式中，只有在被調用時才會觸發守門檢查。

> ❓ **尖銳問題 2**：在 Linux Dev Container 跑 `python yscb.py dev test <mod>` 時，守門 SDK 是否會誤殺測試案例？  
> 💡 **防護解法**：不會。`dev.tester` 在啟動測試子進程時原本就會注入 `YSCB_TESTING=1`，且 Core 守門 SDK 專門設有 `YSCB_TESTING` 快速豁免邏輯，保證單元測試與自動化驗收暢行無阻。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：實裝 Core 守門 SDK (`core.guard`) 並導出至 `core` 模組，編寫 `test_guard.py` 單元測試
- [ ] **TASK-02**：升級 `dev.scaffold.Scaffolder`，適配新規範骨架生成
- [ ] **TASK-03**：升級 `dev.checker.Checker`，實裝 AST 靜態語法檢核（must process, no main, no top-level stmts），編寫 `test_cli_compliance.py`
- [ ] **TASK-04**：改造 `yscb.py` 宿主分發層，注入 Dispatch Token 並改以 `process(args)` 調用
- [ ] **TASK-05**：生態系既有模組全量遷移對齊（`core`、`dev`、`agents-workflow`、`knowledge-db`）
- [ ] **TASK-06**：全生態系模組單元測試與回歸驗收
- [ ] **TASK-DOC**：更新 `docs/` 相關模組說明與微觀代碼 Docstrings

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 全鏈路嚴格靜態與動態雙保險**：靜態依賴 `dev.checker` AST 語法掃描把關源碼合規性；動態依賴 `core.guard` 在執行期第 1 行進行環境安全熔斷。
- **[P04:DR-02] 凍結自部署執行紀律**：所有任務推進過程一律不執行 `install <mod>@build`，僅在 `source/` 源碼進行編碼與跑測。
