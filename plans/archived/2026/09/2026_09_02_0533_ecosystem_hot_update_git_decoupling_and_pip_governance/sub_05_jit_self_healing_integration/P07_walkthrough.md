# 成果展示與結案報告 (Walkthrough)

> 功能名稱：sub_05_jit_self_healing_integration  
> 建立日期：2026-09-04  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Completed  
> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **微內核生命週期總線解耦 (`core.events`)**：建立獨立事件總線模組，提供 `broadcast(event_name, context, emit_module, search_roots)`，徹底移除 `Engine.act_broadcast_event` 重型門面，達成冷啟動與微內核解耦。
  2. **標準 Hook 尋址契約**：確立 `module://<module>/scripts/hook.<Sender>.py` 格式（如 `hook.core.py`, `hook.dev.py`），支援 `on_{event}` 與 `{event}` 雙向匹配。
  3. **宿主生命週期管線整合 (`yscb.py`)**：於命令分發前置執行微環境注入、運行端自癒與 `pre_cli_dispatch` 廣播；分發後執行 `post_cli_dispatch` 廣播與更新提示，自舉指令（`init`, `restore`, `bootstrap`）自動短路。
  4. **模組 Ad-hoc 攔截清理**：`agents-workflow` 的 `ensure_jit_release` 遷移至 `hook.core.py::on_pre_cli_dispatch`，並從 `scripts/cli.py` 徹底剔除 Ad-hoc 入口攔截。
  5. **沙盒跑測總線收斂**：`dev.testing.sandbox` 移除重複之 `_dispatch_test_hooks`，全面改呼叫 `core.events.broadcast(..., emit_module="dev")`。
  6. **事件清冊中繼資料與 CLI**：擴充 `contributes.events: list[{"<name>": "description"}]` 規範與 `source/core/contribute.json`，實作 `python yscb.py event list` CLI 指令。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/events.py` | New | 微內核獨立事件總線，提供 `broadcast()` 與 `get_contributed_events()` |
| `ys_codebase/source/core/core/__init__.py` | Modify | 匯出 `events` 模組供微內核與宿主直接導入 |
| `ys_codebase/source/core/core/engine.py` | Modify | 徹底移除 `act_broadcast_event` 舊門面，內部 `on_reload` 改調用 `core.events.broadcast` |
| `ys_codebase/source/core/core/installer.py` | Modify | 內部事件 `on_installed`、`on_update`、`on_remove` 改調用 `core.events.broadcast` |
| `ys_codebase/source/core/contribute.json` | Modify | 宣告 `core` 模組派送之事件清冊中繼資料 |
| `ys_codebase/source/core/contributes.format.md` | Modify | 增補第 3.3 節 `events` 擴充宣告格式手冊 |
| `ys_codebase/source/core/scripts/cli.py` | Modify | 增加 `event list` CLI 分發常式 |
| `ys_codebase/source/core/tests/test_engine.py` | Modify | 適配 `act_broadcast_event` 門面移除，改調用 `events.broadcast` |
| `ys_codebase/source/core/tests/test_events_pipeline.py` | New | 覆蓋 FT-01~08 與 ET-01~05 完整單元測試清單 |
| `yscb.py` | Modify | 整合前置 `_ensure_jit_lifecycle_pre`、後置 `_ensure_jit_lifecycle_post`，新增 `cmd_event` |
| `ys_codebase/source/agents-workflow/scripts/hook.core.py` | Modify | 實作 `on_pre_cli_dispatch` 觸發 `ensure_jit_release()` |
| `ys_codebase/source/agents-workflow/scripts/cli.py` | Modify | 徹底移除入口處 Ad-hoc 的 `ensure_jit_release()` 攔截邏輯 |
| `ys_codebase/source/agents-workflow/tests/test_jit_release.py` | Modify | 增加 FT-04 與 FT-05 單元測試 |
| `ys_codebase/source/dev/dev/testing/sandbox.py` | Modify | 移除 `_dispatch_test_hooks`，改呼叫 `core.events.broadcast(..., emit_module="dev")` |
| `ys_codebase/source/dev/dev/testing/requirement.py` | Modify | 強化 `@require` 裝飾器支援測試類別與繼承檢查 |
| `ys_codebase/source/dev/dev/testing/runner.py` | Modify | 測試過濾回退支援類別層級之 `__requirement__` 屬性 |
| `ys_codebase/source/dev/tests/test_sandbox.py` | Modify | 增加 FT-06 驗證沙盒透過 `core.events.broadcast` 觸發 hook |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：`384/384 Passed (100.0%)`，0 Failed, 0 Skipped（`python yscb.py dev test --all -q`）。
- **實機 UX / 人工驗證**：開發者指示免測，全部驗收項目通過。
- **Dogfooding 閉環狀態**：
  - `core`: `1.0.3.1` (Released & Updated)
  - `dev`: `1.0.1.12` (Released & Updated)
  - `agents-workflow`: `1.0.3.6` (Released & Updated)

---

## 4. 📚 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **中觀手冊** | `docs/core/lifecycle_and_hooks.md` | ✅ 已同步 | 更新命名空間 Hook 模型、`broadcast()` 調用與 `pre_cli_dispatch` / `post_cli_dispatch` 規範 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | ✅ 已同步 | 登記 `[DN-18]` 微內核獨立事件總線 (`core.events`) 與 Engine 徹底解耦之設計理由與防禦規範 |
| **擴充手冊** | `source/core/contributes.format.md` | ✅ 已交付 | 定義 Section 3.3 事件清冊宣告格式 `list[{"<name>": "description"}]` |
| **模組組態** | `source/core/contribute.json` | ✅ 已交付 | 宣告 `pre_cli_dispatch`、`post_cli_dispatch`、`on_reload` 等生命週期事件清冊 |
| **測試計畫** | `plans/.../sub_05_jit_self_healing_integration/P06_test_plan.md` | ✅ 已交付 | FT-01~08、ET-01~05、RT-01 全數 Passed，記錄 UX 驗收 |
| **發布日誌** | `plans/.../sub_05_jit_self_healing_integration/changelog.md` | ✅ 已交付 | 記錄子計畫從討論、設計、實作、跑測至版本晉升結案歷程 |

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(core,agents-workflow,dev): decouple microkernel event pipeline and integrate jit lifecycle

- Introduce core.events module with broadcast() and get_contributed_events()
- Remove Engine.act_broadcast_event facade and decouple lifecycle events
- Integrate pre_cli_dispatch and post_cli_dispatch lifecycle hooks in yscb.py
- Migrate agents-workflow JIT self-healing into hook.core.py::on_pre_cli_dispatch
- Converge dev sandbox hook dispatching to core.events.broadcast
- Add python yscb.py event list CLI and contributes.events format specification
- Pass 384/384 tests and bump core@1.0.3.1, dev@1.0.1.12, agents-workflow@1.0.3.6
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **結構與註解檢核**：SOP 0~7 產物（P00~P07）齊全無缺失，追溯鏈完備。
