#!/usr/bin/env python3
"""Runs the rewrite the catalog mirror applies to the README and the examples.

The mirror (``catalog-mirror/.gitlab-ci.yml``) copies ``README.md`` and
``examples/`` to a project on somebody's GitLab and rewrites them there: a
remote include becomes a component of that project, and what is only true on
GitHub is dropped. That happens in a pipeline this repository never sees, long
after a release, so a README the rewrite mangles would be found on the page of
a catalog. This file runs it first.

The shell function is read out of the pipeline file itself, so what is tested
is what a mirror runs, and it is given:

  * this repository as it is, pretending to be the release ``VERSION`` names;
  * a small tree written the way older releases were, with what the rewrite
    must leave alone next to what it must change.

What this cannot cover is the rest of the ``sync`` job -- the releases it
lists, the commits and the tags it pushes -- nor GitLab itself.

  python3 tests/catalog-mirror.test.py             # run the cases
  python3 tests/catalog-mirror.test.py --image     # run them in the image of the
                                                   # sync job, through docker
  python3 tests/catalog-mirror.test.py --dump DIR  # write the function to DIR,
                                                   # for shellcheck

The job runs on Alpine, where ``sed`` and ``find`` are the BusyBox ones and
not the GNU ones of a workstation. ``--image`` is the run that counts.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import component  # noqa: E402  (needs the path set above)
from component import REPO_ROOT, yaml  # noqa: E402

PIPELINE = "catalog-mirror/.gitlab-ci.yml"
FUNCTION_KEY = ".rewrite-for-catalog"

# Where the pretend mirror lives. Nested on purpose, and nothing like the path
# the documentation assumes, so a reference left behind stands out.
MIRROR_URL = "https://gitlab.example.com"
MIRROR_PATH = "group/subgroup/security-scanner"
# The path the documentation assumes for a mirror (CATALOG_PROJECT in
# scripts/check-sync.sh). None of it may reach the published copy.
ASSUMED_PATH = "tooark/ci-security-scanner"

# A marker is a comment alone on its line. LOOSE_MARKER is anything that looks
# like one: what it finds and MARKER does not is a marker the mirror would
# publish instead of obeying.
MARKER = re.compile(r"^(?:<!--|#) github-only:(start|end)(?: -->)?$")
LOOSE_MARKER = re.compile(r"^\s*(?:<!--|#)\s*github-only\s*:\s*(?:start|end)\b")

REMOTE_TEMPLATE = re.compile(r"raw\.githubusercontent\.com/\S*/templates/\S*")
COMPONENT_REF = re.compile(r"\$CI_SERVER_FQDN/[^\s`\"']*@[^\s`\"']*")
EXAMPLES_LINK = re.compile(r"https://[^\s)]+/(?:blob|tree)/[^\s)/]+/examples[^\s)]*")

# Written the way releases older than the markers were: another name for the
# repository, pipelines in a subdirectory of examples/. Each line that must
# survive sits next to the one that must change.
OLD_TAG, OLD_VERSION = "v1.1.0", "1.1.0"
OLD_README = """\
<!-- Prose that names "github-only:start" and "github-only:end" stays. -->
# Title

<!-- github-only:start -->

### Remote include

No catalog required.

<!-- github-only:end -->

  - remote: "https://raw.githubusercontent.com/Tooark/ci-security-scanner/v1.1.0/templates/full-scan.yml"
  - remote: https://raw.githubusercontent.com/Tooark/ci-security-scanner/v1.1.0/templates/secret-scan.yml
  - remote: "https://raw.githubusercontent.com/Tooark/ci-security-scanner/<commit-sha>/templates/full-scan.yml"
  - remote: "https://raw.githubusercontent.com/Tooark/ci-security-scanner/v1.0.0/templates/full-scan.yml"
  - remote: "https://raw.githubusercontent.com/someone/else/v1.1.0/templates/their-scan.yml"
  - component: $CI_SERVER_FQDN/tooark/ci-security-scanner/full-scan@1.1.0
  - component: $CI_SERVER_FQDN/tooark/ci-security-scanner/secret-scan@1
  - component: $CI_SERVER_FQDN/components/sast/sast@2.0.0

