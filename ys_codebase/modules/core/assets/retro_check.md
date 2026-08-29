##### CLI 指令 Default-Deny 守門查核 (core: CLI Execution & Safety Guardrails)

Agent 檢視當前 Session 執行的所有 CLI 指令，核對是否符合 `AgentsCliGuild.md` 推薦清單（**採「異常過濾呈遞」原則，僅詳列不合規項目**）：

- [ ] **CLI 查表合規**：檢查執行的每一個 `python yscb.py` 指令是否符合 `AgentsCliGuild.md` 推薦情境。
- [ ] **Default-Deny 守門**：是否有未授權執行未列指令或命中 `🚨 絕對禁止/不適用情境` 之情事。

**📋 標定產出格式 (Standard Output Format)**：
```markdown
- **CLI Default-Deny 守門查核 (core)**：
  - **狀態**：`[✅ CLI 指令全數合規 (共調用 X 次，0 違規) | ⚠️ 發現 Y 項違規/未授權調用]`
  - **不合規指令與文檔根因溯源**（若有）：
    - **違規指令**：`python yscb.py <command>`
    - **違規原因**：`[未列於推薦表 / 命中禁止情境：...]`
    - **文檔根因溯源**：閱讀 `[檔案路徑#Lxx]` 中的 [章節/描述]，延伸做出了 [錯誤調用]。
```
