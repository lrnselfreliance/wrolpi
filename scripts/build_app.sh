#!/usr/bin/env bash
# Build the React app ONLY when the built output is missing or stale.
#
# This is the single source of truth for producing app/build/.  It is called
# from three places that must never drift apart:
#   - repair.sh                                      (on-device: first boot, manual repair, install, upgrade)
#   - pi-gen/stage2/04-wrolpi/03-run-chroot.sh       (bakes build/ into the Raspberry Pi image)
#   - debian-live-config/.../9999-wrolpi.hook.chroot (bakes build/ into the Debian Live ISO)
#
# Both image builds run this at image-build time on the (powerful) build host, so
# the shipped image already contains app/build/ with a matching stamp.  On the
# device the same script then finds the stamp current and does nothing -- a weak
# Pi (even 2GB) never has to run the multi-minute webpack build itself.  It only
# rebuilds when the app source actually changed (e.g. an upgrade pulled new code)
# or when build/ is missing/corrupt.
#
# Offline-safe: this only ever runs `npm run build`, which uses the already
# installed node_modules.  It never runs `npm install`, so repair.sh keeps its
# "will not use internet" guarantee.  Installing node_modules stays the caller's
# job (the install/upgrade scripts and image hooks do it before calling here).
set -e

APP_DIR="${1:-/opt/wrolpi/app}"
cd "$APP_DIR"

# Hash of every input that determines the built output.
#
# KEEP IN SYNC: if a build-affecting input is ever added (craco.config.js, an
# .env / .env.production, a new config dir, etc.) add it here.  A missed input
# means a stale build ships silently -- the worst failure mode, because it looks
# like everything worked.
app_build_stamp() {
  {
    sha256sum package.json package-lock.json tsconfig.json
    find src public -type f -exec sha256sum {} +
  } | sort | sha256sum | cut -d' ' -f1
}

# Verify the built output is actually intact, not just present.
#
# A matching stamp only proves the *inputs* are unchanged; it says nothing about
# whether the *outputs* survived.  repair.sh exists precisely to fix a corrupted
# install, so a build/ that still has index.html + a stamp but is missing a JS/CSS
# chunk must NOT be treated as current -- otherwise repair would leave the UI
# broken where the old unconditional build restored it.  Check that every asset
# referenced by build/asset-manifest.json exists on disk.  node is guaranteed
# here: anything that can run `npm run build` can run node.
build_output_intact() {
  [ -f build/asset-manifest.json ] || return 1
  node -e '
    const fs = require("fs");
    let m;
    try { m = JSON.parse(fs.readFileSync("build/asset-manifest.json", "utf8")); }
    catch { process.exit(1); }                       // unparseable manifest -> rebuild
    const missing = Object.values(m.files || {})
      .map(p => "build/" + p.replace(/^\//, ""))
      .filter(p => !fs.existsSync(p));
    process.exit(missing.length ? 1 : 0);
  ' 2>/dev/null
}

need_build=false
if [ ! -f build/index.html ]; then
  echo "app build is missing."
  need_build=true
elif ! build_output_intact; then
  echo "app build is present but incomplete/corrupt (missing referenced assets)."
  need_build=true
elif [ "$(app_build_stamp)" != "$(cat build/.build-stamp 2>/dev/null)" ]; then
  echo "app source changed since the last build."
  need_build=true
fi

if [ "$need_build" = true ]; then
  echo "Building the React production bundle (this can take several minutes)..."
  # GENERATE_SOURCEMAP=false: source maps are a debugging aid for the deployed
  # bundle that WROLPi never ships or uses; skipping them cuts build time and,
  # importantly on low-RAM devices, peak memory.
  GENERATE_SOURCEMAP=false BROWSERSLIST_IGNORE_OLD_DATA=true npm run build
  # Stamp lives inside build/ so it is naturally absent whenever build/ is, and
  # travels with the baked artifact into the image.
  app_build_stamp > build/.build-stamp
  echo "app build complete; wrote build/.build-stamp."
else
  echo "app build is current -- skipping (stamp match)."
fi
