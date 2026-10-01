"""Offline axe-core signals; these do not constitute a screen-reader or compliance audit."""

import hashlib
import json

from frictionlab.browser.state import redact
from frictionlab.configuration import ASSET_ROOT, CONFIG_DIRECTORY


async def inspect_accessibility(page):
    manifest = json.loads((CONFIG_DIRECTORY / "axe-manifest.json").read_text(encoding="utf-8"))
    path = (ASSET_ROOT / manifest["script"]).resolve()
    if not path.is_relative_to((ASSET_ROOT / "vendor").resolve()):
        raise ValueError("Accessibility resource must stay inside bundled vendor assets")
    script = path.read_bytes()
    if hashlib.sha256(script).hexdigest() != manifest["script_sha256"]:
        raise ValueError("Local axe-core checksum verification failed")
    await page.evaluate(script.decode("utf-8"))
    result = await page.evaluate("""async () => {
      const result = await axe.run(document, {iframes: false, resultTypes: ['violations', 'incomplete']});
      return {version: axe.version, violations: result.violations, incomplete: result.incomplete};
    }""")
    return json.loads(redact(json.dumps(result)))
