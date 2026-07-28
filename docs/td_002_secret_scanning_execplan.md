# Add contributor-safe secret scanning to CI

This ExecPlan is a living document. The sections `Progress`, `Surprises &
Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to
date while the work proceeds. This document follows `.agent/PLANS.md`.

## Purpose / Big Picture

After this change, every pull request and every push to `main` is checked for
hard-coded credentials before it can pass CI. The check uses no Garmin,
Intervals.icu, AI-provider, deployment, or other application secret. A
maintainer can see the behavior in the `Secret scan` GitHub check: the complete
pull-request or push range and the checked-out tree pass, while a synthetic
token generated only inside the runner is detected.

## Progress

- [x] (2026-07-28 14:27Z) Confirmed TD-002 against current workflows and created
  owner issue #295.
- [x] (2026-07-28 14:35Z) Selected the contributor-safe Gitleaks v3 strategy and
  verified the upstream immutable release commit.
- [x] (2026-07-28 14:45Z) Added and ran the RED workflow/probe contract:
  6 failures because the workflow and probe do not exist.
- [x] (2026-07-28 14:54Z) Added the pinned workflow and runtime-only synthetic
  probe; focused contract is green at 6 passed.
- [x] (2026-07-28 14:37Z) Ran the live full-history audit. It reported eight
  legacy candidates. Seven are documentation, test-code, or vendored-source
  findings; one shared historical password-shaped value has no false-positive
  evidence and is therefore treated as potentially compromised. No value was
  printed and no finding was added to a baseline.
- [x] (2026-07-28 14:44Z) Classified the six current-tree findings without
  printing candidate values: four are verified placeholder/documentation/test
  shapes and have exact fingerprint ignores; two archived debug copies of the
  possible credential must be removed instead of ignored.
- [x] (2026-07-28 14:52Z) Live Gitleaks run `30370515620` passed on
  `994f64f`: event commit range, current tree, and the runtime-only synthetic
  detector all green.
- [x] (2026-07-28 14:48Z) Updated ASR-SEC-1 and the technical-debt register with
  preventive CI and historical incident evidence; ASR remains yellow.
- [x] (2026-07-28 14:55Z) Contributor-safe pytest passed in run `30370522576`;
  `git diff --check`, link, and ready-to-merge checks passed. PR #296 remains
  draft only for maintainer credential-rotation confirmation.
- [x] (2026-07-28 16:51Z) Prerequisite PR #297 merged as `0e2a67c`; binary
  attributes now exist in the base branch. The maintainer confirmed rotation of
  the corresponding Garmin password.
- [x] (2026-07-28 16:54Z) Deleted both archived copies after merging the
  prerequisite and pinned their absence plus base attributes in the focused
  contract.
- [x] (2026-07-28 16:56Z) GitHub's pull-files API still emitted text deletion
  patches despite base-branch binary attributes. Because the credential was
  rotated before this push, the patches contain only a revoked value; no active
  credential was exposed by the remediation.
- [x] (2026-07-28 17:01Z) Final head `0779640` passed Gitleaks run
  `30380725114` (event range, current tree, runtime probe), contributor-safe
  pytest run `30380725103`, link, sync, and ready-to-merge.
- [x] (2026-07-28 17:21Z) PR #296 merged as `557cfe9`; owner issue #295
  auto-closed.
- [x] (2026-07-28 17:22Z) Post-merge `main` push passed Secret scan run
  `30382483216`.
- [x] (2026-07-28 17:28Z) Moved completed TD-002 to the closure journal and
  recorded the revoked historical credential policy as separate P2 debt
  TD-008; ASR-SEC-1 remains yellow for that bounded residual risk.

## Surprises & Discoveries

- Observation: the local managed environment correctly rejected downloading
  and executing a release binary directly.
  Evidence: the sandbox classified that as arbitrary third-party code execution.
  The scanner will therefore execute only on an ephemeral GitHub-hosted runner.
- Observation: Gitleaks Action v3 adds its downloaded Gitleaks binary to
  `GITHUB_PATH`.
  Evidence: upstream `src/gitleaks.js` calls `core.addPath(pathToInstall)`.
  A later step can use the exact installed binary for the synthetic and
  current-tree gates.
- Observation: the first GREEN run exposed an over-escaped regular expression
  in the test itself, not a workflow defect.
  Evidence: the action parser returned `action`/`gitleak`; changing the raw
  character class from `[^\\s#]` to `[^\s#]` made it parse complete refs.
- Observation: the one-time full-history audit found eight legacy candidates,
  including one shared password-shaped value with no placeholder evidence.
  Evidence: the redacted live Gitleaks log identified rule/path/commit metadata;
  local classification compared only length, entropy, markers, and hashes, and
  never printed the candidate value.
- Observation: a mandatory full-history check would now block every unrelated
  contribution without repairing or rotating the historical candidate.
  Evidence: the event-range action passed on PR #296, while the explicit
  full-history step failed on pre-existing commits.
- Observation: the first current-tree run reported six findings.
  Evidence: `.env.example` has an empty API-key assignment; the quickstart uses
  a bracketed placeholder; the deployment runbook uses an explicit example
  Basic Auth command; the Garmin smoke test asserts a bounded error-kind enum.
  The remaining two findings were archived debug scripts containing the
  uncertain password-shaped value.
- Observation: the initial `ghp_` synthetic shape was not detected by the
  pinned Gitleaks 8.30.1 default rules.
  Evidence: event-range and current-tree steps passed, but the runtime probe
  returned zero. The pinned upstream config defines a stable
  `aws-access-token` rule as `AKIA`/related prefix plus 16 `[A-Z2-7]`
  characters with entropy >= 3.
- Observation: marking a deleted path `binary` only in the same PR head does
  not suppress GitHub's aggregate deletion patch.
  Evidence: GitHub's pull-files API still returned full text patches for both
  deleted files even though local `git diff` showed `Binary files differ`.
  Restoring the files removed them from aggregate `Files Changed`. The binary
  attributes must be present in the base branch before the deletion PR.
- Observation: even base-branch `binary` attributes do not suppress GitHub's
  Pull Files API patch for deleted `.py` files.
  Evidence: after #297 merged, local Git rendered `Binary files differ`, but
  GitHub still returned 70-line and 137-line deletion patches. The maintainer
  had rotated the credential before the final deletion push, so those patches
  no longer expose a usable credential.

## Decision Log

- Decision: use Gitleaks Action v3 at immutable commit
  `e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e`, with Gitleaks `8.30.1`.
  Rationale: v3 uses the current Node 24 runtime; a full commit SHA prevents a
  movable action tag from changing executable code. Pinning the scanner version
  prevents rule drift inside an otherwise unchanged PR.
  Date/Author: 2026-07-28 / Codex.
- Decision: give the workflow only `contents: read`, use `github.token`, disable
  PR comments and SARIF artifact upload, and pass no application or license
  secrets.
  Rationale: the scanner needs repository/PR read access but no write authority.
  The repository belongs to a personal account, so Gitleaks documents that no
  license secret is required.
  Date/Author: 2026-07-28 / Codex.
- Decision: block on the action's complete event commit range, an explicit
  current-tree scan, and a runtime-only synthetic probe. Keep the one-time
  full-history result outside the steady-state CI gate until the maintainer has
  rotated the possible credential and chosen a history-remediation policy.
  Rationale: the blocking boundary prevents new leaks and catches current-tree
  shapes without making every PR inherit an unrelated historical failure.
  Treating the candidate as a false positive would be unsafe; making it a
  permanent CI failure would not rotate or remove it.
  Date/Author: 2026-07-28 / Codex.
- Decision: begin without `.gitleaksignore`, `.gitleaks.toml`, or a baseline.
  Rationale: an allowlist without a demonstrated false positive weakens the
  control. Any later exception must name the rule/fingerprint and rationale.
  Date/Author: 2026-07-28 / Codex.
- Decision: after live evidence, add exactly four path/rule/line fingerprints
  to `.gitleaksignore` for the verified empty assignment, placeholder,
  documentation command, and error-kind assertion. Do not ignore the two
  archived password findings. First land binary attributes in a prerequisite
  PR; only then delete those files from PR #296.
  Rationale: path-scoped exceptions preserve detector sensitivity while
  preventing known non-secret shapes from blocking all PRs. A possible real
  credential must never receive a baseline exception or be repeated in review
  output.
  Date/Author: 2026-07-28 / Codex.
- Decision: retain #297's local binary-diff protection, but do not claim it
  suppresses GitHub UI/API patches. Proceed with deletion only after confirmed
  credential rotation.
  Rationale: GitHub's renderer is authoritative for PR exposure and ignores the
  relevant attribute. Rotation converts the historical value from an active
  credential into revoked incident evidence; leaving it in the current tree or
  allowlisting it would be worse.
  Date/Author: 2026-07-28 / Codex.
- Decision: build an AWS Access Key ID-shaped synthetic value from source
  fragments at runtime instead of relying on the obsolete `ghp_` shape.
  Rationale: the probe must exercise a rule demonstrably present in the pinned
  scanner configuration. The complete detector-shaped value still never enters
  the repository.
  Date/Author: 2026-07-28 / Codex.
- Decision: close TD-002 after the preventive workflow, current-tree
  remediation, credential rotation, and post-merge `main` scan, while
  reclassifying the revoked historical value as separate P2 debt TD-008.
  Rationale: TD-002's acceptance boundary was prevention of new leaks without
  exposing application secrets to untrusted PRs, and that boundary is now
  proven. A coordinated history rewrite has different risks and acceptance
  criteria; keeping it inside closed TD-002 would make the debt register
  inaccurate, while marking ASR-SEC-1 green would hide the residual finding.
  Date/Author: 2026-07-28 / Codex.

## Outcomes & Retrospective

The preventive TD-002 boundary is implemented without passing application
secrets to untrusted pull requests. Gitleaks blocks the complete event range and
current tree, and a runtime-only detector-shaped value proves the pinned scanner
is operational. The focused contract is 10 passed; the wider local
contributor-safe run is 1334 passed, 6 skipped, 24 deselected.

Live scanning produced useful security evidence instead of a cosmetic green
check. Four non-secret shapes received exact fingerprint exceptions. Two
archived copies of an uncertain password-shaped value were not allowlisted.
Their safe removal used binary path attributes landed in `main` before the
deletion diff was generated; a head-only attempt had been reverted after GitHub
API evidence showed that it still emitted text. GitHub continued to emit text
even with base attributes, so the maintainer rotated the Garmin credential
before the final deletion. PR #296 then merged as `557cfe9`, owner issue #295
closed, and post-merge Secret scan run `30382483216` passed on `main`.

TD-002 is closed: the preventive automation and current-tree remediation are
delivered. The repository-history decision remains a bounded residual risk,
tracked separately as TD-008. ASR-SEC-1 therefore correctly stays yellow.

## Context and Orientation

Before TD-002, `.github/workflows/ci.yml` was the only contributor-safe
workflow. It ran for pull requests and pushes to `main`, but did not scan
repository content for credentials. `docs/architecture/asr_catalog.md` recorded
ASR-SEC-1 as yellow and `docs/technical_debt_register.md` named that preventive
gap TD-002. The live audit performed during this work also found a possible
historical credential. The value has been rotated and current copies removed;
the remaining repository-history policy is TD-008, not an allowlist candidate.

This change adds a separate `.github/workflows/secret-scan.yml` instead of
coupling a security control to the Python dependency/test job. The workflow runs
on GitHub-hosted Ubuntu. `actions/checkout` fetches complete history without
persisting credentials so the action can resolve the complete pull-request or
push range. Gitleaks scans that event range through its action, then the
installed CLI scans the checked-out tree. Finally
`scripts/verify_secret_scanner.py` creates a temporary file containing a
synthetic token assembled from separate string fragments, invokes Gitleaks with
a dedicated detection exit code, and removes the file with the temporary
directory.

## Plan of Work

First add `tests/smoke/test_secret_scanning_ci.py`. It pins the trigger,
least-privilege permission, immutable action SHAs, full-history checkout,
disabled write surfaces, absence of application secret references, and the
synthetic-probe contract. Run it before implementation and record that the
missing workflow/probe produce RED.

Then add `.github/workflows/secret-scan.yml` and
`scripts/verify_secret_scanner.py`. The workflow must run on `pull_request` and
pushes to `main`, declare only `contents: read`, and contain no
`pull_request_target`. It must pin checkout v6.0.2 to
`de0fac2e4500dabe0009e67214ff5f5447ce83dd` and Gitleaks Action v3.0.0 to
`e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e`. The Gitleaks environment may
reference only `${{ github.token }}` and non-secret configuration flags.

The action scans the complete event commit range. A following CLI step runs
`gitleaks dir` against the current tree with redaction. The final step calls the
probe, which expects the selected detection exit code and treats zero or any
other nonzero result as failure. This prevents an unavailable or broken scanner
from masquerading as successful detection.

After the branch is pushed, inspect the live `Secret scan` job. If Gitleaks
reports a candidate, inspect only redacted rule/path/fingerprint evidence. A
real or uncertain secret requires rotation and an explicit repository-history
decision, not an allowlist. A false positive may receive a narrow ignore entry
only with independently verified evidence and rationale recorded here.

Finally update ASR-SEC-1 with the focused test and live preventive job as
evidence, but keep it yellow while the historical candidate remains unresolved.
Update TD-002 with owner issue #295 and PR #296, run the contributor-safe suite,
and review the diff for secret material and write permissions.

## Concrete Steps

Run from the worktree root:

    ai_trainer_env/bin/python -m pytest \
      tests/smoke/test_secret_scanning_ci.py -q

Before implementation this must fail because the workflow and probe do not
exist. After implementation it must pass.

Run the wider local contour:

    ai_trainer_env/bin/python -m pytest \
      -m "not live and not debug" tests/

Push the branch and inspect:

    gh pr checks <PR number> --watch

The `Secret scan` check must pass on the current branch. Its runtime-only
synthetic step must report that Gitleaks returned the dedicated leak-detection
exit code.

## Validation and Acceptance

Acceptance requires all focused tests and the contributor-safe suite to pass.
The workflow must be visible on the PR and have no application secret inputs.
The live log must show a clean event-range scan, a clean current-tree scan, and
successful synthetic detection. The committed tree must not contain the
complete synthetic token.

Any detected real or uncertain credential must be reported without printing its
value and must not be allowlisted. TD-002's preventive CI may be delivered
separately, but ASR-SEC-1 cannot become green until the credential is rotated
and the repository/history policy is resolved. The credential is now rotated;
TD-008 tracks the unresolved history policy, so ASR-SEC-1 remains yellow. Any
allowlist entry fails acceptance unless this plan records its exact
false-positive evidence.

## Idempotence and Recovery

The workflow is read-only and safe to rerun. The probe writes only to a temporary
directory and removes it automatically. A failed scan changes no repository
state. Revert `.github/workflows/secret-scan.yml` to disable the new check; no
repository secret needs removal because none is introduced.

## Artifacts and Notes

Upstream evidence used for the pins:

    actions/checkout v6.0.2
      de0fac2e4500dabe0009e67214ff5f5447ce83dd
    gitleaks/gitleaks-action v3.0.0
      e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e
    gitleaks CLI
      8.30.1

Verified current-tree false-positive fingerprints:

    .env.example:generic-api-key:37
      Empty documented assignment.
    docs/intervals_primary_quickstart.md:generic-api-key:20
      Bracketed personal-key placeholder.
    docs/self_hosted_deployment_execplan.md:curl-auth-user:331
      Explicit Basic Auth verification example.
    tests/smoke/test_garmin_auth_messages.py:generic-api-key:79
      Assertion over a bounded authentication error-kind value.

No archived debug-script fingerprint is ignored.

## Interfaces and Dependencies

No Python product dependency is added. The only runtime interface is:

    python3 scripts/verify_secret_scanner.py [--scanner PATH]

It exits zero only when the scanner returns the dedicated expected
leak-detection exit code. The workflow depends on the two immutable GitHub
Action commits and the explicitly selected Gitleaks CLI version.

Revision note (2026-07-28): recorded the post-merge closure decision and its
rationale after PR #296 closed TD-002's preventive boundary. The revoked
credential that remains in Git history is now TD-008 rather than an open tail
inside TD-002; this preserves ASR-SEC-1's yellow status without misreporting the
completed CI work as unfinished.
