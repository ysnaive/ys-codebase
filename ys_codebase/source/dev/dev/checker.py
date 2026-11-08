"""
Compliance & Architecture Checker for YS-Codebase modules.
Implements a pure static 7-step compliance check pipeline, 3-tier severity classification,
and single-pass AST runtime isolation guardrail analysis.
"""
import os
import ast
import json
from enum import Enum
from dataclasses import dataclass, field
from typing import Tuple, List, Dict, Optional, Any, Set, FrozenSet
from core import uri, vfs, semver, contributes


class CheckSeverity(Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
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


@dataclass(frozen=True)
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

    @property
    def agent_directive(self) -> Optional[str]:
        if not self.has_fails:
            return None
        return (
            "[Agent Directive] Please consult skill 'yscb-module-dev' "
            "(references/acceptance_checklist.md & references/contributes_guide.md) "
            "to resolve module compliance errors."
        )

    def format_report(self) -> str:
        lines = [f"[*] Module: {self.module:<50} [{self.status.value}]"]
        for issue in self.issues:
            loc = f" ({issue.file_path})" if issue.file_path else ""
            lines.append(f"    |-- [{issue.severity.value}] [{issue.category}]{loc} {issue.message}")
        if self.agent_directive and not any(i.category == "DIRECTIVE" for i in self.issues):
            lines.append(self.agent_directive)
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        res: Dict[str, Any] = {
            "module": self.module,
            "status": self.status.value,
            "passed": self.passed,
            "issues": [i.to_dict() for i in self.issues],
        }
        if self.agent_directive:
            res["agent_directive"] = self.agent_directive
        return res


def _extract_ast_tokens(expr_node: ast.AST) -> List[str]:
    tokens: List[str] = []
    for n in ast.walk(expr_node):
        if isinstance(n, ast.Attribute):
            tokens.append(n.attr)
        elif isinstance(n, ast.Name):
            tokens.append(n.id)
    return tokens


def _collect_declared_cli_commands(module_dir: str) -> List[Tuple[str, str]]:
    """Collect (full_cmd, primary_cmd) pairs from contributes/core.json if present."""
    contrib_file = os.path.join(module_dir, "contributes", "core.json")
    if not os.path.isfile(contrib_file):
        return []
    try:
        with open(contrib_file, "r", encoding="utf-8") as f:
            cdata = json.load(f)
        cmd_map = cdata.get("commands", {}).get("cmd", {})
        if not isinstance(cmd_map, dict) or not cmd_map:
            return []

        def _collect_leaves(d: dict, pfx: str = "") -> List[Tuple[str, str]]:
            leaves: List[Tuple[str, str]] = []
            for k, v in d.items():
                if isinstance(v, dict) and isinstance(v.get("cmd"), dict) and v["cmd"]:
                    leaves.extend(_collect_leaves(v["cmd"], pfx=f"{pfx}{k}_"))
                else:
                    full_c = f"{pfx}{k}"
                    primary_c = full_c.split("_", 1)[0]
                    leaves.append((full_c, primary_c))
            return leaves

        return _collect_leaves(cmd_map)
    except (OSError, json.JSONDecodeError):
        return []


def _audit_cli_script_ast(
    tree: ast.Module,
) -> Tuple[Set[str], bool, bool, List[Tuple[int, str]]]:
    """Scan scripts/cli.py top-level AST nodes for functions, forbidden main, and top-level statements."""
    declared_funcs: Set[str] = set()
    has_main_func = False
    has_if_name_main = False
    invalid_top_level_nodes: List[Tuple[int, str]] = []

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef)):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            declared_funcs.add(node.name)
            if node.name == "main":
                has_main_func = True
            continue
        if isinstance(node, ast.Expr):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                continue
            invalid_top_level_nodes.append((getattr(node, "lineno", 0), "top-level expression"))
        elif isinstance(node, ast.If):
            is_name_main = False
            if isinstance(node.test, ast.Compare):
                left = node.test.left
                if isinstance(left, ast.Name) and left.id == "__name__":
                    for comp in node.test.comparators:
                        if isinstance(comp, ast.Constant) and comp.value == "__main__":
                            is_name_main = True
                            break
            if is_name_main:
                has_if_name_main = True
            else:
                invalid_top_level_nodes.append((getattr(node, "lineno", 0), "top-level if-statement"))
        else:
            stmt_type = type(node).__name__
            invalid_top_level_nodes.append((getattr(node, "lineno", 0), f"top-level statement '{stmt_type}'"))

    return declared_funcs, has_main_func, has_if_name_main, invalid_top_level_nodes


def _check_require_decorator_node(target_node: ast.AST, t_file: str, report: CheckReport) -> None:
    """Inspect @require(...) decorator on a test class or test function for LOGIC + ISOLATED_SANDBOX conflict."""
    for dec in getattr(target_node, "decorator_list", []):
        if not isinstance(dec, ast.Call) or not dec.args:
            continue
        func_name = getattr(dec.func, "id", getattr(dec.func, "attr", ""))
        if func_name != "require":
            continue
        tokens = _extract_ast_tokens(dec.args[0])
        if "LOGIC" in tokens and "ISOLATED_SANDBOX" in tokens:
            node_kind = "class" if isinstance(target_node, ast.ClassDef) else "function"
            lineno = getattr(target_node, "lineno", 0)
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.WARN,
                    category="ANTIPATTERN",
                    message=(
                        f"Anti-Pattern: Test {node_kind} '{getattr(target_node, 'name', '')}' in tests/{t_file}:{lineno} "
                        f"is marked with both 'LOGIC' and 'ISOLATED_SANDBOX'. Pure logical tests should not request dedicated per-method sandbox isolation."
                    ),
                    file_path=f"tests/{t_file}",
                    line_number=lineno,
                )
            )


def _method_has_none_requirement(item: ast.AST) -> bool:
    for dec in getattr(item, "decorator_list", []):
        if isinstance(dec, ast.Call) and dec.args:
            f_name = getattr(dec.func, "id", getattr(dec.func, "attr", ""))
            if f_name == "require" and "NONE" in _extract_ast_tokens(dec.args[0]):
                return True
    return False


def _method_calls_mark_passed(item: ast.AST) -> bool:
    for sub_n in ast.walk(item):
        if isinstance(sub_n, ast.Call) and isinstance(sub_n.func, ast.Attribute):
            if sub_n.func.attr == "mark_passed" and isinstance(sub_n.func.value, ast.Name) and sub_n.func.value.id == "self":
                return True
    return False


