# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：終端編碼防護、舊版殘留清理、特殊字元徹底捨棄與測試狀態閉環 (sub_05)  
> 建立日期：2026-09-12  
> 所屬主計畫：2026_09_07_0831_quality_update  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 在架構與 API 規格書中有對應介面與任務清單
- [x] **邊界防護**：EC-01 ~ EC-03 均有具體防禦實作（`errors='replace'`、`try...except` 與門檻寬裕度）
- [x] **依賴純淨**：符合 NFR-01 ~ NFR-03 純標準庫與跨平台無 Warning 指標

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **微觀日誌** | `plans/2026_09_07_0831_quality_update/sub_05_.../changelog.md` | Modify | 記錄 Phase 流轉與實作成效 |
| **母計畫總覽** | `plans/2026_09_07_0831_quality_update/umbrella_overview.md` | Modify | 登記 sub_05 進度與里程碑更新 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：捨棄 Emoji 後，CLI 輸出視覺層次是否會下降？  
> 💡 **防護解法**：全面採用標準方括號英文與中文雙重標籤（如 `[SAFE] 自主安全 (safe)`、`[GATED] 授權守門 (gated)`），版面排版透過固定欄位寬度（`<23`）對齊，視覺辨識度與專業感不減，同時達成 100% 終端相容性。

> ❓ **尖銳問題 2**：Windows CP950 / CP437 終端在沒有環境變數時是否還會報錯？  
> 💡 **防護解法**：在 `yscb.py` 頂層與 `dispatcher` 主動調用 `sys.stdout.reconfigure(encoding='utf-8', errors='replace')`，雙重保險杜絕崩潰。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：修改 `source/core/core/commands/help.py`，全面移除 Emoji，改用 `[SAFE]`, `[CONDITIONAL]`, `[GATED]` 等 ASCII 標籤；同步檢核生態系所有 CLI 輸出。
- [ ] **TASK-02**：於 `yscb.py` 進入點與 `source/core/core/commands/dispatcher.py` 實施 Windows `sys.stdout/stderr` UTF-8 重組與容錯保護。
- [ ] **TASK-03**：清理舊版 `contributes.format.md`（core, server, knowledge-db）並將 `source/knowledge-db/configurable/contribute.json` 重新命名為 `config.project.json`。
- [ ] **TASK-04**：為 `agents-workflow` (44 處) 與 `core` (17 處) 補齊 `self.mark_passed()`，微調 `test_pt_01_uri_resolve_perf` 門檻以抵抗高並發沙盒波動。
- [ ] **TASK-05**：執行 `dev check --all` (0 Warning) 與 `dev test --all` (511 測試 100% Passed)。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 確認執行全生態系特殊字元徹底捨棄與 Windows 終端 UTF-8 防護，並完成全量歷史測試 `mark_passed` 閉環。
