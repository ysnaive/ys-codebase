# 需求規格說明書 (Requirements Specification)

> 功能名稱：工作流審計全面修復 (Workflow Audit Remediation)  
> 建立日期：2026-10-17  
> 所屬主計畫：2026_10_17_1133_workflow_optimization  
> 狀態：Confirmed  
> 模型：Claude Opus 5.5  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

> 範疇：`ys_codebase/source/agents-workflow/`。發現 ID 對應 [R01_workflow_audit_research.md](./R01_workflow_audit_research.md)。

### 1.1 Plans 工具鏈（程式碼）

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 共用標頭狀態解析 | 新增共用狀態解析元件，以 `PlanVerifier.parse_plan_header` 之結構化標頭為**唯一**依據，依序讀取 `狀態` / `計畫狀態` / `調研狀態` / `status` 鍵，回傳正規化狀態值；scanner 與 archiver 一律改用此元件，**禁止**以正文子字串判定狀態。**驗收**：正文任意位置含 `Completed` 字樣不影響判定結果 | P0 | [P00:DR-05]（C-1、C-2、m-1） |
| **FR-02** | Archiver 完成判定標頭化 | 依 Track 判定完成：Fast Track 為 `fast_track_plan.md` 標頭 `Completed`；Full Track 為 `P07_walkthrough.md` 標頭 `Completed`；Umbrella 為 `umbrella_overview.md` 標頭 `Completed`；獨立 Revision 為 `revision_log.md` 標頭 `Completed`；Research 為所有 `R{NN}_*.md` 標頭皆 `Concluded`。附掛 revision_log（根目錄與 `sub_*`）全數標頭 `Completed` 之既有檢核保留並改用 FR-01。**驗收**：探針 H1 情境（FT 標頭 In Progress）被攔截 | P0 | [P00:DR-01]、[P00:DR-05]（C-1、M-3） |
| **FR-03** | Scanner Full Track Phase 判定標頭化 | 目前 Phase 取「存在之最高編號 P 檔」，但 `P06_test_plan.md` 標頭為 `Draft` / `Confirmed` 時不計入；P07 標頭 `Completed` 時顯示 `Completed`。**驗收**：探針 H2 情境（P05 In Progress + P06 Confirmed）顯示 Phase 5 | P0 | [P00:DR-09]（C-2） |
| **FR-04** | Scanner Research Track | 新增 `Research` Track：目錄含 `R\d{2}_*.md` 且不屬 Umbrella / Fast Track / Full Track / 獨立 Revision 時判定為 Research；狀態依 R 檔標頭（全數 `Concluded` → `Concluded`，否則 `Draft`）。Track 判定優先序：Umbrella > Fast Track > Full Track > Revision > Research > Phase 0 | P0 | [P00:DR-07]、[P00:DR-08]（M-3、M-4） |
| **FR-05** | Verifier 調研檔對應放寬 | 檔名符合 `^R\d{2}_.+\.md$` 即對應 `RXX_research_report.md` 模板，不再要求檔名含 `research` | P1 | [P00:DR-07]（M-3、m-4） |
| **FR-06** | Verifier 測試 ID 判定收緊 | `P06_test_plan.md` 測試案例存在性改以正則 `\b(FT\|ET\|RT)-\d{2}\b` 判定 | P1 | [P00:DR-04]（M-10） |
| **FR-07** | 佔位符自動推導 | verifier 自模板目錄之所有模板，擷取標頭 blockquote 行（以 `>` 起始）中之 `[...]` 字面片段，與既有靜態清單取聯集作為佔位符攔截集合。**驗收**：探針 H4 之 `[調研主題/所屬功能]`、`[所屬主計畫 / 無]` 被攔截 | P1 | [P00:DR-05]（M-2） |
| **FR-08** | Archiver handoff 刪除時序 | 目的地衝突檢查須先於 `handoff.md` 刪除；任何前置檢核失敗時 `handoff.md` 保持原狀 | P2 | [P00:DR-05]（m-2） |
| **FR-09** | Verifier 死代碼清理 | 移除未使用之 `VALID_CHANGELOG_TYPES`（或接線使用，於 P02 擇一並登記 DR）；`verify_all_plans` 未使用參數處置；修正類別 docstring 階段描述與實作一致 | P2 | [P00:DR-05]（m-3） |

