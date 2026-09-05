;; Python S-Expression Query for Universal AST
(class_definition
  name: (identifier) @symbol.name
  body: (block
    (expression_statement
      (string) @symbol.docstring)?
  )?
) @definition.class

(class_definition
  body: (block
    (expression_statement
      (assignment
        left: (identifier) @symbol.name
        type: (type)? @symbol.return_type
      ) @definition.field
    )
  )
)

(function_definition
  name: (identifier) @symbol.name
  parameters: (parameters) @symbol.signature
  return_type: (type)? @symbol.return_type
  body: (block
    (expression_statement
      (string) @symbol.docstring)?
  )?
) @definition.function

(call
  function: [
    (identifier) @call.name
    (attribute attribute: (identifier) @call.name)
  ]
) @call.site

(import_statement) @import.stmt
(import_from_statement) @import.stmt
