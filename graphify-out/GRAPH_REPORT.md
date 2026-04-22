# Graph Report - /Users/sss/devprog/devprog_sss/AI_prog/AI_Agents/hermes-agent/hermes_cli  (2026-04-22)

## Corpus Check
- 49 files · ~166,021 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1919 nodes · 4442 edges · 33 communities detected
- Extraction: 73% EXTRACTED · 27% INFERRED · 0% AMBIGUOUS · INFERRED: 1215 edges (avg confidence: 0.7)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Claw CLI Commands|Claw CLI Commands]]
- [[_COMMUNITY_Authentication Flow|Authentication Flow]]
- [[_COMMUNITY_CLI Output & Colors|CLI Output & Colors]]
- [[_COMMUNITY_CLI Output & Colors|CLI Output & Colors]]
- [[_COMMUNITY_Authentication Flow|Authentication Flow]]
- [[_COMMUNITY_Login Flow|Login Flow]]
- [[_COMMUNITY_Login Flow|Login Flow]]
- [[_COMMUNITY_Backup & Snapshots|Backup & Snapshots]]
- [[_COMMUNITY_Model Management|Model Management]]
- [[_COMMUNITY_CLI Banner Display|CLI Banner Display]]
- [[_COMMUNITY_Command Lookup|Command Lookup]]
- [[_COMMUNITY_Model Management|Model Management]]
- [[_COMMUNITY_Debug & Telemetry|Debug & Telemetry]]
- [[_COMMUNITY_Backup & Snapshots|Backup & Snapshots]]
- [[_COMMUNITY_Plugin Context|Plugin Context]]
- [[_COMMUNITY_Clipboard Utilities|Clipboard Utilities]]
- [[_COMMUNITY_Authentication Flow|Authentication Flow]]
- [[_COMMUNITY_Webhooks|Webhooks]]
- [[_COMMUNITY_Doctor Diagnostic|Doctor Diagnostic]]
- [[_COMMUNITY_Model Management|Model Management]]
- [[_COMMUNITY_Model Management|Model Management]]
- [[_COMMUNITY_Uninstaller|Uninstaller]]
- [[_COMMUNITY_Pairing Commands|Pairing Commands]]
- [[_COMMUNITY_Environment Loader|Environment Loader]]
- [[_COMMUNITY_Tips Display|Tips Display]]
- [[_COMMUNITY_Default Soul|Default Soul]]
- [[_COMMUNITY_Misc Components|Misc Components]]
- [[_COMMUNITY_Command Lookup|Command Lookup]]
- [[_COMMUNITY_Command Lookup|Command Lookup]]
- [[_COMMUNITY_Command Lookup|Command Lookup]]
- [[_COMMUNITY_Command Lookup|Command Lookup]]
- [[_COMMUNITY_Command Lookup|Command Lookup]]
- [[_COMMUNITY_Command Lookup|Command Lookup]]

## God Nodes (most connected - your core abstractions)
1. `Colors` - 326 edges
2. `AuthError` - 103 edges
3. `color()` - 72 edges
4. `load_config()` - 69 edges
5. `get_env_value()` - 55 edges
6. `save_config()` - 51 edges
7. `save_env_value()` - 45 edges
8. `print_info()` - 44 edges
9. `gateway_setup()` - 33 edges
10. `gateway_command()` - 32 edges

## Surprising Connections (you probably didn't know these)
- `Exit with a clear error if stdin is not a terminal.      Interactive TUI command` --uses--> `AuthError`  [INFERRED]
  /Users/sss/devprog/devprog_sss/AI_prog/AI_Agents/hermes-agent/hermes_cli/main.py → /Users/sss/devprog/devprog_sss/AI_prog/AI_Agents/hermes-agent/hermes_cli/auth.py
- `Pre-parse --profile/-p and set HERMES_HOME before module imports.` --uses--> `AuthError`  [INFERRED]
  /Users/sss/devprog/devprog_sss/AI_prog/AI_Agents/hermes-agent/hermes_cli/main.py → /Users/sss/devprog/devprog_sss/AI_prog/AI_Agents/hermes-agent/hermes_cli/auth.py
- `Format a timestamp as relative time (e.g., '2h ago', 'yesterday').` --uses--> `AuthError`  [INFERRED]
  /Users/sss/devprog/devprog_sss/AI_prog/AI_Agents/hermes-agent/hermes_cli/main.py → /Users/sss/devprog/devprog_sss/AI_prog/AI_Agents/hermes-agent/hermes_cli/auth.py
