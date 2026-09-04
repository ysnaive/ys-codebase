# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_05_jit_self_healing_integration  
> 建立日期：2026-09-04  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 「接下來拆分子計畫，不要混雜，後續採增量添加，不預設進度，先在新進入 sub-05: JIT 熱更新、自癒機制整合」
  - 核心範疇選擇：「(Recommended) 宿主入口生命週期管線整合：在 yscb.py 建立統一 JIT 生命週期守門，依序排程與收斂 contributes、release-targets、venv 與運行端之熱自癒」
  - 開發者指示：「希望添加標準 hook event，不再由各模組自行攔截 cli，而是有正規觸發管道」
  - 開發者決策修正：「不要採用 contributes 形式，採用標準 core event 管線」
- **核心目標**：
  1. **宿主入口生命週期管線收斂**：在 `yscb.py` 建立統一、標準、輕量 (<2ms) 的 CLI 生命週期調度管線，整合各模組既有之 JIT 嗅探與自癒守門。
  2. **標準 Core Event 管線擴充**：基於微內核既有的標準 Event 機制（`act_broadcast_event` 與 `scripts/hook.core.py`），擴充正規生命週期事件（如 `on_pre_cli_dispatch` 與 `on_post_cli_dispatch`），由宿主在分發前後統一廣播。
  3. **廢除模組 Ad-hoc 入口攔截**：消除各模組自行在各自 `cli.py` 內部撰寫前置侵入式攔截（例如 `agents-workflow` CLI 前置調用 `ensure_jit_release()`）的碎片化實作，改由 `hook.core.py` 監聽標準事件。
- **邊界排除 (Explicitly Excluded)**：
  - 嚴格維持子計畫職責單一，不混入非相關之 Pip 相依性遷移或沙盒檢查。
  - 嚴禁採用 `contributes` 形式宣告 Hook，維持 `contributes` 純粹作為資料擴充點，由標準 `core` 事件管線獨立治理生命週期。
  - 嚴禁引入背景常駐 Daemon 進程或重型監控，全管線嚴格維持純 Python 標準庫與極低延遲 (<2ms) 守則。
  - 主計畫後續子計畫不預先規劃或預設進度，維持增量添加。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 子計畫職責解耦與增量演進原則**：
  廢除原 sub_05 混雜相依性宣告、加速外掛與沙盒檢查之複合規劃；將 sub_05 嚴格聚焦於「JIT 熱更新與自癒機制整合（含標準 Core Event 管線）」，後續計畫依實際需求增量開立。
- **[P00:DR-02] 標準 Core Event 生命週期管線（非 contributes 形式）**：
  嚴禁在 `contribute.json` 或 `contributes.merged.json` 中擴充 Hook 節點。全面採用微內核既有的標準 `core event` 架構（`act_broadcast_event("core", event_name, ctx)` 搭配各模組 `scripts/hook.core.py` 處理函式），新增 `on_pre_cli_dispatch` 與 `on_post_cli_dispatch` 等標準生命週期事件，由宿主 `yscb.py` 在分發前/後直接透過 `core` 管線廣播。
- **[P00:DR-03] 宿主 JIT 自癒管線收斂層級與 Ad-hoc 清理**：
  宿主分發管線依序處理：
  1. 基礎環境探測：私有微環境路徑注入與運行端完整性檢查 (`_is_modules_dirty`)。
  2. 前置事件廣播：調用 `core` 廣播 `on_pre_cli_dispatch` 事件（`agents-workflow` 等模組於 `hook.core.py` 接收並執行 `ensure_jit_release()` 等自癒動作）。
  3. 模組分發執行：調用目標模組 CLI。
  4. 後置事件處理：非阻塞檢查（如 12hr 來源更新提示或 `on_post_cli_dispatch` 事件）。
  5. 徹底清理各模組（如 `agents_workflow/scripts/cli.py`）內部自行攔截的 Ad-hoc 程式碼。

---

## 3. 開放議題與確認紀錄

- [x] 確認 Hook Event 宣告格式：不採用 contributes 形式，全面遵循微內核標準 `core` 事件管線與 `hook.core.py`。
- [x] 確認生命週期事件命名：確立為 `pre_cli_dispatch` 與 `post_cli_dispatch`。
- [ ] 確認 `core` 模組在 `yscb.py` 同進程分發中的調用介面（例如提供輕量 `core.events.broadcast("pre_cli_dispatch")` 或直接透過 `core.engine` 調用）。


