# 生態系模組開發品質與驗收標準 (Module Quality & Acceptance Guild)

本手冊定義 YSCB 模組在進行功能開發與維護時的**代碼品質、四大文檔視角、AST 靜態檢核紅線與驗收標準**。聚焦於靜態工具無法自動感知的深層語意、文檔同步性與架構邊界盲區，並對齊 `dev check` 剛性檢核管線。

> [!TIP]
> 若欲查閱 CLI 實作與 Contributes 宣告對稱性規範，請參閱專門指南：
> - [CLI 活躍合約與指令手冊](./cli_and_commands.md)（第 2 節：實作與宣告對稱性規範）
> - [Contributes 擴充注入與 Schema 規範指南](./contributes_guide.md)（第 4.3 節：實作與注入宣告對稱性鐵律）

---

## 🎯 1. 核心定位：超越機械檢查的語意防禦

`dev check` 與 `contributes check` 負責驗證語法、Schema 格式、URI 協議與 AST 靜態紅線（機械合規）；本注意事項旨在提示開發者與 Agent 關注**「功能實作自洽性、契約對齊與文檔完整性」**：

- **機械工具檢查 (`dev check`)** $\rightarrow$ 「語法是否合規？AST 是否觸碰紅線？契約是否合法？」
- **品質與功能驗收 (本手冊)** $\rightarrow$ 「視角是否純淨？相依是否完備？測試是否具備防禦性？」

---

## 📋 2. 模組品質維度矩陣 (Module Quality Dimensions)

### 維度 ①：四大文檔視角同步與嚴格隔離 (The 4 Documentation Perspectives)

> [!CAUTION]
> **🚨 鐵律：嚴禁橫跨視角撰寫文檔 (Strict Perspective Isolation)**  
> 各文檔目標讀者之**運行環境、心智模型與可用工具鏈截然不同**。撰寫或同步文檔時，必須 100% 拘束於該受眾之視角與權限邊界，**嚴禁將底層架構洩漏給終端使用者，或將僅本地源碼庫才擁有的路徑與工具強加給第三方**。

#### 視角 1：本地儲存庫開發者手冊 (`docs://<module>/`)
- **目標受眾**：本機儲存庫開發者（具備 `dev` 工具鏈 + `<module>` 運行時與完整源碼空間）。
- **核心職責**：記錄系統架構、內部資料流、生命週期調度、跨子系統機制與設計折衷決策（`DESIGN_NOTES.md` DN-XX）。
- **嚴禁事項**：嚴禁記錄終端操作流水帳教學；專注於中觀架構深度與內部原理。

#### 視角 2：第三方使用者手冊 (`<module>/docs/user_guild.md`)
- **目標受眾**：終端使用者（**僅有 `<module>` 運行環境**，無 `dev` 工具鏈亦無源碼）。
- **核心職責**：CLI 終端操作指南、可用命令清冊、參數/選項說明、Cookbook 典型業務情境範例、預期輸入與輸出。
- **嚴禁事項**：**嚴禁**出現 `dev` 工具鏈指令、內部私有類別、未導出介面或全域底層架構術語。

#### 視角 3：第三方開發者手冊 (`<module>/docs/dev_guild.md`)
- **目標受眾**：二次開發者（具備 `<module>` 運行時與依賴引用能力，但**無本模組源碼**）。
- **核心職責**：Public SDK/API 調用指引、介面擴充範式、生命週期 Hooks 掛接、Contributes 注入規範與整合陷阱。
- **嚴禁事項**：**嚴禁**出現 `project://source/` 硬編碼路徑（必須採用 `module://<mod>/` 語意 URI）；嚴禁假設對方能修改本模組源碼。
- **Egress 同步檢核**：若本模組對外開放 Contributes 擴充點（Host），是否已同步更新 `contributes/_manifest.md` 對外契約清冊？

