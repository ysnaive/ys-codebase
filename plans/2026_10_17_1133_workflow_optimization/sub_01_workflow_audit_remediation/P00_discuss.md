# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：工作流審計全面修復 (Workflow Audit Remediation)  
> 建立日期：2026-10-17  
> 所屬主計畫：2026_10_17_1133_workflow_optimization  
> 狀態：Confirmed  
> 模型：Claude Opus 5.5  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：「審計報告的其餘項目皆納入 sub 01 一併處理，同時這份審計作為 sub-01-R01」；先前裁定：AgentsStandards 模板來源改為指向 development-sop SKILL.md 的路徑佔位符、Fast Track 步驟更名為 FP-01/02/03 (Fast Phase)、附掛修訂僅於歸檔時攔截、`plan status` 不標示附掛修訂。
- **核心目標**：一次性修復 [R01_workflow_audit_research.md](./R01_workflow_audit_research.md) 所列全部發現（C-1、C-2、M-1~M-11、m-1~m-10、G-1、D-1），使 `agents-workflow` 規格、模板與 plans 工具鏈一致且可被無歧義執行。
- **邊界排除 (Explicitly Excluded)**：
  - 不手動修改已物化之 `.agents/*`，一律經 release 流程同步。
  - 不追溯改寫已封存計畫與既有 `CHANGELOG.md` 歷史條目（例如舊的 `FT-3` 字樣保留原樣）。
  - 不新增 Track 種類，不變更 CLI 指令契約（`plan status / verify / archive` 參數不變）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** 附掛 `revision_log.md` 未結案時，僅於 `plan archive` 攔截；`plan verify` 不強制。修正 `plan_modes.md` 之相反描述（M-1）。
- **[P00:DR-02]** `plan status` 不標示附掛修訂之狀態。
- **[P00:DR-03]** `AgentsStandards.md` 模板來源改以 `module://agents-workflow/assets/skills/development-sop/SKILL.md` 的連結佔位符指向 development-sop，由其 §6 模板指針提供 target 感知路徑（G-1，R01 §2.2 方案 B）。
- **[P00:DR-04]** Fast Track 步驟 `FT-1/2/3` 更名為 `FP-01/02/03` (Fast Phase)；測試 ID `FT-XX` 維持不變；verifier 測試案例判定收緊為 `\b(FT|ET|RT)-\d{2}\b`（M-10，R01 §2.1 方案 A）。
- **[P00:DR-05]** 審計全部發現納入本子計畫，依 R01 §4 之 P1 → P2 → P3 優先序排程。
- **[P00:DR-06]** 推薦分流：**Full Track**。理由：涉及 plans 工具鏈程式碼重構（共用狀態解析）、修改量遠超 100 行，且變更工作流規格契約。

---

## 3. 開放議題與確認紀錄

以下為進入 P01 前之規格選擇裁定紀錄（2026-10-17 11:44 開發者裁定）：

- [x] **Q1 調研報告命名（m-4）** → **[P00:DR-07]** 統一為 `R{NN}_{topic}.md`，並放寬 verifier 以 `R\d{2}_*.md` 對應調研模板（不再要求檔名含 `research`）。
- [x] **Q2 Research 是否必建 P00（m-7）** → **[P00:DR-08]** 已立項之 Research 計畫必建 `P00 + R{NN} + changelog`；未立項之前置調研僅存於對話，不建檔。
- [x] **Q3 P06 狀態機（M-5）** → **[P00:DR-09]** `Draft`（P02 建立）→ `Confirmed`（P04 定稿）→ `In Progress`（P06 執行中）→ `Passed`（自動化測試全過、待 UX 驗收）→ `Completed`（UX 項目全數標定）；continue / auto / phase_06 卡片依此對齊。
- [x] **Q4 Umbrella 詞彙（m-5）** → **[P00:DR-10]** 統一採 `Pre-planned / Incremental`；umbrella 狀態值併入通用值域，`Executing` 改為 `In Progress`。
- [x] **Q5 Roadmap 實體結構（m-6）** → **[P00:DR-11]** 每主題一檔 `{topic}.md`（查證：`RoadmapManager.scan_roadmaps` 與 `plans/roadmap/` 現況即為每主題一檔），修正 plan_modes / development-sop / new-plan 之單檔 `roadmap.md` 描述。
- [x] **Q6 Revision 升級熔斷（M-7）** → **[P00:DR-12]** 觸及控制流/條件分支變更、Schema 或狀態機變更、機器可解析之輸出格式變更、新增依賴任一項，即強制升級為 Fast Track 或 Full Track。
- [x] **Q7 revision_log 重開語意（M-8）** → **[P00:DR-13]** 同一目錄僅一份 revision_log；已 Completed 後之新修訂原地改回 `In Progress` 並追加 `[REV-XX]`；已封存計畫之修訂改開獨立修訂計畫，標頭「所屬主計畫」填原計畫名。
- [x] **Q8 Fast Track 推進節奏（M-9）** → **[P00:DR-14]** FP-01 結束須 End Turn 等待授權；FP-02 → FP-03 可連續執行。
- [x] **Q9 /auto 起點（m-8）** → **[P00:DR-15]** 允許於「P00 Confirmed 且分流為 Full Track」時觸發。
- [x] **Q10 revision_log 全域 CHANGELOG 同步（m-10）** → **[P00:DR-16]** 僅具使用者可感知影響之修訂需同步，純勘誤/註解類免同步。
- [x] **Q11 判定表灰色地帶與 DR 前綴（m-9）** → **[P00:DR-17]** 不滿足 Fast Track 任一守門即歸 Full Track；Bug Fix 排除於 Revision 之外；DR 前綴定義為 `[FP-0X:DR-XX]`、`[REV-XX:DR-XX]`。
- [x] **Q12 強制語氣分層（m-10）** → **[P00:DR-18]** 僅處理關鍵守門（P06 UX 標定、禁止擅自發布、禁止擅自歸檔）之標記一致化，不做全面語氣重寫。
- [x] **分流確認** → Full Track（[P00:DR-06]）。

