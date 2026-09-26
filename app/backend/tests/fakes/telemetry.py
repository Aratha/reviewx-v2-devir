"""In-memory OpenTelemetry providers for asserting the exact signals of app.core.telemetry."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.core import telemetry

Labels = dict[str, Any]


class TelemetryCapture:
    """Finished spans and cumulative metric points of everything recorded since installation."""

    def __init__(self) -> None:
        self.exporter = InMemorySpanExporter()
        self.tracer_provider = TracerProvider()
        self.tracer_provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.reader = InMemoryMetricReader()
        self.meter_provider = MeterProvider(metric_readers=[self.reader])
        self._series: dict[tuple[str, tuple[tuple[str, Any], ...]], Any] = {}

    def spans(self, name: str | None = None) -> list[ReadableSpan]:
        finished = list(self.exporter.get_finished_spans())
        return [span for span in finished if name is None or span.name == name]

    def _collect(self) -> dict[tuple[str, tuple[tuple[str, Any], ...]], Any]:
        """Latest point per series; a gauge reports only after a change, so points are kept."""

        data = self.reader.get_metrics_data()
        for resource_metrics in data.resource_metrics if data is not None else ():
            for scope_metrics in resource_metrics.scope_metrics:
                for metric in scope_metrics.metrics:
                    for point in metric.data.data_points:
                        labels = tuple(sorted((point.attributes or {}).items()))
                        self._series[(metric.name, labels)] = getattr(point, "value", point)
        return self._series

    def metric_names(self) -> set[str]:
        return {name for name, _ in self._collect()}

    def points(self, name: str) -> list[tuple[Labels, Any]]:
        """(labels, value) per series; the value is the sum, gauge value or histogram point."""

        return [
            (dict(labels), value)
            for (series, labels), value in self._collect().items()
            if series == name
        ]

    def value(self, name: str, **labels: Any) -> Any:
        """The single series whose labels are exactly ``labels``; 0 when it was never recorded."""

        matching = [value for attributes, value in self.points(name) if attributes == labels]
        assert len(matching) <= 1
        return matching[0] if matching else 0

    def everything(self) -> str:
        """Every span name, attribute, event, status text and metric label, for leak checks."""

        parts: list[str] = []
        for span in self.spans():
            parts.append(span.name)
            parts.append(str(span.status.description or ""))
            parts.extend(f"{key}={value}" for key, value in (span.attributes or {}).items())
            for span_event in span.events:
                parts.append(span_event.name)
                parts.extend(f"{k}={v}" for k, v in (span_event.attributes or {}).items())
        for name, labels in self._collect():
            parts.append(name)
            parts.extend(f"{key}={value}" for key, value in labels)
        return "\n".join(parts)


@contextmanager
def captured_telemetry() -> Iterator[TelemetryCapture]:
    capture = TelemetryCapture()
    telemetry.install(capture.tracer_provider, capture.meter_provider)
    try:
        yield capture
    finally:
        telemetry.uninstall()
        capture.tracer_provider.shutdown()
        capture.meter_provider.shutdown()
