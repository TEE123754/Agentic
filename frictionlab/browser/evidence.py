"""Sanitized saved evidence and screenshot marks drawn outside the tested page."""

from __future__ import annotations

import base64
import html
import json
import math
import struct
from pathlib import Path

from pydantic import Field

from frictionlab.browser.state import SANITIZED_DOM, redact
from frictionlab.contracts.models import Contract, EvidenceRef, Observation


class CoordinateSpace(Contract):
    offset_x: float = Field(allow_inf_nan=False)
    offset_y: float = Field(allow_inf_nan=False)
    css_width: float = Field(gt=0, allow_inf_nan=False)
    css_height: float = Field(gt=0, allow_inf_nan=False)
    pixel_width: int = Field(gt=0)
    pixel_height: int = Field(gt=0)

    def css_to_pixel(self, x, y):
        if not all(math.isfinite(value) for value in (x, y)):
            raise ValueError("Coordinates must be finite")
        return (
            (x - self.offset_x) * self.pixel_width / self.css_width,
            (y - self.offset_y) * self.pixel_height / self.css_height,
        )

    def pixel_to_css(self, x, y):
        if not 0 <= x < self.pixel_width or not 0 <= y < self.pixel_height:
            raise ValueError("Visual coordinates must fall inside the captured viewport")
        return (
            x * self.css_width / self.pixel_width + self.offset_x,
            y * self.css_height / self.pixel_height + self.offset_y,
        )


class BrowserObservation(Observation):
    document_id: str
    mutation_epoch: int = Field(ge=0)
    state_digest: str
    semantic_signature: str
    focus: dict[str, str]
    validation: tuple[str, ...]
    frame_urls: tuple[str, ...]
    coverage_gaps: tuple[str, ...]
    coordinates: CoordinateSpace
    extraction_timing_ms: dict[str, float]


class EvidenceWriter:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=False)

    def json(self, name, value):
        (self.directory / name).write_text(json.dumps(value, indent=2), encoding="utf-8")

    async def capture(self, page, observation):
        prefix = str(observation.id)
        # Masking already conceals input content. Hiding the caret can leave an empty
        # style attribute on an input, so retain its original caret/animation state.
        screenshot = await page.screenshot(mask=[page.locator("input, textarea")], caret="initial")
        (self.directory / f"{prefix}.png").write_bytes(screenshot)
        width, height = struct.unpack(">II", screenshot[16:24])
        coordinates = observation.coordinates.model_copy(
            update={"pixel_width": width, "pixel_height": height}
        )
        observation = observation.model_copy(update={"coordinates": coordinates})
        aria = redact(await page.locator("body").aria_snapshot())
        (self.directory / f"{prefix}.aria.txt").write_text(aria, encoding="utf-8")
        self.json(
            f"{prefix}.dom.json", {"sanitized_dom": redact(await page.evaluate(SANITIZED_DOM))}
        )
        marks = []
        for candidate in observation.candidates:
            x, y, w, h = candidate.bounds
            px, py = coordinates.css_to_pixel(x, y)
            pw = w * width / coordinates.css_width
            ph = h * height / coordinates.css_height
            if px + pw <= 0 or py + ph <= 0 or px >= width or py >= height:
                continue
            marks.append(
                f'<g><rect x="{px:.2f}" y="{py:.2f}" width="{pw:.2f}" height="{ph:.2f}" '
                f'fill="none" stroke="#e02a57" stroke-width="2"/>'
                f'<text x="{max(px, 0):.2f}" y="{max(py + 14, 14):.2f}" '
                f'fill="#b40832" font-size="14">{candidate.candidate_id}</text></g>'
            )
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
            f"<title>{html.escape('Observed interactive candidates')}</title>"
            f'<image width="{width}" height="{height}" href="data:image/png;base64,'
            f'{base64.b64encode(screenshot).decode()}"/>{"".join(marks)}</svg>'
        )
        (self.directory / f"{prefix}.marks.svg").write_text(svg, encoding="utf-8")
        refs = tuple(
            EvidenceRef(path=f"evidence/{prefix}.{suffix}", kind=kind)
            for suffix, kind in (
                ("png", "screenshot"),
                ("marks.svg", "screenshot"),
                ("aria.txt", "aria"),
                ("dom.json", "dom"),
                ("observation.json", "event"),
            )
        )
        observation = observation.model_copy(update={"evidence": refs})
        self.json(f"{prefix}.observation.json", observation.model_dump(mode="json"))
        return observation
