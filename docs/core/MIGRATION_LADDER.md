# 模組增量資料遷移與階梯調用手冊 (Migration Ladder Subsystem)

> 適用模組：`core`  
> 模組路徑：`source/core/core/engine.py`  
> 知識庫維度：維度 3（中觀專題手冊 Topic Docs）  
> 最後更新：2026-08-25  

---

## 1. 概念與背景

當模組跨次版本（`minor`）升級時（例如：從 `1.0.0.0` 升級至 `1.3.0.0`），模組儲存在 `storage://<mod>/` 或 `config://` 中的資料結構可能發生演進。
為了保證平滑過渡，YS-Codebase 引入了**增量遷移階梯調用引擎 (Incremental Migration Ladder)**。

---

## 2. 遷移腳本規範與目錄結構

模組開發者可在其源碼目錄中提供遷移腳本：

```text
source/<module>/
  └── scripts/
      └── migrations/
          ├── 1.1.x.py     # 升級至 1.1.x 時觸發
          ├── 1.2.x.py     # 升級至 1.2.x 時觸發
          └── 1.3.x.py     # 升級至 1.3.x 時觸發
```

### 腳本介面簽名
```python
def migrate(ctx: ExecutionContext) -> bool:
    """
    執行具體的遷移邏輯（如資料庫欄位轉換、配置檔案更新）。
    回傳 True 表示遷移成功，回傳 False 或拋出例外表示遷移失敗。
    """
    return True
```

---

## 3. 階梯調用原則

1. **逐級遞進調用**：
   - 跨多個 minor 升級時，引擎會**依序嚴格遞增執行每個階梯腳本**：
     $$\text{v1.0} \xrightarrow{\text{1.1.x.py}} \text{v1.1} \xrightarrow{\text{1.2.x.py}} \text{v1.2} \xrightarrow{\text{1.3.x.py}} \text{v1.3}$$
2. **缺腳本自動靜默跳過**：
   - 若某個中間版本未提供 migration 腳本（例如 `1.2.x.py` 不存在），系統視為無需資料轉換，自動跳過並繼續執行後續階梯。
3. **同 Major 鎖定原則**：
   - `yscb update` 預設限制在同一個 Major 內進行（`^current_version`）。
   - 若要跨 Major 升級，必須明確執行 `yscb install <mod>@<new_major>`。
4. **全原子 Snapshot 回滾防護**：
   - 升級開始前，引擎自動對 `.modules/`, `config/`, `storage/`, `yscb.config.json` 建立快照。
   - 若任何階梯的 `migrate()` 回傳 `False` 或拋出例外，升級立即中斷，並**100% 自動還原代碼、配置與持久化資料**。
