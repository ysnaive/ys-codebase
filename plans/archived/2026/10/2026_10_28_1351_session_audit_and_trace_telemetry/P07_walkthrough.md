# 成果展示與結案報告 (Walkthrough)

> 功能名稱：Session 隱形摩擦自檢技能與三級軌跡提取機制 (`session_audit_and_trace_telemetry`)  
> 建立日期：2026-10-28  
> 所屬主計畫：獨立計畫 (Standalone)  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **`core` 層級統一 CLI 飛行紀錄器 (`core/telemetry.py` & `dispatcher.py`)**：於微內核派發層攔截並寫入 `cache://core/telemetry.jsonl`（涵蓋 `ts`, `epoch`, `module`, `cmd`, `args`, `exit_code`, `duration_ms`, `mode`, `cwd`, `error_hint`），內建沙盒測試預設旁路、`--help` 與 `session-trace` 自身過濾，以及 512KB / 1,500 行滾動截斷。
  2. **`session-trace` 三級軌跡提取與五大摩擦訊號引擎 (`session_trace.py`)**：實作多 `release_targets` 尾行自指信標定錨（自動排除唯讀 Reviewer Subagent，多候選無信標拒絕盲猜）、Telemetry 時間窗自動切片、跨階段 `mtime` 對照 `changelog.md` 合規回寫消歧（`VALIDATED_BACKPROP` vs `SILENT_BACKPATCH`）、五大硬性摩擦訊號聚合與 Tier 3 逆向審訊保底。
  3. **`/session-audit` 初版技能與 `session-trace` CLI 導出**：註冊 `python yscb.py agents-workflow session-trace` 指令與 `session-audit` 唯讀自檢技能（含 `SESSION_AUDIT_STANDARDS` 錨點，全系統擴充至 18 個內建純 Skill 與 23 個 Stage 1 Token 錨點）。
  4. **衍生問題根治（原子替換殘留清理、Pylance 排除與沙盒狀態還原）**：擴充 `AtomicEngine` 自動清掃 `.old_*`/`.staging_*` 殘留目錄，`IdeProjector` 注入 `python.analysis.exclude` 排除 `**/.cache/**` 防止 Pylance 索引沙盒副本導致 RAM 暴增，並於 `YSCBTestCase` 完整還原 `uri` 記憶體變數。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/telemetry.py` | New | 實作 `cache://core/telemetry.jsonl` 飛行紀錄器、沙盒旁路、512KB 滾動截斷與讀取 API |
