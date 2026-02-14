"""Unit tests for Healix Prometheus metrics (push_healix_metrics)."""

import os
import pytest

from healix.prometheus_metrics import (
    push_healix_metrics,
    _get_pushgateway_url,
    _is_configured,
)


class TestGetPushgatewayUrl:
    def test_empty_when_no_env(self):
        with pytest.MonkeyPatch.context() as m:
            m.delenv("HEALIX_PUSHGATEWAY_URL", raising=False)
            m.delenv("PUSHGATEWAY_URL", raising=False)
            assert _get_pushgateway_url() == ""

    def test_strips_http_prefix(self):
        with pytest.MonkeyPatch.context() as m:
            m.setenv("HEALIX_PUSHGATEWAY_URL", "http://localhost:9091")
            assert _get_pushgateway_url() == "localhost:9091"

    def test_strips_https_prefix(self):
        with pytest.MonkeyPatch.context() as m:
            m.setenv("HEALIX_PUSHGATEWAY_URL", "https://push.example.com:9091")
            assert _get_pushgateway_url() == "push.example.com:9091"

    def test_strips_trailing_slash(self):
        with pytest.MonkeyPatch.context() as m:
            m.setenv("HEALIX_PUSHGATEWAY_URL", "http://host:9091/")
            assert _get_pushgateway_url() == "host:9091"

    def test_prefers_healix_env_over_pushgateway(self):
        with pytest.MonkeyPatch.context() as m:
            m.setenv("HEALIX_PUSHGATEWAY_URL", "http://healix:9091")
            m.setenv("PUSHGATEWAY_URL", "http://other:9091")
            assert "healix" in _get_pushgateway_url()


class TestPushHealixMetrics:
    def test_empty_entries_returns_zero_none(self):
        n, err = push_healix_metrics([])
        assert n == 0
        assert err is None

    def test_not_configured_returns_message(self):
        with pytest.MonkeyPatch.context() as m:
            m.delenv("HEALIX_PUSHGATEWAY_URL", raising=False)
            m.delenv("PUSHGATEWAY_URL", raising=False)
            n, err = push_healix_metrics([{"test": "t", "retry_passed": True}])
        assert n == 0
        assert err is not None
        assert "not configured" in err or "HEALIX_PUSHGATEWAY" in err

    def test_push_success_when_configured(self):
        with pytest.MonkeyPatch.context() as m:
            m.setenv("HEALIX_PUSHGATEWAY_URL", "http://localhost:9091")
            try:
                from prometheus_client import push_to_gateway
            except ImportError:
                pytest.skip("prometheus_client not installed")
            with pytest.MonkeyPatch.context() as m2:
                m2.setattr("healix.prometheus_metrics.push_to_gateway", lambda *a, **k: None)
                entries = [
                    {"test": "test_foo", "retry_passed": True},
                    {"test": "test_bar", "nodeid": "file::test_bar", "retry_passed": False},
                    {"test": "test_pending", "retry_passed": None},
                ]
                n, err = push_healix_metrics(entries)
                assert n == 3
                assert err is None

    def test_push_failure_returns_error_message(self):
        with pytest.MonkeyPatch.context() as m:
            m.setenv("HEALIX_PUSHGATEWAY_URL", "http://localhost:9091")
            try:
                import healix.prometheus_metrics as pm
            except ImportError:
                pytest.skip("prometheus_client not installed")
            with pytest.MonkeyPatch.context() as m2:
                m2.setattr(pm, "_PROMETHEUS_AVAILABLE", True)
                m2.setattr(pm, "push_to_gateway", lambda *a, **k: (_ for _ in ()).throw(Exception("connection refused")))
                n, err = push_healix_metrics([{"test": "t", "retry_passed": True}])
                assert n == 0
                assert "connection refused" in err
