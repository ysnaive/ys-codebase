# 技術調研報告：agents-workflow 通用工作流獨立審計

> 調研主題：agents-workflow 通用工作流獨立審計 (Workflow Audit)  
> 建立日期：2026-10-17  
> 所屬主計畫：2026_10_17_1133_workflow_optimization  
> 調研狀態：Concluded  
> 模型：Claude Opus 5.5  
> 模板版本：v1.0  

---

## 1. 背景與調研目標 (Background & Objectives)

- **核心問題與痛點**：近期「修訂計畫正交化」等多輪改動大幅修改了 `agents-workflow` 提供的標準作業流程，需要以全新審計員的角度確認規格、模板與工具鏈仍然一致、可被 Agent 無歧義執行。
- **調研目標**：
  - **範圍**：`ys_codebase/source/agents-workflow/` 原始碼——`assets/standards`、`assets/skills/*`、`assets/templates/*`、`agents_workflow/plans/{scanner,verifier,archiver}.py`、`contributes/`。**不含**已物化/特化之 `.agents/*`。
  - **方法**：逐檔審閱、跨檔交叉比對；對疑似工具鏈缺陷以暫存探針腳本於臨時目錄實機重現（H1~H4，結果見 §3）。
  - **評估維度**：① 工具鏈與規格一致性 ② 規格跨檔一致性 ③ 生命週期完備性 ④ 分流判定 ⑤ Agent 可執行性 ⑥ 通用性 ⑦ 可維護性。

### 1.1 發現總覽

| 嚴重度 | 數量 | 說明 |
| :---: | :---: | :--- |
| 🔴 Critical | 2 | 工具鏈守門可被繞過，或判定與事實相反 |
| 🟠 Major | 11 | 跨檔規格矛盾、生命週期缺口，Agent 會走錯分支 |
| 🟡 Minor | 10 | 命名/詞彙不一致、元數據過時、死代碼 |

### 1.2 發現清冊

#### ① 工具鏈與規格一致性

| ID | 嚴重度 | 發現 | 根因 / 證據 |
| :--- | :---: | :--- | :--- |
| **C-1** | 🔴 | `PlanArchiver` 會歸檔「進行中」的 Fast Track 計畫 | `fast_track_plan.md` 模板寫死 `結案狀態：Completed`；`archiver._is_doc_completed` 只要內文任意處出現 `Completed` 即判完成（H1）。P07 / revision_log / umbrella 正文提及 Completed 同樣誤判 |
| **C-2** | 🔴 | `PlanScanner` 在 Phase 5 期間回報 `Testing/Phase 6` | P06 於 Phase 2 即以 Draft 建立；scanner 以「P05 與 P06 檔案皆存在」判定 Phase 6（H2）。連帶：continue 3-T 將 P06 `Confirmed`（P04 設定）解讀為「測試已通過 → Phase 7」，可能跳過 Phase 5/6 |
| **M-1** | 🟠 | `plan_modes.md` 聲稱 `plan verify` 會檢核附掛 revision_log 已完成，程式碼未實作 | 僅 archiver 檢核（H3）。**已裁定：僅於 archive 攔截，修正規格文字** |
| **M-2** | 🟠 | 佔位符攔截清單未涵蓋全部模板 | 漏 `[調研主題/所屬功能]`、`[所屬主計畫 / 無]`（RXX）、`[Planning \| Executing \| Completed]`、`[Pre-planned ... \| Incremental ...]`（umbrella）、`[Phase X / FT-Y ...]`（handoff）（H4）。清單手動維護，模板改版即漂移 |
| **M-3** | 🟠 | Research Track 於工具鏈無一等公民支援 | scanner 無 Research 分支（僅 R01 → `Unknown/Unknown`，P00+R01 → `Phase 0`）；archiver 不認 `Concluded`，出口 ③ 須 `--force`；verifier 僅檔名含 `research` 才對應模板，research skill 自身範例 `R01_architecture_reference.md` 會略過章節檢核 |
| **m-1** | 🟡 | 三套獨立狀態解析 | scanner、archiver 以子字串比對，verifier 已有結構化 `parse_plan_header`。C-1、C-2 共同根因 |
| **m-2** | 🟡 | archiver 刪除 handoff 時序錯誤 | 先刪 `handoff.md`，後檢查目的地衝突；拋 `PlanDestinationExistsError` 時快照已不可逆遺失 |
| **m-3** | 🟡 | verifier 死代碼 / 名實不符 | `VALID_CHANGELOG_TYPES` 未使用；`verify_all_plans(include_archived)` 參數未使用；docstring 稱 5-Stage 但無 Stage 3 |

#### ② 規格跨檔一致性

