{#-
  PII helpers. Two different techniques, two different purposes:
    * mask_email()  → MASKING: human-readable but redacted ('j***@acme.com'). Irreversible, not joinable.
    * hash_email()  → PSEUDONYMIZATION: deterministic SHA-256. Not readable, but JOINABLE across systems
                      (same email → same hash in Postgres and BigQuery) → an entity-resolution key (Phase 4).
                      Still personal data under GDPR (re-identifiable by hashing candidate emails), so it's
                      classified `internal`, not `public`.
  adapter.dispatch → one macro name, engine-specific SQL (Postgres here, BigQuery in ruta_udl).
-#}
{% macro mask_email(col) %}{{ return(adapter.dispatch('mask_email')(col)) }}{% endmacro %}
{% macro default__mask_email(col) %}regexp_replace({{ col }}, '^(.).*(@.*)$', '\1***\2'){% endmacro %}
{% macro bigquery__mask_email(col) %}regexp_replace({{ col }}, r'^(.).*(@.*)$', r'\1***\2'){% endmacro %}

{% macro hash_email(col) %}{{ return(adapter.dispatch('hash_email')(col)) }}{% endmacro %}
{% macro default__hash_email(col) %}encode(sha256(convert_to(lower(trim({{ col }})), 'UTF8')), 'hex'){% endmacro %}
{% macro bigquery__hash_email(col) %}to_hex(sha256(lower(trim({{ col }})))){% endmacro %}
