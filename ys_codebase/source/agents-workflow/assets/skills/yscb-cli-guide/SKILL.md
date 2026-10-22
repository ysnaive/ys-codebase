---
name: yscb-cli-guide
description: 檢索與核對 yscb (yscb.py) 命令列子命令、參數旗標、三級權限矩陣 ([SAFE] 自主安全 / [CONDITIONAL] 階段條件 / [GATED] 授權守門) 及單行終端執行防呆規則，確保 CLI 呼叫合法安全。觸發情境：準備透過終端工具執行任何 yscb.py 指令前、查詢可用子命令語法或確認操作是否需開發者授權。排除情境：與 yscb 無關之一般作業系統指令、純靜態文檔閱讀或代碼語意檢索（代碼檢索改用 knowledge-db-search）。
---

# YSCB CLI 指令防呆與語意情境對照指南 (Agents CLI Guide)

本手冊彙整 YSCB 生態系各模組之 CLI 指令呼叫規範、語意情境矩陣與 Default-Deny 守門約束。凡 Agent 準備透過終端工具調用 `yscb` 相關命令前，必須遵守本指南之防呆與權限分級規則。

---

## 1. 終端指令防呆紀律 (CLI Execution Safeguard)

1. **指令單行化（Single-Line Command Discipline）**：調用終端工具（如 `run_command`）**嚴禁字串夾帶換行 (`\n`) 或多行互動輸入**；多命令以 `&&` 串接，複雜邏輯強制落檔後執行，嚴防 PTY 次級提示字元等待卡死。
2. **常駐終端現場綁定 (RunPersistent)**：調用終端指令時，必須使用 `RunPersistent: true`（若環境工具支援），且指令格式須為單行字串，避免頻繁建立暫態 Ephemeral PTY 子進程帶來的冷啟動開銷與狀態遺失。
3. **執行前參數確認**：若不確定某個 `yscb` 子命令的參數格式，優先參考下方動態注入之指令對照表，或先執行唯讀 `--help` 查詢，嚴禁盲目猜測旗標（Flags）。

---

## 2. CLI 權限分級矩陣與情境對照 (Permission Matrix)

- **`[SAFE] 自主安全`**：唯讀查詢、狀態診斷、計畫檢核與沙盒單元跑測指令，Agent 可依任務需求自主安全調用。
- **`[CONDITIONAL] 階段條件`**：具特定前置時序約束之指令，必須嚴格滿足表中「限制與守門條件」方可調用。
- **`[GATED] 授權守門`**：涉及版本晉升 (`bump-*`)、正式發布 (`release*`)、環境變更或刪除之高風險指令，**未獲開發者於當前對話顯式授權前絕對禁止主動執行**（Default-Deny）。

<!-- YSCB_AGENTS_CLI_GUIDE_BEGIN -->
`__@{AGENTS_CLI_GUIDE}__`
<!-- YSCB_AGENTS_CLI_GUIDE_END -->

---

## 常見踩坑指南 (Gotchas)

- **歷史授權不可跨任務沿用**：開發者在前一個任務授權過的 `[GATED]` 指令（如 `release`），不代表當前任務可自動再次執行；每次觸及 `[GATED]` 操作皆須重新取得當下確認。
- **切勿手動修改 `<!-- YSCB_AGENTS_CLI_GUIDE_BEGIN -->` 區塊內的生成表格**：該區塊於編譯發布時由錨點動態注入，若需新增 CLI 指令說明，應於對應模組之 `contributes/*.json` 中宣告。
