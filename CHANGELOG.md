# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.5.1] - 2026-11-22

No template changes: every template, input and default is that of 1.5.0, and
a pipeline behaves the same on either. This release exists so that `v1`,
`v1.5` and every later version sit on the history `main` now has.

### Changed

- **The commit history of `main` was rewritten on 2026-11-22**, to correct the
  sign-off trailers of its commit messages. Only messages changed: the files
  of every commit, its author and its dates are the same. Every commit after
  the fourth has a new hash, so:
  - a clone or a fork has to follow: `git fetch origin` and then
    `git reset --hard origin/main`, or a rebase of local work onto it;
  - a pipeline that pins a template by commit hash should pin a tag instead.
    The old commits stay reachable only through the tags listed below.
- **Where each version tag points.** The content behind every tag is unchanged;
  what differs is which history the tag belongs to:
  - `v1.1.0` and `v1.2.0`, with `v1.1` and `v1.2`, moved to the rewritten
    commits;
  - `v1.3.0`, `v1.3.1`, `v1.4.0` and `v1.5.0`, with `v1.3` and `v1.4`, stay on
    their original commits. They are immutable releases, which GitHub does not
    let anyone move, and those commits are no longer part of `main`;
  - `v1` and `v1.5` follow this release.

  A remote include or a catalog component pinned to any of these versions needs
  no change.
- The compare links of 1.3.0 and of this release, at the end of this file,
  cross the two histories, so they compare the two tags directly instead of
  listing commits.

## [1.5.0] - 2026-11-22

The scanner image moves to 1.14, which changes what a job sends to
`report_url`. **Read this before upgrading if a pipeline sets `report_url`,
`REPORT_URL` or `REPORT_SBOM_URL`**; a pipeline that sets none of them only
gains the source-code SBOM below. Two inputs are added and none is removed.
One is deprecated: `scan_path` of `full-scan` gives way to `path`, keeps
working for now and **goes away in 2.0.0**. The only default that changes is
`scanner_version`.

### Changed

- Scanner image bumped to `ghcr.io/tooark/security-scanner:1.14`, the new
  default of `scanner_version`. The tools are the ones of 1.13 (Trivy 0.76.2,
  Betterleaks 1.10.1, Hadolint 2.15.1) and the `ark-report-tools` envelope is
  still v1.3. What changes is the upload:
  - **Every template sends its report.** `image-scan`, `filesystem-scan`,
    `config-scan`, `repo-scan`, `secret-scan` and `dockerfile-lint` now POST
    their envelope when `report_url` or a `REPORT_URL` variable is set. They
    accepted the input before and sent nothing; only `full-scan` did. A
    collector starts receiving envelopes whose `command` is not `full-scan`,
    with the result in `report` instead of `results`. If it turns them down
    and `REPORT_FAIL_ON_ERROR` is `true`, a job that passed starts failing.
    Either accept them, routing on `command`, or set the CI/CD variable
    `REPORT_SEND_EACH_SCAN: "false"`. `full-scan` is not affected: it still
    sends one consolidated report.
  - **A single scan that cannot see `REPORT_TOKEN` now sends without it.** A
    protected `REPORT_TOKEN` does not reach a merge-request job from an
    unprotected branch. A single scan there used to send nothing; with a
    `REPORT_URL` it does see, it now sends without `Authorization`, and a
    collector answering 401 fails it under `REPORT_FAIL_ON_ERROR`.
  - **`image-scan` and `filesystem-scan` with `sbom: true` upload the SBOM
    too**, to `REPORT_URL` unless `REPORT_SBOM_URL` is set. The SBOM is sent
    bare, with no envelope around it.
  - **The SBOM upload no longer borrows the report credentials.** With
    `REPORT_SBOM_URL` set, it uses `REPORT_SBOM_TOKEN` and
    `REPORT_SBOM_HEADERS` alone; `REPORT_TOKEN` and `REPORT_HEADERS` are
    never sent there. A pipeline that set the URL and relied on the report
    token gets a 401 or 403 from the SBOM endpoint: set `REPORT_SBOM_TOKEN`,
    even when the token is the same. Without `REPORT_SBOM_URL` nothing
    changes. The image calls this one breaking.
  - **Upload log lines are reworded**, to `Sending report to …` and
    `Upload of report succeeded (HTTP 200)`. Adjust anything that greps the
    job log for `Report uploaded`.

  A project that needs time pins `scanner_version: "1.13"`. Released as a
  minor because the image moved a minor: the scanner default follows the
  image's own versioning (see `CONTRIBUTING.md`).
