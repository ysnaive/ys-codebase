# 技術路線圖：模組防繞道調用與執行期剛性入口守衛架構 (Roadmap)

> 主題：模組防繞道調用與執行期剛性入口守衛架構  
> 歸檔日期：2026-09-06  
> 狀態：Proposed  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
在以 AI Agents 深度協同開發的場景中，專案雖以 `yscb.py` 作為全生態系統一入口與派發中樞，但 AI Agents 在長上下文、多輪次或任務阻滯情境下，因注意力漂移 (Attention Drift)，經常繞過 `yscb.py` 直接調用內部模組檔案（例如直接執行 `python ys_codebase/source/knowledge-db/scripts/cli.py` 或自製臨時腳本 `import knowledge_db`）。

繞道調用引發之破壞性影響：
1. **私有微虛擬環境遺失**：`.venv` 的 `site-packages` 未被動態注入 `sys.path`，導致依賴缺失或使用到系統污染版本。
2. **生命週期鉤子被截斷**：略過 `pre_cli_dispatch` / `post_cli_dispatch` 與 JIT 同步邏輯。
3. **快取與守護進程狀態撕裂**：快取定位與後台 Daemon 缺乏統一工作區根目錄 (`YSCB_HOST_DIR`) 支援，引發路徑誤判或幽靈鎖。

### 1.2 全庫現狀與架構特性分析
當前 YSCB 的啟動鏈路為：
$$\text{宿主系統 Python} \;\longrightarrow\; \texttt{yscb.py} \;\longrightarrow\; \text{動態將私有 \texttt{.venv} 的 \texttt{site-packages} 插入 \texttt{sys.path}} \;\longrightarrow\; \text{派發執行模組}$$

關鍵架構約束：
- `yscb.py` 作為 Ultra-Thin Single-File Bootstrapper，必須保持 100% Python 標準庫與跨平台零預裝依賴。
- 專案未將宿主環境替換為虛擬環境的 `python` 二進位本體，而是採用執行期 `sys.path.insert` 動態注入。
- 因此，當 Agent 使用系統 Python 直接啟動內部腳本時，專案層級無法直接改動宿主全域 Python 解譯器的原生行為。

### 1.3 核心根因
1. **Python 直譯語言特性**：檔案系統上所有具備語法有效性的 `.py` 檔案均可被 `python <path>` 直接載入。
2. **提示詞約束的半衰期**：純 Prompt / System Rules 約束屬於柔性軟限制 (Soft Constraint)，隨對話輪次增長與上下文稀釋必然復發。
3. **實體檔案結構的誘因反射 (Affordance)**：各模組目錄內暴露 `scripts/cli.py` 且底層帶有 `if __name__ == '__main__':`，對 LLM 形成強烈的可執行暗示。
4. **Audit Hook 在當前架構下的失效**：依賴私有 `.venv` 內 `sitecustomize.py` 的方案，在系統 Python 直接啟動時根本不會被加載，形成偽安全。

---

