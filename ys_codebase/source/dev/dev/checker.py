"""
Compliance & Architecture Checker for YS-Codebase modules.
Implements 5-step compliance check pipeline, 3-tier severity classification,
and AST static security/anti-pattern analysis.
"""
import os
import ast
import json
from enum import Enum
from dataclasses import dataclass, field
from typing import Tuple, List, Dict, Optional, Any
from core import uri
from core import semver

class CheckSeverity(Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"

@dataclass
class CheckIssue:
    severity: CheckSeverity
    category: str        # "MANIFEST", "CONTRIBUTES", "PROBING", "STRUCTURE", "ANTIPATTERN", "SYNTAX"
    message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity.value,
            "category": self.category,
            "message": self.message,
            "file_path": self.file_path,
            "line_number": self.line_number,
        }

@dataclass
class CheckReport:
    module: str
    issues: List[CheckIssue] = field(default_factory=list)

    @property
    def has_fails(self) -> bool:
        return any(i.severity == CheckSeverity.FAIL for i in self.issues)

    @property
    def has_warns(self) -> bool:
        return any(i.severity == CheckSeverity.WARN for i in self.issues)

    @property
    def status(self) -> CheckSeverity:
        if self.has_fails:
            return CheckSeverity.FAIL
        elif self.has_warns:
            return CheckSeverity.WARN
        return CheckSeverity.PASS

    @property
    def passed(self) -> bool:
        return not self.has_fails

    @property
    def errors(self) -> List[str]:
        return [i.message for i in self.issues if i.severity == CheckSeverity.FAIL]

    @property
    def warnings(self) -> List[str]:
        return [i.message for i in self.issues if i.severity == CheckSeverity.WARN]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module": self.module,
            "status": self.status.value,
            "passed": self.passed,
            "issues": [i.to_dict() for i in self.issues],
        }

    def __iter__(self):
        # Backward compatibility with (passed, errors) tuple unpacking
        return iter((self.passed, self.errors))

    def __getitem__(self, index):
        return (self.passed, self.errors)[index]

    def __len__(self):
        return 2


