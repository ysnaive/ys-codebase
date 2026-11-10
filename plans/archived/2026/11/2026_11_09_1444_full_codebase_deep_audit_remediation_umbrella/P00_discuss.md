# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：2026_11_09_1444_full_codebase_deep_audit_remediation_umbrella  
> 建立日期：2026-11-09  
> 所屬主計畫：N/A (Root Plan)  
> 狀態：Completed  
> 模型：Unknown  
> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：「本地以完成新一批優化和 ast 重構，進行 @codebase-deep-auditor 審計 (因幾乎所有 module 都有動到，進行全量審計)」$	o$「全量轉化為修補計畫」。
- **核心目標**：將全倉 10 個審計單元（`Unit 01` ~ `Unit 10`）檢出之全部 **67 項審計問題（4 P0 + 26 P1 + 26 P2 + 11 P3）** 毫無遺漏地轉化為結構化、可直接由本地端 `/auto` 或 Phase 05 接手實作的 Umbrella 主計畫與 5 個職責正交子計畫（`sub_01` ~ `sub_05`）。
- **既有組件復用與查重 (Reuse Discovery)**：完全復用現有 `core.log`、`core.context`、`core.space`、`ast_engine`、`knowledge_db`、`server`、`dev`、`vscode_support`、`agents_workflow` 與 `gdrive_support` 模組架構，原位修補同步原語、生命週期與邊界處理，不引入任何新外部套件。
- **邊界排除 (Explicitly Excluded)**：報告中經 Step 2.5 三步自我反駁確認已具備防禦機制的 38 項 `RFP`（Rejected False Positives）不納入修改範圍，避免破壞既有刻意設計（如 `SQLITE_STATIC` 單執行緒擁有權與預先正規化相對路徑契約）。
- **架構影響範圍**：涵蓋 `yscb.py` 與 `ys_codebase/source/{core,ast,knowledge-db,server,dev,vscode-support,agents-workflow,gdrive-support}` 全 8 大活躍模組。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 採用預先規劃型 Umbrella 主計畫統籌 5 個職責正交子計畫 (`sub_01` ~ `sub_05`)**：依模組依賴拓撲將 10 個審計單元配對收斂為 5 個子計畫（`sub_01` Core & Bootstrap、`sub_02` AST、`sub_03` Knowledge-DB、`sub_04` Server/Dev/VSCode、`sub_05` Agents-Workflow/GDrive），每個子計畫皆預先完成 `P00_discuss.md` (`Confirmed`)、`P01-05_auto.md` (`In Progress`) 與 `P06_test_plan.md` (`Confirmed`)，使本地端 `python yscb.py gdrive pull` 後可立即逐一或平行進入 Phase 05 實作與 Phase 06 測試。
- **[P00:DR-02] P0 ~ P3 全量 67 項 100% 映射至剛性追溯鏈 (`FR-XX` / `EC-XX` / `NFR-XX` $\leftrightarrow$ `FT-XX` / `ET-XX` / `RT-XX`)**：每個子計畫不僅涵蓋 P0/P1 關鍵問題，亦將該模組範疇內所有 P2 邊界問題與 P3 結構/效能優化項完整納入 `P01-05_auto.md` 功能需求與 `TASK-XX` 任務拆解，確保無任何項目遺漏。

---

## 3. 開放議題與確認紀錄

- 已由開發者明確指示「全量轉化為修補計畫」，無開放待決議題。
