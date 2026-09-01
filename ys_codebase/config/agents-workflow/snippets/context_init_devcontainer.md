## 🖥️ Dev Container / IDE 終端執行特性與防呆指南 (Execution Guardrails)

在 Dev Container 與 IDE Agent 控制平面環境下執行 CLI 指令時，遵循以下通訊與終端紀律：

1. **代碼原生執行效能保證**：
   - `yscb.py` 採用同進程動態分發架構，全模組 CLI 本機執行時間均在 **sub-100ms（86 毫秒級）** 內完成，代碼層無通訊阻塞。
2. **常駐終端綁定防呆 (Persistent Terminal)**：
   - 調用終端命令工具時，優先指定並重用常駐終端現場（如 `RunPersistent: true` 與對應 `RequestedTerminalID`），避免每次呼叫建立臨時 Ephemeral PTY 子進程帶來的冷啟動開銷。
3. **同步等待門檻設定 (Sync Wait Threshold)**：
   - 命令調用之同步等待時間建議給予充足餘裕（如 `WaitMsBeforeAsync: 10000`），防止秒級指令在容器端冷握手時因邊界判定被 IDE 自動誤掛起至背景 Task 隊列。
