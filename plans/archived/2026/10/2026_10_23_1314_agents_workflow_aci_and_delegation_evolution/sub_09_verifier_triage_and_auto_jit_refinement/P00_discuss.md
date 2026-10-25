# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：PlanVerifier 缺失率分流處方、確定性標頭自癒、階段前瞻提示與 /auto 兩階段 JIT 讀模板瘦身 (sub_09_verifier_triage_and_auto_jit_refinement)  
> 建立日期：2026-10-25  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (High)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：基於本 Session 實機執行新版 `/auto`（`sub_08`）之歷史軌跡 (`transcript.jsonl`) 分析成效，針對跨 Context 壓縮失憶與 `plan verify` 報錯引發之探索繞路問題，將拍板之 5 項優化點（#1 缺失率分流處方、#2 下一階段前瞻提示、#3 `auto/SKILL.md` 拔除內聯骨架表改採寫檔前 JIT 讀模板、#5 確定性 Header 自動自癒、#6 支柱二 Phase 5 實作子代理量化門檻）直接作為 `sub_09` 立項。
- **核心目標**：
  1. **`auto/SKILL.md` 瘦身與兩階段 JIT 讀模板 (#3)**：拔除 `auto/SKILL.md` §3 內聯骨架速查表（本體瘦身 ~45% 並消除與 `templates/P0X.md` 之雙重維護），改為「免讀肥大的 `phase_01~05.md`（省 8.7K chars），但於動筆寫 `P01~P04`（Batch A）前平行讀取 `.agents/.yscb/templates/P01~P04.md`，並於完成 Phase 5 編碼測試後、動筆寫 `P05~P06`（Batch B）前平行讀取 `P05_task.md` 與 `P06_test_plan.md`（僅 1.2K chars）」，確保最新模板與完整表格欄位永遠位於 Context 最末端，100% 免疫長對話壓縮失憶。
  2. **`auto/SKILL.md` 量化支柱二（Phase 5 實作子代理）觸發門檻 (#6)**：明確定義當 `P04` 規劃涉及 **跨 $\ge 5$ 個檔案修改/整併、或預估需讀改 $> 1,500$ 行代碼** 時，推薦委派 `self` 實作子代理隔離執行 `TASK-XX` 並回傳測試結果，保護主對話 Context 免於過早觸發壓縮。
  3. **`PlanVerifier` 確定性環境標頭無損自癒 (#5)**：於 `verifier.py` 檢核管線中，當主體檔案存在且僅缺少 **100% 確定性環境標頭欄位**（`> 建立日期：` 預設當日、`> 所屬主計畫：` 二級子計畫自動取父目錄名、`> 功能名稱：` 自動繼承同目錄既有 `P00/P01` 或取目錄名）時，自動無損補入檔案頂部 Blockquote 並記錄於 `report.header_healed`，免去為單行標頭多耗費一輪 `edit_file`。
  4. **`PlanVerifier` 缺失率速評分流 (`QUICK_PATCH` vs `FULL_REWRITE`) 與原始標題骨架處方 (#1)**：
     - 保留標準模板之**原始 Markdown 二/三級標題行**（及緊隨之表格表頭列），廢除在報錯中單獨吐出正規化去標點小寫字串（如 `'人工/ux驗證checkpoint'`）。
     - 計算檔案章節缺失率 $R_{\text{section}} = \frac{\text{缺失章節數}}{\text{模板必備章節數}}$：
       - 當 $0 < R_{\text{section}} < 50\%$ 時，輸出 `[TRIAGE: QUICK_PATCH (缺失 M/N 章節)]`，直接內聯印出缺失章節之原始 Markdown 標題與表頭骨架供 `edit_file` 原地補齊。
       - 當 $R_{\text{section}} \ge 50\%$ 時，輸出 `[TRIAGE: FULL_REWRITE (缺失 M/N 章節，屬盲寫結構偏離)]`，阻斷翻找歷史計畫目錄抄襲，直接於終端內聯印出該模板完整原始標題骨架並指引讀取 `.agents/.yscb/templates/<tmpl>.md` 重寫。
  5. **`plan verify` 通過時輸出下一階段前瞻領航提示 (`Forward-Looking Gate Hint`) (#2)**：當單一目標計畫檢核 `PASSED` 且尚未結案（例如處於 `P02`、`P04`、`P06`）時，結合 `PlanStatusResolver.resolve_next_action` 於報告底部輸出 `[NEXT PHASE GATE]`（含下一階段目標檔名、模板路徑 `.agents/.yscb/templates/P0X_*.md` 與必備章節清單），使下一輪推進（如 `P06` 通過後進入 `P07`）時所需規格直接位於最新 Context 末端。
- **邊界排除 (Explicitly Excluded)**：
  - **不採納方案 #4（`git diff` 檢測既有檔案 `> 模型：` 篡改）**：因計畫執行中途（未結案 commit 前）檔案多屬 untracked 狀態，`git diff HEAD` 在實務中無效，故排除。
  - **不考慮超大型企業級跨 Session 自動拆解或進階 Umbrella 編排**：維持輕量實用定位。
- **架構影響範圍**：
  - `ys_codebase/source/agents-workflow/assets/skills/auto/SKILL.md`
  - `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py`
  - `ys_codebase/source/agents-workflow/scripts/cli.py`
  - `ys_codebase/source/agents-workflow/tests/test_plans_toolchain.py` & `test_compiler.py`
  - `docs/agents-workflow/user_guide.md` & `docs/agents-workflow/DESIGN_NOTES.md`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 拔除 `auto/SKILL.md` 內聯骨架表，改採兩階段 JIT 讀模板（免讀 `phase_01~05.md`）**：
  - 經實測數據驗算，`references/phase_01~05.md` 合計 8,675 chars 為真正冗餘來源，而 `.agents/.yscb/templates/P01~P06.md` 單檔僅 505~1,088 chars 且含完整 Markdown 表格表頭。改為 Batch A（寫 `P01~P04` 前）與 Batch B（Phase 5 測試完成、寫 `P05~P06` 前）分兩批按需平行讀取模板，既讓 `auto/SKILL.md` 瘦身 ~45% 並回歸模板 SSOT，又確保 `P05/P06` 模板永遠在壓縮後的 Context 最末端。
- **[P00:DR-02] `PlanVerifier` 診斷升級為「確定性標頭自癒 + 缺失率分流 (`QUICK_PATCH` / `FULL_REWRITE`) + 前瞻提示 (`NEXT PHASE GATE`)」**：
  - 透過自動補齊 100% 確定性環境標頭（建立日期、所屬主計畫、功能名稱）、以章節缺失率 $50\%$ 為界分流局部修補與整份重寫並附帶原始 Markdown 標題骨架，以及在 `PASS` 時預告下一階段（如 `P06` $\to$ `P07`）模板與章節，徹底根除失憶盲寫後的無效探索。

---

## 3. 開放議題與確認紀錄

- 5 項核心優化方向已由開發者於立項討論中明確拍板（`Confirmed`）。

