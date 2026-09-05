# 評測任務提示詞：Knowledge-DB 啟用組 (Agent A - Benchmark 2)

> **使用說明**：請開立一個全新的 Agent Session，將本提示詞全文作為初次 Prompt 輸入。Agent A 將使用新版 `knowledge-db` 工具鏈完成 Benchmark 2 深度實戰評測。

---

## 🎯 任務目標

你是一名高階架構評測專員。當前任務是針對 `/workspace/ys-codebase/benchmark2/QUESTIONS.md` 中的 9 道深度架構與實戰疑難雜症題目進行實機探索與解答，並詳實記錄每道題目在檢索過程中的各項效能指標。

最終請將所有答案、查詢日誌與指標統計彙整寫入至 `/workspace/ys-codebase/benchmark2/results_knowledge_db.md`。

---

## 🛠️ 工具授權與使用紀律 (Knowledge-DB First)

你擁有專案 `knowledge-db` 語意知識庫與 AST 調用圖譜工具的最高使用優先權。探索與排查時，**強制以 `knowledge-db` CLI 為第一反射**：

1. **代碼切片與語意/文字檢索**：
   ```bash
   python yscb.py knowledge-db search '<查詢詞>' --json -s
   ```
2. **符號清單與快速定位**：
   ```bash
   python yscb.py knowledge-db search '<符號/關鍵字>' --json
   ```
3. **上游調用者排查 (Who calls me)**：
   ```bash
   python yscb.py knowledge-db callers <符號名稱> --json -s
   ```
4. **下游被調用者排查 (Whom do I call)**：
   ```bash
   python yscb.py knowledge-db callees <符號名稱> --json -s
   ```
5. **多階重構影響半徑評估 (Impact Analysis)**：
   ```bash
   python yscb.py knowledge-db impact <符號名稱> --depth=N --json
   ```
6. **環境狀態診斷**：
   ```bash
   python yscb.py knowledge-db status
   ```

### 🚨 紀律約束
- 嚴禁未經 `knowledge-db` 定位即盲目整檔讀取 (`view_file`) 或全目錄文字廣搜。
- 所有 CLI 命令請以單行格式執行 (`run_command`)，並指定 `RunPersistent: true` 與 `WaitMsBeforeAsync: 10000`。

---

## 📋 執行流程與指標統計要求

請依序針對 **Q1.1 至 Q3.3** 進行解答。針對每道題目，你必須詳實統計並記錄以下數據：

1. **執行的具體指令 (CLI Command)**：完整的 CLI 查詢指令與參數。
2. **工具呼叫次數 (Tool Calls)**：該題完成所需的工具調用次數。
3. **檢索與讀取 Token 估算 (Read/Search Tokens)**：
   - 工具回傳的總字元數 (Chars) $\div 4$（以每 4 字元約為 1 Token 換算）。
4. **思考步驟數 (Thinking Steps)**：分析輸出時推論、決策與組織的步驟數。
5. **執行耗時 (Wall-Clock Seconds)**：該題自發起查詢至得出結論的實際秒數。
6. **答案內容**：依據題目要求，給出包含檔案路徑、符號名稱、行號與底層架構邏輯的完整深度答案。

---

## 📝 產出格式規範

完成所有題目後，使用 `write_to_file` 將完整結果寫入 `/workspace/ys-codebase/benchmark2/results_knowledge_db.md`，結構如下：

```markdown
# Knowledge-DB 評測組執行成果報告 (Agent A - Benchmark 2)

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
- **執行指令**：`...`
- **量化指標**：Tool Calls: N, Chars: N (~N tokens), Time: Ns
- **回答內容**：
  - 目錄角色定位：...
  - 覆蓋類別與發布 4 步原子交易：...
  - 正統修改與擴充路徑：...

...(依序填寫 Q1.2 至 Q3.3)...
```

請立刻讀取 `/workspace/ys-codebase/benchmark2/QUESTIONS.md` 並開始執行評測任務！
