;; C# S-Expression Query for Universal AST
(class_declaration
  name: (identifier) @symbol.name
) @definition.class

(interface_declaration
  name: (identifier) @symbol.name
) @definition.interface

(struct_declaration
  name: (identifier) @symbol.name
) @definition.struct

(record_declaration
  name: (identifier) @symbol.name
) @definition.struct

(enum_declaration
  name: (identifier) @symbol.name
) @definition.enum

(namespace_declaration
  name: [(identifier) (qualified_name)] @symbol.name
) @definition.namespace

(file_scoped_namespace_declaration
  name: [(identifier) (qualified_name)] @symbol.name
) @definition.namespace

(method_declaration
  name: (identifier) @symbol.name
  parameters: (parameter_list) @symbol.signature
  type: (_)? @symbol.return_type
) @definition.method

(local_function_statement
  name: (identifier) @symbol.name
  parameters: (parameter_list) @symbol.signature
  type: (_)? @symbol.return_type
) @definition.function

(constructor_declaration
  name: (identifier) @symbol.name
  parameters: (parameter_list) @symbol.signature
) @definition.constructor

(property_declaration
  name: (identifier) @symbol.name
  type: (_)? @symbol.return_type
) @definition.property

(invocation_expression
  function: [
    (identifier) @call.name
    (generic_name
      (identifier) @call.name
    )
    (member_access_expression
      name: (identifier) @call.name
    )
    (member_access_expression
      name: (generic_name
        (identifier) @call.name
      )
    )
    (conditional_access_expression
      (member_binding_expression
        name: (identifier) @call.name
      )
    )
    (conditional_access_expression
      (member_binding_expression
        name: (generic_name
          (identifier) @call.name
        )
      )
    )
  ]
) @call.site

(using_directive) @import.stmt
