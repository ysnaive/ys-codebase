# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：通用子代理與盲眼子代理雙層標準抽離及按需調度架構 (`subagent_and_blind_subagent_standards`)  
> 建立日期：2026-11-01  
> 所屬主計畫：`2026_11_01_1309_subagent_and_blind_subagent_standards`  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Revision  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：將下游路線圖提案 `subagent_and_blind_subagent_standards_roadmap` 入庫並立即立項推進（`roadmap promote`），因本案屬純提示詞、中央標準與技能文檔修訂計畫，採用 `Revision` 模式進行，並依討論定案雙層標準之節點注入組合、單一版本明確引用、結構影響範圍門檻（禁用檔案數/行數硬編碼常數）與 `/blind-subagent` 簡化觸發契約。
- **核心目標**：
  1. **建立雙層中央標準並透過節點注入零重複組合**：建立 `SubagentStandards.md`（管轄物理與通訊圍欄）與 `BlindSubagentStandards.md`（前半段透過系統內部節點佔位符直接將 `SubagentStandards.md` 原文注入，後半段疊加盲眼認知隔離、去錨定轉譯、靜態唯讀審查與反方辯護查驗協定），確保維護單一真理來源（SSOT）。
  2. **明確單一引用原則（Mutually Exclusive Single Reference）**：因 `BlindSubagentStandards.md` 編譯後已完整包含 `SubagentStandards.md` 前段通用物理規範，各工作流技能引用時採取「**二擇一明確引用**」——知情實作委派僅引用 `SubagentStandards.md`；盲眼探索、冷眼審查、反向查驗或平行盲審**僅引用 `BlindSubagentStandards.md`（不再重複引用標準版）**。
  3. **新增顯式盲眼調度技能 `/blind-subagent`**：採用 `B-Assist` 斜線＋簡化明確委託雙通契約（觸發詞簡化為「僅於顯式輸入 `/blind-subagent` 或明確要求透過盲眼子代理執行任務時觸發」），內建主代理去錨定轉譯器（De-Anchoring Dispatcher）與四大盲眼任務原型映射。
  4. **以「職責正交與跨模組/跨類別結構影響範圍」取代硬編碼檔案/行數常數門檻，收斂跨技能重複條款**：於 `auto/SKILL.md`、`phase_05_task.md`、`phase_06_test.md`、`phase_07_walkthrough.md`、`discuss/SKILL.md`、`research/SKILL.md` 及 `code-optimizer/references/exploration-and-delegation.md` 全面拔除硬編碼檔案數/行數常數（如 `>= 5 個檔案`、`> 1,500 行`），改以「**是否橫跨多個模組或類別（Classes）、產生職責正交之結構性影響範圍**」作為主代理內聯 vs. 子代理委派之評判界線，並將重複子代理細則收斂為單一標準連結引用。
- **邊界排除 (Explicitly Excluded)**：
  - 不修改 `agents-workflow` 或其他模組之 Python 業務邏輯與公開 API 程式碼（僅涉及 `assets/{standards,skills}/`、`contributes/` 與對應資產合規測試）。
  - 不額外增設對外開放之冗餘 Stage 1 擴充錨點（維持既有 24 個開放錨點地圖不變）。