- Both READMEs describe the upload as it now is: what each template sends,
  the `REPORT_SEND_EACH_SCAN` opt-out, and under Secrets the
  `REPORT_SBOM_HEADERS` variable and the rule that a `REPORT_SBOM_URL`
  carries its own credentials.
- `examples/catalog-component.gitlab-ci.yml` sets `REPORT_URL` and
  `REPORT_FAIL_ON_ERROR` for the whole pipeline, so its two merge-request
  jobs now send a report each. Its comment says what the collector has to
  accept, and how to send the consolidated report alone.
- Both READMEs warn, under Gotchas, that a report URL set for the whole
  pipeline reaches every scan, and say how to keep one job quiet.
- **Catalog mirror: re-fetch `catalog-mirror/.gitlab-ci.yml` to get these**
  (`catalog-mirror/README.md`, "Updating the mirror's own pipeline"); a
  mirror that keeps the old file goes on working as before.
  - Pipelines now start only on the default branch and on a tag that is a
    bare `MAJOR.MINOR.PATCH`. "Run pipeline" on another branch used to run
    `sync` from that branch's head and push it to the default branch; it now
    starts nothing.
  - `sync` holds a `resource_group`, so a manual run that meets the scheduled
    one waits for it instead of racing it to push the same tags.
  - `sync` says in its log when it was not started by a schedule. The weekly
    check has always depended on a pipeline schedule that the file cannot
    create; the README now says so up front, gives the `glab` command for
    it, and lists what to look at when a release never reaches the catalog.
  - The README's table of partial versions used `@1.0.0` and `@1.0`, which no
    mirror has: the catalog starts at 1.1.0. It now uses versions that exist.
- **A release is now published by merging the version bump, not by pushing a
  tag.** On every push to `main` that touches `VERSION`, the release workflow
  looks for the tag and the release of `v<COMPONENT_VERSION>`: when both
  exist it publishes nothing, otherwise it runs the checks, tags that commit
  and creates the release. Nothing changes for a consumer, with two
  exceptions worth knowing:
  - the release notes now open with the changelog section of the version,
    followed by the generated list of pull requests;
  - `vMAJOR` and `vMAJOR.MINOR` move only when the release is the newest of
    its line. A patch cut for an older line (`1.4.1` after `1.5.0`) used to
    drag `v1` back to it.

### Deprecated

- **`scan_path`, the input of `full-scan`, in favour of `path`.** It is the
  same setting under the name the other templates and the GitHub Action
  already use. Nothing breaks in this release, which is why it is a minor:
  - a pipeline that passes `scan_path` scans the same directory as before,
    and its job log carries one line saying the input is deprecated;
  - a pipeline that passes neither still scans `$CI_PROJECT_DIR`;
  - when both are set, `path` wins and the log says `scan_path` was ignored.

  **`scan_path` will be removed in 2.0.0, and that removal is a breaking
  change:** GitLab refuses an include that passes an input the template does
  not declare, so a pipeline still using it will fail to be created. Rename
  `scan_path` to `path` before then; the value does not change.

### Added

- `path` input on `full-scan`, replacing `scan_path` (see Deprecated). Its
  default is `$CI_PROJECT_DIR`, as in the other templates.

- `report_sbom_url` input, on `full-scan`, `image-scan` and
  `filesystem-scan`: the destination of the SBOM, next to `report_url`. It
  sets `REPORT_SBOM_URL`, which could only be set as a CI/CD variable; that
  still works, and the input wins when both are present. Left empty, the SBOM
  keeps going to `report_url`. Its token is a secret and stays out of the
  inputs: `REPORT_SBOM_TOKEN` and `REPORT_SBOM_HEADERS` are masked CI/CD
  variables, like `REPORT_TOKEN`, because an input value shows in the
  rendered pipeline and in the job log. The sister Action gained the same
  input, `report-sbom-url`, in its 1.5.0.
