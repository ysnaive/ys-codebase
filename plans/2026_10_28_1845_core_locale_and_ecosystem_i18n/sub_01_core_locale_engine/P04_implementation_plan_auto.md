# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：實作 `core.locale` 多層語系引擎與宣告式 `definition` 契約校驗 (`sub_01_core_locale_engine`)  
> 建立日期：2026-10-29  
> 所屬主計畫：`2026_10_28_1845_core_locale_and_ecosystem_i18n`  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：`FR-01` ~ `FR-05` 在 `P03_api_spec_auto.md` 中皆有 1:1 對應介面與資料結構定義
- [x] **邊界防護**：`EC-01` ~ `EC-05` 皆有明確之靜態阻斷或執行期降級防禦策略
- [x] **依賴純淨**：100% Python 標準庫實作、PEP 562 延遲載入與 `sub_01` 範疇隔離完全符合 `NFR-01` ~ `NFR-03`

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md` | Modify | 於 Phase 7 結案時補充 `core.locale` 子系統概覽與設定說明 |
| **專題手冊** | `docs/core/contributes_architecture.md` | Modify | 於 Phase 7 結案時補充 `locales` 擴充點與 `definition` 語意契約規範 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | Modify | 於 Phase 7 結案時評估登記顯式退避鏈與 `locales.__modules__` 分桶設計 |
| **微觀註解** | `ys_codebase/source/core/core/locale.py` 等源碼 Docstrings | Modify | 隨源碼一併交付完整介面契約 Docstrings |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時追加 `sub_01` 變更摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：若某個翻譯字串在 `definition.json` 中宣告 `"placeholders": ["rem", "tool.read_range"]`，而宿主方言覆寫檔 `nouns-antigravity.json` 只覆寫了 `"tool.read_range": "read_file"`，靜態校驗器是否會誤判 `nouns-antigravity.json` 遺漏了 `"cli.snippet.truncated_hint"`？  
> [*] **防護解法**：所有 `<lang-id>.json`（含方言層與區域語系）均允許**稀疏鍵定義（Sparse Key Set）**，即不強制要求 `<lang-id>.json` 包含 `definition.json` 的所有 Key；但只要某個 Key 出現在 `<lang-id>.json` 中，該 Key 就必須存在於 `definition.json`（無孤兒鍵），且該條翻譯字串內的 `{placeholder}` 集合必須完全吻合 `definition.json` 為該 Key 宣告的 `placeholders` 集合。

> [?] **尖銳問題 2**：在開發期執行 `python yscb.py dev check <mod>` 時，目標模組尚未安裝至 `.modules/<mod>`，或 `.modules/<mod>` 內為舊版，`validate_module_locales` 如何定位語系 JSON 檔案？  
> [*] **防護解法**：`validate_module_locales` 支援傳入 `base_dir`（在 `dev check` 中直接傳入源碼目錄 `real_dir`；在 `contributes check` 中若為單檔檢查則由 `contributes/<target>.json` 的父目錄推導模組根目錄，若為已安裝模組則解析 `module://<donor>`），確保源碼期與運行期 100% 精準定位。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01 (`FR-01`)**：更新 `ys_codebase/source/core/contributes/_format.json` 與 `_manifest.md`，新增 `"locales"` 擴充點定義。
2. **TASK-02 (`FR-02`)**：更新 `ys_codebase/source/core/core/contributes.py`，於 `ContributesAggregator.scan_and_inject` 實作 `locales.__modules__[donor]` 分桶隔離與專案級覆寫支援，並於 `_scan_contributes_inputs` 納入語系 JSON 檔案之 `(mtime, size)` 快照追蹤。
3. **TASK-03 (`FR-03`, `FR-04`, `FR-05`, `EC-01`~`EC-05`)**：新建 `ys_codebase/source/core/core/locale.py` 並更新 `core/__init__.py`（PEP 562 延遲導出），實作顯式優先級退避鏈、二階遞迴專有名詞插值、雙花括號轉義保護與 `validate_module_locales` 靜態契約校驗器。
4. **TASK-04 (`FR-05`, `EC-04`)**：更新 `ys_codebase/source/core/core/commands/contributes_cmd.py` 與 `ys_codebase/source/dev/dev/checker.py`，串聯 `locale.validate_module_locales` 並確保 `dev check core` 亦執行完整 Contributes 校驗。
5. **TASK-05 (`FT-01`~`FT-05`, `ET-01`~`ET-05`, `RT-01`)**：新增 `ys_codebase/source/core/tests/test_locale.py` 並擴充 `ys_codebase/source/dev/tests/test_checker.py`，執行 `dev check`、`dev test` 與 `@build` 熱部署驗證。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 佔位符集合相等性契約**：對於出現在 `<lang-id>.json` 中的任一 Key，提取其翻譯字串中之佔位符集合 $P_{\text{actual}}$，必須與 `definition.json` 中該 Key 宣告之 `placeholders` 集合 $P_{\text{expected}}$ 完全相等（$P_{\text{actual}} == P_{\text{expected}}$）：多出未宣告佔位符報 `Unknown placeholder(s)`，少寫必備佔位符報 `Missing required placeholder(s)`。
- **[P04:DR-02] 跨模組與公共名詞退避順序**：當遞迴插值解析 `{token}` 時，若 `token` 未帶 `<mod>:` 前綴，先於當前主鍵所屬模組查找 `token`，若當前模組未定義則自動退回 `"core"` 模組查找，方便未來於 `core` 集中定義全系統共用的宿主專有名詞（如 `tool.read_range`）。

