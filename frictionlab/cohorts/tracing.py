"""Local OpenTelemetry JSONL export; no collector, network, or raw page content."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult


class LocalSpanExporter(SpanExporter):
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()

    def export(self, spans):
        try:
            with self.lock, self.path.open("a", encoding="utf-8") as stream:
                for span in spans:
                    stream.write(
                        json.dumps(
                            {
                                "trace_id": f"{span.context.trace_id:032x}",
                                "span_id": f"{span.context.span_id:016x}",
                                "parent_id": f"{span.parent.span_id:016x}" if span.parent else None,
                                "name": span.name,
                                "start_time_ns": span.start_time,
                                "end_time_ns": span.end_time,
                                "attributes": dict(span.attributes or {}),
                            },
                            separators=(",", ":"),
                        )
                        + "\n"
                    )
                stream.flush()
                os.fsync(stream.fileno())
            return SpanExportResult.SUCCESS
        except OSError:
            return SpanExportResult.FAILURE

    def shutdown(self):
        return None


def local_tracer(root: Path):
    provider = TracerProvider(resource=Resource.create({"service.name": "frictionlab.cohort"}))
    provider.add_span_processor(SimpleSpanProcessor(LocalSpanExporter(root / "otel-spans.jsonl")))
    return provider, provider.get_tracer("frictionlab.cohorts")