## 2. 候選架構方案對比 (Candidate Solutions)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：入口剛性熔斷與指令導航 (Runtime Hard Gate)** | 模組入口檢測 `YSCB_HOST_DIR` 或 Dispatch Token；缺失時於第 1 行直接熔斷 (Exit Code 126)，並於 stderr 印出拼接好的標準指令。 | 1. 零架構破壞，純標準庫實作。<br/>2. **即時矯正 Agent 反射**：終端直接反饋修正指令，驅動 LLM 下一步自我修正。 | 仍保留 `cli.py` 實體檔案，無法防止 Agent 首次嘗試調用。 | ⭐️⭐️⭐️⭐️⭐️ |
| **方案 2：結構性消滅腳本誘因 (De-Script & Importable Handler)** | 拔除所有 `if __name__ == '__main__':`，將 `scripts/cli.py` 改為純函式/類別；`yscb.py` 改用 `importlib` 呼叫 `dispatch` 介面。 | 1. **物理級消除誘因**：檔案樹無任何獨立可執行腳本。<br/>2. 即使執行也不會觸發任何邏輯。 | 需統一改造全生態系模組的導出標準與 `yscb.py` 分發核心。 | ⭐️⭐️⭐️⭐️ |
| **方案 3：透明自癒代理 (Transparent Trampoline / Forwarder)** | 當 `cli.py` 偵測到缺乏 Token，自動向上搜尋 `yscb.py`，透過 `os.execv` 原地將進程替換為 `python yscb.py <mod> ...`。 | 極致容錯：即使 Agent 繞道，底層依然被安全劫持回正規生命週期。 | 隱式轉發可能讓 Agent 無法及時學到正確規範。 | ⭐️⭐️⭐️ |
| **方案 4：Python 全域審計鉤子 (Audit Hook via PEP 578)** | 於 `sitecustomize.py` 註冊 `sys.addaudithook` 攔截 `import`。 | 可連 `import` 語句一同阻斷。 | 在「系統 Python -> 動態注入」架構下，系統 Python 繞道時根本不加載私有環境的 `sitecustomize`，機制失效。 | ⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1 (剛性熔斷) | 方案 2 (消滅腳本) | 方案 3 (自癒代理) | 方案 1 + 方案 2 (雙保險) |
| :--- | :---: | :---: | :---: | :---: |
| **可行性 (Feasibility)** | 極高 (100% 現成可用) | 高 (需微調分發) | 中 (需適配跨平台 execv) | **極高** |
| **維護成本 (Maintenance)** | 極低 | 低 (統一介面) | 中 | **低** |
| **可靠性 (Reliability)** | 極高 | 極高 | 高 | **最高** |
| **對 Agent 矯正力** | 5 / 5 (強制中斷引導) | 4 / 5 (消除念頭) | 3 / 5 (默默容錯) | **5 / 5 (結構隱蔽 + 入口硬鎖)** |

---

## 4. 推薦實施標準與作業規範 (SOP & Architecture)

推薦採納 **「方案 1 (剛性熔斷導航) + 方案 2 (消滅獨立腳本)」** 雙重防禦標準：

### 4.1 模組入口防護代碼範式 (Guard Blueprint)
```python
# source/{module}/knowledge_db/cli.py (或 scripts/cli.py) 頂部
import os
import sys

def _assert_yscb_host_dispatch():
    if not os.environ.get("YSCB_HOST_DIR") and not os.environ.get("YSCB_TESTING"):
        print("\n" + "=" * 64, file=sys.stderr)
        print("🚨 [YSCB Security Guard] 禁止直接繞道調用內部模組腳本！", file=sys.stderr)
        print(f"❌ 非法指令：{' '.join(sys.argv)}", file=sys.stderr)
        print("👉 請使用 YS-Codebase 唯一標準宿主入口：", file=sys.stderr)
        print(f"   python yscb.py {MODULE_NAME} {' '.join(sys.argv[1:])}", file=sys.stderr)
        print("=" * 64 + "\n", file=sys.stderr)
        sys.exit(126)

_assert_yscb_host_dispatch()
```

### 4.2 模組介面去腳本化規範
- 徹底移除模組原始碼中的 `if __name__ == '__main__':` 區塊。
- 統一導出 `def handle_cli(argv: List[str]) -> int` 函式。
- `yscb.py` 分發層以 `importlib.import_module` 動態加載並調用 `handle_cli`。

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
作為 `2026_09_06_1927_knowledge_db_architecture_consolidation` 主計畫之候選子計畫儲備，與後續討論之其他架構痛點綜合評估優先順序後立項實施。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1 (規格與 Token 規範定義)**：於 `core` 定義全域統一的 `YSCB_HOST_DISPATCH_TOKEN` 與測試白名單機制。
2. **Stage 2 (knowledge-db 試驗先行)**：在 `knowledge-db` 率先移除 `if __name__ == '__main__':` 並實裝頂層 Runtime Guard 與指令導航。
3. **Stage 3 (yscb.py 分發中樞升級)**：改造 `dispatch_module`，支援以 `importlib` 方式動態調度模組 `handle_cli`，同時保留對舊版 `scripts/cli.py` 的向下相容。
4. **Stage 4 (全生態系推廣覆蓋)**：推廣至 `dev`、`agents-workflow` 等其餘核心模組，形成全專案一致的防禦壁壘。