| ID | 嚴重度 | 發現 | 細節 |
| :--- | :---: | :--- | :--- |
| **M-4** | 🟠 | continue 模式判定與 scanner 優先序相反 | 獨立修訂 `P00 + revision_log`：scanner=Revision、continue=Full Track；主計畫結案 + 附掛 revision_log：表格先命中 Full Track 但 3-R 文字要求進 3-R；Research `P00 + R01`：continue 無分支；3-T 缺 P07 列 |
| **M-5** | 🟠 | P06 狀態語意混亂 | 流程為 Draft → Confirmed → Completed，但 continue 以 Passed 判定通過、auto 寫「嚴禁自行標記 Passed」；phase_06 與 auto 卡片在 UX 驗收前即顯示 `P06 (Completed / 待驗收)` |
| **M-6** | 🟠 | context-init 引用已不存在之紀律條款 | 要求提取「嚴禁連發」「問答≠推進」「嚴禁空降實作」「CLI Default-Deny」，現行 `AgentsStandards.md` 已無此等條款 |
| **m-4** | 🟡 | 調研報告命名四種寫法 | `R{n:2d}_{topic}.md` / `R01_{topic}_research.md` / `R01_{topic}.md` / `RXX_{topic}_research.md` |
| **m-5** | 🟡 | Umbrella 模式詞彙三套 | `Blueprint/Evolutionary`（plan_modes）、`B-1/B-2`（development-sop）、`Pre-planned/Incremental`（模板）；狀態值 `Planning \| Executing` 與通用標頭值域不同 |
| **m-6** | 🟡 | Roadmap 實體結構描述不一致 | plan_modes 為單檔 `roadmap.md`；roadmap skill 為每主題一檔 `{topic}.md` |
| **m-7** | 🟡 | Research 是否建立 P00 不一致 | plan_modes / new-plan 要求 `P00 + R01 + changelog`；research skill 未提 P00 且稱未立項不建檔，卡片卻固定「已落檔 + changelog」 |

#### ③ 生命週期完備性

| ID | 嚴重度 | 發現 | 細節 |
| :--- | :---: | :--- | :--- |
| **M-7** | 🟠 | Revision 缺升級熔斷條款 | 靜態參數、CLI 文案可能改變行為或破壞下游解析；Revision 無 Checkpoint，可能成為繞過 Fast Track 四大守門之捷徑 |
| **M-8** | 🟠 | revision_log 重開語意未定義 | 已 Completed 後之新修訂、已封存計畫之修訂回溯連結皆未規定 |
| **M-9** | 🟠 | Fast Track 模板與流程脫節 | 模板無四大守門檢核區塊；continue 3-F 檢查之「測試驗證清單」checkbox 不存在；3-F 稱「結案發布」與 P07 禁止擅自發布衝突；FT-2 → FT-3 是否 End Turn 未定義 |
| **m-8** | 🟡 | `/auto` 起點歧義 | 排除 Phase 0，但最自然觸發點正是「P00 Confirmed、未建 P01」 |

#### ④ 分流判定

| ID | 嚴重度 | 發現 | 細節 |
| :--- | :---: | :--- | :--- |
| **M-10** | 🟠 | `FT-` ID 命名空間衝突 | `FT-1/2/3` 為 Fast Track 步驟、`FT-01` 為功能測試；verifier 以 `"FT-" in l` 判定 P06 測試案例，提及「FT-3」即可誤過 |
| **m-9** | 🟡 | 判定表灰色地帶與重疊 | ≤100 行、無 API 變更但有跨模組依賴或無測試覆蓋時無明文歸屬；單常數 Bug 修復 Revision 與 Fast Track 皆適用；Fast Track / Revision 之 DR 前綴未定義 |

#### ⑤ Agent 可執行性

| ID | 嚴重度 | 發現 | 細節 |
| :--- | :---: | :--- | :--- |
| **M-11** | 🟠 | P07 模板預填 `[PASS]` | 四列預填「已交付 / 已登記 DN」，照抄即過 verifier；預設登記 DN 牴觸 DN 防膨脹公理 |
| **m-10** | 🟡 | 其他可執行性問題 | 強制語氣通膨稀釋關鍵守門；P07 / revision_log「已執行 plan verify」自我參照 checkbox；revision_log 強制同步全域 `CHANGELOG.md` 不符比例原則；context-init「不依賴 CLI」與其步驟 3 執行 `plan status` 矛盾 |

#### ⑥ 通用性 與 ⑦ 可維護性

| ID | 嚴重度 | 發現 | 細節 |
| :--- | :---: | :--- | :--- |
| **G-1** | 🟠 | AgentsStandards 模板路徑寫死 | `__${project://.agents/.yscb/templates/}__` 寫死 antigravity/codex 投影；claude target 投影至 `project://.claude/.yscb/templates`，`CLAUDE.md` 將指向不存在路徑（詳見 §2.2） |
| **D-1** | 🟡 | contributes 元數據過時 | `agents-workflow.json` export description（development-sop 僅列 3 分流、new-plan「三大分流」）與 SKILL.md frontmatter 不一致；`_manifest.md` 稱 15 個模板，實為 16 個 |

---

## 2. 候選方案分析與對比 (Candidate Evaluation)

