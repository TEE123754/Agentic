"""Deterministic checks on a snapshot; active application behavior is never inferred."""

from html.parser import HTMLParser
from urllib.parse import urlsplit

from frictionlab.assessment.models import Check


class Facts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.labels = set()
        self.title = ""
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append((tag, a))
        if tag == "label" and a.get("for"):
            self.labels.add(a["for"])
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


def catalog(request, snapshot=None):
    result = []

    def add(
        id,
        category,
        title,
        passed=None,
        evidence="",
        recommendation="",
        reason="",
        severity="medium",
    ):
        if category not in request.categories:
            return
        status = "skipped" if passed is None else ("passed" if passed else "failed")
        result.append(
            Check(
                id=id,
                category=category,
                title=title,
                status=status,
                severity=severity if status == "failed" else None,
                confidence=0.75 if passed is not None else 0,
                detail=reason
                or (
                    "Observed in the supplied static snapshot."
                    if snapshot
                    else "URL syntax inspection only."
                ),
                evidence=[evidence] if evidence else [],
                reproduction=["Use the same uploaded snapshot and inspect the document structure."]
                if snapshot
                else ["Inspect the submitted URL scheme without visiting it."],
                recommendation=recommendation,
            )
        )

    parts = urlsplit(request.url)
    add(
        "security.scheme",
        "security",
        "HTTPS URL scheme",
        parts.scheme == "https",
        f"Submitted scheme: {parts.scheme}",
        "Use HTTPS with a valid certificate. A URL scheme does not verify TLS or server configuration.",
        severity="high",
    )
    f = Facts()
    if snapshot:
        f.feed(snapshot.document)
    available = snapshot is not None
    tags = f.tags

    def condition(value):
        return bool(value) if available else None

    add(
        "usability.title",
        "usability",
        "Meaningful page title",
        condition(len(f.title.strip()) >= 3),
        f"Title character count: {len(f.title.strip())}" if available else "",
        "Provide a concise page title describing its purpose.",
    )
    add(
        "usability.heading",
        "usability",
        "Primary heading",
        condition(any(t == "h1" for t, a in tags)),
        f"H1 count: {sum(t == 'h1' for t, a in tags)}" if available else "",
        "Use a clear primary heading and logical content hierarchy.",
    )
    images = [a for t, a in tags if t == "img"]
    missing = sum("alt" not in a for a in images)
    add(
        "accessibility.alt",
        "accessibility",
        "Image alternative attributes",
        condition(missing == 0),
        f"Images missing alt attributes: {missing}" if available else "",
        "Give meaningful images descriptive alt text and decorative images empty alt text.",
    )
    controls = [
        a
        for t, a in tags
        if t in {"input", "textarea", "select"}
        and a.get("type") not in {"hidden", "submit", "button", "reset"}
    ]
    unlabeled = sum(
        not (a.get("aria-label") or a.get("aria-labelledby") or a.get("id") in f.labels)
        for a in controls
    )
    add(
        "accessibility.labels",
        "accessibility",
        "Form control label declarations",
        condition(unlabeled == 0),
        f"Controls without declared label references: {unlabeled}" if available else "",
        "Associate visible labels with controls; verify accessible names and instructions in the working application.",
    )
    viewport = any(
        t == "meta"
        and a.get("name", "").lower() == "viewport"
        and "width=device-width" in a.get("content", "").replace(" ", "")
        for t, a in tags
    )
    add(
        "responsiveness.viewport",
        "responsiveness",
        "Responsive viewport declaration",
        condition(viewport),
        f"Device-width viewport declaration: {viewport}" if available else "",
        "Include a device-width viewport and fluid layouts.",
    )
    empty_links = sum(t == "a" and a.get("href", "").strip() in {"", "#"} for t, a in tags)
    add(
        "functionality.links",
        "functionality",
        "Declared link destinations",
        condition(empty_links == 0),
        f"Links with empty or placeholder destinations: {empty_links}" if available else "",
        "Provide real destinations or use buttons for actions. JavaScript-driven links require an isolated replica to evaluate.",
        severity="low",
    )
    size = len(snapshot.document.encode()) if available else 0
    add(
        "performance.document",
        "performance",
        "HTML document size budget",
        condition(size <= 200_000),
        f"HTML bytes: {size}; heuristic budget: 200000" if available else "",
        "Reduce excessive document markup and measure real loading performance on a verified replica.",
        severity="low",
    )
    for header, title, advice in (
        (
            "content-security-policy",
            "Server CSP header",
            "Define a restrictive Content-Security-Policy suitable for your application.",
        ),
        (
            "x-content-type-options",
            "MIME sniffing protection",
            "Set X-Content-Type-Options: nosniff.",
        ),
    ):
        captured = snapshot and request.mode == "capture"
        value = snapshot.headers.get(header, "") if captured else ""
        valid = bool(value) if header == "content-security-policy" else value.lower() == "nosniff"
        add(
            "security." + header,
            "security",
            title,
            valid if captured else None,
            f"Captured header present: {bool(value)}" if captured else "",
            advice,
            reason="Only original response headers are evaluated; uploaded documents cannot prove server policy.",
        )
    for id, cat, title, reason in (
        (
            "functionality.journeys",
            "functionality",
            "Interactive flows and integrations",
            "Requires a verified isolated local/staging backend with sandboxed accounts, payments, messaging and third-party services.",
        ),
        (
            "usability.personas",
            "usability",
            "Cognitive friction and abandonment",
            "Static documents cannot demonstrate user journeys or human churn. Use the existing owned-fixture cohort CLI or onboard a verified replica.",
        ),
        (
            "accessibility.assistive",
            "accessibility",
            "Screen reader and keyboard flows",
            "Requires an interactive isolated application and assistive/manual review; automated checks do not establish WCAG compliance.",
        ),
        (
            "performance.vitals",
            "performance",
            "Loading performance and Core Web Vitals",
            "Offline snapshot timing does not represent real server/network behavior. Requires a verified replica and a controlled benchmark.",
        ),
        (
            "security.active",
            "security",
            "Authentication, authorization and exploit tests",
            "Requires source review, explicit authorization and an isolated environment. No intrusive security probes run against the submitted URL.",
        ),
    ):
        add(id, cat, title, reason=reason)
    if not snapshot:
        for item in result:
            if item.status == "skipped" and not item.detail.startswith("Requires"):
                item.detail = (
                    "No document fetched. Supply an offline HTML/ZIP snapshot for structural checks. "
                    + item.detail
                )
    return result
