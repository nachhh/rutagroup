{#-
  normalize_tax_id: one business rule, many SQL dialects (adapter.dispatch).
  Canonical form: 1 letter + 8 digits, e.g. 'B12345678'.
    'B-1234567-8' → 'B12345678'   (RutaShip formatting)
    'b12345678'   → 'B12345678'
    'ES B12345678'→ 'B12345678'   (RutaPay VAT prefix: 2-letter country code)
  dbt resolves `postgres__` / `bigquery__` / `default__` by the active adapter. In a real org this macro
  would live in a shared internal dbt package used by every project (one definition = governance).
-#}
{% macro normalize_tax_id(col) %}
  {{ return(adapter.dispatch('normalize_tax_id')(col)) }}
{% endmacro %}

{% macro default__normalize_tax_id(col) %}
  case
    when regexp_replace(upper({{ col }}), '[^A-Z0-9]', '', 'g') ~ '^[A-Z]{2}[A-Z][0-9]{8}$'
      then right(regexp_replace(upper({{ col }}), '[^A-Z0-9]', '', 'g'), 9)
    else nullif(regexp_replace(upper({{ col }}), '[^A-Z0-9]', '', 'g'), '')
  end
{% endmacro %}

{% macro bigquery__normalize_tax_id(col) %}
  case
    when regexp_contains(regexp_replace(upper({{ col }}), r'[^A-Z0-9]', ''), r'^[A-Z]{2}[A-Z][0-9]{8}$')
      then right(regexp_replace(upper({{ col }}), r'[^A-Z0-9]', ''), 9)
    else nullif(regexp_replace(upper({{ col }}), r'[^A-Z0-9]', ''), '')
  end
{% endmacro %}
