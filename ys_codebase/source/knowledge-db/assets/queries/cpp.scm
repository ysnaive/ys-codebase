;; C/C++ S-Expression Query for Universal AST
(class_specifier
  name: [(type_identifier) (template_type)] @symbol.name
) @definition.class

(struct_specifier
  name: [(type_identifier) (template_type)] @symbol.name
) @definition.struct

(enum_specifier
  name: (type_identifier) @symbol.name
) @definition.enum

(namespace_definition
  name: (namespace_identifier) @symbol.name
) @definition.namespace

(function_definition
  declarator: (function_declarator
    declarator: [(identifier) (field_identifier) (qualified_identifier) (destructor_name)] @symbol.name
    parameters: (parameter_list) @symbol.signature
  )
) @definition.function

(field_declaration
  declarator: (function_declarator
    declarator: [(field_identifier) (destructor_name)] @symbol.name
    parameters: (parameter_list) @symbol.signature
  )
) @definition.method

(preproc_def
  name: (identifier) @symbol.name
) @definition.macro

(preproc_function_def
  name: (identifier) @symbol.name
  parameters: (preproc_params) @symbol.signature
) @definition.macro

(call_expression
  function: [
    (identifier) @call.name
    (field_expression field: (field_identifier) @call.name)
    (qualified_identifier name: (identifier) @call.name)
  ]
) @call.site
