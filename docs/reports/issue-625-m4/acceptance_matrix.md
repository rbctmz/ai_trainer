# #625 M4: evidence map

Reference: [accepted specification](../../database_path_guardrails_slice_spec.md).
Results below refer to synthetic source/env only; the listed tests do not claim
to sandbox arbitrary native programs or to certify Windows.

| Requirement | Evidence and scope |
| --- | --- |
| Plain pytest and launcher isolate before collection; external override refuses | `test_external_override_refused_before_collection_without_disclosing_path`, `test_default_collection_uses_owned_store_without_loading_dotenv`, `test_launcher_and_plain_pytest_both_install_before_collection`: child pytest and sentinel assertions. |
| URI, aliases, sidecars, future targets and inaccessible identity | `test_foreign_aliases_and_links_are_not_owned`, `test_sqlite_uri_parsing_cannot_escape_scope`, `test_protected_family_blocks_future_names`, `test_unresolved_symlinks_fail_closed`, `test_inspection_failure_is_safe_and_does_not_disclose_target` and native case/Unicode tests. Actual native alias cases are conditional on filesystem semantics. |
| Late override, connection and SQLite internal opens | `test_audit_blocks_late_escape_in_fresh_child`, `test_sql_open_operations_respect_scope_before_creating_destination`, `test_uri_control_character_cannot_disguise_foreign_file_as_memory`, `test_python_startup_options_cannot_bypass_child_guard`: subprocess/actual open and sentinel checks. |
| Acceptance startup, child, reset, real local health | `test_acceptance_refuses_external_database_before_doctor_or_server`, `test_acceptance_child_rechecks_environment_before_main`, `test_acceptance_reset_refuses_mismatched_store_before_delete`, `test_acceptance_starts_real_isolated_streamlit_health`: synthetic only; not a user service restart. |
| Ordinary product database and demo lifecycle, restart | [product compatibility probe](product_compatibility_probe.py): two fresh interpreters without the scratch runtime guard, synthetic real/demo stores, demo seed and clear, preserved real marker. Probe-only audit bounds SQLite connections and blocks network/dotenv. |
| Cleanup and foreign basetemp | `test_owned_scope_allows_own_files_and_cleanup_is_idempotent`, `test_scope_rejects_replaced_root_without_removing_foreign_data`, `test_cleanup_unlinks_nested_symlink_and_keeps_external_directory`, `test_existing_foreign_basetemp_refused_before_pytest_deletes_it`. |
| Maintenance preview/write and provider gate | `test_direct_repair_apply_requires_operator_consent_before_preview_or_write`, `test_maintenance_cli_apply_requires_confirmation_before_write`, `test_maintenance_previews_are_read_only_and_do_not_call_provider`, `test_operator_backup_must_match_selected_working_database`, `test_confirmed_operator_repair_accepts_matching_synthetic_backup`, generator direct-call tests. No real provider call. |
| Ignore family names | `git check-ignore --no-index --stdin`, four literal strings only, no probe file creation. |
| Relocation/backup/concurrency compatibility | Combined specified `test_database_paths.py`, `test_database_relocation.py`, `test_database_relocation_drill.py`, `test_sqlite_backup_restore.py`, `test_sqlite_concurrency_policy.py`, `test_database_path_guardrails.py`, `test_scratch_entrypoints.py`: 291 passed on macOS. |

CI Linux, full contributor-safe run and browser E2E are recorded separately in
ExecPlan/PR. Native Windows and ACL cases remain NOT RUN unless independently
verified. Personal DBs, user services, credentials and live provider calls are
outside this acceptance.
