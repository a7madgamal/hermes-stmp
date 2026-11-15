#!/bin/sh
# catalog-pin — point the hermes-agent catalog entry at the plugin's current main.
#
# WHAT THIS IS FOR
#   The catalog entry in NousResearch/hermes-agent pins an exact commit of
#   a7madgamal/hermes-stmp. Every plugin change that should reach catalog users
#   needs a two-line PR there: `sha` moves to the new commit, `version` to the
#   plugin's version. This writes that branch for you.
#
# WHY A SCRIPT
#   The mistake this prevents is a pin to a commit that is not on the remote
#   (wrong sha, unpushed work) or a `version` that disagrees with the plugin.
#   Both are checked before the branch is created, so the PR cannot be wrong in
#   the two ways it can be wrong.
#
# USAGE
#   tools/catalog-pin.sh                 # pin to hermes-stmp main
#   tools/catalog-pin.sh <sha>           # pin to an exact commit
#   tools/catalog-pin.sh <sha> <version> # override the version label too
#
# The checkout lives at ~/code/hermes-agent: shallow, blob-filtered, sparse to
# plugin-catalog/ (23 MB rather than 1.5 GB), because this repository only ever
# changes one file in it.

set -e

REPO_DIR="$HOME/code/hermes-agent"
PLUGIN_REPO="a7madgamal/hermes-stmp"
ENTRY="plugin-catalog/stmp.yaml"

[ -d "$REPO_DIR/.git" ] || {
  echo "catalog-pin: $REPO_DIR is not a git checkout." >&2
  echo "catalog-pin: create it with:" >&2
  echo "  git clone --depth 1 --filter=blob:none --sparse https://github.com/NousResearch/hermes-agent.git ~/code/hermes-agent" >&2
  echo "  cd ~/code/hermes-agent && git sparse-checkout set plugin-catalog" >&2
  exit 1
}

# The plugin's own version and main commit. Read from the plugin checkout, so a
# forgotten bump there cannot produce a label that disagrees with the code.
PLUGIN_DIR="$HOME/src/hermes-stmp"
SHA=${1:-}
VERSION=${2:-}

if [ -z "$SHA" ]; then
  [ -d "$PLUGIN_DIR/.git" ] || {
    echo "catalog-pin: $PLUGIN_DIR not found and no sha given." >&2
    exit 1
  }
  SHA=$(git -C "$PLUGIN_DIR" rev-parse main)
  echo "catalog-pin: sha from $PLUGIN_REPO main"
fi

case "$SHA" in
  # A short sha would be silently accepted by GitHub and rejected by the catalog
  # loader (rule 2 wants all 40 characters), so refuse it here instead.
  [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
  *) echo "catalog-pin: '$SHA' is not a full 40-character lowercase sha." >&2; exit 1 ;;
esac

if [ -z "$VERSION" ]; then
  [ -d "$PLUGIN_DIR/.git" ] || {
    echo "catalog-pin: no version given and $PLUGIN_DIR is missing." >&2
    exit 1
  }
  VERSION=$(grep -m1 '^version:' "$PLUGIN_DIR/plugin.yaml" | sed 's/^version:[[:space:]]*//')
  [ -n "$VERSION" ] || { echo "catalog-pin: no version in $PLUGIN_DIR/plugin.yaml" >&2; exit 1; }
fi

cd "$REPO_DIR"

# The pin must exist on the remote. A local-only commit pins nothing installable,
# and the weekly dead-repo job would delist the entry for it.
if ! git ls-remote --exit-code "https://github.com/$PLUGIN_REPO.git" "$SHA" >/dev/null 2>&1; then
  echo "catalog-pin: $SHA is not on $PLUGIN_REPO. Push the plugin first." >&2
  exit 1
fi

git fetch --quiet origin main
BRANCH="catalog/stmp-$VERSION"
git checkout -q -B "$BRANCH" origin/main

sed -i "s|^sha: .*|sha: $SHA|" "$ENTRY"
sed -i "s|^version: .*|version: \"$VERSION\"|" "$ENTRY"

# Two lines, or the branch is not the change this script claims it is.
CHANGED=$(git diff --numstat -- "$ENTRY" | awk '{print $1 + $2}')
[ "$CHANGED" = 2 ] || {
  echo "catalog-pin: expected a 2-line change in $ENTRY, got $CHANGED." >&2
  git diff -- "$ENTRY" >&2
  exit 1
}

git add "$ENTRY"
git -c user.name='Ahmed Gamal' -c user.email='eng.a7mad.gamal@gmail.com' \
  commit -q -m "plugin-catalog: bump stmp to $VERSION" -m "Pins $SHA."

echo "catalog-pin: $BRANCH ready — $VERSION at $SHA"
git show --stat --format='%h %s' HEAD
echo
echo "Next: git push fork $BRANCH:$BRANCH"
echo "      then open the PR against NousResearch/hermes-agent:main"