- **架構影響範圍**：
  - 新增中央標準：`ys_codebase/source/agents-workflow/assets/standards/SubagentStandards.md`、`BlindSubagentStandards.md`
  - 新增內建技能：`ys_codebase/source/agents-workflow/assets/skills/blind-subagent/SKILL.md`
  - 組態註冊：`ys_codebase/source/agents-workflow/contributes/agents-workflow.json`、`_manifest.md`
  - 跨技能去重與影響範圍界線對齊：`auto/SKILL.md`、`development-sop/SKILL.md`、`development-sop/references/{phase_05_task,phase_06_test,phase_07_walkthrough}.md`、`discuss/SKILL.md`、`research/SKILL.md`、`code-optimizer/references/exploration-and-delegation.md`、`how-to-yscb/SKILL.md`
  - 文檔與資產合規測試同步：`docs/agents-workflow/{README,user_guide}.md`、`ys_codebase/source/agents-workflow/tests/test_compiler.py`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 物理雙檔與 `BlindSubagentStandards.md` 內部節點注入組合（Zero-Duplication Composition）**：
  - 採用選項 A 建立 `SubagentStandards.md` 與 `BlindSubagentStandards.md` 兩份獨立標準檔並註冊於 `contributes/agents-workflow.json` 之 `export` (`type: "standard"`)。
  - 為使 `BlindSubagentStandards.md` 前段章節與 `SubagentStandards.md` 100% 同步且零重複維護，比照系統內建 `PHASEXX_HEADER` 之 `insert` (`type: "uri"`, `mode: "replace"`) 機制，於 `BlindSubagentStandards.md` 前段透過內部佔位符直接將 `SubagentStandards.md` 注入，後段接續「盲眼認知隔離、去錨定提示詞淨化、純靜態唯讀審查、反方辯護反向查驗與四大盲眼原型」。
  - **單一版本明確引用鐵律**：由於物化後之 `BlindSubagentStandards.md` 已是完整自包含文件，各技能引用時嚴格執行「**引用盲眼版本即不引用標準版本**」——知情實作委派（如 `P05` / `/auto` 實作）僅引用 `SubagentStandards.md`；盲眼探索、冷眼盲審、反向查驗（如 `discuss`、`research`、`P06`、`P07`、`code-optimizer`、`/blind-subagent`）僅引用 `BlindSubagentStandards.md`。
- **[P00:DR-02] `/blind-subagent` 顯式調度技能與簡化 `B-Assist` 觸發契約**：
  - 新增 `assets/skills/blind-subagent/SKILL.md`，其 Frontmatter `description` 嚴格遵循 `B-Assist` 格式並將委託觸發詞簡化為：
    `透過盲眼子代理執行無預設假設探索、冷眼靜態審查、反方辯護反向查驗與平行審計。僅於顯式輸入 /blind-subagent 或明確要求透過盲眼子代理執行任務時觸發。`
  - 同步掛載於 `development-sop/SKILL.md` §1 生命週期工作流中樞分流與 `how-to-yscb/SKILL.md` 進階技巧說明。
- **[P00:DR-03] 拔除硬編碼檔案/行數常數，統一改採「跨模組/跨類別與職責正交之影響範圍」評判界線**：
  - 全面禁止在 `auto/SKILL.md`、`phase_05_task.md`、`phase_06_test.md`、`phase_07_walkthrough.md` 與中央標準中使用硬編碼檔案數或行數常數（如 `>= 5 個檔案`、`> 1,500 行`）作為子代理觸發門檻。
  - 統一改以**架構影響範圍與職責正交性（Orthogonal Responsibility & Cross-Module/Class Blast Radius）**評判：
    - **預設主代理內聯執行（Inline by Default）**：凡單一職責軸線、局部單一類別/模組內部修改，且未橫跨多模組或多正交類別邊界者，一律預設由主代理內聯完成實作與自檢，保護開發者 Token 預算。
    - **達結構影響範圍門檻或顯式指定時委派（Subagent on Orthogonal Scope / Explicit Demand）**：當任務**橫跨多個模組或多個類別（Classes）、產生正交職責軸線變更**，或由開發者顯式指定時，方啟動知情實作子代理（引用 `SubagentStandards.md`）或盲眼探索/冷眼審查子代理（引用 `BlindSubagentStandards.md`）。
- **[P00:DR-04] 零冗餘擴充錨點原則**：
  - 不對外新增冗餘之 Stage 1 擴充 Token（維持 `extension-guide.md` 24 個擴充錨點不變）。

---

## 3. 開放議題與確認紀錄

- 已全數確認完畢，依 `Revision Plan` 模式直接進入 `revision_log.md` 執行文檔與資產修訂。

