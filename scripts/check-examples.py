#!/usr/bin/env python3
"""Checks that every documented ``include:`` matches the template it names.

GitLab rejects a pipeline whose include passes an input the template does not
declare, a value outside its ``options``, or a string where it wants a boolean.
It does so when the pipeline is created -- in the project of whoever copied the
example. So every include of these templates, in ``examples/`` and in the YAML
blocks of the Markdown documentation, is checked here first:

  * the template it names exists;
  * its ``inputs:`` would be accepted: declared, of the right type, within
    ``options`` and matching ``regex``, with nothing required left out;
  * it passes no deprecated input. GitLab still accepts one, but an example
    that shows it teaches the name that is going away.

``examples/all-inputs.gitlab-ci.yml`` is held to one more rule, the one its
name promises: between its includes it passes every input the templates
declare, the deprecated ones aside.

Usage: python3 scripts/check-examples.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import component
from component import REPO_ROOT, yaml

MARKDOWN = ("README.md", "README.pt-BR.md", "catalog-mirror/README.md")
# The example that documents every input; a new input has to land there too.
REFERENCE = "examples/all-inputs.gitlab-ci.yml"
YAML_BLOCK = re.compile(r"^ *```ya?ml\n(.*?)^ *```", re.MULTILINE | re.DOTALL)

# The three ways a pipeline reaches a template, each ending in its name:
#   remote:    https://raw.githubusercontent.com/<repo>/<ref>/templates/full-scan.yml
#   local:     templates/full-scan.yml
#   component: $CI_SERVER_FQDN/<group>/<project>/full-scan@1.2.0
BY_FILE = re.compile(r"(?:^|/)templates/([a-z0-9-]+)\.yml$")
BY_COMPONENT = re.compile(r"/([a-z0-9-]+)@[^/@]+$")


def included_template(entry: dict) -> str | None:
  """Returns the template name an include entry points at, if it is one of ours."""
  for key in ("remote", "local"):
    match = BY_FILE.search(str(entry.get(key, "")))
    if match:
      return match.group(1)
  match = BY_COMPONENT.search(str(entry.get("component", "")))
  return match.group(1) if match else None


def includes(document) -> list[dict]:
  """Lists the include entries of a pipeline document."""
  if not isinstance(document, dict) or "include" not in document:
    return []
  entries = document["include"]
  if isinstance(entries, dict):
    entries = [entries]
  return [entry for entry in entries if isinstance(entry, dict)]


def check_document(text: str, components: dict) -> tuple[int, list[str], set[str]]:
  """Returns (template includes found, problems, inputs passed) for one document."""
  count = 0
  problems: list[str] = []
  passed: set[str] = set()
  for entry in includes(yaml.safe_load(text)):
    name = included_template(entry)
    if name is None:
      continue
    count += 1
    if name not in components:
      problems.append(f"includes '{name}', which is not a template in templates/")
      continue
    provided = entry.get("inputs") or {}
    problems.extend(component.check_inputs(components[name], provided))
    for key in provided:
      definition = components[name].inputs.get(key)
      if definition is not None and component.is_deprecated(definition):
        problems.append(f"passes '{key}', which {name} only keeps for old pipelines: {definition['description']}")
    passed.update(provided)
  return count, problems, passed


def missing_from_reference(passed: set[str], components: dict) -> list[str]:
  """Lists the inputs the reference example should show and does not."""
  current = {
      name
      for item in components.values()
      for name, definition in item.inputs.items()
      if not component.is_deprecated(definition)
  }
  return sorted(current - passed)


def main() -> int:
  components = component.load_all()

  # (label, YAML text, must include a template) for every place a reader
  # copies a pipeline from.
  documents: list[tuple[str, str, bool]] = []
  for path in sorted((REPO_ROOT / "examples").glob("*.yml")):
    documents.append((path.relative_to(REPO_ROOT).as_posix(), path.read_text(encoding="utf-8"), True))
  for name in MARKDOWN:
    blocks = YAML_BLOCK.findall((REPO_ROOT / name).read_text(encoding="utf-8"))
    for index, block in enumerate(blocks, start=1):
      documents.append((f"{name} (yaml block {index})", block, False))

  failed = False
  total = 0
  reference_seen = False
  for label, text, required in documents:
    try:
      count, problems, passed = check_document(text, components)
    except yaml.YAMLError as exc:
      count, problems, passed = 0, [f"does not parse as YAML: {exc}"], set()
    total += count

    if label == REFERENCE:
      reference_seen = True
      for name in missing_from_reference(passed, components):
        problems.append(f"never passes '{name}'; this example is the one that shows every input")

    if count == 0 and not problems:
      # A Markdown block with no include is a job override or a fragment.
      if not required:
        continue
      problems = ["includes none of the templates; drop it from examples/ or fix the include"]

    if problems:
      failed = True
      print(f"  FAIL {label}")
      for problem in problems:
        print(f"       {problem}")
    else:
      print(f"  ok   {label}")

  if not reference_seen:
    failed = True
    print(f"  FAIL {REFERENCE} is missing; it is the example that shows every input")

  if failed:
    print("\nexample validation failed", file=sys.stderr)
    return 1

  print(f"\n{total} documented includes match their templates")
  return 0


if __name__ == "__main__":
  sys.exit(main())
