# 計畫前置待辦來源清單 (Promoted TODOs)

> 主題：2026_11_01_1054_auto_plan_and_workflow_refinement  
> 建立日期：2026-11-01  
> 狀態：Active  
> 模型：Gemini 4 Argon (Low)  

---

## 立項待辦條目 (Promoted Items)

### [TODO-10] plan search 決策檢索權重強化、熱上下文恢復膠囊與人工規格 vs _auto.md 差異化反向回寫
- **建立日期**：2026-11-01
- **目標範疇**：`agents-workflow (searcher.py, scanner.py, status.py, verifier.py)`
- **備忘與解法要點**：1. 強化 plan search 對 P00/RXX/P07/[DR- 之排序權重、引入歷史歸檔時間衰減 (Time Decay) 並降權已歸檔之 P01~P04 過程檔；2. 修正 searcher.py search_drs 之 dedup_key 納入 relative_to(plan) 防止跨 sub_XX 誤刪、放寬無冒號 DR 正則、修正 search_full_text 保留 sub_XX 相對路徑，並為 plan search 新增 --full 與 --json 及左側截斷保尾顯示；3. 實作 plan status --resume 無 handoff 時之確定性熱恢復膠囊；4. 區分人工簽核 P02/P03 與 _auto.md 之反向回寫策略

### [TODO-13] compiler.py [DN-AW-03] 獨立標籤反引號剝離規則限縮，保留無錨點行內路徑變數外層反引號
- **建立日期**：2026-11-01
- **目標範疇**：`agents-workflow (compiler.py)`
- **備忘與解法要點**：修正 _replace_in_code_span：當 PROJECT_URI_EXACT_REGEX 未帶 anchor（純路徑變數而非 Markdown 連結）時保留展開後之外層反引號，避免下游 snippet 行內代碼路徑退化為純文字