### 1.2 規範、技能與模板（文檔資產）

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-10** | Standards 模板指針改向 | `AgentsStandards.md` 路由表之模板來源改為以 `module://agents-workflow/assets/skills/development-sop/SKILL.md` 之連結佔位符指向 development-sop（§6 模板指針）；不得再寫死任何 target 投影路徑 | P0 | [P00:DR-03]（G-1） |
| **FR-11** | Fast Track 步驟更名 | 全部原始碼資產中之 Fast Track 步驟 `FT-1/2/3`、`FT-Y` 更名為 `FP-01/02/03`、`FP-0X` (Fast Phase)；測試 ID `FT-XX` 不變 | P0 | [P00:DR-04]（M-10） |
| **FR-12** | P06 狀態機對齊 | 依 [P00:DR-09] 狀態機更新 phase_02 / phase_04 / phase_06 手冊、auto 與 phase_06 卡片（UX 驗收前顯示 `Passed`）、continue 3-T 判定表 | P0 | [P00:DR-09]（M-5） |
| **FR-13** | continue 判定表對齊 | 模式判定順序與 FR-04 優先序一致，補齊 Research 分支（3-S）、P07 列、附掛 revision_log 之判定說明；3-F 改依新 Fast Track 模板 checkbox 並將「結案發布」改為「FP-03 結案」 | P0 | [P00:DR-07]、[P00:DR-14]（M-4、M-9） |
| **FR-14** | 調研命名與 P00 規則統一 | 所有資產之調研報告命名統一為 `R{NN}_{topic}.md`；research skill、plan_modes、new-plan、development-sop 明文已立項 Research 必建 `P00 + R{NN} + changelog` | P1 | [P00:DR-07]、[P00:DR-08]（m-4、m-7） |
| **FR-15** | Revision 升級熔斷與 Bug Fix 排除 | plan_modes Revision 段落新增 [P00:DR-12] 四項升級條件與強制升級機制；明文 Bug Fix 不屬 Revision | P1 | [P00:DR-12]、[P00:DR-17]（M-7、m-9） |
| **FR-16** | revision_log 重開語意 | plan_modes 與 continue 3-R 明文 [P00:DR-13] 之重開與封存後修訂規則 | P1 | [P00:DR-13]（M-8） |
| **FR-17** | 修正 verify 檢核附掛修訂之描述 | plan_modes 改為「僅於 `plan archive` 歸檔前強制檢核附掛 revision_log 已完成」 | P0 | [P00:DR-01]（M-1） |
| **FR-18** | Fast Track 模板與節奏 | `fast_track_plan.md` 新增四大守門檢核區塊與測試驗證 checkbox；移除寫死之 `結案狀態：Completed`；plan_modes 明文 FP-01 後 End Turn、FP-02 → FP-03 可連續 | P0 | [P00:DR-14]（C-1、M-9） |
| **FR-19** | /auto 起點 | auto skill 允許於「P00 Confirmed 且分流為 Full Track」時觸發 | P2 | [P00:DR-15]（m-8） |
| **FR-20** | revision_log 全域 CHANGELOG 比例原則 | revision_log 模板與 plan_modes 改為僅使用者可感知影響之修訂需同步專案 `CHANGELOG.md` | P2 | [P00:DR-16]（m-10） |
| **FR-21** | 分流灰色地帶與 DR 前綴 | development-sop / plan_modes / new-plan 明文「不滿足 Fast Track 任一守門即歸 Full Track」；追溯鏈表新增 `[FP-0X:DR-XX]`、`[REV-XX:DR-XX]` 前綴 | P1 | [P00:DR-17]（m-9） |
| **FR-22** | Umbrella 詞彙統一 | 全部資產統一為 `Pre-planned / Incremental`；umbrella 模板狀態值改為 `Planning \| In Progress \| Completed` | P2 | [P00:DR-10]（m-5） |
| **FR-23** | Roadmap 每主題一檔描述對齊 | plan_modes / development-sop / new-plan 改述 Roadmap 為 `workflow.roadmap://` 下每主題一檔 `{topic}.md` | P2 | [P00:DR-11]（m-6） |
| **FR-24** | 關鍵守門標記一致化 | 三項關鍵守門（P06 UX 標定禁止自行通過、禁止擅自發布/升版、禁止擅自歸檔）於所有出現處使用一致之標記與措辭；不做全面語氣重寫 | P2 | [P00:DR-18]（m-10） |
| **FR-25** | context-init 懸空引用修正 | 移除或改寫已不存在之紀律條款引用，對齊現行 AgentsStandards；修正「不依賴 CLI」與步驟 3 之矛盾敘述 | P1 | [P00:DR-05]（M-6、m-10） |
| **FR-26** | P07 模板去預填 | P07 三層文檔對齊表之交付狀態改為待填；DESIGN_NOTES 列改為「僅於確有非直覺設計時登記」；P07 與 revision_log 之「已執行 plan verify」checkbox 改為非 checkbox 之結果欄位 | P1 | [P00:DR-05]（M-11、m-10） |
| **FR-27** | contributes 元數據同步 | `agents-workflow.json` export description 與各 SKILL.md frontmatter 一致；`_manifest.md` 模板數量與實際一致 | P2 | [P00:DR-05]（D-1） |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 文件缺少狀態標頭或標頭格式異常 | 狀態解析回傳 `Unknown`；scanner 顯示 `Unknown` 不中斷；archiver 視為未完成並攔截 |
| **EC-02** | 正文含 `Completed` / `Concluded` 等字樣但標頭為進行中 | 判定以標頭為準，結果為進行中 |
| **EC-03** | 舊式檔名（`FT_plan.md`、`P00_semantic_requirements.md`、`master_plan_*.md`） | 維持現行相容支援，判定改走標頭解析 |
| **EC-04** | Phase 5 期間 P06 為 `Draft` / `Confirmed` | scanner 顯示 Phase 5；P06 為 `In Progress` 以上時才顯示 Phase 6 |
| **EC-05** | Research 計畫多份 R 檔，部分 `Draft`、部分 `Concluded` | 狀態為 `Draft`，archiver 攔截 |
| **EC-06** | 非調研檔以 R 開頭（如 `README.md`、`Revision.md`）或 `revision_log.md` | 不符 `^R\d{2}_.+\.md$`，不對應調研模板，不觸發 Research Track |
| **EC-07** | 歸檔目的地已存在 | 拋出 `PlanDestinationExistsError`，`handoff.md` 與來源目錄完整保留 |
| **EC-08** | 既有 umbrella 標頭使用 `Executing` | 解析時仍視為合法進行中狀態（向後相容），不判為完成 |
| **EC-09** | P06 僅含 `FP-03` 等步驟字樣而無 `FT-XX/ET-XX/RT-XX` 測試編號 | verifier 判定缺少測試案例並 FAIL |
| **EC-10** | 模板目錄不存在或模板無標頭佔位符 | 佔位符集合回退為既有靜態清單，不拋例外 |
| **EC-11** | 目錄含 `handoff.md` 且未完成 | 維持現行 `(Paused)` 後綴顯示行為 |
| **EC-12** | 已封存計畫與既有 `CHANGELOG.md` 含舊式 `FT-3` 字樣 | 不修改；verifier 不掃描封存區，不受影響 |
| **EC-13** | 附掛 revision_log 為 `In Progress` 而主計畫 `Completed` | `plan verify` 不因此 FAIL、`plan status` 不標示；`plan archive` 攔截 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 相容性 | `plan status / verify / archive` CLI 參數、輸出欄位結構與 `PlanReport` 公開屬性維持不變 |
| **NFR-02** | 依賴 | 僅使用 Python 標準函式庫，零新增第三方與跨模組依賴 |
| **NFR-03** | 品質 | `agents-workflow` 既有單元測試 100% 通過；FR-01~FR-08 與 EC-01~EC-13 具對應新增測試；全生態系回歸 100% 通過 |
| **NFR-04** | 通用性 | 修改後之資產不得引入本專案特化詞彙（延續去特化原則） |
| **NFR-05** | 效能 | 標頭解析僅讀取檔案前 35 行範圍之 blockquote，`plan status` 不新增全文掃描 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `.agents/*` 為物化產物，嚴禁手動修改；原始碼資產變更後需經 release 流程同步，`agents-workflow release` 屬授權守門指令，須取得開發者授權。
- **`[!NOTE]`** 既有測試可能以字串斷言 `FT-1/2/3` 或模板內容（如 Fast Track 之 `Completed`），FR-11 / FR-18 實作時需同步檢視並依需求變更正當更新斷言，嚴禁為求綠燈放寬無關斷言。
- **`[!NOTE]`** `parse_plan_header` 會將前 35 行內所有含冒號之 blockquote 行解析為鍵值；FR-07 擷取模板佔位符時僅取標頭區塊，避免把說明性 blockquote（如 P06 之驗證結果說明）誤納入。

> Gemini 3.8 Flash

