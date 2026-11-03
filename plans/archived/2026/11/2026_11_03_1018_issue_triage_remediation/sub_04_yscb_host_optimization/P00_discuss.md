# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：唯一宿主 `yscb.py` 五維度靜態診斷與收斂評估  
> 建立日期：2026-11-03  
> 所屬主計畫：2026_11_03_1018_issue_triage_remediation  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Research  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：「我想先排查一下，經過這幾次更新，唯一宿主也膨脹不少，對其做一次 `/code-optimizer`」、「對外函式 Mode B，對內函式 Mode A，先僅調研」
- **核心目標**：針對唯一單檔自舉宿主 `yscb.py`（現行 1,526 行，43 個頂層函式）執行 `D1~D5` 五維度靜態診斷與 `S1~S6` 重構處方評估，產出 `R01_code_optimization_audit.md`，暫不改動程式碼。
- **既有組件復用與查重 (Reuse Discovery)**：盤點 `yscb.py` 內部跨函式重複之網路/本地 Provider `index.json` 載入、HTTP Proxy Bypass 讀取、就地原子目錄同步與階段化自舉流程。
- **邊界排除 (Explicitly Excluded)**：
  - `S6` 物理拆檔天然排除（`yscb.py` 受單檔零外部依賴自舉宿主與 `__file__` 自指紋校驗剛性約束，嚴禁拆散為多檔案）。
  - 本階段僅執行靜態調研並落檔 `R01_code_optimization_audit.md`，待開發者裁決流轉出口。
- **架構影響範圍**：`yscb.py`（及若後續選用出口 ① 時，直接測試 `yscb._*` 內部私有符號之 `ys_codebase/source/core/tests/`）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** **三維度定錨基準**：
  1. **檢視範圍**：`File Scope`（單一檔案 `yscb.py`）。
  2. **生命週期與相容性模式**：**對外公開函式與常數採 `Mode B`（嚴守向下相容）**，保留 `main`、`cmd_init`、`cmd_self_update`、`cmd_restore`、`load_config`、`dispatch_module`、`__version__`、`CONFIG_FILENAME`、`DEFAULT_PROVIDER_URL`、`LEGACY_PROVIDER_URLS`、`DEFAULT_SELF_UPDATE_URL` 簽名與行為 100% 相容；**對內私有輔助函式（`_*`）與零生產調用之過時殼層採 `Mode A`（收斂期 / 允許破壞性清理）**，強制收斂為單一正統實現並消除 1 行轉發垃圾與重複樣板。
  3. **代理執行軌道**：`[軌道 1：純主代理內聯執行]`（0 子代理冷啟動開銷）。

---

## 3. 開放議題與確認紀錄

- 已全數確認，進入 `R01_code_optimization_audit.md` 落檔與三大流轉出口裁決。

