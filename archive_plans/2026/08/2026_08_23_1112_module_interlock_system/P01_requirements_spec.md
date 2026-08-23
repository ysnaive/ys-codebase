# 需求規格書 (Requirements Specification)

> 功能名稱：Module 安裝期連動系統設計 (Installation-time Interlock System)  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 依據 P00 / 調研報告：[P00_semantic_requirements.md](./P00_semantic_requirements.md) / [R01_installation_interlock_mechanisms.md](./R01_installation_interlock_mechanisms.md)  
> 狀態：Confirmed  
> 擴充項目：dogfooding_pipeline_ext  
> 模板版本：v1.4  

---

## 功能需求 (Functional Requirements)

| ID | 功能描述 | 輸入 | 處理 | 輸出 | 對應 P00 語意 |
|:---|:---|:---|:---|:---|:---|
| **FR-01** | Installer 通用生命週期廣播 Hook 派發 | 模組 `install`, `pull`, `remove` 成功完成（`build` 指令**不觸發**，確保產物純淨性） | 遍歷已安裝模組，若存在 `scripts/_on_modules_changed.py` 則以子進程執行 | 調用 `python _on_modules_changed.py <event> <target>`，其中 `event` 為 `"installed"` / `"updated"` / `"removed"` | P00 協定合約 I / 情境 1 & 2 |
| **FR-02** | Installer 廣播異常隔離防護 | Hook 執行拋錯或 exit code != 0 | 捕獲異常並記錄 `[WARN]` 日誌 | 核心安裝事務不受影響，保證安裝流程成功結束 | P00 協定合約 I / 焦點目標 1 |
| **FR-03** | Core SDK 命名空間貢獻查詢通道 | `ProjectContext.get_contributions(namespace)` | 安全掃描所有已安裝模組的 `manifest.json`，提取指定命名空間下的資料 | 返回 `[(mod_name, mod_dir, payload_dict), ...]` 清單 | P00 協定合約 II / 焦點目標 2 |
| **FR-04** | `agents-workflow` 公開主機協定 Schema 定義 | 貢獻模組的 `manifest.json` | 定義 `"agents-workflow"` 命名空間規格 (`schema_version: "1.0"`, `sop_patches`, `sop_extensions`) | 剛性驗證資料格式相容性 | P00 協定合約 III / 焦點目標 3 |
| **FR-05** | `agents-workflow` 實作 `_on_modules_changed.py` 與 IDE 指令自動同步判定 | 接收來自 Installer 的廣播事件 (`installed`/`updated`/`removed`) | 檢查專案環境（如 `.agents/workflows/` 是否已存在或已配置 IDE 目標），若已啟用則自動觸發工作流指令重新生成與 Slot 補丁合成引擎；若未啟用則安全略過 | 自動且無感同步更新 `.agents/workflows/` 中的 IDE 指令，免除手動重新下達 `--ide-antigravity` | P00 協定合約 I & III / 情境 1 & 2 |
| **FR-06** | `agents-workflow` SOP Slot 標記注入合成 | 來自各模組宣告的 `sop_patches`（含 `target_slot`、`position`、`content_file`） | 讀取帶有 `<!-- YSCB_SLOT:<name> -->` 標記的 SOP 模板，精確比對 `target_slot` 名稱，依 `append/prepend` 注入 `content_file`，最終剝除所有殘留 Slot 標記 | 輸出 100% 純淨（無任何 `YSCB_SLOT` 殘留）的最終 SOP Markdown 文檔 | P00 協定合約 III / 情境 1 & 2 |
| **FR-07** | `agents-workflow` 多來源動態 Extension 發現與調度 | `verify_plan.py` 或 `ext list/show` 觸發 | 動態合併 `sop_ext://`（用戶自定義，最高優先）與各模組 `contributes.sop_extensions`（`yscb://modules/<plugin>/`），同名 Extension 以 `sop_ext://` 優先覆蓋 | 統一調度驗證腳本，`ext list` 輸出含來源標籤（`[sop_ext]` vs `[module: <name>]`） | P00 協定合約 III / 情境 1 & 2 |
| **FR-08** | `agents-workflow` 主機 SOP Slot 全集定義與植入 | SOP 模板原始碼 | 於所有具擴充注入價值的 SOP 模板中植入標準 `YSCB_SLOT` 標記（詳見下方 Slot 全集規格） | 各 SOP 模板包含剛性且可被跨模組查詢的插槽定義 | P00 協定合約 III / 焦點目標 3 |

