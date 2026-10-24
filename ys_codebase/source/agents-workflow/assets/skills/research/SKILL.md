---
name: research
description: 針對高複雜度技術命題與多候選方案執行優劣權衡 (Pros & Cons)、資源代價分析與架構可行性驗證，產出 R{NN}_{topic}.md 專題調研報告與三大流轉出口建議卡。觸發情境：輸入 /research 或 /Research、要求針對未知技術選型、演算法可行性或跨平台架構進行深度調研並產出評估報告 (technical research / trade-off evaluation)。排除情境：方案已明確之日常功能編碼實作（改用 development-sop）、開發測試中途之單純錯誤排查（改用 discuss）。
---

# 深度技術調研工作流 (Research)

本工作流用於高複雜度、新技術選型、演算法可行性或架構演進之深度論證與客觀對比。執行規範遵循 [development-sop](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`)。

---

## 核心原則與雙軌生命週期

1. **僅被動觸發（Explicit / Requested Only）**：獨立前置調研僅在開發者提出探討需求或下達顯式指令（如 `/Research [主題]` 或 `/research [主題]`）時進行，嚴禁在一般功能開發中途擅自發起。
2. **雙軌生命週期（記憶體收斂 -> 實體落檔）**：
   - **獨立前置調研**：未開立計畫前，隨問隨答與方案對比保留於對話與快取中，不主動在磁碟建檔。
   - **正式固化建檔**：開發者指示立項或需正式留痕時，寫入計畫目錄下的 `R{NN}_{topic}.md`（如 `R01_architecture_reference.md`）。
3. **免除死板模板束縛與客觀證據導向**：依標準模板 [`RXX_research_report.md`](`__#{module://agents-workflow/assets/templates/RXX_research_report.md}__`) 建立，維持標準元數據標頭，正文依主題自由排版論述，並聚焦客觀架構取捨（Trade-offs）與數據驗證。
4. **標準命名前綴**：調研報告統一採用 `R{NN}_{topic}.md`。

---

## 執行步驟

開始執行時，請依序遵循以下檢核步驟：

```markdown
/Research 專題調研檢核表：
- [ ] 步驟 1：盤點核心痛點、調研目標與評估維度（若計畫目錄未建立則依 JIT 原則初始化）
- [ ] 步驟 2：針對候選方案進行深度技術剖析、Pros/Cons 對比與 PoC/數據驗證
- [ ] 步驟 3：讀取 RXX_research_report.md 模板，產出 R{NN}_{topic}.md 並更新 changelog.md
- [ ] 步驟 4：呈遞極簡調研卡與三大出口分流建議，並立即 End Turn 等待裁決
```

### 步驟 1：盤點核心調研維度
與開發者梳理本次調研攻堅的具體核心問題、評估指標與技術邊界。

---

### 步驟 2：方案深度探討與客觀權衡 (含 Subagent 支柱一委派協定)
作為架構顧問展開開放式探討：
- 橫向比對至少 2~3 個具代表性的業界成熟實踐與候選方案。
- 客觀分析候選方案優缺點 (Pros & Cons)、資源代價與潛在坑點。
- 結合專案現況給出客觀分析，嚴禁主觀吹捧。
- **[!] 支柱一：唯讀廣域探索隔離 (Pillar 1 Delegation)**：
  - **適用**：調研涉及廣泛檢索多個外部模組、演算法實作或海量文檔時，可派發唯讀 Subagent（支援單一或平行探索，嚴守單層星型拓撲，Subagent 禁碰 `plans/`）。
  - **極簡回傳約束**：Subagent 僅回傳 150~300 Tokens 結構化濃縮摘要（關鍵證據、精確檔案行號與方案優劣對比），嚴禁代碼全文傾倒回主視窗。
  - **降級機制**：若運行環境不支援子代理，自動降級為主視窗內聯搜尋閱讀。

---

### 步驟 3：產出專題調研報告 (`R{NN}_{topic}.md`)
若需正式落檔，讀取標準模板 [`RXX_research_report.md`](`__#{module://agents-workflow/assets/templates/RXX_research_report.md}__`)，填寫真實標頭與 `> 模型：`（依模型紀錄規則）後落檔（獨立調研計畫須伴隨 `P00_discuss.md` 與 `changelog.md`）：
1. 標準元數據標頭（含 `> 模型：`）。
2. 背景痛點與調研目標。
3. 候選方案評估矩陣 (Candidate Options Matrix)。
4. 關鍵維度深入分析（架構圖、PoC 驗證或 Benchmark 數據）。
5. 客觀結論與推薦落地方案。

`__@{RESEARCH_AGENTS_GUIDE}__`

---

### 步驟 4：呈遞極簡調研卡與三大出口分流 (強制 End Turn)

對話 Session **嚴禁全文重複、圖表傾倒或代碼傾倒**，強制僅呈遞以下極簡調研卡，並**立即 End Turn 等待確認**：

```markdown
### 🔬 R01 調研報告已落檔
- **產出文件**：[R01_{topic}.md](__${project://plans}__/{plan_name}/R01_{topic}.md)、[changelog.md](__${project://plans}__/{plan_name}/changelog.md)
- **調研主題**：[1 行調研核心命題]
- **調研結論**：[1~2 行方案選型評估結論 / 推薦採納方案]
- **推薦出口**：
  1. 出口 ① 立即實作：轉入 [/NewPlan](`__#{module://agents-workflow/assets/skills/new-plan/SKILL.md}__`) 或原地追加 P01~P07 升級實作計畫
  2. 出口 ② 路線圖儲備：轉入 [Roadmap](`__#{module://agents-workflow/assets/skills/roadmap/SKILL.md}__`) 納入長期演進儲備（日後以 `roadmap promote` 消耗立項）或轉入 [/Todo](`__#{module://agents-workflow/assets/skills/todo/SKILL.md}__`) 記錄微觀待辦
  3. 出口 ③ 放棄結案：方案不可行或成本過高，記錄原因後於調研報告標記 Concluded 登記結案
- **待確認事項**：請問是否採納此結論，並選擇何種流轉出口？
```

> [!IMPORTANT]
> **出口拍板狀態閉環**：開發者拍板任一出口（①、②、③）時，均須先將 `R{NN}_{topic}.md` 標頭狀態更新為 `Concluded` 再執行流轉；出口 ③ 同步將 `P00_discuss.md` 標記為 `Confirmed` / `Completed`。

---

## 常見踩坑指南 (Gotchas)

- **切勿在對話視窗直接貼出數百行報告取代落檔**：正式調研成果必須寫入 `R{NN}_{topic}.md` 實體檔案（SSOT），對話僅輸出上方摘要卡片。
- **未獲開發者選定出口前切勿自行展開 `P01` 實作**：調研結束後有三大可能出口，必須等待開發者拍板選擇出口 ① 後，才能啟動 `Phase 01` 規格轉譯。
