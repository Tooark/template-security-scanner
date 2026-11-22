#!/usr/bin/env bash
# =============================================================================
# Runs scripts/release.sh against a throwaway repository and a stand-in gh.
#
# Publishing is the one thing here that cannot be taken back, so every state
# the script can find is played out first: a bare repository stands in for
# GitHub's copy of this one, and a `gh` on the PATH answers the two calls the
# script makes, from a list of releases kept in a file.
#
#   bash tests/release.test.sh
# =============================================================================
set -uo pipefail

SCRIPT="$(cd "$(dirname "$0")/.." && pwd)/scripts/release.sh"
ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT

# Nor may the workflow this runs in. On a runner GITHUB_SHA names a commit of
# the real repository, which the script would try to tag in the throwaway one,
# and GITHUB_ACTIONS would turn every expected refusal into an error annotation
# on the run.
unset GITHUB_SHA GITHUB_ACTIONS GITHUB_REF GITHUB_REPOSITORY GH_REPO

# Nothing of the machine's own git setup may leak in: no signing, no hooks.
export GIT_CONFIG_GLOBAL="$ROOT/gitconfig" GIT_CONFIG_NOSYSTEM=1
git config --global user.name "release test"
git config --global user.email "release-test@example.invalid"
git config --global init.defaultBranch main
git config --global advice.detachedHead false

# -----------------------------------------------------------------------------
# The stand-in gh. It knows the release lookup and `release create`, and keeps
# a log of the calls that would have changed something.
# -----------------------------------------------------------------------------
mkdir -p "$ROOT/bin"
cat >"$ROOT/bin/gh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail

if [ "$1" = "api" ]; then
  if [ -n "${GH_STUB_BROKEN:-}" ]; then
    echo "gh: Bad credentials (HTTP 401)" >&2
    exit 1
  fi
  tag="${2##*/}"
  if grep -qxF "$tag" "$GH_STUB_DIR/releases"; then
    echo "$tag"
    exit 0
  fi
  echo "gh: Not Found (HTTP 404)" >&2
  exit 1
fi

if [ "$1 $2" = "release create" ]; then
  tag="$3"
  shift 3
  target="" verify="" notes=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --target) target="$2"; shift 2 ;;
      --verify-tag) verify=1; shift ;;
      --notes-file) notes="$2"; shift 2 ;;
      --title) shift 2 ;;
      *) shift ;;
    esac
  done

  origin="$GH_STUB_DIR/origin.git"
  if [ -n "$verify" ]; then
    git --git-dir="$origin" rev-parse -q --verify "refs/tags/$tag" >/dev/null || {
      echo "tag $tag doesn't exist in the repo" >&2
      exit 1
    }
  else
    # An empty old value makes update-ref refuse a tag that already exists.
    git --git-dir="$origin" update-ref "refs/tags/$tag" "$target" ""
  fi
  cp "$notes" "$GH_STUB_DIR/notes"
  echo "$tag" >>"$GH_STUB_DIR/releases"
  echo "create $tag ${target:+--target}${verify:+--verify-tag}" >>"$GH_STUB_DIR/calls"
  exit 0
fi

echo "gh stub: unexpected call: $*" >&2
exit 2
STUB
chmod +x "$ROOT/bin/gh"
export PATH="$ROOT/bin:$PATH"

failures=0
ok() { printf '  ok   %s\n' "$*"; }
fail() { printf '  FAIL %s\n' "$*" >&2; failures=$((failures + 1)); }

# -----------------------------------------------------------------------------
# Starts a case: a fresh origin with one commit on main per version given, the
# last one checked out in the clone the script runs from. Leaves:
#   WORK      the clone
#   COMMITS   the commit of each version, in the order given
# -----------------------------------------------------------------------------
setup() {
  local version
  CASE_DIR="$ROOT/case"
  rm -rf "$CASE_DIR"
  mkdir -p "$CASE_DIR"
  export GH_STUB_DIR="$CASE_DIR"
  unset GH_STUB_BROKEN
  : >"$CASE_DIR/releases"
  : >"$CASE_DIR/calls"

  git init -q --bare "$CASE_DIR/origin.git"
  WORK="$CASE_DIR/work"
  git init -q "$WORK"
  git -C "$WORK" remote add origin "$CASE_DIR/origin.git"
  mkdir -p "$WORK/scripts"
  cp "$SCRIPT" "$WORK/scripts/release.sh"

  COMMITS=()
  for version in "$@"; do
    printf 'COMPONENT_VERSION=%s\n' "$version" >"$WORK/VERSION"
    {
      printf '# Changelog\n\n## [Unreleased]\n\n## [%s] - 2026-01-01\n\n' "$version"
      printf 'Notes of %s.\n\n### Added\n\n- something\n\n' "$version"
      printf '## [0.9.0] - 2025-01-01\n\nOlder notes.\n\n[0.9.0]: https://example.invalid\n'
    } >"$WORK/CHANGELOG.md"
    git -C "$WORK" add -A
    # --allow-empty: the same version twice is a push that changes nothing.
    git -C "$WORK" commit -q --allow-empty -m "release $version"
    COMMITS+=("$(git -C "$WORK" rev-parse HEAD)")
  done
  git -C "$WORK" push -q origin main
}

# A tag of the origin, as GitHub would hold it: tag <name> <commit> [released]
tag() {
  git --git-dir="$CASE_DIR/origin.git" update-ref "refs/tags/$1" "$2"
  if [ "${3:-}" = "released" ]; then
    echo "$1" >>"$CASE_DIR/releases"
  fi
}