def _verify_test_class_isolation_and_marks(
    class_node: ast.ClassDef,
    t_file: str,
    report: CheckReport,
    is_top_level: bool = False,
) -> None:
    """Validate that a Test* class (or top-level TestCase class) inherits from YSCBTestCase and calls self.mark_passed() in test_* methods."""
    base_names = [
        b.id if isinstance(b, ast.Name) else b.attr
        for b in class_node.bases
        if isinstance(b, (ast.Name, ast.Attribute))
    ]
    if not (class_node.name.startswith("Test") or (is_top_level and any(b in ("TestCase", "YSCBTestCase") for b in base_names))):
        return

    if "TestCase" in base_names and "YSCBTestCase" not in base_names:
        report.issues.append(
            CheckIssue(
                severity=CheckSeverity.FAIL,
                category="STRUCTURE",
                message=(
                    f"Security Guard: Test class '{class_node.name}' in tests/{t_file}:{class_node.lineno} "
                    f"directly subclasses 'unittest.TestCase'. Must inherit from 'dev.testing.case.YSCBTestCase'."
                ),
                file_path=f"tests/{t_file}",
                line_number=class_node.lineno,
            )
        )
        return

    for item in class_node.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) or not item.name.startswith("test_"):
            continue
        if _method_has_none_requirement(item):
            continue
        if not _method_calls_mark_passed(item):
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.WARN,
                    category="STRUCTURE",
                    message=(
                        f"Test method '{item.name}' in tests/{t_file}:{item.lineno} lacks 'self.mark_passed()' call. "
                        f"Unhandled tests will be marked as UNKNOWN in test runner."
                    ),
                    file_path=f"tests/{t_file}",
                    line_number=item.lineno,
                )
            )


def _is_core_spec_at_least_1_2_0(core_spec: Any) -> bool:
    """Verify via multi-point probing and literal inspection that core_spec requires core >= 1.2.0."""
    if not isinstance(core_spec, str) or not core_spec.strip():
        return False
    min_required = semver.parse_semver("1.2.0.0")
    low_probes = ["0.1.0.0", "1.0.0.0", "1.1.0.0", "1.1.99.99"]
    high_probes = ["1.2.0.0", "1.2.7.0", "1.3.0.0", "2.0.0.0"]
    for token in core_spec.replace(",", " ").replace(";", " ").split():
        ver_str = token.lstrip("><=!~^vV").strip()
        if not ver_str:
            continue
        try:
            vt = semver.parse_semver(ver_str)
            if semver.compare_semver(vt, min_required) < 0:
                low_probes.append(ver_str)
            else:
                high_probes.append(ver_str)
        except Exception:
            pass
    try:
        if any(semver.match_constraint(p, core_spec) for p in low_probes):
            return False
        return any(semver.match_constraint(p, core_spec) for p in high_probes)
    except Exception:
        return False


_GUARDRAIL_EXEMPTIONS: FrozenSet[Tuple[str, str, str]] = frozenset({
    ("A1", "core", "core/log.py"),
    ("A1", "dev", "dev/testing/runner.py"),
    ("A2", "server", "server/worker.py"),
    ("B3", "server", "server/master.py"),
    ("B4", "core", "core/context.py"),
    ("B4", "core", "core/platform/venv.py"),
    ("B5", "core", "core/platform/venv.py"),
    ("B6", "server", "server/master.py"),
    ("D10_SYS_MODULES", "core", "core/loader.py"),
    ("D10_SYS_MODULES", "core", "core/platform/venv.py"),
    ("D10_SYS_MODULES", "dev", "dev/testing/runner.py"),
    ("D10_SPEC", "core", "core/loader.py"),
    ("F13_SUBPROCESS", "core", "core/platform/process.py"),
    ("F13_THREAD", "server", "server/service.py"),
    ("F13_THREAD", "server", "server/master.py"),
    ("F13_THREAD", "server", "server/watcher.py"),
    ("F13_THREAD", "dev", "dev/testing/runner.py"),
    ("F13_THREAD", "core", "core/log.py"),
})

_MUTABLE_CONSTRUCTORS: FrozenSet[str] = frozenset({
    "list",
    "dict",
    "set",
    "bytearray",
    "defaultdict",
    "OrderedDict",
    "Counter",
    "deque",
    "SimpleNamespace",
})

_SYS_PATH_MUTATING_METHODS: FrozenSet[str] = frozenset({
    "insert",
    "append",
    "extend",
    "remove",
    "pop",
    "clear",
    "sort",
    "reverse",
})

_DICT_MUTATING_METHODS: FrozenSet[str] = frozenset({
    "pop",
    "popitem",
    "clear",
    "update",
    "setdefault",
})


def _is_mutable_expr(node: ast.AST) -> bool:
    """Return True if an AST expression constructs a mutable container or namespace."""
    if isinstance(node, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)):
        return True
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id in _MUTABLE_CONSTRUCTORS:
            return True
        if isinstance(func, ast.Attribute) and func.attr in _MUTABLE_CONSTRUCTORS:
            return True
    return False


