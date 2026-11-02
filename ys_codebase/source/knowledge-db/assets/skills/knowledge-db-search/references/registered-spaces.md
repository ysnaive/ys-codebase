<!-- yscb:ignore:begin -->
維護者註記：本參考檔透過 Stage 1 `KNOWLEDGE_DB_SPACE` 計算錨點動態注入已註冊空間清單，供 Agent 在全空間檢索無法精準取得目標資料或需排除跨空間雜訊時按需讀取。
<!-- yscb:ignore:end -->
# 已註冊之知識庫空間清單與過濾指南 (Registered Knowledge Spaces)

預設情況下，`knowledge-db search` 會自動對所有已註冊空間之聯集執行檢索並依 `space_weights` 加權排序，日常查詢無須顯式指定 `--space`。唯有當預設檢索結果混雜過多他空間檔案、或需強制鎖定特定領域（如僅查 `source` 源碼或僅查 `docs` 文檔）時，才使用 `--space=<name>` 精確限制檢索範圍：

`__@{KNOWLEDGE_DB_SPACE}__`

