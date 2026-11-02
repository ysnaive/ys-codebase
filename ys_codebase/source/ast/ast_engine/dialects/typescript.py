"""
TypeScript dialect adapter for module:ast.
"""

from .javascript import JavaScriptDialect


class TypeScriptDialect(JavaScriptDialect):
    language = "typescript"
    scope_separator = "."
    supports_partial_aggregation = False
