# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：Agents-Workflow 模組新增 Auto 工作流 (Add Auto Workflow to Agents-Workflow)  
> 建立日期：2026-08-27  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  > "我想於 agents-workflow module 添加新 workflow Auto"  
  > "Auto 為可以在 Phase 01 ~ 05 之間觸發的指令，其功能為在運行到 P06 手動驗證之前，在沒有出現無法確定之問題前，跳過強制 check point"  
  > "1.1 不適用，Fast Track 無長討論情境；1.2 是，Umbrella 主計畫模式下，/Auto 預設為針對當前進行中的子計畫 (sub_XX) 連續推進；2. 是"
- **核心目標**：
  - 於 `agents-workflow` 模組中新增 `/Auto` 工作流指引（`assets/workflows/Auto.md`）與 IDE 註冊宣告（`manifest.json`）。
  - 定義 Auto 工作流的執行語意與權限邊界：
    1. **觸發時機與適用範圍**：
       - 可在 **Phase 01 ~ Phase 05** 之間的任何時點被開發者觸發。
       - 適用於 **Level 1 (Full Track)** 與 **Level 2 (Umbrella 主計畫)** 下處於進行中狀態之 Full Track 子計畫 (`sub_XX`)。
       - **Fast Track (Level 0) 不適用**（因流程極簡、無長討論或多階段等待需求）。
    2. **跳過中間 Checkpoint 連續推進**：
       - 在未出現無法確定的技術疑問、架構爭議或異常前，Agent 獲授權可連續執行並產出後續各 Phase 文件及程式碼實作，無需於各中間 Phase 停頓等待開發者確認。
    3. **P06 手動/UX 驗證絕對阻斷關卡**：
       - 自動推進執行至 Phase 6 且 CLI 自動化測試通過後，**必須強制停步於 P06 手動/UX 驗證 Checkpoint**，呈遞測試報告並等待開發者人工驗收，絕對嚴禁越過 P06 自動結案。
    4. **異常與重大偏差中斷保護 (Circuit Breakers)**：
       - 若執行期間遭遇需求語意不明確（違反零臆測）、Major/Critical 架構偏差、或測試連續失敗時，必須立即中斷自動推進，主動向開發者呈遞問題或轉入 `/Discuss`。
    5. **規範與文件產出 100% 保真**：
       - 自動連續推進時，所有對應 Phase 文件（P01~P06、P05 task 清單、計畫 changelog 日誌）仍必須 100% 嚴格鏡像標準模板完整生成與記錄，不可略過文件產出。
- **邊界排除 (Explicitly Excluded)**：
  - 不支援 Level 0 (Fast Track)。
  - 嚴禁自動略過 Phase 6 的手動/UX 驗證 Checkpoint。
  - 嚴禁在遇到架構不確定、外部範疇變更或測試重大異常時強行猜測推進。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] (雙星伴隨初始化)**：
  - 開立計畫目錄 `workflow.plans://2026_08_27_0344_agents_workflow_auto/`，伴隨建立 `P00_semantic_requirements.md` 與 `changelog.md`。
- **[P00:DR-02] (Auto 工作流定位與執行邊界)**：
  - 確立 Auto 為「Phase 01 ~ 05 區間之連續推進指令」，核心特權為在無不確定性條件下自動通過中間 Checkpoint，直達 P06 人工/UX 驗證前。
  - 確立「零臆測阻斷」、「偏差阻斷」、「P06 UX 阻斷」三大安全防護網。
- **[P00:DR-03] (適用範圍分流與 IDE 發布整合)**：
  - **排除 Fast Track**：明確界定 Fast Track 不適用 Auto，專注服務 Full Track 與 Umbrella 子計畫。
  - **Umbrella 子計畫推進**：在 Umbrella 主計畫下，`/Auto` 鎖定當前進行中的子計畫 (`sub_XX`) 執行連續推進。
  - **IDE 導出與註冊**：於 `manifest.json` 中宣告 `Auto.md` 納入 `export` 與 `release_target`，向 IDE 導出 `/Auto` 工作流。

---

## 3. 開放議題與確認紀錄 (Open Questions)

- [x] **議題 1：Auto 工作流的核心定位與目標情境**（已確認：Phase 01~05 之間觸發，無不確定問題前跳過中間 Checkpoint 直達 P06 手動驗證前）
- [x] **議題 2：Fast Track (Level 0) 與 Umbrella (Level 2) 之適配**（已確認：Fast Track 不適用；Umbrella 鎖定當前活躍 `sub_XX` 子計畫推進）
- [x] **議題 3：工作流導出與 IDE 整合**（已確認：`manifest.json` 納入 `export` 與 `release_target`，發布 `/Auto` Slash Command）