---

## 非功能需求 (Non-Functional Requirements)

| ID | 類別 | 約束描述 | 驗證方式 |
|:---|:---|:---|:---|
| **NFR-01** | 效能 | 跨模組貢獻查詢、SOP 補丁動態合成與 Extension 掃描總耗時 `< 150ms` | 基準測試與計時日誌量測 |
| **NFR-02** | 架構純淨性 | Installer 零領域知識；Core SDK 純資料通道；業務邏輯 100% 封裝於 Host 模組 | 靜態程式碼審查與職責隔離驗證 |
| **NFR-03** | 順序無關性 | 不論主機模組先裝或擴充模組先裝，最終具體化之 `modules/` 運行與指令狀態 100% 一致 | 實機測試先裝 A 後裝 B vs 先裝 B 後裝 A |
| **NFR-04** | 零外部依賴 | 補丁合成與 Hook 調度 100% 純標準庫實現 (Zero External Dependency) | 代碼依賴審查 |

---

## SOP Slot 全集規格 (YSCB_SLOT Full Registry)

> 僅以下 SOP 具備連動注入的業務意義，其餘 SOP（`Continue`、`Discuss`、`Pause`、`Research`）為通用防呆結構，**不植入 Slot**。

| 目標 SOP | Slot 名稱清單 | 植入位置說明 |
|:---|:---|:---|
| **`NewPlan.md`** | `Phase0` / `Phase1` / `Phase2` / `Phase3` / `Phase4` / `Phase5` / `Phase6` / `Phase7` | 各 Phase 段落末尾（`→ Checkpoint` 行之前），供領域特化規則注入 |
| **`Review.md`** | `Step1` / `Step2` / `Step3` / `Step4` | 各步驟段落末尾，供領域特化稽核 Checklist 注入 |
| **`ContextInit.md`** | `Step1` / `Step2` / `Step3` / `Step4` | 各步驟末尾（輕量），供連動模組注入「需額外加載的模組規範摘要」 |

> **標記格式**：`<!-- YSCB_SLOT:<SlotName> -->`
> **最終清除**：注入合成後，所有殘留的 `YSCB_SLOT` 標記在輸出前統一剝除，確保 `.agents/workflows/*.md` 100% 純淨。

---

## Edge Cases (邊界與異常情況)

| ID | 場景描述 | 預期行為 | 對應 FR |
|:---|:---|:---|:---:|
| **EC-01** | 模組未提供 `_on_modules_changed.py` Hook | Installer 安全略過，不報錯不阻塞 | FR-01 |
| **EC-02** | `_on_modules_changed.py` 執行報錯或語法異常 | Installer 記錄 Warning，繼續通知其他模組，不影響安裝事務 | FR-02 |
| **EC-03** | 模組 `manifest.json` 缺少 `contributes` 或格式非字典 | `ProjectContext.get_contributions()` 寬容略過，返回空清單 | FR-03 |
| **EC-04** | SOP 補丁指定的 `target_sop` 檔案不存在 | `agents-workflow` 輸出警告日誌並略過該補丁，不中斷生成 | FR-06 |
| **EC-05** | SOP 補丁指定的 `target_slot` 名稱在目標文檔中找不到對應標記 | `agents-workflow` 輸出警告日誌並略過該 Slot 注入，保留原文檔 | FR-06 |
| **EC-06** | SOP 補丁的 `content_file` 檔案路徑不存在 | `agents-workflow` 輸出警告日誌並略過注入，不崩潰 | FR-06 |
| **EC-07** | `contributes.sop_extensions` 宣告的 `script` 檔案不存在 | `verify_plan.py` 輸出警告標籤並跳過，不中斷整體合規檢查 | FR-07 |
| **EC-08** | 多個模組同時注入相同 `target_sop` 的同一 `target_slot` | 依 `get_contributions()` 返回順序（安裝先後）線性疊加；衝突排序為**未定義行為**，由模組開發者自行設計互補而非覆蓋的內容 | FR-06 |

---

## 專案擴充特化判定矩陣 (Extension Specialization Matrix)