#### 視角 4：初始安裝引導手冊 (`<module>/docs/install_guild.md`)
- **目標受眾**：剛安裝 `<module>` 運行時的初次使用者（首次冷啟動環境）。
- **核心職責**：安裝後的初始化引導、相依環境檢測（Python/系統）、必要設定檔生成、初次連通性驗證、常見安裝報錯排解。
- **嚴禁事項**：嚴禁混入日常重度開發或進階 SDK 呼叫，專注於「從零安裝到順利跑通」。

---

### 維度 ②：模組相依邊界與發布純淨度 (Dependencies & Release Hygiene)

- [ ] **外部依賴宣告完整性 (`manifest.json`)**：
  - 核心相依：非 `core` 模組是否皆已在 `dependencies` 明確宣告 `core`？
  - 可選相依 (`optional`)：弱依賴模組是否包含非空字串 `version` 與 `hint`？
  - 第三方套件 (`pip_dependencies`)：Python 第三方套件依賴是否如實宣告且格式正確？
- [ ] **配置範本目錄規範 (`configurable/`)**：
  - 模組預設設定範本（如 `config.project.json`, `config.local.json`）**嚴禁散落於模組根目錄**！
  - 所有範本必須統一收納於 `configurable/` 子目錄下，且命名符合 `config.*.json` 規範。
- [ ] **`.yscbignore` 發布打包隔離**：
  - 檢視 `.yscbignore`，新增加的非發布資源（如測試 mock 資料、除錯腳本、暫存快照、內部草稿）是否已宣告排除？
  - 確保正式發布包（`project://release/<module>/`）維持純淨，零內部測試夾具或垃圾產物外洩。

---

### 維度 ③：測試案例的語意防禦深度 (Semantic Test Coverage & Defense)

- [ ] **`self.mark_passed()` 狀態閉環**：
  - 所有測試案例成功路徑是否皆顯式呼叫 `self.mark_passed()`？
  - 測試案例是否避免產生 `UNKNOWN` 假狀態？
- [ ] **異常與防禦邊界測試 (ET-XX) 實質性**：
  - 測試案例是否不僅覆蓋成功路徑 (FT-XX)，更具備針對「空值輸入」、「非法字元」、「邊界溢位」、「缺失設定」的主動防禦性測試？
  - 測試內部斷言是否明確檢驗了具體 Exception 型態與錯誤訊息，而非寬鬆捕獲？
- [ ] **真實運行環境還原度 (No Over-Mocking)**：
  - 關鍵業務邏輯是否避免過度 Mock？涉及磁碟原子寫入、語意 URI 解析等是否在沙盒中執行實機路徑驗證？
- [ ] **沙盒測試生命週期鉤子 (`scripts/hook.dev.py`)**：
  - 若模組測試需要特殊環境配置，是否已透過 `on_test_setup(context)` 與 `on_test_teardown(context)` 標準宣告？

---

## 🛡️ 3. `dev check` AST 靜態檢核紅線清冊 (Rigid Checker Redlines)

`dev check` 執行深層 AST 靜態語法樹掃描，以下違規將直接觸發 `FAIL` 或 `WARN` 攔截：

