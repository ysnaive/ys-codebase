;; Markdown S-Expression Query for Universal AST
(atx_heading
  (inline) @symbol.name
) @definition.heading

(setext_heading
  (paragraph) @symbol.name
) @definition.heading

(pipe_table) @definition.table
