{#-
  Company-name normalization for matching (BigQuery):
    lower → strip accents (NFD splits 'í' into 'i' + combining mark; \p{M} removes the marks) → drop punctuation →
    drop trailing legal-form suffixes (S.L., Lda., S.A. de C.V., S.A.S., SpA, S.R.L.) → collapse spaces.
  Normalize BOTH sides with the same function, otherwise EDIT_DISTANCE measures formatting, not identity.
-#}
{% macro normalize_company_name(col) -%}
trim(regexp_replace(
    regexp_replace(
        regexp_replace(regexp_replace(normalize(lower({{ col }}), NFD), r'\p{M}', ''), r'[^a-z0-9 ]', ''),
        r'\s+(sa de cv|sl|lda|sas|spa|srl)$', ''),
    r'\s+', ' '))
{%- endmacro %}
