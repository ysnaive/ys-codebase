### ⚙️ AST 語法樹與呼叫拓撲設定與體檢 (`ast`)
<!-- yscb:ignore:begin -->
供 `/how-to-config-yscb` Step 1 自動驗證之體檢片段；編輯者註記於編譯時自動抹除。
<!-- yscb:ignore:end -->
- **① 組態項目與用途**：
  - **自訂或覆寫語言解析器**：[`config/ast/contribute.json`](`__#{config://ast/contribute.json}__`)（或 Donor 模組 `contributes/ast.json`），透過 `languages.<id>` 宣告 `"mode": "tree_sitter"`（指定 `grammar` 與 `.scm` `query_file`）或 `"mode": "custom"`（指定 `parser_entry`）。
  - **跨模組空間來源**：自動讀取 [`config/core/contribute.json`](`__#{config://core/contribute.json}__`) 與各模組貢獻之 `core.space` 已註冊空間並維護獨立游標 `cursors/ast.json`。
- **② 健康度檢查條件**：
  - `python __${yscb.host://yscb.py}__ ast status`：驗證已註冊空間之 `ast_generation`、符號總數、呼叫圖譜節點/邊數，以及 `parser_load_errors` 是否為空。
  - `python __${yscb.host://yscb.py}__ ast outline __${yscb.host://yscb.py}__`：驗證單檔 AST 解析與結構大綱輸出正常。
  - **常見異常修復**：若自訂解析器顯示於 `parser_load_errors`，修正 `config/ast/contribute.json` 後執行 `python __${yscb.host://yscb.py}__ reload` 與 `python __${yscb.host://yscb.py}__ ast clean` 重建快照。
- **③ 隨包設定手冊語意連結**：
  - 進階方言隔離與自訂解析器注入規範請按需唯讀查閱 [`ast 隨包手冊`](`__#{module://ast/README.md}__`)。