# Runs the script in the clone; leaves STATUS and OUTPUT.
run() {
  OUTPUT="$(cd "$WORK" && GITHUB_OUTPUT="$CASE_DIR/output" bash scripts/release.sh "$@" 2>&1)"
  STATUS=$?
}

tag_commit() {
  git --git-dir="$CASE_DIR/origin.git" rev-parse -q --verify "refs/tags/$1^{commit}" 2>/dev/null || true
}

expect() { # expect <label> <actual> <expected>
  if [ "$2" = "$3" ]; then
    ok "$1"
  else
    fail "$1: got '$2', expected '$3'"
    printf '%s\n' "$OUTPUT" | sed 's/^/       | /' >&2
  fi
}

echo "a version with no tag and no release is tagged and released"
setup 1.5.0
run plan
expect "plan succeeds" "$STATUS" 0
expect "plan reports new" "$(grep '^state=' "$CASE_DIR/output")" "state=new"
expect "plan creates nothing" "$(cat "$CASE_DIR/calls")" ""
run publish
expect "publish succeeds" "$STATUS" 0
expect "the release is created on this commit" "$(cat "$CASE_DIR/calls")" "create v1.5.0 --target"
expect "v1.5.0 is this commit" "$(tag_commit v1.5.0)" "${COMMITS[0]}"
expect "v1 follows" "$(tag_commit v1)" "${COMMITS[0]}"
expect "v1.5 follows" "$(tag_commit v1.5)" "${COMMITS[0]}"
expect "the notes are the changelog section" "$(cat "$CASE_DIR/notes")" \
  "$(printf 'Notes of 1.5.0.\n\n### Added\n\n- something')"

echo "a version already released is left alone"
run publish
expect "publish succeeds" "$STATUS" 0
expect "no second release" "$(cat "$CASE_DIR/calls")" "create v1.5.0 --target"
run plan
expect "plan reports published" "$(tail -n1 "$CASE_DIR/output")" "state=published"

echo "a push that touches VERSION without a new version releases nothing"
setup 1.5.0 1.5.0
tag v1.5.0 "${COMMITS[0]}" released
tag v1 "${COMMITS[0]}"
tag v1.5 "${COMMITS[0]}"
run publish
expect "publish succeeds" "$STATUS" 0
expect "nothing is created" "$(cat "$CASE_DIR/calls")" ""
expect "v1.5.0 stays on its commit" "$(tag_commit v1.5.0)" "${COMMITS[0]}"
expect "v1 stays on its commit" "$(tag_commit v1)" "${COMMITS[0]}"

echo "a tag on this commit without a release gets its release"
setup 1.5.0
tag v1.5.0 "${COMMITS[0]}"
run publish
expect "publish succeeds" "$STATUS" 0
expect "the release is created on the tag" "$(cat "$CASE_DIR/calls")" "create v1.5.0 --verify-tag"
expect "v1 follows" "$(tag_commit v1)" "${COMMITS[0]}"

echo "a tag on another commit without a release stops the run"
setup 1.5.0 1.5.0
tag v1.5.0 "${COMMITS[0]}"
run publish
expect "publish fails" "$STATUS" 1
expect "nothing is created" "$(cat "$CASE_DIR/calls")" ""
expect "the tag is not moved" "$(tag_commit v1.5.0)" "${COMMITS[0]}"

echo "a patch of an older line leaves the newer floating tag alone"
setup 1.5.0 1.4.1
tag v1.4.0 "${COMMITS[0]}" released
tag v1.5.0 "${COMMITS[0]}" released
tag v1.10.0 "${COMMITS[0]}" released
tag v1 "${COMMITS[0]}"
tag v1.4 "${COMMITS[0]}"
run publish
expect "publish succeeds" "$STATUS" 0
expect "v1.4.1 is this commit" "$(tag_commit v1.4.1)" "${COMMITS[1]}"
expect "v1.4 moves" "$(tag_commit v1.4)" "${COMMITS[1]}"
expect "v1 stays on 1.10.0" "$(tag_commit v1)" "${COMMITS[0]}"

echo "a floating tag left behind by a failed run is put right"
setup 1.5.0
tag v1.5.0 "${COMMITS[0]}" released
run publish
expect "publish succeeds" "$STATUS" 0
expect "nothing is created" "$(cat "$CASE_DIR/calls")" ""
expect "v1 points at the release" "$(tag_commit v1)" "${COMMITS[0]}"
expect "v1.5 points at the release" "$(tag_commit v1.5)" "${COMMITS[0]}"

echo "a version without a changelog section is not released"
setup 1.5.0
sed -i 's/^## \[1\.5\.0\].*/## [1.4.9] - 2026-01-01/' "$WORK/CHANGELOG.md"
run publish
expect "publish fails" "$STATUS" 1
expect "nothing is created" "$(cat "$CASE_DIR/calls")" ""
expect "no tag is created" "$(tag_commit v1.5.0)" ""

echo "a version that is not MAJOR.MINOR.PATCH is refused"
setup 1.5
run publish
expect "publish fails" "$STATUS" 1
expect "nothing is created" "$(cat "$CASE_DIR/calls")" ""

echo "a lookup that fails is not taken for a missing release"
setup 1.5.0
export GH_STUB_BROKEN=1
run publish
expect "publish fails" "$STATUS" 1
expect "nothing is created" "$(cat "$CASE_DIR/calls")" ""
expect "no tag is created" "$(tag_commit v1.5.0)" ""
unset GH_STUB_BROKEN

echo
if [ "$failures" -gt 0 ]; then
  printf '%s check(s) failed\n' "$failures" >&2
  exit 1
fi
echo "all release cases passed"
