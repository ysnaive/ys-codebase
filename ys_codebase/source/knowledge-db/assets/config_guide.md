### ⚙️ Knowledge-DB 混合語意知識庫設定與體檢 (`knowledge-db`)

- **① 組態項目與用途（雙層組態分流與三位一體對齊）**：
  - **團隊共享空間宣告**：[`config/knowledge-db/contribute.json`](`__#{config://knowledge-db/contribute.json}__`)（核心配置！`spaces.source.include` 必須與 `project_role.md` 的「本體業務空間」一致，`exclude` 必須排除 `.modules/**`、`.venv/**`、`node_modules/**` 等外部工具包黑盒）。
  - **團隊共享檢索參數**：[`config/knowledge-db/config.project.json`](`__#{config://knowledge-db/config.project.json}__`)（混合檢索權重、分塊大小與模型設定）；個人本機模型快取路徑覆寫則放 `config/knowledge-db/config.local.json`。
- **② 健康度檢查條件（供 Step 1 自動驗證）**：
  - `python __${yscb.host://yscb.py}__ knowledge-db status`：驗證已註冊空間 (`spaces`)、各空間已索引檔案/切片數與資料庫健康度。
  - `python __${yscb.host://yscb.py}__ knowledge-db model status`：驗證本地嵌入模型 (Embedding Model) 已就緒。
  - **常見異常修復**：若 `source` 空間未對齊第一方源碼目錄，更新 `config/knowledge-db/contribute.json` 後執行 `python __${yscb.host://yscb.py}__ reload` 與 `python __${yscb.host://yscb.py}__ knowledge-db index` 更新索引。
- **③ 隨包設定手冊語意連結**：
  - 進階空間配置語法、AST 語言支援與模型管理請按需唯讀查閱 [`knowledge-db 隨包手冊`](`__#{module://knowledge-db/README.md}__`)。
