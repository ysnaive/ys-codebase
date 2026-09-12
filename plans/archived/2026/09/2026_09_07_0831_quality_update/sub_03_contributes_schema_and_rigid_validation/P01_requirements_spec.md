# 需求規格說明書 (Requirements Specification)

> 功能名稱：Contributes 宣告架構升級與 Schema 剛性校驗 (Contributes Schema & Rigid Validation)  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_07_0831_quality_update (品質更新)  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | Contributes 目錄拓撲標準化 | 各模組源碼目錄中統一採用 `module.source://<mod>/contributes/` 拓撲；以底線 `_` 命名空間建立 `_format.json`（Ingress 契約）與 `_manifest.md`（Egress 導覽）；聚合與派發引擎遍歷時自動過濾以 `_` 開頭之特殊檔案。 | P0 | [P00:DR-01] |
| **FR-02** | 輕量型別 DSL 解析與校驗引擎 | 在 `core.contributes` 實作零依賴校驗器，支援簡約型別標記（`str!`, `int?`, `bool? = false`, `enum(...)`）、通配動態鍵（`"*"`）以及 `_types` + `$TypeName` 樹狀遞迴結構參照（完整涵蓋階層化 CLI 指令樹）。 | P0 | [P00:DR-02] |
| **FR-03** | 近似拼寫診斷提示 (Did you mean) | 校驗鍵名或列舉值遇未知屬性時，調用標準庫 `difflib.get_close_matches` 輸出最接近之合法欄位建議與詳細 JSON 路徑。 | P1 | [P00:DR-02] |
| **FR-04** | 核心 CLI `contributes` 指令集 | 於 `core` 模組註冊 `contributes list`（表格展示各模組開放之注入契約）與 `contributes check`（支援模組名、語意 URI 如 `module.source://` 與 `--format` Meta-Check）。 | P0 | [P00:DR-04] |
| **FR-05** | 核心 SDK 公開 API | 導出 `get_format(module: str)`, `validate(target_mod: str, payload: dict, donor_mod: str)`, `list_points(module: str = None)` 等標準程式庫 SDK。 | P0 | [P00:DR-04] |
| **FR-06** | 單向邊界剛性檢測防線 | 1. 靜態層：`dev check` 整合 `ContributesCheckPass`，發現未定義擴充點或跨目標越權注入立即 Exit Code 1 阻斷。<br/>2. 專案層：`config://<target>/contribute.json` 僅能作用於 `<target>`，強制受 Git 追蹤。<br/>3. 運行期：`ContributesAggregator` 移除盲目 `except Exception: pass`，過濾無效鍵並記錄警告，防止髒資料進入快取。 | P0 | [P00:DR-03] |
| **FR-07** | 腳手架預置模組骨架 (`dev create`) | 更新 `dev.scaffold.Scaffolder`，生成新模組時自動建立預置教學範本之 `contributes/_format.json` 與 `contributes/_manifest.md`。 | P1 | [P00:DR-05] |
| **FR-08** | 生態系 5 大模組全面遷移 | 將現有 5 大模組（`core`, `server`, `dev`, `agents-workflow`, `knowledge-db`）之書面手冊移植為標準 `_format.json` 與 `_manifest.md`，並同步清理舊有 `phases` 殘留欄位。 | P0 | [P00:DR-05] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 目標模組未宣告 `_format.json` | 判定為未宣告格式之模組，校驗器輸出 `Warning` 提示但寬容放行，不中斷既有模組正常加載。 |
| **EC-02** | 跨目標越權/錯置注入 | 於 `<donor>/contributes/<target>.json` 中宣告非 `<target>` 開放之鍵名（如在 `core.json` 中宣告 `export`）時，校驗器剛性報錯並指出該鍵所屬目標模組。 |
| **EC-03** | 遞迴指令樹循環或過深嵌套 | 指令樹節點（`cmd`）遞迴校驗時限制最大深度（預設 10 層），超出時終止並報錯 `MaxRecursionDepthExceeded`。 |
| **EC-04** | 型別懸空參照 (Dangling Reference) | 在 Schema 中引用未於 `_types` 定義之 `$TypeName` 時，Meta-Check 立即阻斷並拋出 `UndefinedTypeReferenceError`。 |
| **EC-05** | 專案層級違法注入 (`config://`) | `config/<target>/contribute.json` 包含跨目標鍵時，`ContributesAggregator` 略過無效鍵並記錄警告日誌；偵測到 `contribute.local.json` 則明確警告並忽略。 |
| **EC-06** | JSON 格式毀損或語法錯誤 | 讀取解析異常時精確輸出檔案語意 URI 與解析錯誤訊息，拒絕靜默吞噬。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零第三方依賴 | 100% Python 標準庫實現，嚴禁引入 `pydantic`、外部 `jsonschema` 等套件。 |
| **NFR-02** | 校驗效能指標 | 全生態系 5 大模組全量 contributes 校驗總耗時 $\le 25\text{ms}$；JIT 快取命中時運行期驗證開銷為 $0\text{ms}$。 |
| **NFR-03** | 錯誤可讀性與路徑定位 | 所有校驗錯誤均提供精確 JSON 路徑（例 `commands.cmd.build.tier`）、收斂之違規值與修復提示。 |

---

## 4. 階段決策紀錄 (Phase 1 Decision Records)

- **[P01:DR-01] 漸進式嚴格驗證 (Gradual Strictness)**：未提供 `_format.json` 之模組暫行寬容放行；一旦提供 `_format.json` 則強制 100% 剛性驗證。
- **[P01:DR-02] 預設選填安全設計 (Safe Optional by Default)**：Schema 欄位若未標記 `!`，解析器一律預設為選填（`?`），避免過度約束阻斷未來非破壞性擴充。
- **[P01:DR-03] First-Class 語意 URI 優先**：CLI 與 SDK 統一以語意 URI（`module.source://` 與 `config://`）為核心介面協議，兼容本地相對路徑。

---

## 5. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 聚合引擎吞錯風險**：`core.contributes.ContributesAggregator` 原先有多處 `try...except Exception: pass`，若不移除將導致 Schema 校驗錯誤在執行期被悄悄吞掉，難以察覺。必須以標準 Logging 取代空 except。
- **`[!NOTE]` 雙層 Options 結構**：CLI 指令樹的 `options` 採二層結構（`options.<group>.<option_name>`），通配校驗時必須嚴格按二層字典解算，不可誤當扁平結構處理。
