# 成果展示與結案報告 (Walkthrough)

> 功能名稱：純淨安裝環境下游反饋 4 項缺陷修復與設定引導校準  
> 建立日期：2026-10-15  
> 所屬主計畫：N/A  
> 狀態：Completed  
> 模型：Gemini 3.8 Flash  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

針對下游純淨安裝環境反饋之 4 項缺陷進行根因導向之標準架構修復與 SSOT 文檔對齊：
1. **下載位置 404 與自更新路徑不同步**：確立方案 C，於 `yscb.py` 將官方核心單檔入口 `DEFAULT_SELF_UPDATE_URL` 與模組套件來源 `DEFAULT_PROVIDER_URL` 職責徹底解耦為獨立常數，廢除字串切割推導，保障自更新與初始化路徑 100% 準確。
2. **`release-target` CLI 語法解析差異**：補齊 `agents-workflow/contributes/core.json` 中 `target` 參數與 `target_tier` (`--proj` / `--project`) 宣告，重構 `scripts/cli.py:release_target`，雙向相容 `--add <target>` / `add <target>` 與 `--remove <target>` / `remove <target>`，並加入布林型別防禦。
3. **知識庫空間設定 SSOT 衝突**：確定 `spaces` 為宣告式擴充點之 SSOT 屬於 `contribute.json`，校準 `README.md`、`source/knowledge-db/README.md`、`manifest.json` 與 `docs/knowledge-db/contributes_guide.md`，消除引導矛盾。
4. **切換 Target 誤刪 `AGENTS.md`**：於 `ReleasePublisher` 實作非破壞性純文字軟剝離演算法 (`_soft_unmerge_agents_text`)；切換 Target 觸發陳舊檔案清理時，僅精準剝離 YSCB 託管標記區塊，若包含使用者自訂規範則就地寫回保留且絕不刪檔，唯有純預設空樣板時方安全物理刪除。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `yscb.py` | Modify | 拆分 `DEFAULT_PROVIDER_URL` 與 `DEFAULT_SELF_UPDATE_URL`，重構 `_resolve_self_update_target_url` 與 `cmd_self_update` |
| `ys_codebase/source/agents-workflow/contributes/core.json` | Modify | 補齊 `release-target` 契約：`target` 引數、`target_tier` (`--proj` / `--project`) 選項與使用範例 |
| `ys_codebase/source/agents-workflow/scripts/cli.py` | Modify | 重構 `release_target`，雙向相容 `--add / add` 與 `--remove / remove`，防禦布林滲漏 |
| `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` | Modify | 實作 `_soft_unmerge_agents_text` 軟剝離演算法，於陳舊檔案清理中接入非破壞性保護 |
| `README.md` | Modify | 修正 3.3 節 `knowledge-db` 空間設定指引至 `config/knowledge-db/contribute.json` |
| `ys_codebase/source/knowledge-db/README.md` | Modify | 修正快速上手與 Section 5，明確區分運作組態 (`config.project.json`) 與自訂空間 (`contribute.json`) |
| `ys_codebase/source/knowledge-db/manifest.json` | Modify | 修正 `onboarding` 第一條引導至 `config/knowledge-db/contribute.json` |
| `docs/knowledge-db/contributes_guide.md` | Modify | 校準覆蓋機制公式與檔案路徑至 `contribute.json` |
| `docs/core/DESIGN_NOTES.md` | Modify | 登錄 `[DN-28]` 宿主自更新 URL 與套件 Provider URL 職責分離決策 |
| `docs/agents-workflow/DESIGN_NOTES.md` | Modify | 登錄 `[DN-AW-16]` 根目錄規範入口檔軟剝離 (Soft-Unmerge) 與自訂內容非破壞保護 |
| `CHANGELOG.md` | Modify | 追加本計畫結案成果摘要與技術細節 |
| `ys_codebase/source/core/tests/test_cli_router.py` | Modify | 新增 FT-01 單元測試 `test_self_update_url` |
| `ys_codebase/source/core/tests/test_distribution_lifecycle.py` | Modify | 對齊 FT-01 測試斷言為 Scheme C 解耦常數 |
| `ys_codebase/source/agents-workflow/tests/test_targets.py` | Modify | 新增 FT-02 & FT-03 雙向 CLI 語法測試 `test_ft_05_release_target_cli_syntax` |
| `ys_codebase/source/agents-workflow/tests/test_publisher.py` | Modify | 新增 FT-04 軟剝離演算法測試與 FT-05/FT-06 整合保護測試 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：
  - FT-01 (`test_self_update_url` & `test_resolve_self_update_url`): **Passed**
  - FT-02 & FT-03 (`test_ft_05_release_target_cli_syntax`): **Passed**
  - FT-04 (`test_ft_15_soft_unmerge_agents_text`): **Passed**
  - FT-05 & FT-06 (`test_ft_16_prune_stale_agents_md`): **Passed**
  - RT-01 (`python yscb.py dev test --all`): **562/562 全庫測試 100% 通過 (16.79s)**
- **實機 UX / 人工驗證**：
  - UX-01: **[跳過/免測]**（開發者顯式指示免測）

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | [PASS] 已追加發布摘要 | 完整記錄 4 項修復重點與全模組測試結果 |
| **中觀 (Meso)** | `docs/core/DESIGN_NOTES.md` | [PASS] 已登記 `[DN-28]` | 詳載宿主自更新 URL 與套件 Provider URL 職責分離決策與防禦宣告 |
| **中觀 (Meso)** | `docs/agents-workflow/DESIGN_NOTES.md` | [PASS] 已登記 `[DN-AW-16]` | 詳載規範入口檔軟剝離保護決策與空樣板回收機制 |
| **中觀 (Meso)** | `docs/knowledge-db/contributes_guide.md` | [PASS] 已校準路徑 | 覆蓋優先權公式對齊 `config/knowledge-db/contribute.json` |
| **中觀 (Meso)** | `README.md` & `source/knowledge-db/README.md` | [PASS] 已校準指引 | 快速上手與空間配置對齊 `contribute.json`，消除與 `config.project.json` 混淆 |
| **微觀 (Micro)** | `yscb.py` / `publisher.py` / `cli.py` Docstrings | [PASS] 100% 對齊 | 函式 Docstrings 明確標註職責、演算法行為與參數約定 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
fix(core,agents-workflow,knowledge-db): resolve clean install onboarding feedback and prevent AGENTS.md deletion

- Decouple DEFAULT_SELF_UPDATE_URL and DEFAULT_PROVIDER_URL in yscb.py (DN-28)
- Support bi-directional release-target CLI syntax (--add/add, --remove/remove) and --proj flag
- Implement _soft_unmerge_agents_text in ReleasePublisher to protect user-authored standards (DN-AW-16)
- Align knowledge-db spaces configuration SSOT to config/knowledge-db/contribute.json across documentation
- Add comprehensive automated unit and regression tests (562/562 passed)
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify` 驗證 100% Passed。
- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成。

