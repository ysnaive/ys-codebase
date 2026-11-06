# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：全專案九大模組確定性代碼優化、實作邏輯/併發問題修復與測試套件純化  
> 建立日期：2026-11-06  
> 計畫狀態：Completed  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模型：Gemini 3.1 Pro  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：針對 `ys-codebase` 全部 9 大模組執行業務程式碼確定性優化、實作邏輯與併發競態根治，以及測試套件病灶純化，達成全模組單元測試 100% 通過、`0 ResourceWarning` 與 `Checker` `0 FAIL, 0 WARN`。
- **架構邊界**：對外公開 SDK 與 CLI 嚴守 `Mode B`（100% 向下相容），內部無外部引用之私有輔助函式採 `Mode A`（單一正統入口、零冗餘轉發殼）。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_vscode_support` | Auto Track | Completed | `vscode-support` 模組（`OPT-01~08`, `AUD-01~07` 與 `ISS-02` 修復，22/22 測試通過，完成 P07 結案） |
| **sub_02** | `sub_02_server` | Auto Track | Completed | `server` 模組（`OPT-01~11`, `FIX-01~10`, `AUD-01~12` 與 `ISS-01` 強殺日誌歸檔修復，59/59 測試通過，完成 P07 結案） |
| **sub_03** | `sub_03_file_space` | Auto Track | Completed | `file-space` 模組（`OPT-01~41`, `AUD-01~10`，28/28 測試通過，0 Issue，完成 Review Gate 與 P07 結案） |
| **sub_04** | `sub_04_dev` | Auto Track | Completed | `dev` 模組（`OPT-01~15`, `AUD-01~17`，108/108 測試通過，0 Issue，完成 Review Gate 與 P07 結案） |
| **sub_05** | `sub_05_knowledge_db` | Auto Track | Completed | `knowledge-db` 模組（`OPT-01~12`, `AUD-01~24`，109/109 測試通過，0 Issue，完成 Review Gate 與 P07 結案） |
| **sub_06** | `sub_06_agents_workflow` | Auto Track | Completed | `agents-workflow` 模組（`OPT-01~18`, `AUD-01~32`，145/145 測試通過，0 Issue，完成 Review Gate 與 P07 結案） |
| **sub_07** | `sub_07_ast` | Auto Track | Completed | `ast` 模組（`OPT-01~18`, `AUD-01~18`，36/36 測試通過，0 Issue，完成 Review Gate 與 P07 結案） |
| **sub_08** | `sub_08_core` | Auto Track | Completed | `core` 模組（`OPT-01~18`, `AUD-01~30`，256/256 測試通過，0 Issue，完成 Review Gate 與 P07 結案） |
| **sub_09** | `sub_09_gdrive_support` | Auto Track | Completed | `gdrive-support` 模組（`[TODO-24]` 單向刪除基線保護、`[TODO-25]` 空目錄清理與還原目錄掃描、`sync_state.journal.jsonl` WAL 持久化優化，34/34 測試通過，完成 P07 結案） |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1**：完成 `sub_01` ~ `sub_08` 八大模組之五步盲測子代理閉環（763/763 測試通過，`0 ResourceWarning`）與雲端受控 CoW 同步。
- [x] **里程碑 2**：完成 `sub_01` (`ISS-02`) 與 `sub_02` (`ISS-01`) 遺留缺失修復，並完成 `sub_01` ~ `sub_08` 全部 `P07_walkthrough.md` 結案。
- [x] **里程碑 3**：完成 `sub_09_gdrive_support`（`[TODO-24]`、`[TODO-25]` 與 WAL 持久化優化）並完成主傘計畫最終結案。
