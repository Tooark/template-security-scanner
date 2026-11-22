#!/usr/bin/env bash
# =============================================================================
# Publishes the release that VERSION names, unless it is already published.
#
# A release is COMPONENT_VERSION reaching main:
# .github/workflows/release.yml runs this on every push there that touches
# VERSION. Nobody pushes a version tag by hand, so there is no tag that could
# disagree with VERSION.
#
#   release.sh plan      says what there is to do; in a workflow it also writes
#                        version, tag and state to $GITHUB_OUTPUT
#   release.sh publish   creates the release and its tag, then points the
#                        floating tags at it
#
# The state `plan` reports, for the tag vCOMPONENT_VERSION:
#
#   published   the tag and its release exist      nothing is released
#   new         neither exists                     this commit is tagged and
#                                                  released
#   tagged      the tag exists, the release not    the tag is released as it
#                                                  is, if it is this commit
#
# A version tag is never moved and never recreated. `plan` only reads, so it is
# safe to run from a clone to see what a merge would do.
#
# Needs git, and gh authenticated for the repository of the clone.
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."

REMOTE="${RELEASE_REMOTE:-origin}"

die() {
  # The annotation is what shows up on the summary page of a workflow run.
  if [ -n "${GITHUB_ACTIONS:-}" ]; then
    printf '::error::%s\n' "$*"
  fi
  printf 'release: %s\n' "$*" >&2
  exit 1
}

# -----------------------------------------------------------------------------
# Prints the commit a tag of the remote points at; nothing when it has no such
# tag. An annotated tag is listed twice, the second time peeled to its commit
# (refs/tags/<tag>^{}), and that is the line that counts.
# -----------------------------------------------------------------------------
remote_tag_commit() {
  local listing
  listing="$(git ls-remote --tags "$REMOTE" "refs/tags/$1" "refs/tags/$1^{}")"
  awk 'NF { commit = $1 } END { if (commit != "") print commit }' <<<"$listing"
}

# -----------------------------------------------------------------------------
# Tells whether GitHub has a release for a tag. Only a 404 means it has none:
# any other failure stops the run, because "could not ask" read as "not
# released" would go on to publish.
# -----------------------------------------------------------------------------
release_exists() {
  local answer
  if answer="$(gh api "repos/{owner}/{repo}/releases/tags/$1" --jq .tag_name 2>&1)"; then
    return 0
  fi
  if [[ $answer == *"HTTP 404"* ]]; then
    return 1
  fi
  die "could not look up the release of $1: $answer"
}

# -----------------------------------------------------------------------------
# Prints the body of the CHANGELOG.md section of a version, without the blank
# lines around it. The section ends at the next version heading or at the link
# definitions that close the file.
# -----------------------------------------------------------------------------
changelog_section() {
  awk -v heading="## [$1]" '
    index($0, heading) == 1 { found = 1; next }
    found && (/^## \[/ || /^\[[^]]+\]: /) { exit }
    !found { next }
    /^[[:space:]]*$/ { blank++; next }
    {
      if (printed) { for (; blank > 0; blank--) print "" }
      blank = 0
      print
      printed = 1
    }
  ' CHANGELOG.md
}

version="$(grep -E '^COMPONENT_VERSION=' VERSION | head -n1 | cut -d= -f2- || true)"
if [[ ! $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  die "COMPONENT_VERSION='$version' in VERSION is not MAJOR.MINOR.PATCH"
fi
tag="v$version"
commit="${GITHUB_SHA:-$(git rev-parse HEAD)}"

# -----------------------------------------------------------------------------
# Sets `state`, and refuses what no later step could put right.
# -----------------------------------------------------------------------------
plan() {
  local tag_commit
  tag_commit="$(remote_tag_commit "$tag")"

  if release_exists "$tag"; then
    state="published"
    echo "$tag is already released; nothing to publish"
  elif [ -z "$tag_commit" ]; then
    state="new"
    echo "$tag does not exist yet; ${commit:0:12} is to be tagged and released"
  elif [ "$tag_commit" = "$commit" ]; then
    state="tagged"
    echo "$tag exists on this commit without a release; the release is to be created on it"
  else
    die "$tag exists on ${tag_commit:0:12} without a release, and this run is on ${commit:0:12}." \
      "A version tag is never moved: publish it by hand with" \
      "'gh release create $tag --verify-tag', or name a new version in VERSION"
  fi

  # The release notes open with the changelog section, and a release without
  # one tells consumers nothing about what they have to act on.
  if [ "$state" != "published" ] && [ -z "$(changelog_section "$version")" ]; then
    die "CHANGELOG.md has no '## [$version]' section, or an empty one; write it before releasing"
  fi
}

# -----------------------------------------------------------------------------
# Points vMAJOR and vMAJOR.MINOR at the release, each only when the release is
# the newest of that line: 1.4.1 released after 1.5.0 moves v1.4 and leaves v1
# where it is.
# -----------------------------------------------------------------------------
move_floating_tags() {
  local released listing versions major alias pattern newest current
  released="$(remote_tag_commit "$tag")"
  [ -n "$released" ] || die "$tag is not on $REMOTE after the release was created"

  listing="$(git ls-remote --tags --refs "$REMOTE" 'refs/tags/v*')"
  versions="$(awk '{ sub(".*refs/tags/", ""); print }' <<<"$listing" |
    grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' || true)"

  major="${version%%.*}"
  for alias in "v$major" "v${version%.*}"; do
    if [ "$alias" = "v$major" ]; then
      pattern="^v${major}\.[0-9]+\.[0-9]+$"
    else
      pattern="^${alias//./\\.}\.[0-9]+$"
    fi
    newest="$(grep -E "$pattern" <<<"$versions" | sort -V | tail -n1 || true)"
    if [ "$newest" != "$tag" ]; then
      echo "$alias stays where it is: $newest is newer than $tag"
      continue
    fi

    current="$(remote_tag_commit "$alias")"
    if [ "$current" = "$released" ]; then
      echo "$alias already points at $tag"
      continue
    fi
    echo "moving $alias -> $tag"
    git push --force "$REMOTE" "$released:refs/tags/$alias"
  done
}

publish() {
  local notes
  plan

  if [ "$state" != "published" ]; then
    notes="$(mktemp)"
    # Expanded now, on purpose: `notes` is local and gone by the time the trap
    # runs.
    # shellcheck disable=SC2064
    trap "rm -f '$notes'" EXIT
    changelog_section "$version" >"$notes"

    # --generate-notes appends the list of merged pull requests to the
    # changelog section. --target makes GitHub create the tag with the release,
    # in one request; --verify-tag refuses to create one.
    if [ "$state" = "new" ]; then
      set -- --target "$commit"
    else
      set -- --verify-tag
    fi
    if ! gh release create "$tag" "$@" --title "$tag" --notes-file "$notes" --generate-notes; then
      die "could not create the release $tag. If GitHub answered with a repository rule" \
        "violation, a tag ruleset does not let this workflow create $tag: see Releasing" \
        "in CONTRIBUTING.md"
    fi
    echo "released $tag"
  fi

  move_floating_tags
}

case "${1:-}" in
  plan)
    plan
    if [ -n "${GITHUB_OUTPUT:-}" ]; then
      printf 'version=%s\ntag=%s\nstate=%s\n' "$version" "$tag" "$state" >>"$GITHUB_OUTPUT"
    fi
    ;;
  publish)
    publish
    ;;
  *)
    echo "usage: $0 plan | publish" >&2
    exit 2
    ;;
esac
