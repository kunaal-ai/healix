"""
Optional Prometheus metrics for Healix.

If prometheus_client is installed and a Pushgateway URL is set (HEALIX_PUSHGATEWAY_URL
or PUSHGATEWAY_URL), Healix will push heal metrics so you can see them in Grafana.
Otherwise, all functions no-op.
"""
import os
from datetime import datetime
from typing import Any, List

try:
    from prometheus_client import CollectorRegistry, Counter, Histogram, push_to_gateway
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False


def _get_pushgateway_url() -> str:
    url = (
        os.environ.get("HEALIX_PUSHGATEWAY_URL")
        or os.environ.get("PUSHGATEWAY_URL")
        or ""
    ).strip()
    if not url:
        return ""
    # push_to_gateway expects "host:port"
    if url.startswith("http://"):
        url = url[7:]
    elif url.startswith("https://"):
        url = url[8:]
    url = url.rstrip("/")
    return url


def _is_configured() -> bool:
    return _PROMETHEUS_AVAILABLE and bool(_get_pushgateway_url())


def push_healix_metrics(entries: List[Any]) -> tuple:
    """
    Push Healix heal metrics to Pushgateway if prometheus_client is installed
    and HEALIX_PUSHGATEWAY_URL or PUSHGATEWAY_URL is set.

    entries: list of dicts with keys test, retry_passed (True/False/None), etc.

    Returns:
        (n_pushed, error_message): number of entries pushed, or 0 and None if skipped,
        or 0 and str(err) if push failed (caller can log it).
    """
    if not entries:
        return (0, None)
    if not _is_configured():
        return (0, "not configured (install prometheus-client and set HEALIX_PUSHGATEWAY_URL)")
    url = _get_pushgateway_url()
    if not url:
        return (0, "HEALIX_PUSHGATEWAY_URL / PUSHGATEWAY_URL not set")
    try:
        registry = CollectorRegistry()
        counter = Counter(
            "healix_heals_total",
            "Total locator heals by Healix (pytest plugin)",
            ["test", "retry_passed"],
            registry=registry,
        )
        duration_hist = Histogram(
            "healix_heal_duration_seconds",
            "Time to heal a locator (seconds)",
            ["test"],
            registry=registry,
            buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
        )
        cache_counter = Counter(
            "healix_heal_cache_total",
            "Heals by cache hit or miss",
            ["test", "cache"],
            registry=registry,
        )
        for e in entries:
            test = (e.get("test") or e.get("nodeid") or "unknown")[:128]
            rp = e.get("retry_passed")
            if rp is True:
                label = "true"
            elif rp is False:
                label = "false"
            else:
                label = "pending"
            counter.labels(test=test, retry_passed=label).inc(1)
            dur = e.get("duration_seconds")
            if dur is not None and isinstance(dur, (int, float)):
                duration_hist.labels(test=test).observe(float(dur))
            cache_hit = e.get("cache_hit")
            if cache_hit is True:
                cache_counter.labels(test=test, cache="hit").inc(1)
            elif cache_hit is False:
                cache_counter.labels(test=test, cache="miss").inc(1)
        # Group by run timestamp so each pytest run is a separate series
        grouping_key = {"run": datetime.utcnow().strftime("%Y%m%d%H%M%S")}
        push_to_gateway(url, job="healix", registry=registry, grouping_key=grouping_key)
        return (len(entries), None)
    except Exception as err:
        return (0, str(err))