class _SourceGuardrailVisitor(ast.NodeVisitor):
    """
    Single-pass AST static guardrail analyzer for module source files.
    Enforces Jupyter-style runtime isolation guardrails (A1~F13), Zero Probing,
    import alias tracking, and reflection defense.
    """

    def __init__(self, module_name: str, rel_path: str, is_test_file: bool, report: CheckReport) -> None:
        self.module_name = module_name
        self.rel_path = rel_path
        self.is_test_file = is_test_file
        self.report = report
        self.module_aliases: Dict[str, str] = {
            "os": "os",
            "sys": "sys",
            "subprocess": "subprocess",
            "threading": "threading",
            "signal": "signal",
            "logging": "logging",
            "pprint": "pprint",
            "traceback": "traceback",
            "builtins": "builtins",
            "importlib": "importlib",
            "pathlib": "pathlib",
        }
        self.symbol_imports: Dict[str, Tuple[str, str]] = {
            "Path": ("pathlib", "Path"),
        }
        self.doc_nodes: Set[int] = set()
        self.scope_stack: List[str] = ["module"]
        self._seen_issues: Set[Tuple[Optional[int], str]] = set()

    def _exempt(self, key: str) -> bool:
        return (key, self.module_name, self.rel_path) in _GUARDRAIL_EXEMPTIONS

    def _record_issue(
        self,
        lineno: Optional[int],
        message: str,
        category: str = "ANTIPATTERN",
        severity: CheckSeverity = CheckSeverity.FAIL,
    ) -> None:
        dedup_key = (lineno, message)
        if dedup_key in self._seen_issues:
            return
        self._seen_issues.add(dedup_key)
        self.report.issues.append(
            CheckIssue(
                severity=severity,
                category=category,
                message=message,
                file_path=self.rel_path,
                line_number=lineno,
            )
        )

    def _collect_imports_and_docs(self, tree: ast.Module) -> None:
        if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant):
            self.doc_nodes.add(id(tree.body[0].value))
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant):
                    self.doc_nodes.add(id(n.body[0].value))
            elif isinstance(n, ast.Import):
                for alias in n.names:
                    bound = alias.asname or alias.name.split(".")[0]
                    if alias.name == "importlib.util" and alias.asname:
                        self.module_aliases[alias.asname] = "importlib.util"
                    else:
                        self.module_aliases[bound] = alias.name
            elif isinstance(n, ast.ImportFrom) and n.module:
                for alias in n.names:
                    bound = alias.asname or alias.name
                    self.symbol_imports[bound] = (n.module, alias.name)

    def _resolve_target(self, expr: ast.AST) -> str:
        """Resolve an AST expression to a canonical dotted path (supporting import aliases and getattr literals)."""
        if isinstance(expr, ast.Name):
            if expr.id in self.symbol_imports:
                mod, sym = self.symbol_imports[expr.id]
                return f"{mod}.{sym}"
            if expr.id in self.module_aliases:
                return self.module_aliases[expr.id]
            return expr.id
        if isinstance(expr, ast.Attribute):
            base = self._resolve_target(expr.value)
            if base:
                return f"{base}.{expr.attr}"
            return f"*.{expr.attr}"
        if (
            isinstance(expr, ast.Call)
            and isinstance(expr.func, ast.Name)
            and expr.func.id == "getattr"
            and len(expr.args) >= 2
            and isinstance(expr.args[1], ast.Constant)
            and isinstance(expr.args[1].value, str)
        ):
            base = self._resolve_target(expr.args[0])
            if base:
                return f"{base}.{expr.args[1].value}"
        return ""

    def _check_top_level_stmts(self, stmts: List[ast.stmt], in_except_handler: bool = False) -> None:
        for stmt in stmts:
            if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
                val = stmt.value
                if val is None:
                    continue
                for t in targets:
                    if isinstance(t, ast.Name) and t.id != "__all__":
                        if _is_mutable_expr(val):
                            self._record_issue(
                                stmt.lineno,
                                f"[C8] Forbidden top-level mutable state '{t.id}' in '{self.rel_path}:{stmt.lineno}'. Use immutable constants (frozenset/tuple) or 'core.context.get_runtime_context()'.",
                            )
                        elif isinstance(val, ast.Constant) and val.value is None and not in_except_handler:
                            self._record_issue(
                                stmt.lineno,
                                f"[C8] Forbidden top-level mutable None singleton '{t.id}' in '{self.rel_path}:{stmt.lineno}'. Store runtime singletons in 'core.context.get_runtime_context()'.",
                            )
            elif isinstance(stmt, ast.AugAssign):
                if isinstance(stmt.target, ast.Name) and stmt.target.id != "__all__":
                    self._record_issue(
                        stmt.lineno,
                        f"[C8] Forbidden top-level augmented assignment to '{stmt.target.id}' in '{self.rel_path}:{stmt.lineno}'.",
                    )
            elif isinstance(stmt, ast.If):
                self._check_top_level_stmts(stmt.body, in_except_handler=in_except_handler)
                self._check_top_level_stmts(stmt.orelse, in_except_handler=in_except_handler)
            elif isinstance(stmt, ast.Try):
                self._check_top_level_stmts(stmt.body, in_except_handler=in_except_handler)
                for h in stmt.handlers:
                    self._check_top_level_stmts(h.body, in_except_handler=True)
                self._check_top_level_stmts(stmt.orelse, in_except_handler=in_except_handler)
                self._check_top_level_stmts(stmt.finalbody, in_except_handler=in_except_handler)
            elif isinstance(stmt, ast.With):
                self._check_top_level_stmts(stmt.body, in_except_handler=in_except_handler)

    def analyze(self, tree: ast.Module) -> None:
        self._collect_imports_and_docs(tree)
        if not self.is_test_file:
            self._check_top_level_stmts(tree.body)
        self.visit(tree)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            lineno = getattr(node, "lineno", None)
            self._record_issue(
                lineno,
                f"Bare 'except:' clause detected in '{self.rel_path}:{lineno or 0}'. Catch 'Exception' or specific exception types instead.",
                category="ANTIPATTERN",
                severity=CheckSeverity.WARN,
            )
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if id(node) in self.doc_nodes:
            return
        if not self.is_test_file and self.module_name not in ("dev", "core") and isinstance(node.value, str):
            s_val = node.value
            lineno = getattr(node, "lineno", None)
            if "module.source://" in s_val:
                self._record_issue(
                    lineno,
                    f"Zero Probing violation: 'module.source://' access detected in '{self.rel_path}:{lineno}'.",
                    category="PROBING",
                )
            if s_val in ("config.project.json", "config.local.json"):
                self._record_issue(
                    lineno,
                    f"Reinventing the wheel: direct access to '{s_val}' detected in '{self.rel_path}:{lineno}'. Use 'core.config.get()' / 'core.config.set()' SDK instead.",
                    category="ANTIPATTERN",
                )
            elif s_val == "contributes.merged.json":
                self._record_issue(
                    lineno,
                    f"Direct contributes probing: access to '{s_val}' detected in '{self.rel_path}:{lineno}'. Use 'core.contributes.get()' SDK instead.",
                    category="ANTIPATTERN",
                )
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        if not self.is_test_file:
            self._record_issue(
                node.lineno,
                f"[C8] Forbidden 'global' statement ({', '.join(node.names)}) in '{self.rel_path}:{node.lineno}'. Store mutable state in 'core.context.get_runtime_context()'.",
            )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if not self.is_test_file:
            is_dc = False
            is_frozen = False
            for dec in node.decorator_list:
                dec_target = self._resolve_target(dec.func if isinstance(dec, ast.Call) else dec)
                if dec_target in ("dataclass", "dataclasses.dataclass"):
                    is_dc = True
                    if isinstance(dec, ast.Call):
                        for kw in dec.keywords:
                            if kw.arg == "frozen" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                is_frozen = True
            if is_dc and not is_frozen:
                self._record_issue(
                    node.lineno,
                    f"[C9] @dataclass '{node.name}' in '{self.rel_path}:{node.lineno}' must specify 'frozen=True'.",
                )

            is_enum = any(
                self._resolve_target(b) in ("Enum", "enum.Enum", "IntEnum", "enum.IntEnum", "Flag", "enum.Flag", "IntFlag", "enum.IntFlag")
                for b in node.bases
            )
            if not is_dc and not is_enum:
                for bstmt in node.body:
                    if isinstance(bstmt, (ast.Assign, ast.AnnAssign)) and bstmt.value is not None:
                        if _is_mutable_expr(bstmt.value):
                            self._record_issue(
                                bstmt.lineno,
                                f"[C9] Forbidden mutable class attribute in '{node.name}' ('{self.rel_path}:{bstmt.lineno}'). Initialize mutable attributes inside '__init__'.",
                            )

        self.scope_stack.append("class")
        self.generic_visit(node)
        self.scope_stack.pop()

    def _visit_func(self, node: ast.AST) -> None:
        if not self.is_test_file:
            args_obj = getattr(node, "args", None)
            func_name = getattr(node, "name", "")
            lineno = getattr(node, "lineno", 0)
            if args_obj is not None:
                defaults = list(args_obj.defaults) + [x for x in args_obj.kw_defaults if x is not None]
                for d in defaults:
                    if _is_mutable_expr(d):
                        self._record_issue(
                            lineno,
                            f"[C7] Forbidden mutable default argument in function '{func_name}' ('{self.rel_path}:{lineno}'). Use 'None' and initialize inside the function body.",
                        )
            scope_tag = "dunder_getattr" if func_name == "__getattr__" and self.scope_stack[-1] == "module" else "func"
        else:
            scope_tag = "func"
        self.scope_stack.append(scope_tag)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_func(node)

    def _check_mutation_target(self, target: ast.AST, lineno: int, is_delete: bool = False) -> None:
        if self.is_test_file:
            return
        if isinstance(target, ast.Subscript):
            val_target = self._resolve_target(target.value)
            if val_target == "os.environ" and not self._exempt("B5"):
                self._record_issue(
                    lineno,
                    f"[B5] Forbidden direct mutation of 'os.environ' in '{self.rel_path}:{lineno}'. Use 'core.context.get_env()' or 'ExecutionContext.env'.",
                )
            elif val_target == "sys.modules" and not self._exempt("D10_SYS_MODULES"):
                self._record_issue(
                    lineno,
                    f"[D10] Forbidden direct mutation of 'sys.modules' in '{self.rel_path}:{lineno}'. Delegate module loading to 'core.loader'.",
                )
            elif val_target == "sys.path" and self.module_name != "core":
                action_desc = "deletion on sys.path" if is_delete else "assignment to sys.path"
                self._record_issue(
                    lineno,
                    f"Forbidden direct sys.path mutation in '{self.rel_path}:{lineno}' ({action_desc}). Runtime sys.path management must be delegated to 'core.platform'.",
                )
            elif isinstance(target.value, ast.Call) and self._resolve_target(target.value.func) in ("globals", "builtins.globals"):
                if self.scope_stack[-1] != "dunder_getattr":
                    self._record_issue(
                        lineno,
                        f"[C8] Forbidden dynamic mutation of 'globals()[...]' in '{self.rel_path}:{lineno}'. Store runtime state in 'core.context.get_runtime_context()'.",
                    )
        else:
            val_target = self._resolve_target(target)
            if val_target == "os.environ" and not self._exempt("B5"):
                self._record_issue(
                    lineno,
                    f"[B5] Forbidden direct mutation of 'os.environ' in '{self.rel_path}:{lineno}'.",
                )
            elif val_target == "sys.modules" and not self._exempt("D10_SYS_MODULES"):
                self._record_issue(
                    lineno,
                    f"[D10] Forbidden direct mutation of 'sys.modules' in '{self.rel_path}:{lineno}'.",
                )
            elif val_target == "sys.path" and self.module_name != "core":
                action_desc = "deletion on sys.path" if is_delete else "assignment to sys.path"
                self._record_issue(
                    lineno,
                    f"Forbidden direct sys.path mutation in '{self.rel_path}:{lineno}' ({action_desc}). Runtime sys.path management must be delegated to 'core.platform'.",
                )

    def visit_Assign(self, node: ast.Assign) -> None:
        for t in node.targets:
            self._check_mutation_target(t, node.lineno)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._check_mutation_target(node.target, node.lineno)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._check_mutation_target(node.target, node.lineno)
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        for t in node.targets:
            self._check_mutation_target(t, node.lineno, is_delete=True)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if self.is_test_file:
            self.generic_visit(node)
            return

        lineno = node.lineno
        target = self._resolve_target(node.func)

        if target in ("setattr", "builtins.setattr", "delattr", "builtins.delattr") and len(node.args) >= 2:
            if isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                reflected = f"{self._resolve_target(node.args[0])}.{node.args[1].value}"
                if reflected == "sys.path" and self.module_name != "core":
                    self._record_issue(
                        lineno,
                        f"Forbidden direct sys.path mutation in '{self.rel_path}:{lineno}' (reflection on sys.path). Runtime sys.path management must be delegated to 'core.platform'.",
                    )
                elif reflected == "sys.modules" and not self._exempt("D10_SYS_MODULES"):
                    self._record_issue(
                        lineno,
                        f"[D10] Forbidden reflected mutation of 'sys.modules' in '{self.rel_path}:{lineno}'.",
                    )
                elif reflected == "os.environ" and not self._exempt("B5"):
                    self._record_issue(
                        lineno,
                        f"[B5] Forbidden reflected mutation of 'os.environ' in '{self.rel_path}:{lineno}'.",
                    )

        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in ("setdefault", "update", "clear")
            and isinstance(node.func.value, ast.Call)
            and self._resolve_target(node.func.value.func) in ("globals", "builtins.globals")
        ):
            self._record_issue(
                lineno,
                f"[C8] Forbidden dynamic mutation via 'globals().{node.func.attr}()' in '{self.rel_path}:{lineno}'.",
            )

        if not self._exempt("A1"):
            if target in ("print", "builtins.print", "pprint.pprint", "pprint", "traceback.print_exc", "traceback.print_exception"):
                self._record_issue(
                    lineno,
                    f"[A1] Forbidden unmanaged output call '{target}()' in '{self.rel_path}:{lineno}'. Use 'core.log' instead.",
                )
            elif target.startswith(("sys.stdout.", "sys.stderr.", "sys.__stdout__.", "sys.__stderr__.")) and target.split(".")[-1] in ("write", "writelines", "flush"):
                self._record_issue(
                    lineno,
                    f"[A1] Forbidden direct stream output '{target}()' in '{self.rel_path}:{lineno}'. Use 'core.log' instead.",
                )
            elif target.startswith("logging.") or (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in ("logger", "_logger", "LOG")
            ):
                self._record_issue(
                    lineno,
                    f"[A1] Forbidden stdlib logging call '{target}()' in '{self.rel_path}:{lineno}'. Use 'core.log' instead.",
                )

        if not self._exempt("A2"):
            if target in ("input", "builtins.input") or target.startswith(("sys.stdin.", "sys.__stdin__.")):
                self._record_issue(
                    lineno,
                    f"[A2] Forbidden blocking stdin call '{target}()' in '{self.rel_path}:{lineno}'.",
                )

        if not self._exempt("B3"):
            if target in ("sys.exit", "os._exit", "exit", "builtins.exit", "quit", "builtins.quit"):
                self._record_issue(
                    lineno,
                    f"[B3] Forbidden process exit call '{target}()' in '{self.rel_path}:{lineno}'. Return an exit status code instead.",
                )

        if not self._exempt("B4"):
            if target in ("os.chdir", "os.fchdir", "os.getcwd", "os.getcwdb", "pathlib.Path.cwd"):
                self._record_issue(
                    lineno,
                    f"[B4] Forbidden process CWD call '{target}()' in '{self.rel_path}:{lineno}'. Use 'core.context.get_cwd()' or 'uri.resolve()'.",
                )

        if not self._exempt("B5"):
            if target in ("os.putenv", "os.unsetenv") or (
                target.startswith("os.environ.") and target.split(".")[-1] in _DICT_MUTATING_METHODS
            ):
                self._record_issue(
                    lineno,
                    f"[B5] Forbidden 'os.environ' mutation '{target}()' in '{self.rel_path}:{lineno}'.",
                )

        if not self._exempt("B6"):
            if target == "signal.signal":
                self._record_issue(
                    lineno,
                    f"[B6] Forbidden 'signal.signal()' registration in '{self.rel_path}:{lineno}'.",
                )

        if target.startswith("sys.path.") and target.split(".")[-1] in _SYS_PATH_MUTATING_METHODS:
            if self.module_name != "core":
                method_name = target.split(".")[-1]
                self._record_issue(
                    lineno,
                    f"Forbidden direct sys.path mutation in '{self.rel_path}:{lineno}' (sys.path.{method_name}()). Runtime sys.path management must be delegated to 'core.platform'.",
                )

        if target.startswith("sys.modules.") and target.split(".")[-1] in _DICT_MUTATING_METHODS:
            if not self._exempt("D10_SYS_MODULES"):
                self._record_issue(
                    lineno,
                    f"[D10] Forbidden 'sys.modules' mutation '{target}()' in '{self.rel_path}:{lineno}'.",
                )

        if target.endswith("spec_from_file_location") or target == "spec_from_file_location":
            if not self._exempt("D10_SPEC"):
                self._record_issue(
                    lineno,
                    f"[D10] Forbidden unmanaged dynamic loader '{target}()' in '{self.rel_path}:{lineno}'. Use 'core.loader' instead.",
                )

        if target in ("eval", "builtins.eval", "exec", "builtins.exec", "__import__", "builtins.__import__", "importlib.__import__"):
            self._record_issue(
                lineno,
                f"[D11] Forbidden dynamic code execution '{target}()' in '{self.rel_path}:{lineno}'.",
            )

        if target in ("os.rename", "os.renames", "pathlib.Path.rename") or (
            isinstance(node.func, ast.Attribute) and node.func.attr == "rename"
        ):
            self._record_issue(
                lineno,
                f"[E12] Forbidden non-atomic rename '{target or '*.rename'}()' in '{self.rel_path}:{lineno}'. Use 'os.replace()' or 'Path.replace()'.",
            )

        if target in ("subprocess.run", "subprocess.call", "subprocess.check_call", "subprocess.check_output"):
            if not self._exempt("F13_SUBPROCESS"):
                has_timeout = any(kw.arg == "timeout" for kw in node.keywords)
                if not has_timeout:
                    self._record_issue(
                        lineno,
                        f"[F13] Subprocess call '{target}()' in '{self.rel_path}:{lineno}' missing required 'timeout=' keyword argument.",
                    )

        if target in ("os.system", "os.popen"):
            self._record_issue(
                lineno,
                f"[F13] Forbidden unmanaged shell execution '{target}()' in '{self.rel_path}:{lineno}'.",
            )

        if target in ("threading.Thread", "threading.Timer"):
            if not self._exempt("F13_THREAD"):
                self._record_issue(
                    lineno,
                    f"[F13] Forbidden unmanaged thread creation '{target}()' in '{self.rel_path}:{lineno}'.",
                )

        if target in ("getattr", "builtins.getattr") and len(node.args) >= 2:
            if isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                ref_target = f"{self._resolve_target(node.args[0])}.{node.args[1].value}"
                if ref_target in ("os.environ", "os.putenv", "os.unsetenv") and not self._exempt("B5"):
                    self._record_issue(
                        lineno,
                        f"[B5] Forbidden reflection access '{ref_target}' in '{self.rel_path}:{lineno}'.",
                    )
                elif ref_target in ("os.chdir", "os.fchdir", "os.getcwd", "os.getcwdb", "pathlib.Path.cwd") and not self._exempt("B4"):
                    self._record_issue(
                        lineno,
                        f"[B4] Forbidden reflection access '{ref_target}' in '{self.rel_path}:{lineno}'.",
                    )
                elif ref_target in ("sys.exit", "os._exit") and not self._exempt("B3"):
                    self._record_issue(
                        lineno,
                        f"[B3] Forbidden reflection access '{ref_target}' in '{self.rel_path}:{lineno}'.",
                    )
                elif ref_target == "sys.modules" and not self._exempt("D10_SYS_MODULES"):
                    self._record_issue(
                        lineno,
                        f"[D10] Forbidden reflection access '{ref_target}' in '{self.rel_path}:{lineno}'.",
                    )
                elif ref_target == "sys.path" and self.module_name != "core":
                    self._record_issue(
                        lineno,
                        f"Forbidden direct sys.path mutation in '{self.rel_path}:{lineno}' (reflection on sys.path). Runtime sys.path management must be delegated to 'core.platform'.",
                    )

        self.generic_visit(node)


