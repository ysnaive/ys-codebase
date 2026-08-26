# 需求規格說明書 (Requirements Specification)

> 功能名稱：框架骨架最終打磨與 CLI UX 體驗優化 (Framework Final Polish & CLI UX)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P00/調研報告：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 狀態：Confirmed (Phase 1 已確認)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格說明 | 對應 P00 語意 |
| :--- | :--- | :--- | :--- |
| **FR-01** | 移除 `dev release` Gate 1 Git Dirty 限制 | 1. 徹底移除 `source/dev/dev/releaser.py` 中 Pre-flight Gate 1 的 `git status --porcelain` 乾淨檢查。<br/>2. 本地發布流水線保持 100% 敏捷流暢，直接執行 Gate 2 (測試守門)、Gate 3 (版本唯一性) 與 Gate 4 (Manifest 合規檢查)。<br/>3. 發布產物純淨打包至 `release/<mod>/<ver>.zip` 並更新 `index.json`，由開發者自行掌控何時 Push 遠端。 | P00 §1 (議題一)<br/>[P00:DR-01] |
| **FR-02** | `yscb.py --help` 全域動態派發與層次排版 | 1. 統一 `yscb.py --help` 輸出視覺層次：包含 Banner、Usage、`CORE COMMANDS` 與 `MODULE COMMANDS`。<br/>2. `init` 指令作為宿主特化指令，自動整併至 `CORE COMMANDS` 區塊說明。<br/>3. 宿主透過微內核與 Contributes 聚合器，依序動態掃描所有已安裝模組（如 `dev` 及第三方模組）並輸出標準對齊之 `MODULE COMMANDS` 清冊。 | P00 §1 (議題二)<br/>[P00:DR-02] |
| **FR-03** | 各子指令深層 `--help` 統一規範 | 1. 支援 `python yscb.py <core_cmd> --help`（如 `install --help`, `update --help`）輸出標準參數與說明。<br/>2. 支援 `python yscb.py dev <subcmd> --help`（如 `dev create --help`, `dev test --help`, `dev release --help`）輸出標準參數表格與範例。 | P00 §1 (議題二)<br/>[P00:DR-02] |
| **FR-04** | 智慧指令拼寫錯誤建議 (Did you mean?) | 當使用者輸入未知指令（如 `python yscb.py relod` 或 `python yscb.py dev bulid`）時，透過 Python 標準庫 `difflib.get_close_matches` 自動比對已知指令，輸出如 `Unknown command 'relod'. Did you mean 'reload'?` 之智慧指引。 | P00 §1 (議題二)<br/>[P00:DR-02] |

---

## 2. 邊界與異常情況處理 (Edge Cases)

| 邊界編號 | 邊界情境說明 | 防禦處置與預期行為 | 對應需求 |
| :--- | :--- | :--- | :--- |
| **EC-01** | 未安裝任何擴充模組時的 `--help` 輸出 | 若系統僅初始化 `core` 微內核（尚未安裝 `dev` 等模組），`MODULE COMMANDS` 區塊優雅提示 `(No module commands available. Use 'install <module>' to add capabilities.)`，零異常拋出。 | FR-02 |
| **EC-02** | 模組未宣告說明文字或格式異常 | 若第三方模組之 `manifest.json` 缺少 `description` 或 contributes 格式不完整，聚合器自動容錯降級（以預設名稱呈現），不阻斷 `--help` 輸出。 | FR-02, FR-03 |
| **EC-03** | 輸入完全無相近候選之未知指令 | 若輸入之未知指令字串與所有已知指令差異過大（`difflib` 無相近匹配），輸出標準錯誤提示並引導使用者執行 `python yscb.py --help` 查看完整清單。 | FR-04 |

---

## 3. 非功能需求 (Non-Functional Requirements)

- **NFR-01（100% Python 標準庫）**：所有 CLI 格式化、參數解析與拼寫比對 (`difflib`) 100% 使用 Python 標準庫，零任何第三方依賴。
- **NFR-02（完全向後相容）**：所有既有 CLI 指令簽名與行為保持 100% 向後相容。
- **NFR-03（測試通過率 100%）**：全模組回歸測試（74/74+）維持 100% 綠燈 Passed。

---

## 4. 專案擴充特化判定矩陣 (Extension Specialization Matrix)

| 擴充功能名稱 | 觸發模式 | 判定結果 | 評估理由 |
| :--- | :--- | :---: | :--- |
| `dogfooding_pipeline_ext` | always | **Excluded (排除)** | 本計畫為 CLI UX 與發布守門精簡，依循標準四步閉環流水線執行。 |