[examples](https://github.com/Tooark/template-security-scanner/tree/main/examples) and
[one](https://github.com/Tooark/template-security-scanner/blob/main/examples/one.yml), but
[theirs](https://github.com/Tooark/base-images/tree/main/examples) and
[docs](https://github.com/Tooark/template-security-scanner/tree/main/docs).
"""
OLD_README_REWRITTEN = """\
<!-- Prose that names "github-only:start" and "github-only:end" stays. -->
# Title


  - component: $CI_SERVER_FQDN/{path}/full-scan@1.1.0
  - component: $CI_SERVER_FQDN/{path}/secret-scan@1.1.0
  - remote: "https://raw.githubusercontent.com/Tooark/ci-security-scanner/<commit-sha>/templates/full-scan.yml"
  - remote: "https://raw.githubusercontent.com/Tooark/ci-security-scanner/v1.0.0/templates/full-scan.yml"
  - remote: "https://raw.githubusercontent.com/someone/else/v1.1.0/templates/their-scan.yml"
  - component: $CI_SERVER_FQDN/{path}/full-scan@1.1.0
  - component: $CI_SERVER_FQDN/{path}/secret-scan@1
  - component: $CI_SERVER_FQDN/components/sast/sast@2.0.0

[examples]({url}/{path}/-/tree/1.1.0/examples) and
[one]({url}/{path}/-/blob/1.1.0/examples/one.yml), but
[theirs](https://github.com/Tooark/base-images/tree/main/examples) and
[docs](https://github.com/Tooark/template-security-scanner/tree/main/docs).
"""
OLD_EXAMPLE = """\
# A pipeline.
# github-only:start
# Works wherever raw.githubusercontent.com is reachable.
# github-only:end
include:
  - remote: "https://raw.githubusercontent.com/Tooark/ci-security-scanner/v1.1.0/templates/full-scan.yml"
    inputs:
      stage: test
"""
OLD_EXAMPLE_REWRITTEN = """\
# A pipeline.
include:
  - component: $CI_SERVER_FQDN/{path}/full-scan@1.1.0
    inputs:
      stage: test
"""


def load_function() -> tuple[str, str, str, list[str]]:
  """Returns the rewrite function, UPSTREAM_REPO, the job image and what is wrong."""
  pipeline = yaml.safe_load((REPO_ROOT / PIPELINE).read_text(encoding="utf-8"))
  problems: list[str] = []

  entries = pipeline.get(FUNCTION_KEY)
  if not (isinstance(entries, list) and len(entries) == 1 and isinstance(entries[0], str)):
    return "", "", "", [f"{PIPELINE} has no '{FUNCTION_KEY}' holding the one script that defines the function"]

  # The function is only worth testing if the job runs that very text.
  script = pipeline.get("sync", {}).get("script", [])
  if not script or script[0] != entries:
    problems.append(f"the sync job of {PIPELINE} does not start its script with '{FUNCTION_KEY}'")
  if not any(isinstance(entry, str) and 'rewrite_for_catalog "$upstream_tag" "$version"' in entry for entry in script):
    problems.append(f"the sync job of {PIPELINE} never calls rewrite_for_catalog for a release")

  variables = pipeline.get("variables", {})
  synced = str(variables.get("SYNCED_PATHS", "")).split()
  for path in ("templates", "examples", "README.md"):
    if path not in synced:
      problems.append(f"SYNCED_PATHS of {PIPELINE} leaves out {path}, which the rewrite reads")

  image = str(pipeline.get("sync", {}).get("image", ""))
  return entries[0], str(variables.get("UPSTREAM_REPO", "")), image, problems


def rewrite(shell: list[str], function: str, upstream: str, tree: Path, tag: str, version: str,
            path: str = MIRROR_PATH) -> subprocess.CompletedProcess:
  """Runs the function in a tree the way the sync job does, under set -eu."""
  variables = dict(CI_PROJECT_PATH=path, CI_SERVER_URL=MIRROR_URL, UPSTREAM_REPO=upstream)
  script = f"set -eu\n{function}\nrewrite_for_catalog {shlex.quote(tag)} {shlex.quote(version)}\n"
  # A shell is the path of sh. An image is run with the tree mounted as its
  # working directory, which is all the function reads and writes.
  if shell[0] == "docker":
    passed = [flag for name in variables for flag in ("-e", name)]
    command = ["docker", "run", "--rm", "-v", f"{tree}:/work", "-w", "/work", *passed, shell[1], "sh"]
  else:
    command = shell
  return subprocess.run(
      [*command, "-c", script], env=dict(os.environ, **variables), cwd=tree,
      capture_output=True, text=True, check=False,
  )


def write(path: Path, text: str) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(text, encoding="utf-8", newline="\n")


def dropped_lines(label: str, text: str) -> tuple[int, list[str]]:
  """Counts the lines the markers of a file take out, and checks they pair up."""
  problems: list[str] = []
  dropped = 0
  opened = 0
  for number, line in enumerate(text.splitlines(), start=1):
    match = MARKER.match(line)
    if match is None:
      if LOOSE_MARKER.match(line):
        problems.append(f"{label}:{number} looks like a marker but is not one the mirror obeys: {line.strip()}")
      dropped += 1 if opened else 0
      continue
    dropped += 1
    if match.group(1) == "start":
      if opened:
        problems.append(f"{label}:{number} opens a block inside the one opened on line {opened}")
      opened = number
    elif opened:
      opened = 0
    else:
      problems.append(f"{label}:{number} closes a block that was never opened")
  if opened:
    problems.append(f"{label}:{opened} opens a block that is never closed; the mirror would drop the rest of the file")
  return dropped, problems


def load_check_examples():
  """Imports scripts/check-examples.py, whose name is not an identifier."""
  spec = importlib.util.spec_from_file_location("check_examples", REPO_ROOT / "scripts" / "check-examples.py")
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


def include_keys(text: str, check_examples) -> list[str]:
  """Lists how each include of one of the templates reaches it."""
  keys = []
  for entry in check_examples.includes(yaml.safe_load(text)):
    if check_examples.included_template(entry) is not None:
      keys.extend(key for key in ("remote", "local", "component") if key in entry)
  return keys


def case_repository(shell: list[str], function: str, upstream: str, tmp: Path) -> list[str]:
  """This repository, published as the version it is about to release."""
  components = component.load_all()
  check_examples = load_check_examples()
  version = re.search(r"^COMPONENT_VERSION=(.+)$", (REPO_ROOT / "VERSION").read_text(encoding="utf-8"), re.MULTILINE)
  version = version.group(1).strip()

  tree = tmp / "repository"
  shutil.copytree(REPO_ROOT / "templates", tree / "templates")
  shutil.copytree(REPO_ROOT / "examples", tree / "examples")
  shutil.copy(REPO_ROOT / "README.md", tree / "README.md")
  files = ["README.md", *sorted(path.relative_to(tree).as_posix() for path in (tree / "examples").rglob("*.yml"))]
  before = {name: (tree / name).read_text(encoding="utf-8") for name in files}

  problems: list[str] = []
  expected_lines = {}
  for name, text in before.items():
    dropped, marker_problems = dropped_lines(name, text)
    problems.extend(marker_problems)
    expected_lines[name] = len(text.splitlines()) - dropped
  if problems:
    return problems

  result = rewrite(shell, function, upstream, tree, f"v{version}", version)
  if result.returncode != 0:
    return [f"the rewrite exited {result.returncode}\n{result.stdout}{result.stderr}"]

  expected_ref = re.compile(
      re.escape(f"$CI_SERVER_FQDN/{MIRROR_PATH}/") + "(" + "|".join(sorted(components)) + ")@" + re.escape(version) + "$"
  )
  links = 0
  for name in files:
    text = (tree / name).read_text(encoding="utf-8")
    lines = text.splitlines()

    # Nothing but the marked blocks may go: a range that ran away would take
    # the rest of the file with it and still leave valid Markdown behind.
    if len(lines) != expected_lines[name]:
      problems.append(f"{name} has {len(lines)} lines, expected {expected_lines[name]} once its marked blocks are out")
    if "github-only:" in text and name != "README.md":
      problems.append(f"{name} still names a github-only marker")
    for number, line in enumerate(lines, start=1):
      if MARKER.match(line) or LOOSE_MARKER.match(line):
        problems.append(f"{name}:{number} still carries a marker")
      for found in REMOTE_TEMPLATE.findall(line):
        # The one remote include that stays: the README shows how to pin a
        # commit, which only a remote include can do.
        if "<commit-sha>" not in found:
          problems.append(f"{name}:{number} still includes a template from GitHub: {found}")
      for found in COMPONENT_REF.findall(line):
        if not expected_ref.match(found):
          problems.append(f"{name}:{number} names a component the mirror does not publish: {found}")
      for found in EXAMPLES_LINK.findall(line):
        links += 1
        prefix = f"{MIRROR_URL}/{MIRROR_PATH}/-/"
        target = re.sub(r"^(?:blob|tree)/" + re.escape(version) + "/", "", found.removeprefix(prefix))
        if not found.startswith(prefix) or target == found.removeprefix(prefix):
          problems.append(f"{name}:{number} links to examples outside the mirror or its version: {found}")
        elif not (tree / target).exists():
          problems.append(f"{name}:{number} links to {target}, which the mirror does not have")
    if ASSUMED_PATH in text:
      problems.append(f"{name} still names {ASSUMED_PATH}, the path the documentation assumes for a mirror")

    # What a reader copies from the mirror has to be accepted by GitLab like
    # what they copy from here, and every include has to have followed.
    documents = [text] if name != "README.md" else check_examples.YAML_BLOCK.findall(text)
    for index, document in enumerate(documents, start=1):
      label = name if name != "README.md" else f"{name} (yaml block {index})"
      try:
        _, include_problems, _ = check_examples.check_document(document, components)
        keys = include_keys(document, check_examples)
      except yaml.YAMLError as exc:
        problems.append(f"{label} no longer parses as YAML: {exc}")
        continue
      problems.extend(f"{label} {problem}" for problem in include_problems)
      if name != "README.md":
        was = include_keys(before[name], check_examples)
        if len(keys) != len(was):
          problems.append(f"{label} had {len(was)} includes of the templates and has {len(keys)} now")
        if set(keys) - {"component"}:
          problems.append(f"{label} still reaches a template through {sorted(set(keys) - {'component'})}")

  if links == 0:
    problems.append("README.md links to no example; the check of those links has nothing to read")
  return problems


def case_older_release(shell: list[str], function: str, upstream: str, tmp: Path) -> list[str]:
  """The shapes older releases have, and everything the rewrite must not touch."""
  tree = tmp / "older"
  write(tree / "README.md", OLD_README)
  write(tree / "templates" / "full-scan.yml", "")
  write(tree / "templates" / "secret-scan.yml", "")
  # No pipeline directly under examples/, as in 1.1.0 and 1.2.0.
  write(tree / "examples" / "gitlab" / "pipeline.yml", OLD_EXAMPLE)
  write(tree / "examples" / "gitlab" / "notes.txt", OLD_EXAMPLE)

  expected = {
      "README.md": OLD_README_REWRITTEN.format(path=MIRROR_PATH, url=MIRROR_URL),
      "examples/gitlab/pipeline.yml": OLD_EXAMPLE_REWRITTEN.format(path=MIRROR_PATH),
      "examples/gitlab/notes.txt": OLD_EXAMPLE,
  }

  problems: list[str] = []
  # Twice: a second pass over its own output must change nothing.
  for attempt in ("first", "second"):
    result = rewrite(shell, function, upstream, tree, OLD_TAG, OLD_VERSION)
    if result.returncode != 0:
      return [f"the {attempt} run exited {result.returncode}\n{result.stdout}{result.stderr}"]
    for name, wanted in expected.items():
      actual = (tree / name).read_text(encoding="utf-8")
      if actual != wanted:
        problems.append(f"{name} after the {attempt} run:\n--- expected\n{wanted}--- actual\n{actual}")
    if problems:
      break
  return problems


def case_assumed_path(shell: list[str], function: str, upstream: str, tmp: Path) -> list[str]:
  """A mirror that lives where the documentation assumes, with no examples/."""
  tree = tmp / "assumed"
  write(tree / "README.md", OLD_README)
  write(tree / "templates" / "full-scan.yml", "")
  write(tree / "templates" / "secret-scan.yml", "")

  result = rewrite(shell, function, upstream, tree, OLD_TAG, OLD_VERSION, path=ASSUMED_PATH)
  if result.returncode != 0:
    return [f"the rewrite exited {result.returncode}\n{result.stdout}{result.stderr}"]
  wanted = OLD_README_REWRITTEN.format(path=ASSUMED_PATH, url=MIRROR_URL)
  actual = (tree / "README.md").read_text(encoding="utf-8")
  if actual != wanted:
    return [f"README.md:\n--- expected\n{wanted}--- actual\n{actual}"]
  return []


def case_no_templates(shell: list[str], function: str, upstream: str, tmp: Path) -> list[str]:
  """Without a template there is no include to recognise: stop, change nothing."""
  tree = tmp / "empty"
  write(tree / "README.md", OLD_README)
  (tree / "templates").mkdir()

  result = rewrite(shell, function, upstream, tree, OLD_TAG, OLD_VERSION)
  problems: list[str] = []
  if result.returncode == 0:
    problems.append("the rewrite succeeded with an empty templates/")
  if (tree / "README.md").read_text(encoding="utf-8") != OLD_README:
    problems.append("README.md was changed although the rewrite failed")
  return problems


CASES = [
    ("this repository, as the release VERSION names", case_repository),
    ("an older release: another repository name, nested examples, things to leave alone", case_older_release),
    ("a mirror at the path the documentation assumes, without examples/", case_assumed_path),
    ("a release without templates stops the sync", case_no_templates),
]


def main(argv: list[str]) -> int:
  function, upstream, image, problems = load_function()
  if not function:
    print("  FAIL " + problems[0], file=sys.stderr)
    return 1

  if len(argv) == 3 and argv[1] == "--dump":
    target = Path(argv[2]) / "rewrite-for-catalog.sh"
    write(target, "#!/bin/sh\n" + function)
    print(f"  wrote {target.as_posix()}")
    return 0

  if argv[1:] == ["--image"]:
    shell = ["docker", image]
    missing = "docker and an image for the sync job are"
  elif len(argv) == 1:
    # sh, not bash: the job runs in whatever /bin/sh its image has.
    shell = [shutil.which("sh") or ""]
    missing = "sh is"
  else:
    print(__doc__, file=sys.stderr)
    return 2
  if not all(shell) or shutil.which(shell[0]) is None:
    print(f"{missing} required to run the rewrite", file=sys.stderr)
    return 1

  failed = 0
  if problems:
    failed += 1
    print(f"  FAIL {PIPELINE} runs the function it defines")
    for problem in problems:
      print("       " + problem)
  else:
    print(f"  ok   {PIPELINE} runs the function it defines")

  with tempfile.TemporaryDirectory() as tmp:
    for name, case in CASES:
      problems = case(shell, function, upstream, Path(tmp))
      if problems:
        failed += 1
        print(f"  FAIL {name}")
        for problem in problems:
          print("       " + problem.replace("\n", "\n       "))
      else:
        print(f"  ok   {name}")

  if failed:
    print(f"\n{failed} case(s) failed", file=sys.stderr)
    return 1

  print(f"\nall {len(CASES)} catalog mirror cases passed")
  return 0


if __name__ == "__main__":
  sys.exit(main(sys.argv))
