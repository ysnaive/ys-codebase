;; JavaScript S-Expression Query for Universal AST
(class_declaration
  name: (identifier) @symbol.name
) @definition.class

(function_declaration
  name: (identifier) @symbol.name
  parameters: (formal_parameters) @symbol.signature
) @definition.function

(method_definition
  name: [(property_identifier) (identifier)] @symbol.name
  parameters: (formal_parameters) @symbol.signature
) @definition.method

(variable_declarator
  name: (identifier) @symbol.name
  value: (function_expression
    parameters: (formal_parameters) @symbol.signature
  )
) @definition.function

(variable_declarator
  name: (identifier) @symbol.name
  value: (arrow_function
    parameters: (formal_parameters) @symbol.signature
  )
) @definition.function

(call_expression
  function: [
    (identifier) @call.name
    (member_expression
      property: (property_identifier) @call.name
    )
  ]
) @call.site

(import_statement) @import.stmt
(export_statement) @export.stmt
