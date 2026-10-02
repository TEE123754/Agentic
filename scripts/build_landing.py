"""Stage only the public product information and synthetic sample for Pages."""

import shutil
import sys
from html.parser import HTMLParser
from pathlib import Path

root = Path(__file__).resolve().parents[1]
output = Path(sys.argv[1]).resolve()
output.mkdir(parents=True, exist_ok=True)
source = (root / "site/index.html").read_text(encoding="utf-8")
source = source.replace('href="../examples/', 'href="examples/')
for name in ("IMPLEMENTATION_PLAN.md", "LICENSE", "CONTRIBUTING.md", "SECURITY.md"):
    source = source.replace(
        f'href="../{name}"', f'href="https://github.com/TEE123754/Agentic/blob/main/{name}"'
    )
source = source.replace(
    'href="../docs/', 'href="https://github.com/TEE123754/Agentic/blob/main/docs/'
)
(output / "index.html").write_text(source, encoding="utf-8")
shutil.copytree(
    root / "examples/phase9-static", output / "examples/phase9-static", dirs_exist_ok=True
)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.add(attributes["id"])
        if tag == "a" and attributes.get("href"):
            self.links.append(attributes["href"])


links = Links()
links.feed(source)
for destination in links.links:
    if destination.startswith("#"):
        if destination != "#" and destination[1:] not in links.ids:
            raise ValueError("Landing page has an unresolved section link")
    elif not destination.startswith("https://"):
        path = (output / destination).resolve()
        if not path.is_relative_to(output) or not path.is_file():
            raise ValueError("Landing page has a missing local link")
print("Staged static landing and verified internal links")
