##### 知識庫 Search 效益評測 (knowledge-db: Search Efficiency & Ranking Quality)

- [ ] **總調用次數統計**：統計當前 Session 調用 `knowledge-db search` 總次數。
- [ ] **調用時機合理性**：是否在未知符號/架構探索時及時調用？有無過度濫用或應調用而漏調用？
- [ ] **效益性對比**：相較傳統 `grep_search` / `list_dir` / `view_file` 盲目翻找，估算節省之 Token、Turn 數與往返時間。
- [ ] **演算法有效性**：檢索結果對解決問題之實質貢獻度，以及高相關內容是否排名靠前 (Top 1~3)。

**📋 標定產出格式 (Standard Output Format)**：
```markdown
- **知識庫 Search 效益評測 (knowledge-db)**：
  - **調用統計**：共調用 `[X]` 次
  - **時機合理性**：`[合理 | 偏多/過度 | 偏少/漏調用]`（說明：`[簡要說明調用時機合理性]`）
  - **效益性對比 (vs. 傳統工具)**：
    - 傳統工具預估消耗：約 `[A]` Tokens / `[B]` 次往返翻找
    - `knowledge-db` 實際消耗：約 `[C]` Tokens / `[X]` 次檢索
    - 效益估算：節省約 `[A - C]` Tokens（提升約 `[N]%` 效率）
  - **演算法有效性與排名**：
    - Top 1~3 命中率：`[P]%`
    - 解題實質貢獻度：`[高 (關鍵代碼精確命中) | 中 (部分相關) | 低 (需二次搜尋)]`
    - 逐次檢索明細（可選）：
      1. `python yscb.py knowledge-db search '<query_1>'` ➔ 命中 Top `[N]`：`[file:line]` (`[有效/無效]`)
```
