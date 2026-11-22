# Mirror project for a self-hosted CI/CD Catalog

GitLab only lists components that live in a project on the GitLab instance
itself, so a GitHub repository cannot be published to the catalog directly.
This directory holds the pipeline for a small mirror project that closes that
gap: it watches releases of
[`Tooark/template-security-scanner`](https://github.com/Tooark/template-security-scanner),
copies `templates/` across for every release it has not published yet, and
publishes each one to the internal catalog.

GitHub stays the source of truth. Nothing is authored here.

## What the pipeline does

Two kinds of pipeline run in the mirror, one job each:

| Pipeline              | Started by                                             | Job       | What it does                                                                                                                    |
| --------------------- | ------------------------------------------------------ | --------- | ------------------------------------------------------------------------------------------------------------------------------- |
| On the default branch | the weekly schedule, **Run pipeline**, or a push to it | `sync`    | Lists the upstream releases and, oldest first, commits the `templates/` of each one that has no tag here yet and pushes its tag |
| On a version tag      | `sync`, which pushes one tag per release               | `release` | Publishes that tag to the CI/CD Catalog                                                                                         |

Nothing else starts a pipeline: `workflow:rules` leaves out every other
branch and every tag that is not a bare `MAJOR.MINOR.PATCH`. That is on
purpose. `sync` pushes its commits to the default branch, so it must never run
from the head of another one, and only the tags it creates are published.

**The weekly check is the schedule, and the schedule is yours to create.**
GitLab keeps pipeline schedules in the project, not in the repository, so
`.gitlab-ci.yml` cannot bring one. [Step 6](#one-time-setup) of the setup
creates it. Until then the mirror looks for a new release only when someone
runs the pipeline by hand, and `sync` says so in its log whenever it was not
started by a schedule.

Re-running `sync` when nothing changed is a no-op, so the schedule can be as
aggressive as you like. Two runs never overlap: `sync` holds a
`resource_group`, so a manual run that meets the scheduled one waits for it
and then finds nothing left to publish.

`sync` publishes every release it is missing, not only the newest one. A patch
released in the same week as the next version still reaches the catalog, and
so does a fix released later for an older line — otherwise `@1.3` would stop
at whichever patch the schedule happened to catch. The default branch follows
the newest release; an older line is published by its tag alone. A new mirror
therefore publishes the whole release history on its first sync, one release
pipeline per version.

The `release` job runs `glab`, which the `release` keyword uses on GitLab 18.0
and later. On an older instance, switch its image to
`registry.gitlab.com/gitlab-org/release-cli`.

## One-time setup

1. **Create the project** on your GitLab instance, for example
   `tooark/ci-security-scanner`. Give it a **description** — the catalog
   refuses to publish a project without one.

2. **Seed it** with this file as `.gitlab-ci.yml` at the repository root:

   ```bash
   git clone https://gitlab.example.com/tooark/ci-security-scanner.git
   cd ci-security-scanner
   curl -fsSLO https://raw.githubusercontent.com/Tooark/template-security-scanner/main/catalog-mirror/.gitlab-ci.yml
   git add .gitlab-ci.yml
   git commit -m "chore: add catalog sync pipeline"
   git push
   ```

   `templates/`, `README.md`, `LICENSE` and `VERSION` arrive with the first
   sync — there is no need to copy them by hand.

3. **Mark it as a catalog resource**: _Settings > General > Visibility, project
   features, permissions_ and turn on **CI/CD Catalog project** (Owner role).
   The project becomes findable only after the first release is published.

   Do this before the first tag pipeline runs. The `release` job publishes to
   the catalog only when the toggle is already on; turning it on afterwards
   does not publish releases that already exist.

4. **Create a project access token** with the `write_repository` scope and the
   Maintainer role, so the `sync` job can push commits and tags. Add it under
   _Settings > CI/CD > Variables_ as:

   | Variable             | Value                    | Flags             |
   | -------------------- | ------------------------ | ----------------- |
   | `CATALOG_PUSH_TOKEN` | the project access token | Masked, Protected |

   If the default branch is protected, either mark the variable as protected
   and allow the token to push to it, or drop the protection on the variable.

5. **Allow the token past branch protection**: _Settings > Repository >
   Protected branches_ — the token's user needs push rights on the default
   branch, and _Protected tags_ must allow it to create tags.

6. **Add the weekly schedule.** This is what makes the mirror check for a new
   release by itself: _Build > Pipeline schedules > New schedule_, cron
   `0 6 * * 1` (Mondays at 06:00) on the default branch, **Activated**
   ticked. Or from a terminal, with [`glab`](https://gitlab.com/gitlab-org/cli)
   signed in to the instance:

   ```bash
   glab schedule create --repo tooark/ci-security-scanner \
     --cron "0 6 * * 1" --cronTimeZone "UTC" --ref main \
     --description "Weekly sync with Tooark/template-security-scanner"
   ```

   The schedule runs as whoever created it. If that account is blocked or
   leaves the project, its schedule stops producing pipelines and the mirror
   quietly stops following upstream; another maintainer takes it over with
   **Take ownership** on the same page.

   To check right away instead of waiting for Monday, press the play button
   of the schedule, or _Build > Pipelines > Run pipeline_ on the default
   branch.

7. Optionally set `UPSTREAM_TOKEN` to a GitHub token. It is only needed if the
   instance shares an egress IP with enough other traffic to hit GitHub's
   unauthenticated rate limit of 60 requests per hour.

## Using the published component

Once the first release lands, projects on the instance include it by path:

```yaml
include:
  - component: $CI_SERVER_FQDN/tooark/ci-security-scanner/full-scan@1.5.1
    inputs:
      image: "$CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA"
      trivy_severity: "CRITICAL,HIGH"
```

`$CI_SERVER_FQDN` resolves to the instance host, so the same snippet works in
every project without hardcoding the domain.

The version after `@` can also be partial. GitLab resolves it when the pipeline
is created, to the newest version matching it among those published in the
catalog:

| Reference  | Resolves to                     | Use when                           |
| ---------- | ------------------------------- | ---------------------------------- |
| `@1.3.1`   | Exactly that version            | Reproducible pipelines             |
| `@1.3`     | Newest 1.3.x in the catalog     | Automatic patch updates            |
| `@1`       | Newest 1.x.x in the catalog     | Automatic minor and patch updates  |
| `@~latest` | Newest version, a new major too | Never in a pipeline you care about |

These are not tags: the mirror pushes only the full version, and needs no
floating `1` or `1.3` tag to follow the upstream `v1` and `v1.3`. A new patch
reaches `@1.3` and `@1` as soon as its release job publishes it.

The catalog starts at 1.1.0, the first version upstream published as a
release; there is no `@1.0.0` to pin.

## Updating the mirror's own pipeline

`sync` replaces `templates/`, `README.md`, `LICENSE` and `VERSION` and nothing
else. The `.gitlab-ci.yml` of the mirror is local, so a fix to the pipeline in
this directory does not reach a mirror by itself. When the
[changelog](../CHANGELOG.md) names a change to the catalog mirror, fetch the
file again and commit it:

```bash
cd ci-security-scanner
git pull
curl -fsSLO https://raw.githubusercontent.com/Tooark/template-security-scanner/main/catalog-mirror/.gitlab-ci.yml
git commit -am "chore: update the catalog sync pipeline"
git push
```

That push starts a `sync` on the default branch, which doubles as the test of
the new file. Versions already published are not touched, and the variables,
the token and the schedule stay as they are.

## Moving an existing mirror to this repository

Until 1.2.0 the templates were released from a repository called
`Tooark/ci-security-scanner`. It has since been renamed
[`Tooark/action-security-scanner`](https://github.com/Tooark/action-security-scanner)
and is the GitHub Action only. A mirror set up back then still has
`UPSTREAM_REPO: "Tooark/ci-security-scanner"`; GitHub redirects that name to
the renamed repository, so its `sync` job finds a release without `templates/`
and fails with `upstream release is missing templates`.

Point it here instead. Either edit `UPSTREAM_REPO` in the mirror's
`.gitlab-ci.yml`:

```yaml
variables:
  UPSTREAM_REPO: "Tooark/template-security-scanner"
```

or leave the file alone and add `UPSTREAM_REPO` with that value under
_Settings > CI/CD > Variables_ — a project variable wins over the one in the
file. Nothing else changes: the versions already published stay as they are,
and the next `sync` publishes every release of this repository that the mirror
has no tag for yet.

## Version mapping

GitHub tags carry a `v` prefix (`v1.0.0`); the catalog expects a bare semantic
version (`1.0.0`). The `sync` job strips the prefix, so upstream `v1.2.3`
becomes catalog version `1.2.3`.

## When a sync goes wrong

| Symptom                                                          | Cause                                                                                                                                                                                                                                                                                                                    |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `CATALOG_PUSH_TOKEN is not set`                                  | The CI/CD variable is missing, or it is protected and the branch is not                                                                                                                                                                                                                                                  |
| `remote: You are not allowed to push code to this project` (403) | The push authenticated as something that cannot push. The runner rewrites the bare project URL to one carrying `CI_JOB_TOKEN`, which is read-only; the pipeline avoids that by pushing to an `oauth2@` URL, so check that was not changed. Otherwise the token lacks the `write_repository` scope or the Maintainer role |
| `You are not allowed to push code to protected branches`         | The token's user lacks push rights on the default branch, or _Protected tags_ do not let it create tags                                                                                                                                                                                                                  |
| The release job succeeds but the catalog stays empty             | The **CI/CD Catalog project** toggle was off when the job ran. Turn it on, delete the release (_Deploy > Releases_) and retry the `release` job; it runs `glab` with `--no-update`, so it fails while the release exists                                                                                                 |
| The release job fails with `Project must have a description`     | Set the description under _Settings > General_ and retry the job. `Project must have a README` and `Project must contain components` mean the tagged commit lacks `README.md` or `templates/`                                                                                                                            |
| `found no release of ... tagged vMAJOR.MINOR.PATCH`              | `UPSTREAM_REPO` names a repository without a published release tagged `vX.Y.Z`; drafts and prereleases do not count                                                                                                                                                                                                      |
| `API rate limit exceeded`                                        | Set `UPSTREAM_TOKEN` to a GitHub token                                                                                                                                                                                                                                                                                   |
| A release is out upstream and the catalog never gets it          | No pipeline ran since. Under _Build > Pipeline schedules_, check that the schedule exists, is **active** and has an owner who can still run pipelines; then press its play button. A `sync` log that opens with `started by 'web', not by a schedule` on every run means no scheduled run ever happened                  |
| No pipeline starts for a branch or a tag                         | Expected for any branch but the default one, and for a tag that is not a bare `MAJOR.MINOR.PATCH`: `workflow:rules` leaves both out                                                                                                                                                                                      |
| `sync` sits in _waiting for resource_                            | Another `sync` is running; the two share a `resource_group`. It starts when the first one ends                                                                                                                                                                                                                           |