| 檢查範疇 | 違規態樣與反模式 (Anti-Pattern) | 嚴重度 | 處置要求與正確做法 |
| :--- | :--- | :---: | :--- |
| **CLI 入口** | `scripts/cli.py` 缺少 `process(args)` 且未宣告新版命令函式 | `FAIL` | 必須宣告 `def process(args)` 或對應命令函式 |
| **CLI 入口** | `scripts/cli.py` 宣告 `def main(...)` | `FAIL` | 嚴禁宣告 `main()`，模組 CLI 必須為純導入型別 |
| **CLI 入口** | `scripts/cli.py` 包含 `if __name__ == '__main__':` | `FAIL` | 嚴禁包含 `__name__` 執行塊，一律由微內核派發 |
| **CLI 入口** | `scripts/cli.py` 頂層散落可執行陳述式 | `FAIL` | 頂層僅允許 Import、ClassDef、FunctionDef 與 Docstring |
| **架構邊界** | 非 core/dev 模組源碼包含 `"module.source://"` | `FAIL` | Zero Probing 違規！禁止探索源碼空間，改用 `module://` |
| **SDK 防線** | 源碼硬編碼存取 `"config.project.json"` 或 `"config.local.json"` | `FAIL` | 禁止直接讀檔，必須使用 `core.config.get()` / `set()` SDK |
| **SDK 防線** | 源碼硬編碼存取 `"contributes.merged.json"` | `FAIL` | 禁止直接讀檔，必須使用 `core.contributes.get()` SDK |
| **測試規範** | 測試類別直接繼承 `unittest.TestCase` | `FAIL` | 必須繼承 `dev.testing.case.YSCBTestCase` |
| **測試規範** | 測試方法遺漏 `self.mark_passed()` 呼叫 | `WARN` | 補齊 `self.mark_passed()`，避免測試被標記為 `UNKNOWN` |
| **測試規範** | 測試類別或方法同時標註 `LOGIC` 與 `ISOLATED_SANDBOX` | `WARN` | 純邏輯測試嚴禁混用獨佔沙盒，移除 `ISOLATED_SANDBOX` |
| **沙盒鉤子** | `scripts/hook.dev.py` 語法錯誤或頂層散落可執行語句 | `FAIL` | 修正語法，移除頂層副作用語句 |
| **沙盒鉤子** | `hook.dev.py` 之 `on_test_setup/teardown` 無參數 | `FAIL` | 函式簽名必須至少接受 1 個參數 (`context`) |
| **結構規範** | 模組根目錄散落 `config.*.json` 範本 | `FAIL` | 範本必須移入 `configurable/` 目錄 |
| **結構規範** | `configurable/` 檔案未以 `config.*.json` 命名 | `WARN` | 統一範本命名為 `config.<type>.json` |
| **契約規範** | 模組包含 `contributes/` 但缺少 `_manifest.md` | `FAIL` | 必須建立 `contributes/_manifest.md` 導覽清冊 |
| **文檔純淨** | `docs/` 第三方手冊中出現 `project://source/` 硬編碼 | `WARN` | 移除 source 路徑，改用 `module://<mod>/` 語意 URI |

---

## 📋 4. 模組功能品質速查核對表 (Module Quality Quick Check)

在完成模組功能開發或代碼異動後，請逐一核對以下品質要點：

| 品質維度 | 核心核對問題 | 自檢判定 |
| :--- | :--- | :---: |
| **1. 本地架構文檔 (`docs://`)** | 內部資料流、折衷設計 (`DESIGN_NOTES.md`) 是否已同步？（嚴禁寫入終端教學） | [ ] 已記錄 |
| **2. 使用者手冊 (`user_guild.md`)** | 終端命令清冊與典型 Cookbook 是否已更新？（嚴禁出現 `dev` 與源碼術語） | [ ] 已同步 |
| **3. 開發者手冊 (`dev_guild.md`)** | 對外 Public SDK/API 介面、Hook 與注意事項是否更新？（嚴禁出現 `project://source/`） | [ ] 已同步 |
| **4. 初始安裝手冊 (`install_guild.md`)** | 安裝驗證、環境前置檢測與初次配置是否完備？（專注從零到跑通） | [ ] 已更新 |
| **5. Egress 清冊 (`_manifest.md`)** | 若有開放擴充點，`contributes/_manifest.md` 是否已同步登記？ | [ ] 已登記 |
| **6. 依賴與範本純淨度** | `manifest.json` 依賴是否補齊？配置範本是否收納於 `configurable/`？ | [ ] 已隔離 |
| **7. 測試狀態與邊界防禦** | 測試是否呼叫 `self.mark_passed()`？是否深度覆蓋錯誤分支 (ET-XX)？ | [ ] 深度覆蓋 |
| **8. 剛性檢核通過** | 執行 `python yscb.py dev check <mod>` 是否 0 FAIL、0 WARN 通過？ | [ ] 綠燈通過 |
