# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：core_pip_sdk_and_environment_export  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 「因近期 core 模組升級了 pip 相依性支援，須同步更新 dev 工具練，core 須開放相關工具 SDK，dev 需支援建置虛擬基環境之前，對當前 build 版做 pip 適配」
  - 「同意啟動首個子計畫」
- **核心目標**：
  1. **開放 Core Pip 工具鏈 SDK**：將 `PipManager`、`PipInstallError` 與微環境解析工具納入 `core` 公開導出契約 (`from core import PipManager, PipInstallError`)。
  2. **封裝微環境相依性標準解析函式**：在 `PipManager` 或 `core.pip_manager` 中提供高階靜態/實例工具，支援解析模組 `manifest.json` 之 `pip_dependencies` 規格字典為 pip 規範字串清單，供下游（如 `dev` 沙盒與構建工具）直接調用，杜絕 Ad-hoc 解析。
  3. **微環境邊界與路徑相容性加固**：確保 `PipManager` 在任意宿主/沙盒目錄結構下均能正確初始化並取得對應 Python 版本標籤、site-packages 路徑與直譯器路徑。
  4. **全套測試防護與向後相容**：撰寫 SDK 導出與功能驗證單元測試，確保全庫 0 破壞性變更，跑測 100% 通過。
- **邊界排除 (Explicitly Excluded)**：
  - `dev` 工具鏈中對沙盒建立前 build 版 pip 適配的具體邏輯（由 `sub_02` 負責）。
  - 不更動 `core` 模組以 Wheel-Only 為核心之底層安全安裝機制。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** SDK 導出契約規範：在 `source/core/core/__init__.py` 的 `__all__` 清單中正式加入 `PipManager`、`PipInstallError`，支援 `from core import PipManager, PipInstallError` 與模組化匯入 `from core.pip_manager import PipManager`，確立公開 API 穩定性。
- **[P00:DR-02]** 相依性規格解析工具化：在 `PipManager` 新增靜態方法 `parse_pip_dependencies(pip_deps: Any) -> List[str]`，支援將 `{"pkg": ">=1.0.0", "pkg2": ""}` 轉換為 `["pkg>=1.0.0", "pkg2"]`，並進行合法性校驗與去重，供 `Installer` 及下游 `dev` 模組共享使用（DRY 原則）。
- **[P00:DR-03]** 測試與品質守門：在 `source/core/tests/` 新增 `test_pip_manager_sdk.py`，覆蓋 SDK 導出契約、規格解析與路徑探測邏輯，確保 `dev test core --quiet` 100% 通過。

---

## 3. 開放議題與確認紀錄

- [x] 是否在 `core` 提供統一的 `parse_pip_dependencies` 解析工具？（已決策：於 `PipManager` 實作標準解析函式供全系統共用）。
- [x] 是否保持 Wheel-Only 剛性安裝約束？（已決策：100% 維持原安全性約束不變）。
