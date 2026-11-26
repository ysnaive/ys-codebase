# 計畫前置待辦來源清單 (Promoted TODOs)

> 主題：2026_11_25_1157_core_v2_observability_profiler  
> 建立日期：2026-11-25  
> 狀態：Active  
> 模型：Gemini 4 Neon (XHigh)  

---

## 立項待辦條目 (Promoted Items)

### [TODO-31] 消除 Core 2.0 daemon start --supervisor 啟動期雙重 WorkspaceKernel 建置與全掃雜湊熱點
- **建立日期**：2026-11-25
- **目標範疇**：`core_v2/source/core/core/surface/bootstrap/factory.py`
- **備忘與解法要點**：Windows -B 實測顯示 daemon start --supervisor 先於 CLI 會話建置一次 WorkspaceKernel 再於 run_deferred_daemon 重建一次且每次啟動全掃 .modules/core SHA-256，建議於 Wave B 瘦身時對 --supervisor 走輕量直啟路徑以縮短 Windows 冷啟動時間