> 執行 `python yscb_cli.py agents-workflow ext list` 盤點 `sop_ext://` 下所有可用擴充，逐項評估本計畫之適用性：

| 擴充項目名稱 | 觸發模式 | 本計畫適用性判定 | 納入 / 排除具體理由 |
| :--- | :--- | :--- | :--- |
| `dogfooding_pipeline_ext` | `always` | ✅ 納入 (Included) | 本計畫將修改 `source/core/`、`source/agents-workflow/` 及 `yscb_installer.py`，必須強制遵守 Dogfooding 三層空間標準流水線與發布守門。 |

---

## 外部研究摘要

| 主題 | 摘要 | 來源 | 可信度 |
|:---|:---|:---|:---:|
| **主機-外掛架構 (Host-Plugin Model)** | 安裝器只負責分發通用生命週期事件，主機模組負責自主查詢並合成領域指令，實現零領域耦合。 | VS Code Extension Contributes / Python Entry Points | 高 |
| **Slot 標記注入演算法 (Slot Marker Injection)** | 在 SOP 模板中預留剛性 `<!-- YSCB_SLOT:<name> -->` 標記，注入後統一剝除殘留，比 Markdown 標題匹配更精準且不受標題文字漂移影響。 | Linux `/etc/*.d` Fragment Architecture | 高 |
| **Extension 雙層發現鏈** | `sop_ext://` 用戶自定義層（最高優先）+ `modules/<plugin>/` 模組連動注入層（隨插即用），同名 Extension 本地優先覆蓋。 | VS Code Extension Activation Events | 高 |

---

## Decision Records

### [REQ:DR-01] 安裝器職責邊界與通用生命週期 Hook 設計
- **議題**：安裝期跨模組連動是否應由 `yscb_installer.py` 直接處理 SOP 合成？
- **結論**：**絕對禁止**。Installer 僅實作通用 `_on_modules_changed.py` 廣播與資料搬移；SOP 動態合成與 Extension 調度 100% 由 `agents-workflow` 主機模組自主處理。
- **理由**：維護 Installer 作為底層通用套件管理器的純淨性（SRP/OCP 原則），防止將 `agents-workflow` 私有領域邏輯硬編碼進通用安裝器。

### [REQ:DR-02] `build` 指令排除廣播觸發範圍
- **議題**：`installer build` 完成後是否也應觸發 `_on_modules_changed.py` 廣播？
- **結論**：**絕對排除**。`build` 的職責是產出純淨可發布的二進位/打包物，不應帶有任何執行期或安裝期的副作用。
- **理由**：`build` 產物本身尚未進入本地專案上下文（`modules/`），觸發廣播等同於在「發布包尚未落地」的狀態下執行「已安裝」的連動邏輯，語意錯誤且破壞 `build` 的冪等性。廣播僅在 `install`、`pull`（含 Dogfooding Sync 的 `install --force`）與 `remove` 等正式改變本地 `modules/` 狀態的指令後觸發。

### [REQ:DR-03] SOP 注入機制從「標題匹配」升級為「Slot 標記注入」
- **議題**：補丁合成引擎應採用 Markdown 標題關鍵字匹配（`target_phase`）還是剛性 Slot 標記注入（`target_slot`）？
- **結論**：採用 **Slot 標記注入**（`<!-- YSCB_SLOT:<name> -->`），廢除 `target_phase` 欄位，改用 `target_slot`。
- **理由**：Markdown 標題文字存在語意漂移風險（繁簡體、標點符號、Emoji 等細微差異均可導致匹配失敗）；Slot 標記為剛性不可見的插槽協定，精準定位且對文檔可讀性零影響，並在最終輸出時自動剝除以保持純淨。

### [REQ:DR-04] 多模組同 Slot 衝突排序為未定義行為
- **議題**：若多個模組同時注入同一 SOP 同一 Slot，其順序是否需要被規格化？
- **結論**：**衝突排序定義為未定義行為 (Undefined Behavior)**，由呼叫順序（安裝先後）決定疊加次序。
- **理由**：強制規格化優先級會引入額外複雜度（如 `priority` 數字欄位），且實際應用場景中兩個模組注入同一 Slot 的情境應屬極罕見的反模式；各模組應設計互補性規則而非覆蓋性內容。
