# API 與介面規格書 (API & Interface Specification)

> 功能名稱：終端編碼防護、舊版殘留清理、特殊字元徹底捨棄與測試狀態閉環 (sub_05)  
> 建立日期：2026-09-12  
> 所屬主計畫：2026_09_07_0831_quality_update  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `HelpRenderer._tier_badge` | `core/commands/help.py` | Internal | 格式化回傳 `[SAFE]`, `[CONDITIONAL]`, `[GATED]` 純文字標籤 (0 Emoji) |
| `main` / `_ensure_stdio_utf8` | `yscb.py` | Public Entry | 進入點安全重組 `sys.stdout` 與 `sys.stderr` 為 UTF-8 |
| `dispatch` | `core/commands/dispatcher.py` | Public | 派發前防禦性編碼重組與純文字錯誤/提示渲染 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. core.commands.help.HelpRenderer
class HelpRenderer:
    @staticmethod
    def _tier_badge(tier: str) -> str:
        """
        回傳標準純文字權限階層標記 (100% ASCII 相容，零 Emoji)。
        
        Args:
            tier: 權限字串 ('safe', 'conditional', 'gated' 等)
            
        Returns:
            str: '[SAFE] 自主安全 (safe)' 或 '[GATED] 授權守門 (gated)' 等純文字標籤
        """
        tier_lower = tier.lower()
        if tier_lower in ("safe", "green"):
            return "[SAFE] 自主安全 (safe)"
        elif tier_lower in ("gated", "danger", "red"):
            return "[GATED] 授權守門 (gated)"
        elif tier_lower in ("conditional", "warn", "warning", "yellow"):
            return "[CONDITIONAL] 階段條件 (conditional)"
        return f"[{tier}]"

# 2. yscb.py (Host Entry)
def _ensure_stdio_utf8() -> None:
    """在 Windows 或未知環境下主動加固標準輸出為 UTF-8 (errors='replace')。"""
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: yscb.py & core.commands.help] -> 消除所有 Emoji 與加固 Windows 編碼
                     |
[Step 2: Legacy File Cleanup] -> 刪除 3x contributes.format.md 與修正 contribute.json 命名
                     |
[Step 3: Test mark_passed & Perf Polish] -> 補齊 61 處 mark_passed 並微調 perf 測試門檻
                     |
[Step 4: Full Validation] -> dev check --all (0 Warning) & dev test --all (100% Passed)
```