- `full-scan` with `sbom: true` and no image step writes an SBOM of the
  source code: `trivy-filesystem.sbom.json`, or `trivy-repo.sbom.json` with
  `scan_mode: "repo"`. That is the case whenever `image` is empty, since the
  template then skips the image step. It used to write no SBOM and say
  nothing, while the envelope still reported `sbom_enabled: true`. With an
  image the SBOM still describes the image. The description of the `sbom`
  input of `full-scan` now covers both cases.
- Every upload carries the header `X-Ark-Payload: report` or
  `X-Ark-Payload: sbom`, so a collector that receives both on one endpoint
  can route without parsing the body.
- Three examples, the counterparts of the ones the GitHub Action ships:
  `report-webhook.gitlab-ci.yml` (the report sent to a collector),
  `report-and-sbom.gitlab-ci.yml` (the report to one endpoint, the SBOM to
  another, each with its own token) and `all-inputs.gitlab-ci.yml` (every
  input with its default written out).
- Checks that keep the above from drifting. `check-sync.sh` now fails when an
  example writes out a `scanner_version` other than the one in `VERSION`,
  when the onboarding guide counts a different number of inputs than the
  templates declare, and when `CHANGELOG.md` has no section for
  `COMPONENT_VERSION`. `check-examples.py` fails when `all-inputs` leaves an
  input out, and when any example or README snippet passes a deprecated one.

## [1.4.0] - 2026-11-19

The scanner image moves to 1.13, and the catalog mirror stops skipping
releases. No input, default other than `scanner_version`, or job name changes.

### Added

- `catalog-mirror/README.md` lists the partial versions a component accepts:
  `@1.0` and `@1` resolve to the newest 1.0.x and 1.x.x published in the
  catalog, the way `v1.0` and `v1` do on GitHub. The mirror needs no floating
  tags for them.

### Changed

- Scanner image bumped to `ghcr.io/tooark/security-scanner:1.13`, the new
  default of `scanner_version`. It carries newer tools and nothing else: Trivy
  0.74.0 → 0.76.2 and Betterleaks 1.8.1 → 1.10.1, with Hadolint still at
  2.15.1. The `ark-tools` commands, the variables the image reads and the
  `ark-report-tools` envelope v1.3 are the ones of 1.10, so no input changes
  and a collector behind `report_url` needs no update. Newer scanners know
  more rules: a pipeline that passed can start failing a gate on a finding
  the older tools did not report. A project that needs time pins
  `scanner_version: "1.10"`. Released as a minor because the image moved a
  minor: the scanner default follows the image's own versioning (see
  `CONTRIBUTING.md`).

### Fixed

- The `sync` job of the catalog mirror no longer skips releases. It read only
  the newest upstream release, so a patch released in the same week as the
  next version never reached the catalog and `@1.3` stopped short of the last
  1.3 patch; a fix released later for an older line was never published
  either. It now publishes every upstream release that has no tag in the
  mirror yet, oldest first, and moves the default branch only to the newest
  one. A mirror picks this up once its `.gitlab-ci.yml` is replaced with the
  one in `catalog-mirror/`; its next run backfills the releases it missed, one
  release pipeline per version, and a new mirror publishes the whole release
  history on its first sync.

## [1.3.1] - 2026-10-06

The repository is renamed `Tooark/template-security-scanner`. Nothing a
template runs changes: this release only moves the addresses that point here.

### Changed

- The repository is now `Tooark/template-security-scanner`; 1.3.0 was released
  as `Tooark/template-ci-security-scanner`. The examples, both READMEs,
  `SUPPORTED-INTEGRATIONS.md` and the default `UPSTREAM_REPO` of the catalog
  mirror use the new name. A remote include or a catalog mirror that still
  names the old one keeps resolving for as long as GitHub redirects it, but
  should move:
  - a remote include points at
    `https://raw.githubusercontent.com/Tooark/template-security-scanner/<tag>/templates/<scan>.yml`;
  - a catalog mirror sets `UPSTREAM_REPO` to
    `Tooark/template-security-scanner`, in its `.gitlab-ci.yml` or as a
    project CI/CD variable. Component paths on your instance do not change.
