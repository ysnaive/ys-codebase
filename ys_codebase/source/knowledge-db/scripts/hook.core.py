"""
YSCB Core Lifecycle Hook for module:knowledge-db.

Listens to pre_cli_dispatch event, inspects enable_hot_reload_server configuration,
and automatically launches or restarts the HotReloadServer in background.
"""

import os
import sys
from typing import Any, Optional

_script_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_script_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)


def on_pre_cli_dispatch(ctx: Optional[Any] = None) -> bool:
    """
    在 CLI 命令分發前觸發 [FR-02]：
    1. 檢驗是否處於測試沙盒環境，若處於沙盒則強制禁用常駐 Server (EC-06)。
    2. 載入 KnowledgeDBConfig，若 enable_hot_reload_server == True：
       - 調用 HotReloadServer.ensure_running() 確保 Server 存活。
       - 若版本變更自動重啟 (FR-11)。
    3. 耗時 <= 10ms，不阻塞前台 CLI 響應。

    :return: 是否喚醒或重啟了 Server
    """
    # 1. 測試沙盒環境隔離 (EC-06)
    if os.environ.get("YSCB_TEST_SANDBOX") == "1":
        return False

    try:
        from knowledge_db.config import KnowledgeDBConfig
        config = KnowledgeDBConfig.load()

        if not getattr(config, "enable_hot_reload_server", False):
            return False

        from knowledge_db.daemon import HotReloadServer
        return HotReloadServer.ensure_running()
    except Exception as e:
        print(f"[knowledge-db:hook] Warning: Failed during on_pre_cli_dispatch: {e}", file=sys.stderr)
        return False
