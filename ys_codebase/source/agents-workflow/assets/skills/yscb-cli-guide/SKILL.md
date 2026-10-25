---
name: yscb-cli-guide
description: 規範 yscb (yscb.py) 命令列單行執行防呆、常駐 Server 守門、技能內建指令直跑與非常規指令 -h 按需自省機制，確保 CLI 呼叫合法安全。觸發情境：準備透過終端工具執行任何 yscb.py 指令前、查詢不熟悉之子命令語法或透過 -h 確認操作安全等級。排除情境：與 yscb 無關之一般作業系統指令、純靜態文檔閱讀或代碼語意檢索（代碼檢索改用 knowledge-db-search）。
---

# YSCB CLI 執行慣例與 `-h` 按需自省指南 (Agents CLI Guide)

凡 Agent 準備透過終端工具調用 `yscb` (`__${yscb.host://yscb.py}__`) 相關命令前，必須遵守本指南之單行防呆紀律與雙軌安全檢核機制。

```markdown
yscb-cli-guide 執行前檢核表：
- [ ] Step 1: 單行與引號防呆（無換行 `\n`、`--log`/`--note` 雙引號內無 `"` 或 `` ` ``）
- [ ] Step 2: 雙軌分流（技能內建標準指令直接執行；非常規指令或未知旗標先跑 `-h` 自省）
- [ ] Step 3: 權限守門（確認非未授權之 `[GATED]` 紅線指令，滿足 `[CONDITIONAL]` 前置約束）
```

---

## 1. 終端指令執行防呆慣例 (CLI Execution Conventions)

1. **指令單行化 (Single-Line Command Discipline)**：調用終端工具（如 `run_command`）**嚴禁字串夾帶換行 (`\n`) 或多行互動輸入**；多命令於 PowerShell 以 `;` 串接（Bash 以 `&&` 串接），複雜邏輯強制落檔後執行，嚴防 PTY 次級提示字元等待卡死。
2. **雙引號參數字串逃逸防呆 (Quote & Backtick Safeguard)**：調用帶有文字摘要參數之 CLI 指令（如 `plan verify --log "<摘要>"` 或 `todo add "<標題>" --note "<備註>"`）時，雙引號包裹之內文字串**嚴禁夾帶雙引號 `"` 或反引號 `` ` ``**（避免引發 Shell 命令替換或引號解析崩潰）；如需強調識別符、檔案或階段名稱，一律改用單引號 `'...'` 或方括號 `[...]`。
3. **常駐 Server 守門處置 (`[BLOCKER]` Daemon Handling)**：當專案安裝 `server` 模組且 `require_server_for_agents: true` 時，若執行 CLI 遭遇 `[BLOCKER] YSCB Persistent Server is not running`，應立即以終端工具背景常駐模式（例如設定 `IsDaemon: true` 或非阻塞背景等待）執行 `python __${yscb.host://yscb.py}__ server start --console` 啟動守護進程，隨後重試原指令。

---

## 2. 雙軌指令調用與 `-h` 按需自省 (2-Track Execution & JIT `-h` Inspection)

YSCB 全面採用 Progressive Disclosure（漸進式揭露），不再於技能內靜態傾倒全系統 CLI 大表，改採以下雙軌調用機制：

1. **軌跡 A — 技能內建指令免查直跑 (`Skill-Vetted Fast Pass`)**：
   - 凡於各工作流與工具技能（如 [`development-sop`](../development-sop/SKILL.md)、[`knowledge-db-search`](../knowledge-db-search/SKILL.md)、[`yscb-module-dev`](../yscb-module-dev/SKILL.md)、[`todo`](../todo/SKILL.md)、[`roadmap`](../roadmap/SKILL.md) 等）步驟中**已明確寫出完整語法的標準指令**（如 `plan verify`、`knowledge-db search`、`dev check`、`dev test`、`todo list` 等），均已預審為 `[SAFE]` 自主安全（或已由該技能內建確認節點守門），Agent **可直接執行，無須額外查表或跑 `-h`**。
2. **軌跡 B — 非常規指令／未知參數強制 `-h` 自省 (`Just-in-Time -h Inspection`)**：
   - 當準備調用**未在當前技能步驟中明文列出之指令**、**嘗試非標準選項旗標**、或**不確定某指令之安全等級與時序限制**時，**嚴禁盲目猜測參數**；必須先執行 `-h` / `--help` 按需自省：
     ```bash
     python __${yscb.host://yscb.py}__ <module> [command] [subcommand] -h
     ```
   - `yscb` 的 `-h` 輸出由核心 `HelpRenderer` 統一渲染，原生包含：
     - `Security   : [SAFE] / [CONDITIONAL] / [GATED]`（權限分級）
     - `ARGUMENTS` & `OPTIONS`（正交選項分組、必填屬性與型別）
     - `RECOMMENDED USAGE (Pros)`（推薦適用情境）
     - `RESTRICTIONS & GATES (Cons)`（禁止事項與前置守門條件）

---

## 3. 三級權限模型與 `[GATED]` 紅線家族 (Permission Tiers & Red-Line Families)

- **`[SAFE] 自主安全`**：唯讀檢索、狀態診斷、計畫校驗與沙盒測試指令，Agent 可依任務需求自主安全調用。
- **`[CONDITIONAL] 階段條件`**：具特定時序約束之指令，違反將浪費資源或破壞現場（例如：`dev test` 內部已自動整合記憶體同步，**嚴禁**在跑測前手動執行 `dev build`；`knowledge-db search` 已內建 JIT 增量索引，日常檢索**無須**手動執行 `knowledge-db index`）。
- **`[GATED] 授權守門（Default-Deny 紅線家族）`**：凡涉及環境套件異動、版本發布、清理覆寫或底層資料表操作之指令家族，**未獲開發者於當前對話輪次顯式授權前，絕對禁止主動執行**：
  - **核心環境與模組變更**：`install`（開發階段安裝 `<module>@build` 熱調試除外）、`remove`、`update`、`rollback`、`init`
  - **打包發布與版本晉升**：`dev release`、`agents-workflow release`（完成 `@build` 安裝後同步工作流產物除外）、`/bump-revision`
  - **工作流封存與快取抹除**：`agents-workflow plan archive`、`dev clean`、`knowledge-db clean`
  - **底層運維與破壞性指令**：任何帶有 `op-*` 前綴（如 `op-reindex`、`op-migrate`）或 `--force- clean/reset` 性質之指令

`__@{AGENTS_CLI_GUIDE}__`

---

## 常見踩坑指南 (Gotchas)

- **歷史授權不可跨任務沿用**：開發者在前一個任務授權過的 `[GATED]` 指令（如 `dev release`），不代表當前任務可自動再次執行；每次觸及 `[GATED]` 操作皆須重新取得當下確認。
- **切勿在跑測前手動 `dev build`**：`python __${yscb.host://yscb.py}__ dev test <module>` 已自動處理測試沙盒同步；`dev build` 僅供準備執行 `install <module>@build` 進行本機熱部署時使用。