- The onboarding guide moved to
  <https://tooark.com/template-security-scanner/>. Its old address,
  `https://tooark.com/template-ci-security-scanner/`, no longer resolves.

## [1.3.0] - 2026-10-05

This repository is now the home of the GitLab CI/CD templates, and of nothing
else. The GitHub Action stays in the repository the two used to share, renamed
[`Tooark/action-security-scanner`](https://github.com/Tooark/action-security-scanner).
**A remote include and a catalog mirror both have to point here** — see the
first entry under _Changed_.

### Added

- `examples/quick-start.gitlab-ci.yml`, the one-line include, and a recipe in
  the README and in `examples/remote-include.gitlab-ci.yml` for the case that
  trips most first pipelines: scanning an image in the project's own, private
  registry needs `TRIVY_USERNAME` and `TRIVY_PASSWORD` set from
  `CI_REGISTRY_USER` and `CI_REGISTRY_PASSWORD`.
- `tests/templates.test.py` runs the job each template generates, without
  GitLab and without the scanner image. It renders the template with a set of
  inputs, runs `before_script` and `script` against a stand-in `ark-tools`, and
  asserts on the command line and the environment that stand-in received:
  precedence, the arguments of each scan, `extra_args` splitting, the exit
  code. CI runs it on every commit, and also lints the script blocks of the
  templates with ShellCheck, which nothing did before.
- `scripts/check-examples.py` checks every include of these templates, in
  `examples/` and in the YAML blocks of the READMEs, the way GitLab would when
  creating the pipeline: an undeclared input, a value of the wrong type or
  outside `options`, or a missing required input fails CI here instead of in
  the project of whoever copied the example.
- `scripts/check-sync.sh` now also fails when an input is missing from either
  README, and when the `scanner_version` row of a README or the current line
  of `SUPPORTED-INTEGRATIONS.md` names an image tag other than the one in
  `VERSION`. `scripts/validate-templates.py` now fails when a template
  interpolates an input into `before_script`, `script` or `after_script`:
  inputs reaching the shell only as environment variables was a rule on paper,
  and is now a check.
- `SUPPORTED-INTEGRATIONS.md` states the minimum GitLab version: 16.11 for a
  remote include, because the templates use array-typed inputs and stage a
  boolean input under `variables:`; 17.0 for a CI/CD Catalog component.
- Contributing, Help and Security and Support sections at the end of both
  READMEs.

### Changed

- **The templates are released from this repository.** Up to 1.2.0 they were
  released together with the GitHub Action, from a repository then called
  `Tooark/ci-security-scanner`; this one continues them from the same history
  and the same tags. The templates themselves did not move inside the
  repository. What a consumer has to change:
  - a remote include now points at
    `https://raw.githubusercontent.com/Tooark/template-security-scanner/<tag>/templates/<scan>.yml`.
    One that still names `Tooark/ci-security-scanner` resolves only for as
    long as GitHub redirects the old name, only for tags up to `v1.2.0`, and
    gets no further releases;
  - a catalog mirror must set `UPSTREAM_REPO` to
    `Tooark/template-security-scanner`, in its `.gitlab-ci.yml` or as a
    project CI/CD variable. `catalog-mirror/README.md` has the steps. Component
    paths on your instance do not change.
- The catalog mirror moved from `examples/gitlab-catalog-mirror/` to
  `catalog-mirror/`, and the example pipelines from `examples/gitlab/` to
  `examples/`.
- The README is written for GitLab only: every input with its default and the
  templates that accept it, the report files each scan writes, the GitLab
  version and executors required, and recipes. Every section heading carries
  an icon, which changes the anchor of the section: it now starts with a
  hyphen, `#-inputs` where it was `#inputs`.
- `SUPPORTED-INTEGRATIONS.md`, `CONTRIBUTING.md`, `SECURITY.md`, `SUPPORT.md`
  and the issue and pull request templates describe the templates only, and
  send GitHub Actions questions to the sister repository.
- The onboarding guide covers the templates only, at its own address,
  <https://tooark.com/template-security-scanner/>. It gained sections on how
  a project consumes a template, the anatomy of one, the path of a run and the
  catalog; it takes GitLab's orange as its accent colour; and it closes with a
  card pointing at the sibling guide of the GitHub Action.

### Removed

- The GitHub Action — `action.yml` and `src/run-scanner.sh` — and the GitHub
  example workflow. They live on in
  [`Tooark/action-security-scanner`](https://github.com/Tooark/action-security-scanner).

### Fixed

- `full-scan` no longer overrides `FULL_SCAN_DOCKERFILES` and `FULL_SCAN_MODE`
  set as CI/CD variables. The `dockerfiles` and `scan_mode` inputs defaulted to
  `"Dockerfile"` and `"fs"` — the image's own defaults — and a non-empty
  default is always forwarded, so a project that set either variable and left
  the input alone had it silently replaced. Both inputs now default to empty,
  like every other forwarding input, and `scan_mode` accepts `""`. A pipeline
  that sets neither the input nor the variable behaves exactly as before. **A
  project that does set `FULL_SCAN_DOCKERFILES` or `FULL_SCAN_MODE` as a
  variable will see it take effect for the first time.**
- The Trivy database cache is now saved when the job fails too. The five
  templates that cache it declared no `cache:when`, and GitLab's default saves
  a cache only on success — while these jobs fail by design whenever a gate
  trips. A project with findings therefore never populated the cache and
  downloaded the whole database on every run. The cache entry now sets
  `when: always`, the counterpart of the separate save step the GitHub Action
  has always had.

## [1.2.0] - 2026-09-27

### Added

- The onboarding guide is bilingual. A language button beside the theme button
  switches between Portuguese and English without reloading the page. Both
  languages live in the same file, side by side, so they cannot drift apart the
  way two separate files can; the choice is remembered per visitor, and a
  first-time visitor gets whichever language their browser asks for. Without
  JavaScript the page still renders, in Portuguese.
- The guide links out: a GitHub button beside the language and theme buttons
  and the repository badge open the repository, the version badge opens that
  version's release, and the scanner badge opens the `Tooark/base-images`
  release of the image it pins.

### Changed

- The onboarding guide no longer carries versions of its own. It writes
  placeholders, and `scripts/render-docs.sh` fills them in from `VERSION` —
  which now also declares `REPORT_SCHEMA` and `REPORT_VERSION` — before Pages
  publishes the page. Pages now also redeploys when only `VERSION` changes.
  `check-sync.sh` reads the rendered page, fails on a version typed into the
  guide by hand, and checks that every live mention of the report envelope
  names `REPORT_VERSION`.

- Scanner image bumped to `ghcr.io/tooark/security-scanner:1.10`, the new
  default of `scanner_version` / `scanner-version`. Its reports use the
  `ark-report-tools` envelope v1.3, which adds an optional `image` object —
  `name`, `version`, `tag`, `digest` and `reference` of the scanner image that
  produced the report — and sets `version` to `"1.3"`. A collector behind
  `report_url` / `report-url` that only accepts the literal `"1.2"` must be
  updated; reports without `image` still validate against the new schema.
  Released as a minor because the image moved a minor: the scanner default
  follows the image's own versioning (see `CONTRIBUTING.md`).
- Reports say which image produced them. The image knows only its own build
  version, so both front ends pass `ARK_IMAGE_NAME` and `ARK_IMAGE_TAG` from
  `scanner_image` / `scanner-image` and `scanner_version` / `scanner-version`:
  a mirror or the floating `1.10` tag is recorded as it ran, not as
  `ghcr.io/tooark/security-scanner:1.10.0`. The Action also resolves the
  digest of the image it runs and passes `ARK_IMAGE_DIGEST`, so
  `image.reference` becomes an immutable `name@sha256:…`. GitLab exposes no
  digest for a job image; a project that wants one sets `ARK_IMAGE_DIGEST` as
  a CI/CD variable. A CI/CD variable, or the job `env` on GitHub, overrides all
  three.

### Fixed

- The onboarding guide no longer serves `uses: Tooark/ci-security-scanner@v1.1.0`
  as `[email protected]`. Cloudflare proxies `tooark.com` and its Email Address
  Obfuscation rewrites anything shaped like an address; `name@vX.Y.Z` qualifies.
  The affected spans now carry Cloudflare's `email_off` opt-out.
- The `[1.0.0]` and `[1.1.0]` links at the bottom of this file pointed at a
  `v1.0.0` tag that was never pushed, so both 404'd.
- The guide's JavaScript moved out of the page and into `docs/guide.js`. The
  site is served behind a Content Security Policy of `script-src 'self'`, which
  blocks inline `<script>` outright — so the theme toggle, the language toggle
  and the nav highlight were all dead on the published page while working
  locally. The button labels moved into `data-` attributes on the buttons, so
  the script file now carries no translated text at all.
- The guide serves its own favicon. The link pointed at `../media/favicon.png`,
  which resolves above the published root — `docs/` is the site root — and only
  appeared to work because the organization's site happens to serve an
  identical file at that path. It also declared `image/x-icon` for a PNG.
- The Portuguese half of the guide had fallen behind the English one. It still
  showed `v1.0.0` in both tag tables, `actions/cache/restore@v4` and
  `actions/checkout@v4`, and it listed three `check-sync.sh` invariants where
  there are four. Both halves said the scanner version is pinned in ten places;
  it is nine, since `run-scanner.sh` has a single version fallback. On narrow
  phones the header buttons no longer overlap the eyebrow line.
- The catalog mirror's `sync` job could not push. GitLab Runner rewrites the
  bare project URL to one carrying `CI_JOB_TOKEN`
  (`url.<with token>.insteadOf <without>`), so the push went out with the
  read-only job token instead of `CATALOG_PUSH_TOKEN` and failed with
  `You are not allowed to push code to this project`. The push URL now carries
  a user part (`https://oauth2@…`), which that prefix match no longer rewrites,
  and every push resets `credential.helper` first, so a job-token helper the
  runner installs under `FF_GIT_URLS_WITHOUT_TOKENS` cannot answer instead.
- The mirror's push to the default branch carries `-o ci.skip`. Without it the
  push started a branch pipeline whose own `sync` job raced the tag push, and
  failed trying to create the same tag whenever it won.
- The README reaches the catalog mirror without `media/`, `docs/`, `examples/`,
  `action.yml` or the other language's README, so on the catalog page the
  banner and those links were broken. Links to files the mirror does not sync
  are now absolute; `templates/`, `LICENSE` and `VERSION` stay relative.
- The mirror's troubleshooting table blamed branch protection for the 403 that
  was really the runner's job token, and listed a missing description as a
  cause of an empty catalog, when it actually fails the release job with
  `Project must have a description`. It now covers both, and how to publish a
  release that was created while the **CI/CD Catalog project** toggle was off.

### Security

- The mirror pipeline pins its images by digest: `alpine:3.24.2` for `sync`,
  which holds `CATALOG_PUSH_TOKEN` (3.20 reached end of support on
  2026-04-01), and `glab` v1.119.0 for `release` instead of the mutable
  `latest`. The mirror's README notes that the `glab` path needs GitLab 18.0 or
  later.

## [1.1.0] - 2026-09-22

### Added

- Onboarding guide in `docs/`, deployed to GitHub Pages by
  `.github/workflows/pages.yml`. It walks the repository file by file and
  records the reasoning behind each decision, for readers who know software
  development but not CI.
- OSS governance files modelled on `Tooark/base-images`: `SECURITY.md`,
  `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SUPPORT.md`, `.github/CODEOWNERS`,
  `.github/FUNDING.yml`, a pull request template and issue forms.
- `SUPPORTED-INTEGRATIONS.md`, recording the support boundaries previously
  scattered across header comments and README gotchas: supported platforms,
  runners and executors, the component-to-image version pairing, and the
  network destinations a scan needs.
- `scripts/check-sync.sh` now also verifies that every copy-paste reference in
  the README, the examples, the onboarding guide and
  `SUPPORTED-INTEGRATIONS.md` pins `COMPONENT_VERSION`. Only the three forms a
  reader actually copies are matched; prose explaining the tagging scheme is
  not. Without it, a release silently left the quick start teaching the
  previous version.

### Changed

- **Minimum Actions Runner version on self-hosted runners.** `action.yml` now
  references `actions/upload-artifact@v7` and `actions/cache@v6`, which run on
  Node.js 24 and require Actions Runner **2.327.1 or newer** — the floor
  introduced by `actions/upload-artifact@v6`. GitHub-hosted runners are
  unaffected. A self-hosted runner older than that will fail the artifact
  upload and the cache steps once `v1` or `v1.0` moves to a release containing
  this change.
- This repository's own workflows moved to `actions/checkout@v7`,
  `actions/configure-pages@v6` and `actions/deploy-pages@v5`. No consumer
  impact; the runners had started warning that Node 20 is deprecated.
- The GitHub example in `examples/` moved to `actions/checkout@v7`, so a reader
  copying it does not start on a version the runner already warns about.

### Fixed

- `scripts/check-sync.sh` no longer trips ShellCheck `SC2013`, which failed the
  CI lint step on every commit and blocked every Dependabot pull request. The
  `ARK_IN_*` parity check now reads names with `while read` fed by process
  substitution, which keeps the loop in the current shell so the failure flag
  survives it.
- The onboarding guide is linked by its canonical address,
  `https://tooark.com/ci-security-scanner/`. The `tooark.github.io` URL used
  until now is a redirect: the organization serves Pages from a custom domain.

## [1.0.0] - 2026-09-21

First release. Pins `ghcr.io/tooark/security-scanner:1.9`. Never published as
a tag — this content first reached consumers as part of 1.1.0.

### Added

- GitLab CI/CD component templates, one job each: `full-scan`, `image-scan`,
  `filesystem-scan`, `config-scan`, `repo-scan`, `dockerfile-lint` and
  `secret-scan`. Usable through `include: remote:` or from a CI/CD Catalog.
- GitHub composite Action (`action.yml`) covering the same seven scans through
  a `command` input, with `exit-code`, `reports-dir` and `report` outputs.
- Shared precedence rule across both platforms: an empty input is never
  forwarded, so `input > CI variable > image default` holds everywhere.
- Secret passthrough (`TRIVY_TOKEN`, `REPORT_TOKEN`, registry credentials and
  friends) via environment rather than inputs.
- Trivy database caching on both platforms, skipped for the two scans that do
  not read the database. GitLab caches `.cache/trivy` under a fixed key; GitHub
  uses `actions/cache` with one entry per day per scanner version, saved from
  an explicit step so a tripped failure gate still populates it.
- `scripts/validate-templates.py` and `scripts/check-sync.sh`, which fail CI on
  undeclared or unused inputs, broken `ARK_IN_*` wiring, and version pins that
  drift from `VERSION`.
- Release workflow that validates, checks the tag against `VERSION`, publishes
  the GitHub release and moves the floating `vMAJOR` and `vMAJOR.MINOR` tags.
- Mirror pipeline in `examples/gitlab-catalog-mirror/` that polls GitHub
  releases on a schedule and republishes to a self-hosted CI/CD Catalog.
- Copy-ready examples for both platforms in `examples/`.

### Security

- `extra_args` is split under `set -f`, so a value such as `*` is passed
  literally instead of expanding against the files in the repository.
- The catalog mirror hands its push token to git through a credential helper
  rather than a remote URL, keeping it out of argv and out of git's errors.
- The third-party `actionlint` image is pinned by digest, and Dependabot keeps
  the remaining action references current.
- The reports directory is tightened again once a scan finishes, limiting the
  world-writable window the non-root container user requires.
- Documented the disclosure paths that configuration can open: the Docker
  socket mount, unredacted Betterleaks output, and Trivy's secret scanner
  writing findings into an uploaded artifact.

[Unreleased]: https://github.com/Tooark/template-security-scanner/compare/v1.5.1...HEAD
[1.5.1]: https://github.com/Tooark/template-security-scanner/compare/v1.5.0..v1.5.1
[1.5.0]: https://github.com/Tooark/template-security-scanner/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/Tooark/template-security-scanner/compare/v1.3.1...v1.4.0
[1.3.1]: https://github.com/Tooark/template-security-scanner/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/Tooark/template-security-scanner/compare/v1.2.0..v1.3.0
[1.2.0]: https://github.com/Tooark/template-security-scanner/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/Tooark/template-security-scanner/releases/tag/v1.1.0
[1.0.0]: https://github.com/Tooark/template-security-scanner/commit/56263b1c4c085d5ce785ed263194c04609b8f0be
