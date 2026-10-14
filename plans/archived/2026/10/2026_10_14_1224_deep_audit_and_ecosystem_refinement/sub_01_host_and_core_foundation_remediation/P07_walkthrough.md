# 成果展示與結案報告 (Walkthrough)

> 功能名稱：sub_01_host_and_core_foundation_remediation  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Completed  
> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **Contributes 宣告與 CLI 隔離修復**：修正 `core/_format.json` 與 `core.json` 契約宣告，為 `ContributesAggregator` 導入 `__modules__` 雙層分桶機制，徹底解決多模組同名指令衝突（CLI Guild 與擴充點隔離）。
  2. **語意 URI 高頻快取與安全邊界強化**：在 `core.uri` 引入 `(yscb_dir, mtime)` 極速記憶體快取（$< 0.1\text{ms}$ 命中延遲）；修正 `to_uri()` 反向推導支援 `config://`；以 `target_base + os.sep` 精準阻斷同前綴兄弟目錄穿越攻擊 (EC-05)。
  3. **微內核基礎服務健壯化**：安全清理 `core.engine` 重複死代碼；統一委派 `PipManager` 與 `IdeProjector` 至標準根目錄與 `.gitignore` 生成器；`_maybe_auto_spawn_server` 雙層路徑讀取相容本機與測試環境；修復 `semver.py` 含預發布版本時保留 revision。
  4. **宿主腳本薄化與 CLI 參數增強**：`yscb.py` 強化 `init` / `self-update` 之空格與等號傳參支援（`-p <val>` / `--provider=<val>`）；對無效來源補齊 `FileNotFoundError` 防呆。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/contributes/_format.json` | Modify | 對齊 `ArgDef.required` 預設值為 `"bool? = true"` |
| `ys_codebase/source/core/contributes/core.json` | Modify | 補齊 `contributes list --module` 與 `restore --provider` 選項宣告並清理多餘鍵 |
| `ys_codebase/source/core/core/semver.py` | Modify | `VersionTuple.__str__` 在包含 prerelease 時完整保留非零 revision |
| `ys_codebase/source/core/core/commands/registry.py` | Modify | `CommandsRegistry` 同時支援 `choice` 與 `choices` 語法相容 |
| `ys_codebase/source/core/core/uri.py` | Modify | 記憶體快取 `_SCHEMES_CACHE`、`config` 反向解析、安全邊界 `target_base + os.sep` |
| `ys_codebase/source/core/core/__init__.py` | Modify | 補齊 PEP 562 延遲載入映射與 `__all__` 導出清單 |
| `ys_codebase/source/core/core/contributes.py` | Modify | `ContributesAggregator` 引入 `__modules__` 雙層分桶機制 |
| `ys_codebase/source/core/core/providers.py` | Modify | `get_agents_cli_guild` 優先遍歷 `__modules__`，支援舊版平鋪結構容錯退化 |
| `ys_codebase/source/core/core/engine.py` | Modify | 清理重複定義死代碼，修復 `module.mirror://` 語意 URI 解析 |
| `ys_codebase/source/core/core/pip_manager.py` | Modify | 統一委派至 `core.uri._get_yscb_root()`，消弭重複解析邏輯 |
| `ys_codebase/source/core/core/ide_projector.py` | Modify | 委派根目錄解析與 `.gitignore` 標記維護 |
| `ys_codebase/source/core/core/commands/dispatcher.py` | Modify | `_maybe_auto_spawn_server` 雙層路徑讀取相容本機覆蓋與臨時目錄測試 |
| `ys_codebase/source/core/core/installer.py` | Modify | `cmd_list` 支援 remote/provider，`cmd_update` 支援 zip/index.json 本地探測 |
| `yscb.py` | Modify | 強化 `init`/`self-update` 空格與等號雙語法參數解析，補齊無效來源異常防呆 |
| `ys_codebase/source/core/tests/test_uri.py` | Modify | 新增同前綴目錄穿越阻斷斷言與 VFS 快取驗證 |
| `docs/core/DESIGN_NOTES.md` | Modify | 登記 `[DN-26]` 雙層分桶指令聚合與語意 URI 記憶體快取架構決策 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：
  - `core` 模組全量測試：**192 Total, 192 Passed, 0 Failed (100% Ready)**
  - 全生態系 5 大模組回歸：**Pass: 550 (100.0%), Fail: 0, Skip: 0**
- **實機 UX / 人工驗證**：
  - `UX-01`: `python yscb.py contributes list --module=core` 成功輸出 core 註冊之 3 大擴充點（uri_schemes, commands, events）。
  - `UX-02`: `python yscb.py uri resolve config://core/config.project.json` 成功解析實體絕對路徑，反向 `to-uri` 亦雙向閉環。

---

## 4. 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | [PASS] 已交付 | 記錄 `[DN-26]` 雙層分桶指令聚合與語意 URI 記憶體快取決策 |
| **主計畫關聯** | `plans/.../umbrella_overview.md` | [PASS] 已交付 | 更新 sub_01 推進狀態至 Completed |

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
fix(core,host): remediate contributes isolation, uri memory caching, and cli parsing

- Fix ContributesAggregator to support __modules__ dual-bucket isolation
- Add in-memory mtime cache and directory traversal sandbox guards to core.uri
- Align ArgDef.required schema and CommandsRegistry choices handling
- Clean dead code in AtomicEngine and support module.mirror:// URIs
- Enhance yscb.py CLI argument parsing with space/equal separator flexibility
- Register [DN-26] design decision in docs/core/DESIGN_NOTES.md
- Ensure 100% green tests across core (192/192) and ecosystem (550/550)
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **結構與註解檢核**：`sub_01` 全套 P00 ~ P07、CHANGELOG 及追溯鏈皆已對齊閉環。

