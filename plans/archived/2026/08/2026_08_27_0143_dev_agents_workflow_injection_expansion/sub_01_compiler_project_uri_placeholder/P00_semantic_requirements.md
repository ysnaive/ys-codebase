# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：編譯器支援專案根目錄相對路徑佔位符 __${uri}__ 與三大佔位符語意規範明確化 (Compiler Project URI Placeholder & Placeholder Semantics Clarification)  
> 建立日期：2026-08-27  
> 所屬主計畫：2026_08_27_0143_dev_agents_workflow_injection_expansion  
> 狀態：Confirmed  
> 計畫類型：Feature / Refactor  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  > 我傾向建立新佔位符類型，並於文檔明確舊有語意:
  > - 原有: `__@{content token}__` : 文件內容佔位符
  > - 原有: `__#{local uri token}__` : 以自身為相對路徑拆解的協議佔位符
  > - 新增: `__${project uri token}__` : 以 project:// 為相對路徑拆解的協議佔位符
  > 此為本計畫之衍伸問題，建立衍生子計畫。
- **核心目標**：
  1. 在 `agents-workflow` 編譯器 (`compiler.py`) 中擴充支援專案相對路徑佔位符 `__${uri}__`（以 `project://` 專案根目錄為基準點計算相對路徑）。
  2. 明確三大佔位符體系語意規範與解析規則：
     - `__@{token}__`：文件內容佔位符（Stage 1 內容遞迴展開）
     - `__#{uri}__`：自身相對路徑佔位符（Stage 2 文檔自身目錄相對路徑，適用於 Markdown 超連結）
     - `__${uri}__`：專案相對路徑佔位符（Stage 2 專案根目錄相對路徑，適用於 Shell 指令與路徑參數）
  3. 更新文檔規範（`contributes.format.md`、`docs/agents-workflow/user_guide.md`）登載三大佔位符規格。
  4. 將 `ContextInit.md` 中的起手式指令更新為 `python __${yscb.host://yscb.py}__ agents-workflow plan status`，達成跨目錄拓撲 100% 自適應。
- **邊界排除 (Explicitly Excluded)**：
  - 不修改 `core.uri` 底層語意協議解析邏輯，僅在 `agents-workflow` 編譯器 Stage 2 擴充路徑基準點模式。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 三大佔位符語意分工與解析基準**：
  - `__@{token}__`：Stage 1 文件內容佔位符（字串/模板片段嵌入/動態函式輸出）。
  - `__#{uri}__`：Stage 2 自身相對路徑佔位符（以當前生成 Markdown 文件自身目錄 `cur_doc_dir` 為相對基準）。
  - `__${uri}__`：Stage 2 專案根目錄相對路徑佔位符（以專案根目錄 `project://` 為相對基準）。
- **[P00:DR-02] 路徑正規化格式標準**：
  - `__${uri}__` 展開時，若目標檔案位於專案根目錄，輸出乾淨檔名（如 `yscb.py`）；若位於子目錄，輸出相對於根目錄之路徑（如 `tools/yscb.py`），不附加多餘前綴 `./`。
- **[P00:DR-03] 強制反引號包裹與穿插展開語意 (Strict Backtick Enclosing & Inline Expansion)**：
  - 佔位符**必須**存在於反引號（代碼塊 `` `...` ``）之中方可被解析。
  - 支援代碼塊內部穿插其他文字（例如 `` `python __${yscb.host://yscb.py}__ agents-workflow plan status` ``），展開時**僅替換佔位符本體**，精確保留穿插文字與外層反引號（展開為 `` `python yscb.py agents-workflow plan status` ``）。
- **[P00:DR-04] 未包裹佔位符安全阻斷與警示 (Un-enclosed Placeholder Warning Gate)**：
  - 若文本中偵測到未被反引號包裹的裸佔位符（如裸 `__@{...}__`, `__#{...}__`, `__${...}__`）：
    - **絕對不予展開**（保持原樣，避免破壞純文本）。
    - 於編譯時輸出 warning 提示訊息，提醒開發者為佔位符加上反引號。

---

## 3. 開放議題與確認紀錄

- [x] **Q-01**：`__${uri}__` 在專案根目錄下之相對路徑格式？ ➔ **已確認**：標準格式為 `yscb.py`，子目錄為 `sub/path`。
- [x] **Q-02**：三大佔位符是否支援無反引號寫法？ ➔ **已確認**：強制必須有反引號包裹；未包裹者不展開並印出警示。

