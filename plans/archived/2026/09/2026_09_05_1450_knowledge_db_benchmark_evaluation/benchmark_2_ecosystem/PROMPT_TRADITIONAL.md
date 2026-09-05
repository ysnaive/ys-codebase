# 評測任務提示詞：傳統工具對照組 (Agent B - Benchmark 2)

> **使用說明**：請開立一個全新的 Agent Session，將本提示詞全文作為初次 Prompt 輸入。Agent B 將僅使用傳統搜尋工具（grep/find/view_file）完成 Benchmark 2 深度實戰評測。

---

## 🎯 任務目標

你是一名高階架構評測專員。當前任務是針對 `/workspace/ys-codebase/benchmark2/QUESTIONS.md` 中的 9 道深度架構與實戰疑難雜症題目進行實機探索與解答，並詳實記錄每道題目在檢索過程中的各項效能指標。

最終請將所有答案、查詢日誌與指標統計彙整寫入至 `/workspace/ys-codebase/benchmark2/results_traditional.md`。

---

## 🚫 工具限制與授權邊界 (Traditional Tools Only)

在本次評測中，你作為對照組，**嚴格限制僅能使用傳統程式碼探索工具**：

### 🚨 絕對禁止事項
- **絕對嚴禁執行任何 `knowledge-db` 指令**（例如 `python yscb.py knowledge-db ...`）。
- **絕對嚴禁直接讀取 `.cache/knowledge-db/` 下的快取檔案或索引資料庫**。

### ✅ 允許使用的傳統工具
1. **Agent 原生檔案與搜尋工具**：
   - `grep_search`（文字或正則搜尋）
   - `view_file`（檢視指定檔案內容）
   - `list_dir`（列出目錄結構）
2. **標準 Linux Shell 指令 (透過 `run_command`)**：
   - `grep -rn "..." path/`、`find path/ -name "..."`、`cat`、`head`、`tail` 等常用文字搜尋與檢視指令。

---

## 📋 執行流程與指標統計要求

請依序針對 **Q1.1 至 Q3.3** 進行解答。針對每道題目，你必須詳實統計並記錄以下數據：

1. **執行的具體工具或指令**：所有使用的 `grep_search`, `view_file` 或 Shell 命令清單。
2. **工具呼叫次數 (Tool Calls)**：該題完成所調用的工具總次數（每次 `grep_search`、`view_file`、`run_command` 各算 1 次）。
3. **檢索與讀取 Token 估算 (Read/Search Tokens)**：
   - 工具回傳的總字元數 (Chars) $\div 4$（以每 4 字元約為 1 Token 換算；包括 grep 匹配輸出與 view_file 讀取的內文字元總和）。
4. **思考步驟數 (Thinking Steps)**：分析輸出時推論、決策與組織的步驟數。
5. **執行耗時 (Wall-Clock Seconds)**：該題自發起查詢至得出結論的實際秒數。
6. **答案內容**：依據題目要求，給出包含檔案路徑、符號名稱、行號與底層架構邏輯的完整深度答案。

---

## 📝 產出格式規範

完成所有題目後，使用 `write_to_file` 將完整結果寫入 `/workspace/ys-codebase/benchmark2/results_traditional.md`，結構如下：

```markdown
# 傳統工具對照組執行成果報告 (Agent B - Benchmark 2)

## 📊 效能總結儀表板 (Summary Dashboard)

| 題號 | 難度分級 | 工具次數 (Calls) | 讀取字元 (Chars) | 預估 Tokens | 耗時 (秒) | 思考步驟 | 答案完整度 (0-100%) |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| Q1.1 | Level 1 (機制排查) | | | | | | |
| Q1.2 | Level 1 (機制排查) | | | | | | |
| Q1.3 | Level 1 (機制排查) | | | | | | |
| Q2.1 | Level 2 (架構運作) | | | | | | |
| Q2.2 | Level 2 (架構運作) | | | | | | |
| Q2.3 | Level 2 (架構運作) | | | | | | |
| Q3.1 | Level 3 (疑難雜症) | | | | | | |
| Q3.2 | Level 3 (疑難雜症) | | | | | | |
| Q3.3 | Level 3 (疑難雜症) | | | | | | |
| **總計** | **Total** | **N** | **N** | **N** | **N s** | **N** | **Avg: N%** |

---

## 📝 各題詳細解答與執行日誌

### Q1.1 為什麼手動修改 .agents/ 內的 workflow 檔案會被覆蓋重置？
- **執行指令/工具**：`grep_search(...)` / `view_file(...)`
- **量化指標**：Tool Calls: N, Chars: N (~N tokens), Time: Ns
- **回答內容**：
  - 目錄角色定位：...
  - 覆蓋類別與發布 4 步原子交易：...
  - 正統修改與擴充路徑：...

...(依序填寫 Q1.2 至 Q3.3)...
```

請立刻讀取 `/workspace/ys-codebase/benchmark2/QUESTIONS.md` 並開始執行評測任務！