class Checker:
    def __init__(self):
        pass

    def check_module(self, name: str) -> CheckReport:
        report = CheckReport(module=name)
        src_uri = f"module.source://{name}"
        if not uri.exists(src_uri):
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="MANIFEST",
                    message=f"Module source not found at {src_uri}.",
                )
            )
            return report

        real_dir = uri.resolve(src_uri)

        # 1. Check manifest.json
        self._check_manifest(name, real_dir, report)

        # 2. Check Core injection (contributes/core.json)
        self._check_core_injection(name, real_dir, report)

        # 3. Check File Structure & Configurable templates
        self._check_file_structure(name, real_dir, report)

        # 4. Check AST Syntax, Zero Probing & Anti-patterns in Python files
        self._check_source_files(name, real_dir, report)

        # 5. Check Test Classes (YSCBTestCase inheritance)
        self._check_test_classes(name, real_dir, report)

        return report

    def _check_manifest(self, name: str, real_dir: str, report: CheckReport) -> None:
        manifest_path = os.path.join(real_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="MANIFEST",
                    message="Missing 'manifest.json'.",
                    file_path="manifest.json",
                )
            )
            return

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                m_data = json.load(f)

            for field_name in ("name", "version", "entry", "dependencies"):
                if field_name not in m_data:
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.FAIL,
                            category="MANIFEST",
                            message=f"Missing required field '{field_name}' in manifest.json.",
                            file_path="manifest.json",
                        )
                    )

            m_name = m_data.get("name")
            if m_name and m_name != name:
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.FAIL,
                        category="MANIFEST",
                        message=f"Manifest name '{m_name}' does not match directory name '{name}'.",
                        file_path="manifest.json",
                    )
                )

            m_ver = m_data.get("version")
            if m_ver:
                try:
                    semver.parse_semver(str(m_ver))
                except Exception:
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.FAIL,
                            category="MANIFEST",
                            message=f"Manifest version '{m_ver}' is not a valid SemVer format.",
                            file_path="manifest.json",
                        )
                    )


            deps = m_data.get("dependencies")
            if deps is not None:
                if not isinstance(deps, (list, dict)):
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.FAIL,
                            category="MANIFEST",
                            message="'dependencies' field must be a list or object.",
                            file_path="manifest.json",
                        )
                    )
                elif name != "core":
                    dep_names = deps if isinstance(deps, list) else list(deps.keys())
                    if "core" not in dep_names:
                        report.issues.append(
                            CheckIssue(
                                severity=CheckSeverity.FAIL,
                                category="MANIFEST",
                                message="Module must explicitly declare 'core' in 'dependencies'.",
                                file_path="manifest.json",
                            )
                        )
        except Exception as e:
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="MANIFEST",
                    message=f"Invalid JSON in manifest.json: {e}",
                    file_path="manifest.json",
                )
            )

    def _check_core_injection(self, name: str, real_dir: str, report: CheckReport) -> None:
        if name == "core":
            return
        core_contribute_path = os.path.join(real_dir, "contributes", "core.json")
        if not os.path.exists(core_contribute_path):
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.WARN,
                    category="CONTRIBUTES",
                    message="Module lacks 'contributes/core.json' declaration. Consider declaring CLI commands or URI schemes.",
                    file_path="contributes/core.json",
                )
            )
        else:
            try:
                with open(core_contribute_path, "r", encoding="utf-8") as f:
                    c_data = json.load(f)
                if not any(k in c_data for k in ("commands", "uri_schemes")):
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.WARN,
                            category="CONTRIBUTES",
                            message="'contributes/core.json' has no 'commands' or 'uri_schemes' declared.",
                            file_path="contributes/core.json",
                        )
                    )
            except Exception as e:
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.FAIL,
                        category="CONTRIBUTES",
                        message=f"Invalid JSON in 'contributes/core.json': {e}",
                        file_path="contributes/core.json",
                    )
                )

    def _check_file_structure(self, name: str, real_dir: str, report: CheckReport) -> None:
        # 1. Entry point check
        cli_path = os.path.join(real_dir, "scripts", "cli.py")
        if not os.path.exists(cli_path):
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="STRUCTURE",
                    message="Missing entry point 'scripts/cli.py'.",
                    file_path="scripts/cli.py",
                )
            )

        # 2. Check for scattered config.*.json at root
        for item in os.listdir(real_dir):
            if item.startswith("config.") and item.endswith(".json"):
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.FAIL,
                        category="STRUCTURE",
                        message=f"Scattered config template found at module root: '{item}'. Templates must be placed under 'configurable/' directory.",
                        file_path=item,
                    )
                )

        # 3. Check configurable/ templates validity if present
        cfg_dir = os.path.join(real_dir, "configurable")
        if os.path.isdir(cfg_dir):
            for cfg_f in os.listdir(cfg_dir):
                if cfg_f.endswith(".json"):
                    cfg_full = os.path.join(cfg_dir, cfg_f)
                    try:
                        with open(cfg_full, "r", encoding="utf-8") as f:
                            json.load(f)
                    except Exception as e:
                        report.issues.append(
                            CheckIssue(
                                severity=CheckSeverity.FAIL,
                                category="STRUCTURE",
                                message=f"Invalid JSON in 'configurable/{cfg_f}': {e}",
                                file_path=f"configurable/{cfg_f}",
                            )
                        )

        # 4. Check for leftover temp files
        for root, _, files in os.walk(real_dir):
            if "__pycache__" in root or ".pytest_cache" in root or ".git" in root:
                continue
            for f in files:
                if f.endswith((".tmp", ".bak", ".DS_Store")) or f.endswith("~"):
                    rel_p = os.path.relpath(os.path.join(root, f), real_dir).replace("\\", "/")
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.WARN,
                            category="STRUCTURE",
                            message=f"Found leftover temporary/junk file: '{rel_p}'.",
                            file_path=rel_p,
                        )
                    )

        # 5. Check contributes.format.md presence
        fmt_doc = os.path.join(real_dir, "contributes.format.md")
        if not os.path.exists(fmt_doc):
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.WARN,
                    category="STRUCTURE",
                    message="Module lacks 'contributes.format.md' documentation.",
                    file_path="contributes.format.md",
                )
            )

    def _check_source_files(self, name: str, real_dir: str, report: CheckReport) -> None:
        for root, _, files in os.walk(real_dir):
            if "__pycache__" in root or ".pytest_cache" in root:
                continue
            for f in files:
                if not f.endswith(".py"):
                    continue

                full_p = os.path.join(root, f)
                rel_p = os.path.relpath(full_p, real_dir).replace("\\", "/")
                is_test_file = rel_p.startswith("tests/")

                try:
                    with open(full_p, "r", encoding="utf-8") as py_f:
                        content = py_f.read()
                    tree = ast.parse(content, filename=rel_p)
                except SyntaxError as se:
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.FAIL,
                            category="SYNTAX",
                            message=f"SyntaxError in {rel_p}:{se.lineno}: {se.msg}",
                            file_path=rel_p,
                            line_number=se.lineno,
                        )
                    )
                    continue
                except Exception as e:
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.FAIL,
                            category="SYNTAX",
                            message=f"Error parsing {rel_p}: {e}",
                            file_path=rel_p,
                        )
                    )
                    continue

                # AST string literal inspections
                for node in ast.walk(tree):
                    # Check string constants in AST
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        s_val = node.value
                        lineno = getattr(node, "lineno", None)

                        # FR-03: Zero Probing for source space
                        if name not in ("dev", "core") and not is_test_file:
                            if "module.source://" in s_val:
                                report.issues.append(
                                    CheckIssue(
                                        severity=CheckSeverity.FAIL,
                                        category="PROBING",
                                        message=f"Zero Probing violation: 'module.source://' access detected in '{rel_p}:{lineno}'.",
                                        file_path=rel_p,
                                        line_number=lineno,
                                    )
                                )

                        # FR-07: Anti-Pattern Check (Reinventing the wheel)
                        if name not in ("core", "dev") and not is_test_file:
                            if s_val in ("config.project.json", "config.local.json"):
                                report.issues.append(
                                    CheckIssue(
                                        severity=CheckSeverity.FAIL,
                                        category="ANTIPATTERN",
                                        message=f"Reinventing the wheel: direct access to '{s_val}' detected in '{rel_p}:{lineno}'. Use 'core.config.get()' / 'core.config.set()' SDK instead.",
                                        file_path=rel_p,
                                        line_number=lineno,
                                    )
                                )
                            elif s_val == "contributes.merged.json":
                                report.issues.append(
                                    CheckIssue(
                                        severity=CheckSeverity.FAIL,
                                        category="ANTIPATTERN",
                                        message=f"Direct contributes probing: access to '{s_val}' detected in '{rel_p}:{lineno}'. Use 'core.contributes.get()' SDK instead.",
                                        file_path=rel_p,
                                        line_number=lineno,
                                    )
                                )


    def _check_test_classes(self, name: str, real_dir: str, report: CheckReport) -> None:
        tests_dir = os.path.join(real_dir, "tests")
        if not os.path.isdir(tests_dir):
            return

        def _extract_tokens(expr_node: ast.AST) -> List[str]:
            tokens = []
            for n in ast.walk(expr_node):
                if isinstance(n, ast.Attribute):
                    tokens.append(n.attr)
                elif isinstance(n, ast.Name):
                    tokens.append(n.id)
            return tokens

        def _check_require_node(target_node: ast.AST, t_file: str) -> None:
            for dec in getattr(target_node, "decorator_list", []):
                if isinstance(dec, ast.Call):
                    func_name = ""
                    if isinstance(dec.func, ast.Name):
                        func_name = dec.func.id
                    elif isinstance(dec.func, ast.Attribute):
                        func_name = dec.func.attr
                    
                    if func_name == "require" and dec.args:
                        tokens = _extract_tokens(dec.args[0])
                        if "LOGIC" in tokens and ("ISOLATED_SANDBOX" in tokens or "ISOLATE_SANDBOX" in tokens):
                            node_kind = "class" if isinstance(target_node, ast.ClassDef) else "function"
                            report.issues.append(
                                CheckIssue(
                                    severity=CheckSeverity.WARN,
                                    category="ANTIPATTERN",
                                    message=(
                                        f"Anti-Pattern: Test {node_kind} '{getattr(target_node, 'name', '')}' in tests/{t_file}:{target_node.lineno} "
                                        f"is marked with both 'LOGIC' and 'ISOLATED_SANDBOX'. Pure logical tests should not request dedicated per-method sandbox isolation."
                                    ),
                                    file_path=f"tests/{t_file}",
                                    line_number=target_node.lineno,
                                )
                            )

        for t_file in os.listdir(tests_dir):
            if t_file.startswith("test_") and t_file.endswith(".py"):
                t_full = os.path.join(tests_dir, t_file)
                try:
                    with open(t_full, "r", encoding="utf-8") as tf:
                        tree = ast.parse(tf.read(), filename=t_file)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            if node.name.startswith("Test"):
                                base_names = []
                                for b in node.bases:
                                    if isinstance(b, ast.Name):
                                        base_names.append(b.id)
                                    elif isinstance(b, ast.Attribute):
                                        base_names.append(b.attr)
                                if "TestCase" in base_names and "YSCBTestCase" not in base_names:
                                    report.issues.append(
                                        CheckIssue(
                                            severity=CheckSeverity.FAIL,
                                            category="STRUCTURE",
                                            message=f"Security Guard: Test class '{node.name}' in tests/{t_file}:{node.lineno} directly subclasses 'unittest.TestCase'. Must inherit from 'dev.testing.case.YSCBTestCase'.",
                                            file_path=f"tests/{t_file}",
                                            line_number=node.lineno,
                                        )
                                    )
                            _check_require_node(node, t_file)
                        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            _check_require_node(node, t_file)
                except Exception as e:
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.FAIL,
                            category="SYNTAX",
                            message=f"Error parsing test file tests/{t_file}: {e}",
                            file_path=f"tests/{t_file}",
                        )
                    )


    def check_all(self) -> Dict[str, CheckReport]:
        results = {}
        src_root_uri = "module.source://"
        if not uri.exists(src_root_uri):
            return results

        for item in uri.listdir(src_root_uri):
            item_uri = f"module.source://{item}"
            if uri.is_dir(item_uri) and uri.exists(f"{item_uri}/manifest.json"):
                results[item] = self.check_module(item)

        return results
