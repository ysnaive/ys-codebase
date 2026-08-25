#!/usr/bin/env python3
"""_on_modules_changed.py for mock_workflow_plugin"""
import sys
from pathlib import Path

def main():
    log_file = Path(__file__).resolve().parent / "hook_invoked.log"
    log_file.write_text(" ".join(sys.argv[1:]), encoding="utf-8")
    return 0

if __name__ == "__main__":
    sys.exit(main())
