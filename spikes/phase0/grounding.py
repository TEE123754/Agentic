"""Version-pinned browser-use extraction with no BrowserSession or action watchdogs."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, dataclass
from types import SimpleNamespace
from uuid import uuid4

from browser_use.dom.service import DomService
from cdp_use import CDPClient


class ObservationSession:
    """Only the session surface DomService needs for the single top-level fixture."""

    def __init__(self, websocket_url, target_id):
        self.id = "frictionlab-observation-only"
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
            raise ValueError("Observation adapter cannot switch targets or change focus")
        return self.channel

    async def get_all_frames(self):
        raise NotImplementedError("Cross-origin frame extraction is outside this phase spike")

    async def stop(self):
        if self.channel:
            await self.client.send.Target.detachFromTarget(params={"sessionId": self.channel.session_id})
        await self.client.stop()


@dataclass
class Candidate:
    candidate_id: int
    name: str
    role: str
    xpath: str
    backend_node_id: int
    target_id: str


class GroundingAdapter:
    def __init__(self, session):
        self.session = session
        self.service = DomService(session, cross_origin_iframes=False, viewport_threshold=0)
        self.observation_id = None
        self.dom_digest = None
        self.registry = {}

    async def observe(self, page):
        self.observation_id = str(uuid4())
        self.dom_digest = hashlib.sha256((await page.content()).encode()).hexdigest()
        serialized, _, timing = await self.service.get_serialized_dom_tree()
        self.registry = {}
        for candidate_id, node in serialized.selector_map.items():
            if node.tag_name not in {"button", "a", "input", "select", "textarea"}:
                continue
            if not node.is_visible or "disabled" in node.attributes:
                continue
            ax = node.ax_node
            self.registry[candidate_id] = Candidate(
                candidate_id=candidate_id,
                name=str(ax.name or "") if ax else node.llm_representation(),
                role=str(ax.role or node.tag_name) if ax else node.tag_name,
                xpath=node.xpath,
                backend_node_id=node.backend_node_id,
                target_id=node.target_id,
            )
        return {
            "observation_id": self.observation_id,
            "target_id": self.session.agent_focus_target_id,
            "dom_digest": self.dom_digest,
            "url": page.url,
            "semantic_text": serialized.llm_representation(),
            "candidates": [asdict(candidate) for candidate in self.registry.values()],
            "extraction_timing_ms": timing,
        }

    async def execute_click(self, page, observation_id, candidate_id):
        if observation_id != self.observation_id or candidate_id not in self.registry:
            raise ValueError("Stale observation or unknown candidate")
        current_digest = hashlib.sha256((await page.content()).encode()).hexdigest()
        if current_digest != self.dom_digest:
            raise ValueError("Page changed after observation; recapture before acting")
        candidate = self.registry[candidate_id]
        if candidate.target_id != self.session.agent_focus_target_id:
            raise ValueError("Candidate belongs to another browser target")
        target = page.locator("xpath=/" + candidate.xpath)
        if await target.count() != 1 or not await target.is_visible() or not await target.is_enabled():
            raise ValueError("Candidate no longer resolves to one visible enabled element")
        await target.click(timeout=10_000)
        self.observation_id = None
        self.registry = {}
        return asdict(candidate)
