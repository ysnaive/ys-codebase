# Phase 0: 需求討論與邊界釐清 (P00 Discuss Guide)

本手冊定義 Full Track / Research 計畫 Phase 0 階段之角色職責、討論防呆與 JIT 延遲建檔規範。

```markdown
Phase 00 執行檢核表：
- [ ] 1. 執行「五維度防放水反詰探針」掃描（既有資產查重復用、預設值隱性副作用、生命週期與拆卸冪等性、跨切面不變量、顯式排除範圍），將真實風險轉化為精煉問題反詰確認
- [ ] 2. 評估變更規模並建議計畫分流模式（Full Track / Fast Track / Umbrella / Research / Revision）
- [ ] 3. 讀取 P00_discuss.md 模板落檔（狀態設為 Discussing 或 Confirmed）並同步記錄 changelog.md
- [ ] 4. 呈遞 P00 狀態卡並立即 End Turn 等待開發者拍板
```

---

## 1. 核心定位与五維度防放水反詰協議 (Adversarial Clarification Protocol)

- **角色定位**：扮演「挑刺審計員（Adversarial Clarifier）」與架構把關者，主動探測隱性預設副作用與既有資產重疊度，防止在 `/auto` 自動推進軌下將模糊邊界或重複造輪子放大為巨額返工債。
- **零臆測防呆**：
  - 面對抽象或寬泛指令（例「優化某模組」），**嚴禁主動發散腦補具體需求清單**；必須反問「請問具體的優化目標與期望範圍為何？」。
  - 唯有在開發者明確指示「幫我分析/評估」時，方可開展候選方案與架構對比。
- **[!] 第一階護欄：`P00` 鎖定 `Confirmed` 前之五維度防放水反詰探針（5-Axis Red-Team Probes）**：
  在將 `P00_discuss.md` 定案為 `Confirmed` 前，Agent 強制依序掃描以下五個正交維度（僅將掃描出**真實風險或歧義**之維度壓縮為附帶推薦預設解的高密度選擇題向開發者反詰，收斂後固化為 `[P00:DR-XX]`）：
  1. **軸一：既有組件重疊與復用查證 (`Reuse Discovery Before Invention`)**：凡涉及新增控制項、資料結構、序列化器或底層服務，必須先以 `knowledge-db search` 查重，確認是否可復用或泛型化既有組件；未附具正交職責差異證明前，嚴禁放行與既有組件功能重疊之平行實作。
  2. **軸二：預設值與隱性行為副作用 (`Default & Implicit Side-Effect Probe`)**：檢驗新增旗標、自動補值或全域註冊若納入 `Default` 行為，是否會對無頭測試、沙盒隔離或一般輕量呼叫端造成跨期狀態污染。
  3. **軸三：生命週期、卸載與異常逆向路徑 (`Lifecycle & Teardown Probe`)**：檢驗動態掛載、熱重載、取消或銷毀時，資源釋放順序與失敗回退是否具備冪等性與異常安全保證。
  4. **軸四：全局座標／時鐘／ID 等跨切面不變量 (`Cross-Cutting Invariant Probe`)**：檢驗變更是否觸及物理／邏輯單位轉換、時間軸推進或跨端序列化識別碼，防止將全局契約切碎於局部修補。
  5. **軸五：顯式排除與延後邊界 (`Explicit Out-of-Scope Lock`)**：強制將易引發範疇蔓延之相鄰特性明列於 `P00_discuss.md` 之「邊界排除 (Explicitly Excluded)」，杜絕實作階段偷渡未授權擴充。

---

## 2. JIT 延遲建檔與分流守門

1. **對話先行**：輸入 [/new-plan](`__#{module://agents-workflow/assets/skills/new-plan/SKILL.md}__`) 時不立即建立實體目錄，先於對話中進行深入探討。
2. **確立分流伴隨建檔**：與開發者充分討論並確認分流類型後，伴隨建立計畫目錄並產出對應初始文件（`P00_discuss.md`、`fast_track_plan.md` 或 `revision_log.md`）與 `changelog.md`。
3. **調研或討論無痛轉入修訂**：若前置討論 (`P00`) 或調研 (`R{NN}_{topic}.md`) 收斂後確認僅涉及非業務邏輯之 UI/UX/DX、參數或文檔微調，可直接於同計畫目錄建立 `revision_log.md` 進入修訂計畫。
4. **調研無痛升級**：若需求過於複雜或未知技術過多，主動建議先入調研計畫（產出 `R{NN}_{topic}.md` 後可無縫升級）。
5. **Umbrella 子計畫立項登記**：於 Umbrella 下開立 `sub_XX` 時，同步登記於父目錄 `umbrella_overview.md` §2 子計畫矩陣並記錄於主目錄 `changelog.md`；首個子計畫啟動時主計畫標頭轉為 `In Progress`。

---

## 3. `P00_discuss.md` 產出核心規範

- **背景與動機**：記錄問題痛點、系統現狀與業務價值。
- **需求釐清清單**：記錄問答記錄，確保雙方對邊界達成 100% 共識。
- **架構影響範圍**：預判涉及之模組、資料流轉向與介面相容性。
- **關鍵架構決策 ([P00:DR-XX])**：記錄已拍板定案之核心技術方案。

---

`__@{PHASE00_AGENTS_GUIDE}__`

---

## [!] 4. Phase 0 結束 Checkpoint

- **極精簡 Session 回覆格式**：產出 `P00_discuss.md` 與 `changelog.md` 後，對話中**嚴禁全文重複或冗長轉述**，強制僅呈遞以下極簡卡片：
  ```markdown
  ###  P00 需求討論與分流確認
  - **產出文件**：[P00_discuss.md](`__${project://plans}__/{plan_name}/P00_discuss.md`)、[changelog.md](`__${project://plans}__/{plan_name}/changelog.md`)
  - **推薦分流**：[Full Track | Fast Track | Umbrella | Revision | Research]
  - **核心決策**：[1~2 行關鍵架構定案或主要 [P00:DR-XX]]
  - **待確認事項**：請問是否同意此分流並推進至下一階段？
  ```
- **立即 End Turn 等待確認**：嚴禁跨階段連續產出。

