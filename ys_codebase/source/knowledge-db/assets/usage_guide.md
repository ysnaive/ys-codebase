### 📦 Knowledge-DB 混合語意知識庫 (`knowledge-db` — AST 代碼切片檢索、調用圖譜與影響面分析)

- **① 模組定位與適用時機**：
  - 結合向量語意檢索、BM25 關鍵字匹配與 AST 語法樹解析，以最小 Token 開銷秒級定位文檔與程式碼切片（隨包導出 [`knowledge-db-search`](`__#{module://knowledge-db/assets/skills/knowledge-db-search/SKILL.md}__`) 技能）。
  - 當你需要探索未知程式碼、查詢文檔規範、追蹤函式上下游調用鏈或評估重構影響半徑時優先使用。
- **② 標準用法速查 (Golden Recipes)**：
  - **檢索架構與設計文檔 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ knowledge-db search "<查詢詞>" --space=docs --ftype=md -s`
  - **檢索業務源碼與符號 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ knowledge-db search "<查詢詞>" --space=source -s`
  - **追蹤上下游調用圖譜 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ knowledge-db callers <symbol> -s` / `python __${yscb.host://yscb.py}__ knowledge-db callees <symbol>`
  - **評估修改影響半徑 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ knowledge-db impact <symbol> --depth 2`
- **③ 隨包手冊語意連結**：
  - 深入探索完整過濾旗標與多空間檢索策略請按需唯讀查閱 [`knowledge-db 隨包手冊`](`__#{module://knowledge-db/README.md}__`)。
