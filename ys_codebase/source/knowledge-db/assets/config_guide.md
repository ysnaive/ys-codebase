### ⚙️ Knowledge-DB 混合語意知識庫設定與體檢 (`knowledge-db`)
<!-- yscb:ignore:begin -->
供 `/how-to-config-yscb` Step 1 自動驗證之體檢片段；編輯者註記於編譯時自動抹除。
<!-- yscb:ignore:end -->
- **① 組態項目與用途**：
  - **工作空間幾何範圍**：統一由 [`config/core/contribute.json`](`__#{config://core/contribute.json}__`) 宣告（`spaces.source.entries` 對齊本體業務空間，`exclude` 排除 `.modules/**`、`.venv/**` 等外部工具包黑盒）。
  - **空間檢索權重與同義詞庫**：[`config/knowledge-db/contribute.json`](`__#{config://knowledge-db/contribute.json}__`)（設定 `space_weights`、`thesaurus`、`aliases`、`related`）。
  - **團隊共享檢索與向量參數**：[`config/knowledge-db/config.project.json`](`__#{config://knowledge-db/config.project.json}__`)（混合檢索權重、模型名稱與 `jit_vector_timeout_ms`）；個人本機覆寫則放 `config.local://knowledge-db/config.local.json`（`.config.local/knowledge-db/config.local.json`）。
- **② 健康度檢查條件**：
  - `python __${yscb.host://yscb.py}__ knowledge-db status`：驗證已註冊空間 (`spaces`)、BM25 / Vector 索引覆蓋率與 `acked_ast_generation` 同步水位。
  - `python __${yscb.host://yscb.py}__ knowledge-db model status`：驗證本地嵌入模型 (Embedding Model) 已就緒。
- **③ 隨包設定手冊語意連結**：
  - 進階空間權重、同義詞配置與模型管理請按需唯讀查閱 [`knowledge-db 隨包手冊`](`__#{module://knowledge-db/README.md}__`)。
