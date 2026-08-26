# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：工程健檢缺陷修復與治理 (Dev Tests, PlanVerifier & Docs Alignment)  
> 建立日期：2026-08-27  
> 所屬主計畫：2026_08_27_0412_dev_and_governance_health_fix  
> 狀態：Confirmed  
> 計畫類型：Bug Fix / Refactor  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：「/NewPlan 並針對發現務規劃修復方案」
- **核心目標**：針對地毯式軟體工程健檢所發現的 3 大具體缺陷與潛在風險進行系統化修復與規範校準：
  1. **修復 `dev` 模組測試套件之版本硬編碼缺陷**：消除測試中對 `core` 模組固定版本字串（`"1.0.0.build.zip"`、`"1.0.0.0.zip"`）之靜態依賴，改為自適應動態讀取 Manifest 或使用專屬 Mock Package，使 `python yscb.py dev test dev` 恢復 100% 通過（30/30）。
  2. **增強 `PlanVerifier` 對調研報告 (RXX) 標頭欄位之語意容錯**：於 `verifier.py` 中擴充合法 Header 欄位別名（認列 `調研主題`、`調研狀態`、`topic` 等），消除 `agents-workflow plan verify` 之虛假警報。
  3. **校準 `docs/README.md` 全域知識地圖**：補齊 `agents-workflow` 模組手冊索引與生態登載，同步校準各模組即時版本號矩陣。
- **邊界排除 (Explicitly Excluded)**：
  - 本計畫不變更 `core`、`dev`、`agents-workflow` 之 Public API 簽名與對外 CLI 命令介面。
  - 本計畫暫不引入重度之定時沙盒清理背景常駐排程（僅專注於測項修復與合規性驗證）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 測試版本解算策略**：
  - 在 `dev` 模組的測試中，透過 `core.uri` 動態讀取目標模組（如 `core`）之 `manifest.json` 取得當前版本（`manifest["version"]`），據此動態拼接預期產物檔名（如 `f"{ver.rsplit('.', 1)[0]}.build.zip"`），徹底避免未來 `core` 或其他模組依 SemVer 升版時再次破壞 `dev` 測試。
- **[P00:DR-02] PlanVerifier 標頭擴充原則**：
  - `PlanVerifier` 在檢查 Markdown Header 時，應區分通用計畫文件（P00~P07）與專題調研報告（RXX），將 `調研主題` 視為 `功能名稱` 之等價別名，將 `調研狀態` 視為 `狀態` 之等價別名，保持規範彈性與一致性。
- **[P00:DR-03] 知識地圖對齊原則**：
  - `docs/README.md` 作為專案宏觀入口，必須即時反映已安裝之一等公民核心模組（`core`, `dev`, `agents-workflow`）及其最新版本與手冊連結。

---

## 3. 開放議題與確認紀錄

- [ ] 確認修復範疇是否完整涵蓋開發者預期（`dev` 測試修復、`PlanVerifier` 標頭相容、`docs/README.md` 索引同步）。
- [ ] 待開發者確認本語意需求說明書 (P00) 內容與邊界，並指示推進後續階段。
