# ML Forge — Security model

ML Forge is a **single-user local application**. It listens on `127.0.0.1` only. The sandbox is a
reasonable local isolation layer, **not** a hardened boundary for hostile, internet-facing use.

## Threats considered

| Threat | Mitigation | Verified by |
|---|---|---|
| Learner code harming the host | Runs only in a container: `--network none`, read-only rootfs, tmpfs `/tmp` (16 MB, `noexec,nosuid,nodev`), `--cap-drop ALL`, `no-new-privileges`, UID/GID 10001, no host mounts, no Docker socket, `--ipc none`, `--log-driver none` | `test_host_filesystem_and_secrets_not_visible` |
| Infinite loops / CPU burn | Per-test timeout (2 s) + total budget (5 s) in the harness, `RLIMIT_CPU`, container wall clock (budget + 15 s) with `docker kill` | `test_infinite_loop_is_stopped_by_timeout`, E2E #7 |
| Memory exhaustion | cgroup `--memory 256m --memory-swap 256m`, child `RLIMIT_AS` 192 MB → clean `MemoryError` | `test_large_memory_allocation_fails_safely` |
| Fork bombs | `--pids-limit 64` | `test_fork_bomb_is_limited` |
| Output floods / disk fill | 64 KB kept per test, child killed beyond 4 MB, read-only FS, 16 MB tmpfs, `RLIMIT_FSIZE` 1 MB | `test_huge_stdout_is_truncated` |
| Network exfiltration | No network namespace interfaces (connect and DNS fail) | `test_network_is_unreachable` |
| Leaking host secrets | Container gets no env from the host; key lives only in the API process | same + `test_ai_unavailable_without_key_and_key_never_leaks` |
| Orphan containers | Labelled containers; removed after each run, on cancel and on start-up | `test_cancel_kills_container_and_leaves_no_orphans`, API cancel test |
| Cross-submission interference | One container per job, fresh interpreter per test | `test_neighbouring_runs_are_isolated`, `test_each_test_runs_in_fresh_process` |
| Reading hidden tests / solutions via API | Exercise payload is an explicit whitelist; hidden results redacted at write time (no input/expected/actual/stdout/message) | `test_exercise_payload_hides_solution_and_hidden_tests`, E2E #3, #9 |
| Reading expected values from inside the sandbox | Expected values are **never sent** into the container; grading is host-side | `test_expected_values_never_enter_container` |
| Spoofing results from learner code | Result line is tagged with a per-run random nonce; the harness reports only observations (not verdicts) | design |
| Prompt injection via code/stdout into the AI | Learner content wrapped in `<learner_data>` and declared untrusted in the system prompt; the AI has no tools, no FS access; AI output never changes mastery | `test_ai.py` |
| AI cost runaway | Per-day request and USD caps checked *before* each call; context truncation; unknown prices reported as unknown, never invented | `test_ai.py` |
| Path traversal in restore | Backup names restricted to `[A-Za-z0-9_.-]+\.db` in `data/backups`; schema/integrity check; explicit `confirm="RESTORE"`; automatic safety backup | `test_backup_restore_and_export` |
| XSS through content or learner text | Markdown rendered by `react-markdown` without raw HTML; security headers (`nosniff`, `DENY` framing, `same-origin` referrer) | review |

## Known limitations (be honest)

* **Hidden test inputs are visible inside the sandbox** (the code must be called with them). A
  learner who prints them could learn them. Expected outputs are not exposed. The independent
  assessment is an *educational* signal, not anti-cheat; self-reports ("I didn't use AI") are not
  trusted as proof.
* Learner code and the in-container harness share a UID. Deliberately malicious code can interfere
  with the harness (e.g. through `/proc`); the nonce only stops naive spoofing. Since grading is
  host-side, it cannot fabricate a pass without knowing the expected outputs.
* Docker on macOS runs in a VM; on Linux containers share the host kernel. For any **public**
  deployment, use microVM / gVisor-class isolation, authentication, quotas and a separate
  security review (spec §10).
* No authentication: the app trusts whoever can reach `127.0.0.1:3000`. Do not expose the ports.
* The default Docker seccomp profile is used; no custom AppArmor profile is shipped.

## Secrets

* `ANTHROPIC_API_KEY` only in `.env` / environment of the backend; `.env` is git-ignored.
* Never in `app_settings`, API responses, the frontend bundle, logs or backups.
* `GET /api/v1/settings` exposes only `configured: true/false`.