- `Check if at least one inference provider is usable.` --uses--> `AuthError`  [INFERRED]
  /Users/sss/devprog/devprog_sss/AI_prog/AI_Agents/hermes-agent/hermes_cli/main.py → /Users/sss/devprog/devprog_sss/AI_prog/AI_Agents/hermes-agent/hermes_cli/auth.py
- `Interactive curses-based session browser with live search filtering.      Return` --uses--> `AuthError`  [INFERRED]
  /Users/sss/devprog/devprog_sss/AI_prog/AI_Agents/hermes-agent/hermes_cli/main.py → /Users/sss/devprog/devprog_sss/AI_prog/AI_Agents/hermes-agent/hermes_cli/auth.py

## Communities

### Community 0 - "Claw CLI Commands"
Cohesion: 0.02
Nodes (237): _archive_directory(), claw_command(), _cmd_cleanup(), _cmd_migrate(), _detect_openclaw_processes(), _find_migration_script(), _find_openclaw_dirs(), _load_migration_module() (+229 more)

### Community 1 - "Authentication Flow"
Cohesion: 0.02
Nodes (218): _agent_key_is_usable(), _auth_file_path(), _auth_lock_path(), _auth_store_lock(), AuthError, clear_provider_auth(), _codex_access_token_is_expiring(), _codex_device_code_login() (+210 more)

### Community 2 - "CLI Output & Colors"
Cohesion: 0.02
Nodes (206): Shared CLI output helpers for Hermes CLI modules.  Extracts the identical ``prin, Print a green success message with ✓ prefix., Print a yellow warning message with ⚠ prefix., Colors, Get a value from ~/.hermes/.env or environment., check_config_version(), config_command(), ConfigIssue (+198 more)

### Community 3 - "CLI Output & Colors"
Cohesion: 0.02
Nodes (172): color(), Shared ANSI color utilities for Hermes CLI modules., Apply color codes to text (only when color output is appropriate)., Return True when colored output is appropriate.      Respects the NO_COLOR envir, should_use_color(), Save configuration to ~/.hermes/config.yaml., save_config(), curses_checklist() (+164 more)

### Community 4 - "Authentication Flow"
Cohesion: 0.02
Nodes (145): get_anthropic_key(), Return the first usable Anthropic credential, or ``""``.      Checks both the ``, check_config_version(), config_command(), ConfigIssue, _deep_merge(), edit_config(), _ensure_default_soul_md() (+137 more)

### Community 5 - "Login Flow"
Cohesion: 0.03
Nodes (102): _add_forward_compat_models(), _fetch_models_from_api(), get_codex_model_ids(), Codex model discovery from API, local cache, and config., Return available Codex model IDs, trying API first, then local sources., Add Clawdbot-style synthetic forward-compat Codex models.      If a newer Codex, Fetch available models from the Codex API. Returns visible models sorted by prio, _read_cache_models() (+94 more)

### Community 6 - "Login Flow"
Cohesion: 0.03
Nodes (98): login_command(), Deprecated: use 'hermes model' or 'hermes setup' instead., check_for_updates(), Check how many commits behind origin/main the local repo is.      Does a ``git f, _clean(), generate_bash(), generate_fish(), generate_zsh() (+90 more)

### Community 7 - "Backup & Snapshots"
Cohesion: 0.04
Nodes (96): create_quick_snapshot(), _detect_prefix(), _format_size(), list_quick_snapshots(), _prune_quick_snapshots(), _quick_snapshot_root(), Backup and import commands for hermes CLI.  `hermes backup` creates a zip archiv, Human-readable file size. (+88 more)

### Community 8 - "Model Management"
Cohesion: 0.03
Nodes (80): BaseModel, cmd_dashboard(), Start the web UI server., Look up the most recent CLI session ID from SQLite. Returns None if unavailable., _resolve_last_cli_session(), get_disabled_skills(), Return disabled skill names. Platform-specific list falls back to global., _anthropic_oauth_status() (+72 more)

### Community 9 - "CLI Banner Display"
Cohesion: 0.04
Nodes (67): build_welcome_banner(), cprint(), _display_toolset_name(), format_banner_version_label(), _format_context_length(), get_available_skills(), get_git_banner_state(), get_update_result() (+59 more)

### Community 10 - "Command Lookup"
Cohesion: 0.05
Nodes (49): AutoSuggest, _build_command_lookup(), _build_description(), _clamp_command_names(), _collect_gateway_skill_entries(), CommandDef, _completion_text(), _context_completions() (+41 more)

### Community 11 - "Model Management"
Cohesion: 0.05
Nodes (55): _check_hermes_model_warning(), CustomAutoResult, DirectAlias, _ensure_direct_aliases(), get_authenticated_provider_slugs(), is_nous_hermes_non_agentic(), list_authenticated_providers(), ModelIdentity (+47 more)