class Checker:
    def __init__(self) -> None:
        self._parsed_py_cache: Dict[str, Any] = {}
        self._syntax_reported_files: Set[str] = set()

    def _get_parsed_py(self, full_path: str, filename: Optional[str] = None) -> Tuple[str, ast.Module]:
        """Reads and parses a Python file into (content, ast.Module), caching per check_module run."""
        norm_p = os.path.abspath(full_path)
        if norm_p in self._parsed_py_cache:
            cached = self._parsed_py_cache[norm_p]
            if isinstance(cached, BaseException):
                raise cached
            return cached
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            tree = ast.parse(content, filename=filename or full_path)
            self._parsed_py_cache[norm_p] = (content, tree)
            return content, tree
        except Exception as exc:
            self._parsed_py_cache[norm_p] = exc
            raise

    def _record_syntax_issue(self, report: CheckReport, norm_p: str, rel_p: str, exc: Exception) -> None:
        if norm_p in self._syntax_reported_files:
            return
        self._syntax_reported_files.add(norm_p)
        if isinstance(exc, SyntaxError):
            msg = f"SyntaxError in {rel_p}:{exc.lineno}: {exc.msg}"
            lineno = exc.lineno
        else:
            msg = f"Error parsing {rel_p}: {exc}"
            lineno = None
        report.issues.append(
            CheckIssue(
                severity=CheckSeverity.FAIL,
                category="SYNTAX",
                message=msg,
                file_path=rel_p,
                line_number=lineno,
            )
        )

    def check_module(self, name: str) -> CheckReport:
        self._parsed_py_cache = {}
        self._syntax_reported_files = set()
        report = CheckReport(module=name)
        src_uri = f"module.source://{name}"
        if not vfs.exists(src_uri):
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="MANIFEST",
                    message=f"Module source not found at {src_uri}.",
                )
            )
        else:
            real_dir = uri.resolve(src_uri)
            m_data = self._check_manifest(name, real_dir, report)
            self._check_core_injection(name, real_dir, report, m_data=m_data)
            self._check_file_structure(name, real_dir, report)
            self._check_source_files(name, real_dir, report)
            self._check_test_classes(name, real_dir, report)
            self._check_sandbox_hooks(name, real_dir, report)
            self._check_docs_pollution(name, real_dir, report)

        if report.has_fails and report.agent_directive:
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="DIRECTIVE",
                    message=report.agent_directive,
                )
            )
        return report

    def _check_manifest(self, name: str, real_dir: str, report: CheckReport) -> Optional[Dict[str, Any]]:
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
            return None

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                m_data = json.load(f)
            if not isinstance(m_data, dict):
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.FAIL,
                        category="MANIFEST",
                        message="Invalid JSON in manifest.json: root must be an object.",
                        file_path="manifest.json",
                    )
                )
                return None

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
                except ValueError:
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

            opt = m_data.get("optional")
            if opt is not None:
                if not isinstance(opt, dict):
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.FAIL,
                            category="MANIFEST",
                            message="'optional' field must be an object/dict mapping module names to config.",
                            file_path="manifest.json",
                        )
                    )
                else:
                    for opt_mod, opt_cfg in opt.items():
                        if not isinstance(opt_cfg, dict):
                            report.issues.append(
                                CheckIssue(
                                    severity=CheckSeverity.FAIL,
                                    category="MANIFEST",
                                    message=f"Optional module '{opt_mod}' configuration must be an object with 'version' and 'hint'.",
                                    file_path="manifest.json",
                                )
                            )
                        else:
                            if "version" not in opt_cfg or not isinstance(opt_cfg["version"], str) or not opt_cfg["version"].strip():
                                report.issues.append(
                                    CheckIssue(
                                        severity=CheckSeverity.FAIL,
                                        category="MANIFEST",
                                        message=f"Optional module '{opt_mod}' missing non-empty string 'version'.",
                                        file_path="manifest.json",
                                    )
                                )
                            if "hint" not in opt_cfg or not isinstance(opt_cfg["hint"], str) or not opt_cfg["hint"].strip():
                                report.issues.append(
                                    CheckIssue(
                                        severity=CheckSeverity.FAIL,
                                        category="MANIFEST",
                                        message=f"Optional module '{opt_mod}' missing non-empty string 'hint'.",
                                        file_path="manifest.json",
                                    )
                                )

            onboarding = m_data.get("onboarding")
            if onboarding is not None:
                if not isinstance(onboarding, list) or any(not isinstance(item, str) or not item.strip() for item in onboarding):
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.FAIL,
                            category="MANIFEST",
                            message="'onboarding' field in manifest.json must be a list of non-empty strings.",
                            file_path="manifest.json",
                        )
                    )

            rel_meta = m_data.get("release")
            if rel_meta is not None:
                if not isinstance(rel_meta, dict):
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.FAIL,
                            category="MANIFEST",
                            message="'release' field in manifest.json must be a JSON object.",
                            file_path="manifest.json",
                        )
                    )
                else:
                    for rk in ("type", "urgency", "summary"):
                        if rk in rel_meta and (not isinstance(rel_meta[rk], str) or not rel_meta[rk].strip()):
                            report.issues.append(
                                CheckIssue(
                                    severity=CheckSeverity.FAIL,
                                    category="MANIFEST",
                                    message=f"'release.{rk}' in manifest.json must be a non-empty string.",
                                    file_path="manifest.json",
                                )
                            )

            self._check_pip_dependencies(name, m_data, report)
            if isinstance(m_ver, str) and m_ver.strip():
                self._check_package_dunder_version(name, real_dir, m_ver.strip(), report)
            return m_data
        except Exception as e:
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="MANIFEST",
                    message=f"Invalid JSON in manifest.json: {e}",
                    file_path="manifest.json",
                )
            )
            return None

    def _check_package_dunder_version(self, name: str, real_dir: str, manifest_ver: str, report: CheckReport) -> None:
        """Verify that top-level package `__init__.py` `__version__` string literal (if present) matches `manifest.json` version."""
        try:
            entries = os.listdir(real_dir)
        except OSError:
            return
        for entry in sorted(entries):
            if entry in ("tests", "scripts", "contributes", "configurable", "assets", "skills") or entry.startswith("."):
                continue
            init_path = os.path.join(real_dir, entry, "__init__.py")
            if not os.path.isfile(init_path):
                continue
            rel_init = f"{entry}/__init__.py"
            try:
                _, tree = self._get_parsed_py(init_path, filename=rel_init)
            except Exception:
                continue
            for node in tree.body:
                target_names: List[str] = []
                val_node: Optional[ast.AST] = None
                if isinstance(node, ast.Assign):
                    target_names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                    val_node = node.value
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    target_names = [node.target.id]
                    val_node = node.value
                if "__version__" in target_names and isinstance(val_node, ast.Constant) and isinstance(val_node.value, str):
                    dunder_ver = val_node.value.strip()
                    if dunder_ver != manifest_ver:
                        report.issues.append(
                            CheckIssue(
                                severity=CheckSeverity.FAIL,
                                category="MANIFEST",
                                message=(
                                    f"Package __version__ mismatch in '{rel_init}': "
                                    f"__version__ is '{dunder_ver}', but manifest.json version is '{manifest_ver}'."
                                ),
                                file_path=rel_init,
                                line_number=getattr(node, "lineno", None),
                            )
                        )

    def _check_pip_dependencies(self, name: str, m_data: Dict[str, Any], report: CheckReport) -> None:
        if "pip_dependencies" not in m_data:
            return

        pip_deps = m_data.get("pip_dependencies")
        if not isinstance(pip_deps, dict):
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="MANIFEST",
                    message="'pip_dependencies' field must be an object (dict).",
                    file_path="manifest.json",
                )
            )
            return

        for pkg_name, spec in pip_deps.items():
            if not isinstance(pkg_name, str) or not pkg_name.strip():
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.FAIL,
                        category="MANIFEST",
                        message=f"Invalid package name in 'pip_dependencies': '{pkg_name}'. Must be a non-empty string.",
                        file_path="manifest.json",
                    )
                )
            elif spec is not None and not isinstance(spec, str):
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.FAIL,
                        category="MANIFEST",
                        message=f"Invalid version specification for package '{pkg_name}' in 'pip_dependencies': expected string or null, got {type(spec).__name__}.",
                        file_path="manifest.json",
                    )
                )

    def _check_core_injection(
        self,
        name: str,
        real_dir: str,
        report: CheckReport,
        m_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        core_contribute_path = os.path.join(real_dir, "contributes", "core.json")
        if name != "core" and not os.path.exists(core_contribute_path):
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.WARN,
                    category="CONTRIBUTES",
                    message="Module lacks 'contributes/core.json' declaration. Consider declaring CLI commands or URI schemes.",
                    file_path="contributes/core.json",
                )
            )

        contrib_dir = os.path.join(real_dir, "contributes")
        if not os.path.isdir(contrib_dir):
            return

        from core.validator import ContributesValidator

        # 1. Meta-Check: _format.json if present
        fmt_path = os.path.join(contrib_dir, "_format.json")
        if os.path.exists(fmt_path):
            try:
                with open(fmt_path, "r", encoding="utf-8") as f:
                    fmt_data = json.load(f)
                meta_res = ContributesValidator.validate_format_schema(fmt_data)
                for err in meta_res.errors:
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.FAIL,
                            category="CONTRIBUTES",
                            message=f"Invalid _format.json schema: [{err.path}] {err.message}",
                            file_path="contributes/_format.json",
                        )
                    )
                for w in meta_res.warnings:
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.WARN,
                            category="CONTRIBUTES",
                            message=f"_format.json note: [{w.path}] {w.message}",
                            file_path="contributes/_format.json",
                        )
                    )
            except Exception as e:
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.FAIL,
                        category="CONTRIBUTES",
                        message=f"Syntax error in 'contributes/_format.json': {e}",
                        file_path="contributes/_format.json",
                    )
                )

        # 2. Ingress & Egress Boundary Check on <target>.json
        try:
            files = sorted(f for f in os.listdir(contrib_dir) if f.endswith(".json"))
        except OSError:
            files = []

        for fname in files:
            if fname.startswith("_"):
                continue
            target = fname[:-5]
            f_path = os.path.join(contrib_dir, fname)
            try:
                with open(f_path, "r", encoding="utf-8") as f:
                    c_data = json.load(f)
            except Exception as e:
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.FAIL,
                        category="CONTRIBUTES",
                        message=f"Syntax error in 'contributes/{fname}': {e}",
                        file_path=f"contributes/{fname}",
                    )
                )
                continue

            target_fmt = None
            src_fmt_uri = f"module.source://{target}/contributes/_format.json"
            if vfs.exists(src_fmt_uri):
                try:
                    target_fmt = vfs.read_json(src_fmt_uri)
                except Exception:
                    target_fmt = None
            if target_fmt is None:
                target_fmt = contributes.get_format(target)
            if target_fmt is None:
                continue

            val_res = ContributesValidator.validate(target, c_data, donor_mod=name, format_schema=target_fmt, strict_points=True)
            if target == "core" and isinstance(c_data, dict) and "locales" in c_data and isinstance(c_data["locales"], dict):
                if name != "core":
                    manifest_obj = m_data
                    if manifest_obj is None:
                        manifest_path = os.path.join(real_dir, "manifest.json")
                        if os.path.exists(manifest_path):
                            try:
                                with open(manifest_path, "r", encoding="utf-8") as mf:
                                    loaded_mf = json.load(mf)
                                if isinstance(loaded_mf, dict):
                                    manifest_obj = loaded_mf
                            except (OSError, json.JSONDecodeError):
                                manifest_obj = None
                    if isinstance(manifest_obj, dict):
                        deps = manifest_obj.get("dependencies")
                        core_spec = deps.get("core") if isinstance(deps, dict) else None
                        if not _is_core_spec_at_least_1_2_0(core_spec):
                            report.issues.append(
                                CheckIssue(
                                    severity=CheckSeverity.FAIL,
                                    category="MANIFEST",
                                    message=(
                                        f"Module '{name}' declares 'locales' in 'contributes/core.json' "
                                        f"which requires 'core' >= 1.2.0 in 'manifest.json' dependencies "
                                        f"(found: {core_spec!r})."
                                    ),
                                    file_path="manifest.json",
                                )
                            )
                try:
                    from core import locale as core_locale
                    loc_res = core_locale.validate_module_locales(name, c_data["locales"], base_dir=real_dir)
                    val_res.issues.extend(loc_res.issues)
                    val_res.is_valid = len([i for i in val_res.issues if i.severity == "ERROR"]) == 0
                except Exception as e:
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.FAIL,
                            category="CONTRIBUTES",
                            message=f"Locale validation error in 'contributes/{fname}': {e}",
                            file_path=f"contributes/{fname}",
                        )
                    )
            for err in val_res.errors:
                hint = f" ({err.suggestion})" if err.suggestion else ""
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.FAIL,
                        category="CONTRIBUTES",
                        message=f"Schema violation in 'contributes/{fname}': [{err.path}] {err.message}{hint}",
                        file_path=f"contributes/{fname}",
                    )
                )
            for w in val_res.warnings:
                hint = f" ({w.suggestion})" if w.suggestion else ""
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.WARN,
                        category="CONTRIBUTES",
                        message=f"Schema warning in 'contributes/{fname}': [{w.path}] {w.message}{hint}",
                        file_path=f"contributes/{fname}",
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
        else:
            self._check_cli_compliance(name, cli_path, report)

        # 2. Check for scattered config.*.json at root
        for item in sorted(os.listdir(real_dir)):
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
            for cfg_f in sorted(os.listdir(cfg_dir)):
                if not ((cfg_f.startswith("config.") and cfg_f.endswith(".json")) or cfg_f == "_format.json"):
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.WARN,
                            category="STRUCTURE",
                            message=f"Non-standard configuration template naming in 'configurable/{cfg_f}'. Expected pattern 'config.*.json' or '_format.json'.",
                            file_path=f"configurable/{cfg_f}",
                        )
                    )
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
        for root, dirs, files in os.walk(real_dir):
            dirs[:] = sorted(d for d in dirs if d not in ("__pycache__", ".pytest_cache", ".git"))
            for f in sorted(files):
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

        # 5. Check contributes/_manifest.md presence
        contrib_dir = os.path.join(real_dir, "contributes")
        if os.path.isdir(contrib_dir):
            manifest_doc = os.path.join(contrib_dir, "_manifest.md")
            if not os.path.exists(manifest_doc):
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.FAIL,
                        category="CONTRIBUTES",
                        message="Module defines 'contributes/' directory but lacks 'contributes/_manifest.md' declaration index.",
                        file_path="contributes/_manifest.md",
                    )
                )
        legacy_fmt_doc = os.path.join(real_dir, "contributes.format.md")
        if os.path.exists(legacy_fmt_doc):
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.WARN,
                    category="CONTRIBUTES",
                    message="Legacy 'contributes.format.md' detected. Please migrate to 'contributes/_manifest.md'.",
                    file_path="contributes.format.md",
                )
            )

    def _check_cli_compliance(self, name: str, cli_path: str, report: CheckReport) -> None:
        """
        以 AST 靜態檢核 scripts/cli.py 的合規性：
        1. 必須宣告對應 contributes/core.json 的具名命令函式 def <cmd>(cmd_bags: CmdBags) -> int
        2. 絕對不可有 def main(...) 或舊版 def process(...)
        3. 絕對不可有 if __name__ == '__main__':
        4. 頂層節點除 Docstring、Import、ImportFrom、FunctionDef、ClassDef 外，嚴禁任何未包覆在 func/class 內的執行陳述式。
        """
        try:
            _, tree = self._get_parsed_py(cli_path, filename="scripts/cli.py")
        except Exception as e:
            self._record_syntax_issue(report, os.path.abspath(cli_path), "scripts/cli.py", e)
            return

        declared_funcs, has_main_func, has_if_name_main, invalid_top_level_nodes = _audit_cli_script_ast(tree)

        module_dir = os.path.dirname(os.path.dirname(os.path.abspath(cli_path)))
        cmd_leaves = _collect_declared_cli_commands(module_dir)

        if cmd_leaves:
            missing_cmd_funcs = []
            for full_cmd, primary_cmd in cmd_leaves:
                candidates = {full_cmd.replace("-", "_"), primary_cmd.replace("-", "_")}
                if not any(c in declared_funcs for c in candidates):
                    missing_cmd_funcs.append(full_cmd)
            if missing_cmd_funcs:
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.FAIL,
                        category="STRUCTURE",
                        message=f"Missing required command handler functions in 'scripts/cli.py': {', '.join(missing_cmd_funcs)}.",
                        file_path="scripts/cli.py",
                    )
                )
        else:
            public_handlers = [fn for fn in declared_funcs if not fn.startswith("_") and fn not in ("main", "process")]
            if not public_handlers:
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.FAIL,
                        category="STRUCTURE",
                        message="Missing required command handler function 'def <cmd>(cmd_bags: CmdBags) -> int' in 'scripts/cli.py'.",
                        file_path="scripts/cli.py",
                    )
                )

        if has_main_func:
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="STRUCTURE",
                    message="Forbidden function 'main' found in 'scripts/cli.py'. Module CLI entries must declare command handlers 'def <cmd>(cmd_bags: CmdBags) -> int'.",
                    file_path="scripts/cli.py",
                )
            )

        if has_if_name_main:
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="STRUCTURE",
                    message="Forbidden 'if __name__ == \"__main__\":' execution block found in 'scripts/cli.py'. Module CLI must be purely importable.",
                    file_path="scripts/cli.py",
                )
            )

        for lineno, desc in invalid_top_level_nodes:
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="ANTIPATTERN",
                    message=f"Forbidden {desc} outside function/class at line {lineno} in 'scripts/cli.py'. All executable statements must be enclosed inside functions or classes.",
                    file_path="scripts/cli.py",
                    line_number=lineno,
                )
            )

    def _check_source_files(self, name: str, real_dir: str, report: CheckReport) -> None:
        for root, dirs, files in os.walk(real_dir):
            dirs[:] = sorted(d for d in dirs if d not in ("__pycache__", ".pytest_cache", ".git"))
            for f in sorted(files):
                if not f.endswith(".py"):
                    continue

                full_p = os.path.join(root, f)
                rel_p = os.path.relpath(full_p, real_dir).replace("\\", "/")
                is_test_file = rel_p.startswith("tests/")

                try:
                    _, tree = self._get_parsed_py(full_p, filename=rel_p)
                except Exception as e:
                    self._record_syntax_issue(report, os.path.abspath(full_p), rel_p, e)
                    continue

                visitor = _SourceGuardrailVisitor(name, rel_p, is_test_file, report)
                visitor.analyze(tree)

    def _check_test_classes(self, name: str, real_dir: str, report: CheckReport) -> None:
        tests_dir = os.path.join(real_dir, "tests")
        if not os.path.isdir(tests_dir):
            return

        for t_file in sorted(os.listdir(tests_dir)):
            if not (t_file.startswith("test_") and t_file.endswith(".py")):
                continue
            t_full = os.path.join(tests_dir, t_file)
            rel_p = f"tests/{t_file}"
            try:
                _, tree = self._get_parsed_py(t_full, filename=rel_p)
            except Exception as e:
                self._record_syntax_issue(report, os.path.abspath(t_full), rel_p, e)
                continue

            top_level_classes = {n for n in tree.body if isinstance(n, ast.ClassDef)}
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    _verify_test_class_isolation_and_marks(
                        node, t_file, report, is_top_level=(node in top_level_classes)
                    )
                    _check_require_decorator_node(node, t_file, report)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _check_require_decorator_node(node, t_file, report)

    def _check_sandbox_hooks(self, name: str, real_dir: str, report: CheckReport) -> None:
        scripts_dir = os.path.join(real_dir, "scripts")
        if not os.path.isdir(scripts_dir):
            return

        try:
            script_files = sorted(os.listdir(scripts_dir))
        except OSError:
            return

        for s_file in script_files:
            if not (s_file.startswith("hook.") and s_file.endswith(".py")):
                continue
            hook_path = os.path.join(scripts_dir, s_file)
            rel_p = f"scripts/{s_file}"
            try:
                _, tree = self._get_parsed_py(hook_path, filename=rel_p)
            except Exception as e:
                self._record_syntax_issue(report, os.path.abspath(hook_path), rel_p, e)
                continue

            for node in tree.body:
                if isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if node.name.startswith("on_") or node.name in ("pre_cli_dispatch", "post_cli_dispatch"):
                            total_args = len(node.args.args) + (1 if node.args.vararg else 0) + (1 if node.args.kwarg else 0)
                            if total_args < 1:
                                report.issues.append(
                                    CheckIssue(
                                        severity=CheckSeverity.FAIL,
                                        category="STRUCTURE",
                                        message=f"Hook function '{node.name}' in {rel_p}:{node.lineno} must accept at least 1 parameter ('context').",
                                        file_path=rel_p,
                                        line_number=node.lineno,
                                    )
                                )
                elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    continue
                elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                else:
                    stmt_type = type(node).__name__
                    lineno = getattr(node, "lineno", 0)
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.FAIL,
                            category="ANTIPATTERN",
                            message=f"Forbidden top-level statement '{stmt_type}' in {rel_p}:{lineno}. Hook scripts must only declare imports, functions, or classes.",
                            file_path=rel_p,
                            line_number=lineno,
                        )
                    )

    def _check_docs_pollution(self, name: str, real_dir: str, report: CheckReport) -> None:
        docs_dir = os.path.join(real_dir, "docs")
        if not os.path.isdir(docs_dir):
            return

        for root, dirs, files in os.walk(docs_dir):
            dirs[:] = sorted(d for d in dirs if d not in ("__pycache__", ".pytest_cache", ".git"))
            for f in sorted(files):
                if not f.endswith(".md"):
                    continue
                full_p = os.path.join(root, f)
                rel_p = os.path.relpath(full_p, real_dir).replace("\\", "/")
                try:
                    with open(full_p, "r", encoding="utf-8", errors="replace") as df:
                        for lineno, line in enumerate(df, start=1):
                            if "project://source/" in line:
                                report.issues.append(
                                    CheckIssue(
                                        severity=CheckSeverity.WARN,
                                        category="DOCUMENTATION",
                                        message=f"Documentation path pollution: Hardcoded 'project://source/' detected in '{rel_p}:{lineno}'. Downstream developers have no source/ directory; use 'module://<mod>/' semantic URI instead.",
                                        file_path=rel_p,
                                        line_number=lineno,
                                    )
                                )
                except OSError:
                    pass

    def check_all(self) -> Dict[str, CheckReport]:
        return {mod: self.check_module(mod) for mod in discover_source_modules()}


def discover_source_modules(
    target: Optional[str] = None,
    require_manifest: bool = True,
) -> List[str]:
    """
    Scan module.source:// and return sorted valid module names.
    Supports optional target filtering (<mod> or <mod>:<selector>) and manifest.json check.
    """
    src_root_uri = "module.source://"
    if not vfs.exists(src_root_uri):
        return []
    src_real = uri.resolve(src_root_uri)
    if not os.path.isdir(src_real):
        return []

    if target:
        target_mod = target.split(":", 1)[0] if ":" in target else target
        mod_path = os.path.join(src_real, target_mod)
        if os.path.isdir(mod_path) and (not require_manifest or os.path.isfile(os.path.join(mod_path, "manifest.json"))):
            return [target_mod]
        return []

    modules: List[str] = []
    for item in sorted(os.listdir(src_real)):
        if item.startswith("."):
            continue
        mod_path = os.path.join(src_real, item)
        if os.path.isdir(mod_path) and (not require_manifest or os.path.isfile(os.path.join(mod_path, "manifest.json"))):
            modules.append(item)
    return modules
