# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：實作 `core.locale` 多層語系引擎與宣告式 `definition` 契約校驗 (`sub_01_core_locale_engine`)  
> 建立日期：2026-10-29  
> 所屬主計畫：`2026_10_28_1845_core_locale_and_ecosystem_i18n`  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `core/contributes/_format.json` 接受合法 `"locales"` 宣告並剛性攔截缺失 `"definition"` 必填鍵之非法宣告 | FR-01, EC-01 | `python yscb.py dev test core -q -k test_ft_01_core_format_schema_accepts_locales_and_rejects_missing_definition` |
| **FT-02** | 整合測試 | 驗證 `ContributesAggregator` 將多模組之 `"locales"` 獨立保存於 `locales.__modules__[<donor>]` 且互不覆蓋 | FR-02 | `python yscb.py dev test core -q -k test_ft_02_contributes_aggregator_per_module_locales_buckets` |
| **FT-03** | 單元測試 | 驗證 `core.locale` 100% 依顯式優先級退避鏈順序查找，不做隱式 `-` 連字號切分父語系猜測 | FR-03 | `python yscb.py dev test core -q -k test_ft_03_explicit_fallback_chain_without_implicit_hyphen_splitting` |
| **FT-04** | 單元測試 | 驗證二階遞迴專有名詞插值（`[nouns-antigravity] -> zh-TW -> en`）自動沿同一退避鏈解析 `{tool.read_range}` 並與 `kwargs` 合成完整字串 | FR-04 | `python yscb.py dev test core -q -k test_ft_04_two_stage_recursive_noun_interpolation` |
| **FT-05** | 單元/整合測試 | 驗證 `validate_module_locales` 與 `dev check` 精準攔截孤兒鍵（含 `Did you mean` 建議）、佔位符不一致與缺失 `description` | FR-05, EC-04 | `python yscb.py dev test core -q -k test_ft_05_validate_module_locales_contract_checks` & `dev test dev -q -k test_checker_locales_contract_validation` |
| **ET-01** | 邊界測試 | 驗證遞迴專有名詞插值遭遇直接或間接循環引用（`A -> {B}`, `B -> {A}`）與超深時安全停止展開，零 `RecursionError` | EC-02 | `python yscb.py dev test core -q -k test_et_01_cycle_and_max_depth_guard` |
| **ET-02** | 邊界測試 | 驗證雙花括號轉義 `{{...}}` 不被誤判為佔位符並正確反轉義為單花括號 `{...}`，且漏傳未知佔位符時安全保留字面量 | EC-03 | `python yscb.py dev test core -q -k test_et_02_escaped_double_braces_and_missing_kwargs_preserved` |
| **ET-03** | 邊界測試 | 驗證語系檔案路徑含 `..` 越界穿越時被剛性拒絕並回報錯誤 | EC-05 | `python yscb.py dev test core -q -k test_et_03_path_traversal_rejected` |
| **PT-01** | 效能與依賴測試 | 驗證 `core.locale` 零第三方套件依賴、PEP 562 延遲導出且記憶體快取熱路徑單次解析耗時 $< 0.5\text{ms}$ | NFR-01, NFR-02, NFR-03 | `python yscb.py dev test core -q -k test_pt_01_lazy_import_and_hot_cache_performance` |
| **RT-01** | 全量回歸測試 | 驗證 `core`（204 項測試）與 `dev`（80 項測試）全量回歸套件及 `dev check` 100% 通過 | FR-01 ~ FR-05 | `python yscb.py dev test core -q && python yscb.py dev test dev -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `Pass: 1(100.0%), Fail: 0` — 成功驗證 `core/contributes/_format.json` 之 `locales` Schema 與 `definition` 必填攔截 | 2026-10-29 02:56 |
| **FT-02** | `Passed` | `Pass: 1(100.0%), Fail: 0` — 成功驗證 `locales.__modules__` 多模組隔離分桶與執行期獨立命名空間查找 | 2026-10-29 02:56 |
| **FT-03** | `Passed` | `Pass: 1(100.0%), Fail: 0` — 成功驗證顯式退避鏈不隱式拆分 `-`，嚴格依配置列表順序退避 | 2026-10-29 02:56 |
| **FT-04** | `Passed` | `Pass: 1(100.0%), Fail: 0` — 成功驗證 `nouns-antigravity`、`nouns-claude` 與通用退避之遞迴名詞插值 | 2026-10-29 02:56 |
| **FT-05** | `Passed` | `Pass: 2(100.0%), Fail: 0` — 成功於 `core.locale` 與 `dev check` 攔截孤兒鍵、佔位符缺失/未宣告及空 `description` | 2026-10-29 02:56 |
| **ET-01** | `Passed` | `Pass: 1(100.0%), Fail: 0` — 循環引用 `cycle.a <-> cycle.b` 安全停止於 `A->B->{cycle.a}` | 2026-10-29 02:56 |
| **ET-02** | `Passed` | `Pass: 1(100.0%), Fail: 0` — 雙花括號 `{{"status": "ok"}}` 正確通過靜態檢查並渲染為 `{"status": "ok"}` | 2026-10-29 02:56 |
| **ET-03** | `Passed` | `Pass: 1(100.0%), Fail: 0` — `../outside_def.json` 越界路徑被剛性攔截 | 2026-10-29 02:56 |
| **PT-01** | `Passed` | `Pass: 1(100.0%), Fail: 0` — 100 次遞迴插值熱路徑執行耗時 $< 0.05\text{s}$（平均 $< 0.5\text{ms}$/次） | 2026-10-29 02:56 |
| **RT-01** | `Passed` | `core`: `Pass: 204(100.0%), Fail: 0`; `dev`: `Pass: 80(100.0%), Fail: 0`; `dev check core/dev`: `PASSED` | 2026-10-29 02:56 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py contributes list --module core` 與 `python yscb.py contributes check --all`，確認 `core` 已公開 `locales` 擴充點且全系統 Contributes 契約校驗通過 | `[跳過/免測]` | 開發者指示免測，於後續各模組對接時進行 dogfooding 回測 |

