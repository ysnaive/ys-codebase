# Contributes 擴充與依賴清冊 (`knowledge-db`)

本文件記錄 `knowledge-db` 模組對其他模組提供的擴充貢獻，以及本模組對外開放的擴充介面。

## 1. 對外貢獻清冊 (Contributes to Hosts)

### 1.1 `core.json` (宿主：`core`)
- **URI Schemes**:
  - `knowledge.storage://` -> `storage.local://knowledge-db/`（知識資料庫之語意 Bundle、模型權重與檢索索引儲存根目錄）
  - `knowledge.cache://` -> `cache://knowledge-db/`（知識資料庫快取與進程鎖根目錄別名）
- **Commands (`knowledge-db` / `kdb`)**:
  - `status`: 顯示各知識空間、索引健康度與快取統計資訊。
  - `index`: 增量掃描變更檔案、提取語意結構並更新混合檢索索引。
  - `search`: 執行跨空間混合語意檢索並即時提取高密度代碼或文檔切片。
  - `clean`: 清除指定或全部知識空間之索引快取與重置變更游標。
  - `model`: 管理向量嵌入推論模型（`status` / `download`）。
- **Hooks**:
  - `dev`: `on_test_setup` (`scripts/hook.dev.py`) — 沙盒測試初始化時準備 `.storage.local/knowledge-db/` 與 `.cache/knowledge-db/` 目錄結構。
  - `server`: `on_Context_build` (`scripts/hook.server.py`) — 常駐服務啟動時掛載單例 `KnowledgeEngine` 並預熱索引。
  - `core`: `on_file_space_changed` (`scripts/hook.core.py`) — 監聽 `core.space` 空間指紋變更事件，透過 `consume_diff` 執行熱增量索引修補。

---

## 2. 開放擴充點清冊 (Extension Schema: `_format.json`)

其他模組可透過 `contributes/knowledge-db.json`（或專案於 `ys_codebase/config/knowledge-db/contribute.json`）向本模組注入以下擴充：

- **`space_weights`**: 定義各邏輯空間之檢索加權係數（`dict[str, float]`，權重值須 `> 0`）。空間幾何範圍統一向 `core` 模組 (`core.space`) 註冊，語法與語言擴充統一向 `ast` 模組註冊。
