#!/usr/bin/env python3
"""
Warn the WROLPi maintainer about security problems in the torrent client WROLPis run.

qBittorrent faces the Internet (the VPN forwards a port to it), so a flaw in it, or in libtorrent, needs a WROLPi
release quickly.  Daily (wrolpi-torrent-advisories.timer), this asks OSV.dev, which collects Debian's security tracker,
for the vulnerabilities affecting the exact versions Debian ships, and checks for new upstream releases (often where a
fix appears first).  Anything not seen before is sent to the notify command.

  WROLPI_ADVISORY_NOTIFY  A command which takes a message as its only argument (e.g. a Pushover script).  Unset: print.
  WROLPI_ADVISORY_STATE   Where what has been seen is kept (default /var/lib/wrolpi-torrent-advisories/seen.json).

Run it on a machine with Debian's apt sources for the release WROLPis run (it asks apt which versions Debian ships).
"""
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.request

DEBIAN_RELEASE = '13'
# (Debian binary package apt is asked about, its source package as OSV names it, its upstream GitHub repository, whether
# upstream fixes the series Debian ships: libtorrent maintains 2.0.x beside 2.1.x; qBittorrent fixes only its newest)
PACKAGES = (
    ('qbittorrent-nox', 'qbittorrent', 'qbittorrent/qBittorrent', False),
    ('libtorrent-rasterbar2.0t64', 'libtorrent-rasterbar', 'arvidn/libtorrent', True),
)
STATE = pathlib.Path(os.environ.get('WROLPI_ADVISORY_STATE', '/var/lib/wrolpi-torrent-advisories/seen.json'))
TIMEOUT = 30
USER_AGENT = 'wrolpi-torrent-advisories'


def debian_version(binary_package: str) -> str:
    """The version of a package Debian ships (apt's candidate)."""
    output = subprocess.run(['apt-cache', 'policy', binary_package], capture_output=True, text=True).stdout
    match = re.search(r'Candidate:\s*(\S+)', output)
    if not match or match.group(1) == '(none)':
        raise RuntimeError(f'apt does not know {binary_package}; is this machine on Debian {DEBIAN_RELEASE}?')
    return match.group(1)


def upstream_version(debian_version_: str) -> str:
    """5.1.0-2 -> 5.1.0; 1:2.0.11-1+b1 -> 2.0.11"""
    return debian_version_.split(':')[-1].split('-')[0].split('+')[0]


def fetch_json(url: str, data: dict = None):
    request = urllib.request.Request(url, data=json.dumps(data).encode() if data else None,
                                     headers={'User-Agent': USER_AGENT, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read())


def vulnerabilities(source_package: str, version: str) -> list[dict]:
    reply = fetch_json('https://api.osv.dev/v1/query', {
        'version': version, 'package': {'name': source_package, 'ecosystem': f'Debian:{DEBIAN_RELEASE}'}})
    return reply.get('vulns') or []


def version_key(version: str) -> tuple:
    return tuple(int(i) for i in re.findall(r'\d+', version))


def latest_release(repository: str, series: str = None) -> str | None:
    """The newest upstream release's version (e.g. tag 'release-5.1.2' -> '5.1.2'), in `series` (e.g. '2.0') if given."""
    versions = []
    for release in fetch_json(f'https://api.github.com/repos/{repository}/releases?per_page=50'):
        match = re.search(r'\d+(\.\d+)+', release.get('tag_name') or '')
        if match and not release.get('prerelease') and not release.get('draft'):
            version = match.group(0)
            if series is None or version.startswith(f'{series}.'):
                versions.append(version)
    return max(versions, key=version_key) if versions else None


def findings() -> dict[str, str]:
    """Everything worth knowing now, by a key which stays the same while it is true."""
    found = {}
    for binary_package, source_package, repository, same_series in PACKAGES:
        version = debian_version(binary_package)
        for vulnerability in vulnerabilities(source_package, version):
            summary = vulnerability.get('summary') or vulnerability.get('details', '')[:120] or ''
            aliases = ', '.join(vulnerability.get('aliases') or [])
            found[f'{source_package}:{vulnerability["id"]}'] = \
                f'{source_package} {version} (Debian {DEBIAN_RELEASE}): {vulnerability["id"]}' \
                f'{f" ({aliases})" if aliases else ""} {summary}'.strip()
        series = '.'.join(upstream_version(version).split('.')[:2]) if same_series else None
        latest = latest_release(repository, series)
        if latest and version_key(latest) > version_key(upstream_version(version)):
            found[f'{source_package}:release:{latest}'] = \
                f'{source_package} {latest} is out upstream; Debian {DEBIAN_RELEASE} ships {version}.  Check its ' \
                f'changes for security fixes: https://github.com/{repository}/releases'
    return found


def notify(message: str):
    command = os.environ.get('WROLPI_ADVISORY_NOTIFY')
    if command:
        subprocess.run([command, message], check=False)
    else:
        print(message)


def main() -> int:
    try:
        found = findings()
    except Exception as e:
        notify(f'WROLPi torrent advisory check failed: {e}')
        return 1
    try:
        seen = set(json.loads(STATE.read_text()))
    except (FileNotFoundError, json.JSONDecodeError):
        seen = set()
    new = {key: message for key, message in found.items() if key not in seen}
    if new:
        notify('WROLPi torrent client advisories (qBittorrent faces the Internet through the VPN):\n\n'
               + '\n\n'.join(new.values()))
    else:
        print(f'Nothing new ({len(found)} known).')
    STATE.parent.mkdir(parents=True, exist_ok=True)
    # Forget what is no longer true (e.g. a fixed version shipped), so it is told again if it comes back.
    STATE.write_text(json.dumps(sorted(found)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