### 2.1 M-10 `FT-` 命名空間

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 A** | 步驟更名，測試維持 `FT-XX` | 測試追溯鏈 `FT/ET/RT/PT` 對稱；verifier 免改 | 已封存計畫仍為 `FT-3`，新舊並存 | ★★★ |
| **方案 B** | 測試更名（如 `FN-XX`），步驟維持 `FT-1/2/3` | 保留「FT = Fast Track」直覺 | 破壞前綴對稱；需改程式碼與測試 | ★ |
| **方案 C** | 不改名，以位數區分並收緊 verifier | 改動最小 | 歧義僅被規範化而未消除 | ★★ |

**裁定**：採方案 A，步驟更名為 **`FP-01` / `FP-02` / `FP-03` (Fast Phase)**；verifier 一併收緊為 `\b(FT|ET|RT)-\d{2}\b`。

### 2.2 G-1 模板路徑佔位符

- `build_deployment_map` 僅註冊檔案級鍵；目錄 URI `module://agents-workflow/assets/templates/` 於 Stage 2 不會命中 Tier 1，將落入 Tier 2 解析為模組運行端目錄。
- skill 項目之 `source_uri`（含 `SKILL.md`）已註冊於 deployment map，可依 target 正確解析。

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 A** | publisher 增註目錄級鍵，Standards 改用目錄佔位符 | 保留目錄語意 | 需改程式碼與測試 | ★★ |
| **方案 B** | Standards 改以 `__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__` 指向 development-sop（其 §6 模板指針已 target 感知） | 免改程式碼；單一真理集中於 development-sop | 間接一跳 | ★★★ |

**裁定**：採方案 B。

### 2.3 M-1 / 可見性

**裁定**：附掛 revision_log 未結案時**僅於 `plan archive` 攔截**；`plan status` **不標示**附掛修訂。

---

## 3. 架構設計與驗證 (Architecture & PoC)

- **架構方案 / 時序說明**：C-1、C-2、M-1、m-1 之共同根因為「缺乏單一真理之狀態解析」。建議抽出共用 `PlanStatusResolver`，以 `PlanVerifier.parse_plan_header` 解析之標頭狀態為唯一依據，Phase 判定改依各 P 檔標頭狀態而非檔案存在性，scanner / archiver / verifier 共用。
- **PoC 實作或 Benchmark 數據**：以探針腳本於臨時目錄構造計畫並直接呼叫 `PlanScanner` / `PlanVerifier` / `PlanArchiver`（2026-10-17 11:21 執行）：

| 探針 | 構造情境 | 實測結果 | 對應發現 |
| :---: | :--- | :--- | :--- |
| **H1** | Fast Track 標頭 `狀態：In Progress`，CHANGELOG 已提及計畫名 | verifier 0 錯誤 → archiver `success: True` 已搬移 | C-1 |
| **H2** | P01~P04 + P05 `In Progress` + P06 `Confirmed` | scanner `('Full Track', 'Testing/Phase 6')` | C-2 |
| **H3** | P01 + P07 `Completed` + revision_log `In Progress` | verifier 0 項 revision 錯誤；scanner `Completed` | M-1 |
| **H4** | RXX 模板僅替換 `[主題名稱]`、日期、模型 | 僅狀態值被攔截，`[調研主題/所屬功能]`、`[所屬主計畫 / 無]` 通過；scanner `('Unknown', 'Unknown')` | M-2、M-3 |

---

## 4. 調研結論與落地建議 (Conclusion & Recommendation)

- **推薦落地策略**：審計全部發現（C-1、C-2、M-1~M-11、m-1~m-10、G-1、D-1）納入 `sub_01_workflow_audit_remediation` 一併處理，依下列優先序排程：

| 優先 | 項目 | 方向 |
| :---: | :--- | :--- |
| P1 | C-1、C-2、m-1、M-5 | 共用 `PlanStatusResolver`；移除 FT 模板寫死之 `Completed`；定義各 P 檔狀態機並對齊 continue / auto / phase_06 |
| P2 | M-3、M-4、m-4、m-7、M-7、M-8、M-10、M-2、G-1、M-1 | Research Track 一等公民與命名統一；continue 判定表對齊；Revision 升級熔斷與重開語意；`FP-01/02/03` 更名與 verifier 收緊；佔位符自動推導；Standards 指針改向 development-sop；修正 plan_modes 之 verify 描述 |
| P3 | M-6、M-9、M-11、m-2、m-3、m-5、m-6、m-8、m-9、m-10、D-1 | 懸空引用、FT 模板守門區塊、P07 預設值、handoff 刪除時序、死代碼、詞彙統一、元數據同步 |

- **後續行動與 P00 銜接**：本報告為 `sub_01` 之 `P00_discuss.md` 前置依據；`P00` 需逐項收斂尚未裁定之規格選擇（命名規則、狀態機、Revision 熔斷條件等）後再進入 P01。

