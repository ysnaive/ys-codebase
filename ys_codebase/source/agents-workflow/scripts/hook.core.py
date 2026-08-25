"""
Microkernel Lifecycle Hook for agents-workflow.
Listens to 'on_reload' event to autonomously re-compile and materialize exports.
"""
import sys
import os

# Ensure package directory is importable
_script_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_script_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from agents_workflow.compiler import ArtifactCompiler


def on_reload(ctx) -> None:
    """
    Autonomously triggered on microkernel Stage 4 reload.
    Re-compiles all registered exports and materializes them to exports/.
    """
    try:
        compiler = ArtifactCompiler()
        compiler.compile_all()
    except Exception as e:
        print(f"[agents-workflow:hook] Auto-compile on reload failed: {e}")
