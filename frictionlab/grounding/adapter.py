"""Interactive candidates come from the exact browser target controlled by Playwright."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from types import SimpleNamespace


class ObservationSession:
    def __init__(self, websocket_url, target_id):
        os.environ["ANONYMIZED_TELEMETRY"] = "false"
        os.environ["BROWSER_USE_CLOUD_SYNC"] = "false"
        os.environ["BROWSER_USE_LOGGING_LEVEL"] = "error"
        from cdp_use import CDPClient

        self.id = "frictionlab-read-only-dom"
        self.agent_focus_target_id = target_id
        self.client = CDPClient(websocket_url)
        self.channel = None
        self.logger = logging.getLogger("frictionlab.grounding")

    async def start(self):
        await self.client.start()
        attached = await self.client.send.Target.attachToTarget(
            params={"targetId": self.agent_focus_target_id, "flatten": True}
        )
        self.channel = SimpleNamespace(cdp_client=self.client, session_id=attached["sessionId"])

    async def get_or_create_cdp_session(self, target_id, focus=False):
        if target_id != self.agent_focus_target_id or focus:
            raise ValueError("Read-only grounding cannot switch browser targets or focus")
        return self.channel

    async def get_all_frames(self):
        # Frame presence is captured separately; no claim of actionable iframe grounding.
        return {}

    async def stop(self):
        try:
            if self.channel:
                await self.client.send.Target.detachFromTarget(
                    params={"sessionId": self.channel.session_id}
                )
        finally:
            await self.client.stop()


@dataclass(frozen=True)
class GroundedNode:
    candidate_id: int
    name: str
    role: str
    xpath: str
    backend_node_id: int
    target_id: str
    bounds: tuple[float, float, float, float]
    input_type: str


class GroundingAdapter:
    def __init__(self, session):
        from browser_use.dom.service import DomService

        self.session = session
        self.service = DomService(session, cross_origin_iframes=False, viewport_threshold=0)

    async def extract(self, page):
        serialized, _, timing = await self.service.get_serialized_dom_tree()
        nodes = {}
        for candidate_id, node in serialized.selector_map.items():
            if candidate_id < 1 or node.target_id != self.session.agent_focus_target_id:
                continue
            if node.tag_name not in {"button", "a", "input", "textarea"}:
                continue
            if not node.is_visible or "disabled" in node.attributes:
                continue
            if node.attributes.get("id") in {"reset", "switch-variant", "variant"}:
                continue
            if (
                node.shadow_root_type
                or node.tag_name == "input"
                and node.attributes.get("type") == "password"
            ):
                continue
            xpath = "/" + node.xpath
            locator = page.locator("xpath=" + xpath)
            if (
                await locator.count() != 1
                or not await locator.is_visible()
                or not await locator.is_enabled()
            ):
                continue
            box = await locator.bounding_box()
            if not box:
                continue
            ax = node.ax_node
            nodes[candidate_id] = GroundedNode(
                candidate_id=candidate_id,
                name=str(ax.name or "") if ax else "",
                role=str(ax.role or node.tag_name) if ax else node.tag_name,
                xpath=xpath,
                backend_node_id=node.backend_node_id,
                target_id=node.target_id,
                bounds=(box["x"], box["y"], box["width"], box["height"]),
                input_type=node.attributes.get("type", "text"),
            )
        return nodes, timing
