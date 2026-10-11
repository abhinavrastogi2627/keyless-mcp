#!/usr/bin/env bash
# Create the launch labels and issues on GitHub from the files in docs/launch/issues/.
#
#   docs/launch/create_issues.sh                       # sineframe/keyless-mcp
#   docs/launch/create_issues.sh someone/keyless-mcp   # another repository, e.g. a fork to rehearse on
#   DRY_RUN=1 docs/launch/create_issues.sh             # print what would happen, change nothing
#
# Needs the GitHub CLI (`gh`), logged in with permission to create labels and issues, and python3
# (standard library only). It is safe to run more than once: labels are created or updated, and
# an issue is skipped when an issue with the same title already exists (open or closed).
#
# Each issue file starts with front matter holding a `title` and a `labels` list, both written
# as JSON strings, followed by the Markdown body.
#
# The script refuses to run while an issue refers to a toolset missing from TOOLSETS in
# src/keyless_mcp/core/adapters.py, because a contributor could not scaffold that adapter.
# Set SKIP_TOOLSET_CHECK=1 to override.
set -euo pipefail

REPO="${1:-sineframe/keyless-mcp}"
DRY_RUN="${DRY_RUN:-0}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ISSUES_DIR="${HERE}/issues"
ROOT="$(cd "${HERE}/../.." && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "create_issues: python3 is required to read the issue files." >&2
  exit 1
fi
if [ "${DRY_RUN}" != "1" ]; then
  if ! command -v gh >/dev/null 2>&1; then
    echo "create_issues: the GitHub CLI (gh) is required. See https://cli.github.com/" >&2
    exit 1
  fi
  gh auth status >/dev/null 2>&1 || { echo "create_issues: run 'gh auth login' first." >&2; exit 1; }
fi

# Read an issue file and print "title<TAB>comma,separated,labels" on one line, then the body in a
# separate temp file named by the second argument.
parse_issue() {
  python3 - "$1" "$2" <<'PY'
import json
import sys

path, body_path = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
if not text.startswith("---\n"):
    sys.exit(f"{path}: missing front matter")
head, _, body = text[4:].partition("\n---\n")
fields = {}
for line in head.splitlines():
    key, _, value = line.partition(":")
    fields[key.strip()] = json.loads(value.strip())
title, labels = fields["title"], fields["labels"]
if not isinstance(title, str) or not title or not isinstance(labels, list) or not labels:
    sys.exit(f"{path}: title must be a string and labels a non-empty list")
open(body_path, "w", encoding="utf-8").write(body.lstrip("\n"))
print(title + "\t" + ",".join(labels))
PY
}

# ---- 1. Every toolset named by an issue must exist in the code -------------------------------
if [ "${SKIP_TOOLSET_CHECK:-0}" != "1" ]; then
  missing="$(python3 - "${ROOT}" "${ISSUES_DIR}" <<'PY'
import glob
import re
import sys

root, issues = sys.argv[1], sys.argv[2]
source = open(f"{root}/src/keyless_mcp/core/adapters.py", encoding="utf-8").read()
known = set(re.findall(r'"(\w+)"', re.search(r"^TOOLSETS = \(([^)]*)\)", source, re.M).group(1)))
used = set()
for path in glob.glob(f"{issues}/*.md"):
    used.update(re.findall(r"toolset:(\w+)", open(path, encoding="utf-8").read().split("\n---\n")[0]))
print(" ".join(sorted(used - known)))
PY
)"
  if [ -n "${missing}" ]; then
    echo "create_issues: these toolsets are used by the issues but are not in TOOLSETS yet: ${missing}" >&2
    echo "Add them to TOOLSETS in src/keyless_mcp/core/adapters.py and scripts/new_adapter.py, or set SKIP_TOOLSET_CHECK=1 to go ahead anyway." >&2
    exit 1
  fi
fi

# ---- 2. Labels ---------------------------------------------------------------------------------
# name|color|description
LABELS=(
  "good first issue|7057ff|Good for newcomers"
  "help wanted|008672|Extra attention is needed"
  "hacktoberfest|ff7518|Open for Hacktoberfest contributors"
  "adapter|1d76db|A new keyless API adapter"
  "bug|d73a4a|Something is not working"
  "toolset:science|0e8a16|Science and research adapters"
  "toolset:dev|5319e7|Developer tooling adapters"
  "toolset:geo|fbca04|Places, maps and weather adapters"
  "toolset:news|d93f0b|News and community feed adapters"
  "toolset:finance|0052cc|Money and economic data adapters"
  "toolset:reference|006b75|Books, words, history and other reference adapters"
  "toolset:fun|f9a8d4|Games, trivia and entertainment adapters"
  "area:core|b60205|The shared server code in src/keyless_mcp/core"
  "area:ci|bfdadc|Workflows and release pipeline"
  "area:docs|0075ca|Documentation"
  "area:testing|c2e0c6|Tests, M3 and the agent lane"
  "area:dx|c5def5|Developer and user experience"
  "benchmark-change-approved|fef2c0|A maintainer allows this pull request to lower the M3 benchmark baseline"
)

for entry in "${LABELS[@]}"; do
  IFS='|' read -r name color description <<<"${entry}"
  if [ "${DRY_RUN}" = "1" ]; then
    echo "[dry run] label: ${name} (#${color}) ${description}"
  else
    gh label create "${name}" --repo "${REPO}" --color "${color}" --description "${description}" --force >/dev/null
    echo "label: ${name}"
  fi
done

# ---- 3. Issues -------------------------------------------------------------------------------
existing="$(mktemp)"
body="$(mktemp)"
trap 'rm -f "${existing}" "${body}"' EXIT

if [ "${DRY_RUN}" != "1" ]; then
  gh issue list --repo "${REPO}" --state all --limit 1000 --json title --jq '.[].title' > "${existing}"
fi

created=0
skipped=0
shopt -s nullglob
for file in "${ISSUES_DIR}"/*.md; do
  parsed="$(parse_issue "${file}" "${body}")"
  title="${parsed%%$'\t'*}"
  labels="${parsed#*$'\t'}"
  if grep -Fxq -- "${title}" "${existing}"; then
    echo "skip (exists): ${title}"
    skipped=$((skipped + 1))
    continue
  fi
  if [ "${DRY_RUN}" = "1" ]; then
    echo "[dry run] issue: ${title} [${labels}]"
    created=$((created + 1))
    continue
  fi
  args=(--repo "${REPO}" --title "${title}" --body-file "${body}")
  IFS=',' read -r -a label_list <<<"${labels}"
  for label in "${label_list[@]}"; do
    args+=(--label "${label}")
  done
  gh issue create "${args[@]}" >/dev/null
  echo "created: ${title}"
  created=$((created + 1))
  printf '%s\n' "${title}" >> "${existing}"
  sleep 2  # stay clear of GitHub's secondary rate limits for content creation
done

echo "done: ${created} created, ${skipped} skipped (${REPO})"
