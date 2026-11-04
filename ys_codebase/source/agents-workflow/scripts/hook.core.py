"""
Microkernel Lifecycle Hook for agents-workflow.
Listens to 'on_reload' event to autonomously execute release transaction for all active targets.
"""
import sys

from agents_workflow.publisher import ReleasePublisher


def on_reload(ctx=None) -> None:
    """
    Autonomously triggered on microkernel Stage 4 reload.
    Executes full 4-step atomic release transaction for all active targets.
    """
    try:
        publisher = ReleasePublisher()
        res = publisher.release_all(force=False)
        if res.get("success", False):
            if res.get("short_circuited", False):
                print(f"[agents-workflow:hook] Auto-release skipped on reload (no changes detected, {res.get('skipped_count', 0)} files up to date).")
            else:
                print(f"[agents-workflow:hook] Auto-released on reload ({res.get('written_count', 0)} written, {res.get('skipped_count', 0)} unchanged, {res.get('removed_count', 0)} removed, targets: {', '.join(res.get('active_targets', []))}).")
        else:
            print(f"[agents-workflow:hook] Auto-release failed on reload: {res.get('error', 'Unknown')}")
    except Exception as e:
        print(f"[agents-workflow:hook] Auto-release on reload failed: {e}")


def on_pre_cli_dispatch(ctx=None) -> bool:
    """
    在 CLI 命令分發前觸發，呼叫 ensure_jit_release()。
    若來源特徵指紋變更，原地執行 release_all(force=False) 自癒物化至 Targets；
    若無變更 (Clean)，<1ms 極速短路跳過。

    :return: 是否發生實質物化寫入
    """
    try:
        from agents_workflow.publisher import ensure_jit_release
        return ensure_jit_release()
    except Exception as e:
        print(f"[agents-workflow:hook] Warning: Failed during on_pre_cli_dispatch: {e}", file=sys.stderr)
        return False

