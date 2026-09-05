;; C S-Expression Query for Universal AST
(struct_specifier
  name: (type_identifier) @symbol.name
) @definition.struct

(enum_specifier
  name: (type_identifier) @symbol.name
) @definition.enum

(union_specifier
  name: (type_identifier) @symbol.name
) @definition.union

(function_definition
  declarator: (function_declarator
    declarator: (identifier) @symbol.name
    parameters: (parameter_list) @symbol.signature
  )
) @definition.function

(call_expression
  function: (identifier) @call.name
) @call.site
