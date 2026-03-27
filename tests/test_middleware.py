"""Unit tests for middleware layer."""
import pytest
import time

from src.agent.middleware_pkg.base import with_middleware
from src.agent.middleware_pkg.logging_mw import logging_middleware
from src.agent.middleware_pkg.error_mw import error_handling_middleware
from src.agent.middleware_pkg.metrics_mw import metrics_middleware, get_node_metrics, reset_metrics


# --- Middleware Base Tests ---

class TestWithMiddleware:
    @pytest.mark.asyncio
    async def test_middleware_wraps_node(self):
        @with_middleware(logging_middleware)
        async def my_node(state):
            return {"result": "ok"}

        result = await my_node({"input": "test"})
        assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_middleware_preserves_function_name(self):
        @with_middleware(logging_middleware)
        async def my_node(state):
            return {}

        assert my_node.__name__ == "my_node"

    @pytest.mark.asyncio
    async def test_middleware_propagates_error(self):
        @with_middleware(logging_middleware, error_handling_middleware)
        async def failing_node(state):
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            await failing_node({})

    @pytest.mark.asyncio
    async def test_multiple_middleware_chain(self):
        call_order = []

        class mw1:
            @staticmethod
            async def before(ctx):
                call_order.append("mw1_before")
            @staticmethod
            async def after(ctx):
                call_order.append("mw1_after")

        class mw2:
            @staticmethod
            async def before(ctx):
                call_order.append("mw2_before")
            @staticmethod
            async def after(ctx):
                call_order.append("mw2_after")

        @with_middleware(mw1, mw2)
        async def my_node(state):
            call_order.append("node")
            return {}

        await my_node({})
        assert call_order == ["mw1_before", "mw2_before", "node", "mw2_after", "mw1_after"]


# --- Logging Middleware Tests ---

class TestLoggingMiddleware:
    @pytest.mark.asyncio
    async def test_logging_before(self):
        context = {"node_name": "test_node", "start_time": time.monotonic()}
        await logging_middleware.before(context)
        # Should not raise

    @pytest.mark.asyncio
    async def test_logging_after(self):
        context = {"node_name": "test_node", "start_time": time.monotonic() - 1.5}
        await logging_middleware.after(context)

    @pytest.mark.asyncio
    async def test_logging_on_error(self):
        context = {
            "node_name": "test_node",
            "start_time": time.monotonic(),
            "error": ValueError("test"),
        }
        result = await logging_middleware.on_error(context)
        assert result is None  # Should not recover


# --- Error Handling Middleware Tests ---

class TestErrorHandlingMiddleware:
    @pytest.mark.asyncio
    async def test_classify_transient(self):
        context = {
            "node_name": "test",
            "error": ConnectionError("refused"),
        }
        result = await error_handling_middleware.on_error(context)
        assert result is None  # Propagate

    @pytest.mark.asyncio
    async def test_classify_permanent(self):
        context = {
            "node_name": "test",
            "error": ValueError("bad value"),
        }
        result = await error_handling_middleware.on_error(context)
        assert result is None


# --- Metrics Middleware Tests ---

class TestMetricsMiddleware:
    def setup_method(self):
        reset_metrics()

    @pytest.mark.asyncio
    async def test_metrics_success(self):
        context = {"node_name": "test_node", "start_time": time.monotonic() - 0.5}
        await metrics_middleware.before(context)
        await metrics_middleware.after(context)

        metrics = get_node_metrics()
        assert metrics["test_node"]["total_calls"] == 1
        assert metrics["test_node"]["success_count"] == 1
        assert metrics["test_node"]["failure_count"] == 0
        assert metrics["test_node"]["total_duration_s"] > 0

    @pytest.mark.asyncio
    async def test_metrics_failure(self):
        context = {
            "node_name": "fail_node",
            "start_time": time.monotonic(),
            "error": RuntimeError("boom"),
        }
        await metrics_middleware.before(context)
        await metrics_middleware.on_error(context)

        metrics = get_node_metrics()
        assert metrics["fail_node"]["total_calls"] == 1
        assert metrics["fail_node"]["failure_count"] == 1
        assert metrics["fail_node"]["last_error"] == "boom"

    @pytest.mark.asyncio
    async def test_metrics_multiple_calls(self):
        for i in range(3):
            ctx = {"node_name": "multi", "start_time": time.monotonic()}
            await metrics_middleware.before(ctx)
            await metrics_middleware.after(ctx)

        metrics = get_node_metrics()
        assert metrics["multi"]["total_calls"] == 3
        assert metrics["multi"]["success_count"] == 3

    def test_reset_metrics(self):
        _metrics = get_node_metrics()
        reset_metrics()
        assert get_node_metrics() == {}

    @pytest.mark.asyncio
    async def test_full_middleware_with_metrics(self):
        reset_metrics()

        @with_middleware(logging_middleware, metrics_middleware)
        async def tracked_node(state):
            return {"done": True}

        await tracked_node({"input": "test"})
        metrics = get_node_metrics()
        assert metrics["tracked_node"]["total_calls"] == 1
        assert metrics["tracked_node"]["success_count"] == 1
