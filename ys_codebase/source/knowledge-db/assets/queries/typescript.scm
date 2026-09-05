;; TypeScript S-Expression Query for Universal AST
(class_declaration
  name: (type_identifier) @symbol.name
) @definition.class

(interface_declaration
  name: (type_identifier) @symbol.name
) @definition.interface

(enum_declaration
  name: (identifier) @symbol.name
) @definition.enum

(type_alias_declaration
  name: (type_identifier) @symbol.name
) @definition.type

(function_declaration
  name: (identifier) @symbol.name
  parameters: (formal_parameters) @symbol.signature
  return_type: (type_annotation)? @symbol.return_type
) @definition.function

(method_definition
  name: [(property_identifier) (identifier)] @symbol.name
  parameters: (formal_parameters) @symbol.signature
  return_type: (type_annotation)? @symbol.return_type
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
