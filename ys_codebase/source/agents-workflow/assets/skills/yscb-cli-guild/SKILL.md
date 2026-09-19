---
name: yscb-cli-guild
description: YSCB CLI 指令防呆與語意情境對照指南。當需要查詢、驗證或執行 yscb 命令列指令、查閱 CLI 權限矩陣（自主安全/階段條件/授權守門）與防呆規範時觸發。
---

# YSCB CLI 指令防呆與語意情境對照指南 (Agents CLI Guild)

本手冊彙整 YSCB 生態系各模組之 CLI 指令呼叫規範、語意情境矩陣與 Default-Deny 守門約束。

---

## 1. 終端指令防呆紀律 (CLI Execution Safeguard)

1. **指令單行化**：調用終端工具（如 `run_command`）**嚴禁字串夾帶換行 (`\n`)**；多命令以 `&&` 串接，複雜邏輯強制落檔後執行，嚴防 PTY 次級提示字元等待卡死。
2. **常駐終端現場綁定 (RunPersistent)**：調用終端指令時，必須使用 `RunPersistent: true`（若環境工具支援），且指令格式須為單行字串，避免頻繁建立暫態 Ephemeral PTY 子進程帶來的冷啟動開銷與狀態遺失。

---

## 2. CLI 權限分級矩陣與情境對照 (Permission Matrix)

<!-- YSCB_AGENTS_CLI_GUILD_BEGIN -->
`__@{AGENTS_CLI_GUILD}__`
<!-- YSCB_AGENTS_CLI_GUILD_END -->