### Community 12 - "Debug & Telemetry"
Cohesion: 0.06
Nodes (49): _capture_dump(), collect_debug_report(), ``hermes debug`` — debug tools for Hermes Agent.  Currently supports:     hermes, Find the log file for *log_name*, falling back to the .1 rotation.      Returns, Read the last *num_lines* from a log file, or return a placeholder., Read a log file for standalone upload.      Returns the file content (last *max_, Run ``hermes dump`` and return its stdout as a string., Build the summary debug report: system dump + log tails.      Parameters     --- (+41 more)

### Community 13 - "Backup & Snapshots"
Cohesion: 0.09
Nodes (40): _derive_category_from_install_path(), do_audit(), do_browse(), do_check(), do_inspect(), do_install(), do_list(), do_publish() (+32 more)

### Community 14 - "Plugin Context"
Cohesion: 0.05
Nodes (22): PluginContext, PluginManager, PluginManifest, Facade given to plugins so they can register tools and hooks., Register a tool in the global registry **and** track it as plugin-provided., Inject a message into the active conversation.          If the agent is idle (wa, Register a CLI subcommand (e.g. ``hermes honcho ...``).          The *setup_fn*, Register a context engine to replace the built-in ContextCompressor.          On (+14 more)

### Community 15 - "Clipboard Utilities"
Cohesion: 0.08
Nodes (36): _convert_to_png(), _find_powershell(), _get_ps_exe(), has_clipboard_image(), _linux_save(), _macos_has_image(), _macos_osascript(), _macos_pngpaste() (+28 more)

### Community 16 - "Authentication Flow"
Cohesion: 0.16
Nodes (26): _api_key_default_label(), auth_add_command(), auth_command(), auth_list_command(), auth_remove_command(), auth_reset_command(), _display_source(), _format_exhausted_status() (+18 more)

### Community 17 - "Webhooks"
Cohesion: 0.18
Nodes (21): cmd_webhook(), Webhook subscription management., _cmd_list(), _cmd_remove(), _cmd_subscribe(), _cmd_test(), _get_webhook_base_url(), _get_webhook_config() (+13 more)

### Community 18 - "Doctor Diagnostic"
Cohesion: 0.16
Nodes (20): _apply_doctor_tool_availability_overrides(), check_fail(), _check_gateway_service_linger(), check_info(), check_ok(), check_warn(), _has_provider_env_config(), _honcho_is_configured_for_doctor() (+12 more)

### Community 19 - "Model Management"
Cohesion: 0.14
Nodes (15): apply_nous_managed_defaults(), apply_nous_provider_defaults(), _browser_label(), get_nous_subscription_explainer_lines(), get_nous_subscription_features(), _has_agent_browser(), _model_config_dict(), NousFeatureState (+7 more)

### Community 20 - "Model Management"
Cohesion: 0.16
Nodes (17): detect_vendor(), _dots_to_hyphens(), _normalize_for_deepseek(), normalize_model_for_provider(), _normalize_provider_alias(), _prepend_vendor(), Per-provider model name normalization.  Different LLM providers expect model ide, Map any model input to one of DeepSeek's two accepted identifiers.      Rules: (+9 more)

### Community 21 - "Uninstaller"
Cohesion: 0.2
Nodes (16): find_shell_configs(), get_project_root(), log_info(), log_success(), log_warn(), Hermes Agent Uninstaller.  Provides options for: - Full uninstall: Remove everyt, Stop and uninstall the gateway service if running., Run the uninstall process.          Options:     - Full uninstall: removes code (+8 more)

### Community 22 - "Pairing Commands"
Cohesion: 0.23
Nodes (11): _cmd_approve(), _cmd_clear_pending(), _cmd_list(), _cmd_revoke(), pairing_command(), CLI commands for the DM pairing system.  Usage:     hermes pairing list, Handle hermes pairing subcommands., List all pending and approved users. (+3 more)

### Community 23 - "Environment Loader"
Cohesion: 0.38
Nodes (6): _load_dotenv_with_fallback(), load_hermes_dotenv(), Helpers for loading Hermes .env files consistently across entrypoints., Pre-sanitize a .env file before python-dotenv reads it.      python-dotenv does, Load Hermes environment files with user config taking precedence.      Behavior:, _sanitize_env_file_if_needed()

### Community 24 - "Tips Display"
Cohesion: 0.5
Nodes (3): get_random_tip(), Random tips shown at CLI session start to help users discover features., Return a random tip string.      Args:         exclude_recent: not used currentl

### Community 25 - "Default Soul"
Cohesion: 1.0
Nodes (1): Default SOUL.md template seeded into HERMES_HOME on first run.

### Community 26 - "Misc Components"
Cohesion: 1.0
Nodes (1): Hermes CLI - Unified command-line interface for Hermes Agent.  Provides subcomma

### Community 27 - "Command Lookup"
Cohesion: 1.0
Nodes (1): Return replacement text for a completion.          When the user has already typ

### Community 28 - "Command Lookup"
Cohesion: 1.0
Nodes (1): Extract the current word if it looks like a file path.          Returns the path

### Community 29 - "Command Lookup"
Cohesion: 1.0
Nodes (1): Yield Completion objects for file paths matching *word*.

### Community 30 - "Command Lookup"
Cohesion: 1.0
Nodes (1): Extract a bare ``@`` token for context reference completions.

### Community 31 - "Command Lookup"
Cohesion: 1.0
Nodes (1): Yield Claude Code-style @ context completions.          Bare ``@`` or ``@partial

### Community 32 - "Command Lookup"
Cohesion: 1.0
Nodes (1): Score a file path against a fuzzy query. Higher = better match.

## Knowledge Gaps
- **452 isolated node(s):** `Hermes Plugin System ====================  Discovers, loads, and manages plugins`, `Return True when an env var is set to a truthy opt-in value.`, `Read the disabled plugins list from config.yaml.`, `Parsed representation of a plugin.yaml manifest.`, `Runtime state for a single loaded plugin.` (+447 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Default Soul`** (2 nodes): `Default SOUL.md template seeded into HERMES_HOME on first run.`, `default_soul.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Components`** (2 nodes): `Hermes CLI - Unified command-line interface for Hermes Agent.  Provides subcomma`, `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Command Lookup`** (1 nodes): `Return replacement text for a completion.          When the user has already typ`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Command Lookup`** (1 nodes): `Extract the current word if it looks like a file path.          Returns the path`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Command Lookup`** (1 nodes): `Yield Completion objects for file paths matching *word*.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Command Lookup`** (1 nodes): `Extract a bare ``@`` token for context reference completions.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Command Lookup`** (1 nodes): `Yield Claude Code-style @ context completions.          Bare ``@`` or ``@partial`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Command Lookup`** (1 nodes): `Score a file path against a fuzzy query. Higher = better match.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Colors` connect `CLI Output & Colors` to `Claw CLI Commands`, `Authentication Flow`, `CLI Output & Colors`, `Authentication Flow`, `Login Flow`, `Model Management`, `Doctor Diagnostic`, `Uninstaller`?**
  _High betweenness centrality (0.227) - this node is a cross-community bridge._
- **Why does `load_config()` connect `Authentication Flow` to `Claw CLI Commands`, `Authentication Flow`, `CLI Output & Colors`, `CLI Output & Colors`, `Login Flow`, `Login Flow`, `Model Management`, `Authentication Flow`, `Webhooks`, `Model Management`?**
  _High betweenness centrality (0.110) - this node is a cross-community bridge._
- **Why does `AuthError` connect `Authentication Flow` to `Claw CLI Commands`, `Authentication Flow`, `Login Flow`, `Login Flow`, `Backup & Snapshots`, `Model Management`, `Debug & Telemetry`, `Authentication Flow`, `Webhooks`, `Doctor Diagnostic`?**
  _High betweenness centrality (0.100) - this node is a cross-community bridge._
- **Are the 325 inferred relationships involving `Colors` (e.g. with `Gateway subcommand for hermes CLI.  Handles: hermes gateway [run|start|stop|rest` and `Return PIDs currently managed by systemd or launchd gateway services.      Used`) actually correct?**
  _`Colors` has 325 INFERRED edges - model-reasoned connections that need verification._
- **Are the 84 inferred relationships involving `AuthError` (e.g. with `Shared runtime provider resolution for CLI, gateway, cron, and helpers.` and `Auto-detect api_mode from the resolved base URL.      Direct api.openai.com endp`) actually correct?**
  _`AuthError` has 84 INFERRED edges - model-reasoned connections that need verification._
- **Are the 69 inferred relationships involving `color()` (e.g. with `_setup_standard_platform()` and `_setup_weixin()`) actually correct?**
  _`color()` has 69 INFERRED edges - model-reasoned connections that need verification._
- **Are the 54 inferred relationships involving `load_config()` (e.g. with `_get_disabled_plugins()` and `is_provider_explicitly_configured()`) actually correct?**
  _`load_config()` has 54 INFERRED edges - model-reasoned connections that need verification._