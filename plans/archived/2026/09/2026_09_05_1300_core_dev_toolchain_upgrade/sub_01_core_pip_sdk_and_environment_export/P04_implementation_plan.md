# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：core_pip_sdk_and_environment_export  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-04 在 API 規格書中有對應介面
- [x] **邊界防護**：EC-01 ~ EC-03 具備防禦性型態校驗與安全回退
- [x] **依賴純淨**：符合 NFR-01 與 NFR-02 指標約束（純標準庫零新依賴）

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `source/core/README.md` | Modify | 補充 `PipManager` SDK 與公開微環境介面調用範例 |
| **專題手冊** | `docs/core/pip_environment.md` | Modify | 記錄 PipManager SDK 導出契約與相依性正規化規範 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | Modify | 登記 DN-08 Pip SDK 公開契約與去重規格解析 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：外部模組直接調用 `from core import PipManager` 是否會導致循環相依或初始化效能拖累？  
> 💡 **防護解法**：`core/__init__.py` 僅做頂層宣告匯入，`PipManager` 本身只依賴 Python 標準庫 (`venv`, `sys`, `os`, `platform`, `subprocess`)，無任何內部 core 模組循環相依，匯入時間 $< 0.1\text{ms}$。

> ❓ **尖銳問題 2**：若下游傳入非標準字典（例如 value 為數字或 None），`parse_pip_dependencies` 是否會崩潰？  
> 💡 **防護解法**：全面實施防禦性型態檢查，鍵值強制字串化並去除空格，若約束值為空或 None 則僅保留套件名稱，異常結構安全回傳 `[]`。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：在 `source/core/core/pip_manager.py` 實作 `PipManager.parse_pip_dependencies(pip_deps: Any) -> List[str]`
- [ ] **TASK-02**：在 `source/core/core/__init__.py` 匯入並將 `PipManager`、`PipInstallError` 加入 `__all__`
- [ ] **TASK-03**：重構 `source/core/core/installer.py` 的 `sync_pip_dependencies`，改調用 `PipManager.parse_pip_dependencies`
- [ ] **TASK-04**：在 `source/core/tests/test_pip_manager_sdk.py` 編寫單元測試，驗證 SDK 導出、解析邏輯與路徑探測
- [ ] **TASK-05**：執行自動化測試驗證 (`python yscb.py dev test core --quiet`)，確保 100% 通過

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 契約確認：正式定稿 `PipManager` 與 `PipInstallError` 導出規格，並將 `parse_pip_dependencies` 作為全生態系統一規格解析標準。
