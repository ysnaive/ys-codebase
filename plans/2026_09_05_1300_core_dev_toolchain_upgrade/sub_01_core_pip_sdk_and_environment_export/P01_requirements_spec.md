# 需求規格說明書 (Requirements Specification)

> 功能名稱：core_pip_sdk_and_environment_export  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | Core SDK 匯出契約 | 於 `source/core/core/__init__.py` 的 `__all__` 清單顯式導出 `PipManager` 與 `PipInstallError`，支援 `from core import PipManager, PipInstallError`。 | P0 | [P00:DR-01] |
| **FR-02** | 依賴規格標準解析函式 | 於 `PipManager` 新增靜態方法 `parse_pip_dependencies(pip_deps: Any) -> List[str]`，支援將字典或清單正規化為已去重且符合 pip 規範之字串清單。 | P0 | [P00:DR-02] |
| **FR-03** | 安裝器依賴解析收斂 | 重構 `source/core/core/installer.py` 之 `sync_pip_dependencies`，改調用 `PipManager.parse_pip_dependencies` 提取相依規格，消除 Ad-hoc 解析重複代碼。 | P1 | [P00:DR-02] |
| **FR-04** | 靈活目錄綁定與探測 | 確保 `PipManager(yscb_dir)` 支援外部任意自定義根路徑，提供穩健之直譯器、site-packages 與版本標籤解析能力。 | P1 | [P00:DR-01] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `parse_pip_dependencies` 傳入 None、非字典非清單或空結構 | 安全返回空清單 `[]`，絕不拋出例外。 |
| **EC-02** | 相依性規格包含首尾空白、空字串或重複套件宣告 | 自動去除空白字元、過濾無效空項目，並保持順序去重。 |
| **EC-03** | 傳入無效版本約束或自定義路徑不存在 | 嚴格防禦性處理，僅在物化微環境時拋出語意明確之 `RuntimeError` 或 `PipInstallError`。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能 / 依賴 | `parse_pip_dependencies` 解析 100 筆規格耗時 $< 1\text{ms}$，維持 100% Python 標準庫零第三方相依。 |
| **NFR-02** | 模組相容性 | 100% 保持既有 Public API 向後相容，全生態系單元測試 100% 通過。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`**：微環境路徑在 Windows 與 POSIX 結構不同（Windows 為 `Scripts/python.exe` 與 `Lib/site-packages`；POSIX 為 `bin/python` 與 `lib/pythonX.Y/site-packages`），`PipManager` 已原生封裝此跨平台差異，下游模組（如 `dev`）調用時應統一使用 SDK 介面，嚴禁外部手刻字串拼接路徑。