| `ys_codebase/source/core/core/__init__.py` | Modify | 匯出 `telemetry` 子模組 |
| `ys_codebase/source/core/core/commands/dispatcher.py` | Modify | 於 `dispatch()` 整合 Telemetry 寫入、`_try_hot_dispatch` 擷取 `error_hint`，並過濾 `.modules/` 下點號開頭目錄 |
| `ys_codebase/source/core/core/engine.py` | Modify | 新增 `_force_rmtree_with_retry` 與 `_cleanup_stale_swap_dirs`，清除 `.old_*` 與 `.staging_*` 殘留目錄 |
| `ys_codebase/source/core/core/ide_projector.py` | Modify | 新增 `python.analysis.exclude` 託管排除 `**/.cache/**` 等目錄，防堵 Pylance 索引沙盒副本暴衝記憶體 |
| `ys_codebase/source/core/core/installer.py` | Modify | 移除 `_restore_module_package` 對 `.build/<mod>` 裸目錄之誤配候選 |
| `ys_codebase/source/core/core/vfs/os_backend.py` | Modify | `_safe_copytree` 自動略過 `.old_*` 與 `.staging_*` 暫存目錄 |
| `ys_codebase/source/dev/dev/testing/case.py` | Modify | `setUp`/`tearDown` 保存並還原 `uri._active_host_dir`、`_active_yscb_dir` 與 `_active_module_context` |
| `ys_codebase/source/dev/dev/testing/sandbox.py` | Modify | `create_sandbox` 略過點號開頭暫存目錄與 `mock_*` 測試套件 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/session_trace.py` | New | 實作 `SessionTraceEngine` 三級軌跡提取、尾行信標定錨、`mtime` 消歧與五大摩擦訊號引擎 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/__init__.py` | Modify | 匯出 `SessionTraceEngine`、`FrictionSignal` 與 `SessionTraceReport` |
| `ys_codebase/source/agents-workflow/agents_workflow/__init__.py` | Modify | 公開匯出 `SessionTraceEngine` 等類別 |
| `ys_codebase/source/agents-workflow/scripts/cli.py` | Modify | 實作 `session_trace` 與 `cmd_session_trace` CLI 入口 |
| `ys_codebase/source/agents-workflow/assets/skills/session-audit/SKILL.md` | New | 建立初版 `/session-audit` 唯讀事後自檢技能 |
| `ys_codebase/source/agents-workflow/assets/skills/skill-creator/references/extension-guide.md` | Modify | 更新全系統 23 個 Stage 1 Token 錨點地圖（納入 `SESSION_AUDIT_STANDARDS`） |
| `ys_codebase/source/agents-workflow/contributes/core.json` | Modify | 註冊 `session-trace` CLI 指令與選項 Schema |
| `ys_codebase/source/agents-workflow/contributes/agents-workflow.json` | Modify | 註冊 `session-audit` Skill 導出與 `SESSION_AUDIT_STANDARDS` Token |
| `ys_codebase/source/agents-workflow/contributes/_manifest.md` | Modify | 同步更新 18 個內建純 Skill 與 22 個模組內建 Token 清冊 |
| `ys_codebase/source/core/tests/test_cli_router.py` | Modify | 新增 `test_ft_11_telemetry_flight_recorder_and_sandbox_isolation` 單元與邊界測試 |
| `ys_codebase/source/core/tests/test_engine.py` | Modify | 新增 `test_atomic_swap_dir_cleans_stale_old_and_staging_remnants` 測試 |
| `ys_codebase/source/core/tests/test_platform.py` | Modify | 為 `spawn_detached` 測試補齊 `try...finally` 進程樹清理保護 |
| `ys_codebase/source/agents-workflow/tests/test_plans_toolchain.py` | Modify | 新增 `test_ft_15_session_trace_beacon_anchoring_and_five_friction_signals` 完整測試 |
| `ys_codebase/source/agents-workflow/tests/test_compiler.py` | Modify | 更新 18 個內建純 Skill 與 23 個全系統 Stage 1 Token 錨點合規斷言 |
| `docs/core/README.md`, `docs/agents-workflow/README.md`, `docs/agents-workflow/user_guide.md`, `docs/agents-workflow/DESIGN_NOTES.md`, `CHANGELOG.md` | Modify | 完成三層文檔同步更新與 `[DN-AW-17]` 登錄 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：
  - `python yscb.py contributes check`：15/15 files valid (`PASSED`)
  - `python yscb.py dev check core` / `dev check dev` / `dev check agents-workflow`：全數 `PASSED`
  - `python yscb.py dev test core -q`：**195/195 (100.0% Passed)**
  - `python yscb.py dev test dev -q`：**79/79 (100.0% Passed)**
  - `python yscb.py dev test agents-workflow -q`：**134/134 (100.0% Passed)**
- **實機 UX / 人工驗證**：`UX-01` 已由開發者確認 **`[測試通過]`**，且通過支柱三 Pre-UX 獨立盲審（`REVIEW_STATUS: PASSED`）。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | [CHANGELOG.md](../../CHANGELOG.md) | `Completed` | 已於頂部新增 `2026_10_28_1351_session_audit_and_trace_telemetry` 完整變更摘要 |
| **中觀 (Meso)** | [docs/core/README.md](../../docs/core/README.md), [docs/agents-workflow/README.md](../../docs/agents-workflow/README.md) | `Completed` | 新增 §3.5 `core.telemetry` 飛行紀錄器、§5.3 `python.analysis.exclude`、`session-audit` 技能與 `session-trace` CLI 速查 |
| **中觀 (Meso)** | [docs/agents-workflow/user_guide.md](../../docs/agents-workflow/user_guide.md) | `Completed` | 新增 §7.5 `/session-audit` 與 `session-trace` 三級軌跡提取操作指南 |
| **中觀 (Meso)** | [docs/agents-workflow/DESIGN_NOTES.md](../../docs/agents-workflow/DESIGN_NOTES.md) | `Completed` | 登記 `[DN-AW-17]` 多宿主 `.jsonl` 尾行自指信標定錨與跨階段 `mtime` 回寫消歧機制 |
| **微觀 (Micro)** | `core/telemetry.py`, `session_trace.py` 公開 API Docstrings | `Completed` | 完整標註型別簽名、參數契約与異常安全防禦說明 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(core,agents-workflow): add CLI flight telemetry, session-trace engine, and /session-audit skill

- Add zero-coupling CLI flight recorder in core/telemetry.py writing to cache://core/telemetry.jsonl with 512KB rotation and sandbox bypass
- Implement SessionTraceEngine in agents-workflow with 3-step transcript beacon anchoring, plan mtime vs changelog disambiguation, and 5 friction signals
- Export /session-audit read-only post-mortem skill and SESSION_AUDIT_STANDARDS token anchor
- Harden AtomicEngine directory swap cleanup, IdeProjector python.analysis.exclude, and YSCBTestCase URI state restoration
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

