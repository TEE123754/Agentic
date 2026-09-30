"""Install the verified, pinned axe-core distribution from the local npm download."""

import hashlib
import json
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "4.13.0"
ARCHIVE_SHA1 = "f868ecb1bd61d982321760e51d841ab497ab86d0"


def main():
    archive = ROOT / ".cache" / f"axe-core-{VERSION}.tgz"
    if hashlib.sha1(archive.read_bytes(), usedforsecurity=False).hexdigest() != ARCHIVE_SHA1:
        raise ValueError("axe-core archive differs from the pinned npm distribution checksum")
    destination = ROOT / "vendor" / "axe-core"
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as bundle:
        for filename in ("axe.min.js", "LICENSE", "LICENSE-3RD-PARTY.txt"):
            member = bundle.getmember(f"package/{filename}")
            if not member.isfile() or member.size > 2 * 1024 * 1024:
                raise ValueError("Unexpected axe-core distribution member")
            with bundle.extractfile(member) as resource:
                (destination / filename).write_bytes(resource.read())
    manifest = {
        "repository": "https://github.com/dequelabs/axe-core",
        "version": VERSION,
        "release": f"https://github.com/dequelabs/axe-core/releases/tag/v{VERSION}",
        "distribution": f"https://registry.npmjs.org/axe-core/-/axe-core-{VERSION}.tgz",
        "license": "MPL-2.0",
        "archive_sha1": ARCHIVE_SHA1,
        "script": "vendor/axe-core/axe.min.js",
        "script_sha256": hashlib.sha256((destination / "axe.min.js").read_bytes()).hexdigest(),
        "offline_runtime": True,
    }
    (ROOT / "configs" / "axe-manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
