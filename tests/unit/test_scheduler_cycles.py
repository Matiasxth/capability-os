"""Tests for ProactiveScheduler quick/deep cycles and multi-channel delivery."""

import pytest
from unittest.mock import MagicMock, patch
from system.core.scheduler.task_queue import TaskQueue
from system.core.scheduler.proactive_scheduler import ProactiveScheduler


@pytest.fixture
def tmp_queue(tmp_path):
    return TaskQueue(data_path=tmp_path / "queue.json")


@pytest.fixture
def mock_event_bus():
    bus = MagicMock()
    bus.emit = MagicMock()
    return bus


@pytest.fixture
def scheduler(tmp_queue, mock_event_bus):
    return ProactiveScheduler(
        task_queue=tmp_queue,
        event_bus=mock_event_bus,
    )


class TestQuickCycle:
    def test_emits_event(self, scheduler, mock_event_bus):
        scheduler._quick_cycle()
        mock_event_bus.emit.assert_called()
        call_args = mock_event_bus.emit.call_args
        assert call_args[0][0] == "scheduler_cycle"
        assert call_args[0][1]["cycle"] == "quick"

    def test_logs_execution(self, scheduler):
        scheduler._quick_cycle()
        assert len(scheduler.execution_log) >= 1
        assert scheduler.execution_log[-1]["task_id"] == "quick_cycle"

    def test_disables_failing_tasks(self, scheduler, tmp_queue):
        task = tmp_queue.add("test task", schedule="every_hour")
        # Simulate 3 failed runs
        tmp_queue.mark_completed(task["id"], {"status": "error", "error": "fail"})
        tmp_queue.mark_completed(task["id"], {"status": "error", "error": "fail"})
        tmp_queue.mark_completed(task["id"], {"status": "error", "error": "fail"})

        scheduler._quick_cycle()
        updated = tmp_queue.get(task["id"])
        assert updated["enabled"] is False

    def test_prunes_old_logs(self, scheduler):
        scheduler._execution_log = [{"task_id": f"t{i}", "status": "ok"} for i in range(250)]
        scheduler._quick_cycle()
        assert len(scheduler._execution_log) <= 101  # 100 kept + 1 new


class TestDeepCycle:
    def test_emits_summary_event(self, scheduler, mock_event_bus):
        scheduler._deep_cycle()
        mock_event_bus.emit.assert_called()
        call_args = mock_event_bus.emit.call_args
        assert call_args[0][0] == "scheduler_cycle"
        data = call_args[0][1]
        assert data["cycle"] == "deep"
        assert "summary" in data
        assert "total_tasks" in data["summary"]
        assert "recent_success_rate" in data["summary"]

    def test_calculates_success_rate(self, scheduler):
        scheduler._execution_log = [
            {"status": "success"}, {"status": "success"}, {"status": "error"},
        ]
        scheduler._deep_cycle()
        log = scheduler.execution_log[-1]
        assert "66.7%" in log["detail"]

    def test_empty_queue(self, scheduler):
        scheduler._deep_cycle()
        log = scheduler.execution_log[-1]
        assert "tasks=0" in log["detail"]


class TestMultiChannelDelivery:
    def test_send_whatsapp(self, scheduler):
        scheduler._whatsapp = MagicMock()
        scheduler._send_to_channel("whatsapp", "hello")
        scheduler._whatsapp.send_message.assert_called_once_with("owner", "hello")

    def test_send_telegram(self, scheduler):
        scheduler._telegram = MagicMock()
        scheduler._send_to_channel("telegram", "hello")
        scheduler._telegram.send_message.assert_called_once_with("", "hello")

    def test_send_slack(self, scheduler):
        scheduler._slack = MagicMock()
        scheduler._send_to_channel("slack", "hello")
        scheduler._slack.send_message.assert_called_once_with("", "hello")

    def test_send_discord(self, scheduler):
        scheduler._discord = MagicMock()
        scheduler._send_to_channel("discord", "hello")
        scheduler._discord.send_message.assert_called_once_with("", "hello")

    def test_no_connector_no_error(self, scheduler):
        # Should not raise even without connectors
        scheduler._send_to_channel("telegram", "hello")
        scheduler._send_to_channel("slack", "hello")
        scheduler._send_to_channel("discord", "hello")

    def test_truncates_long_messages(self, scheduler):
        scheduler._whatsapp = MagicMock()
        scheduler._send_to_channel("whatsapp", "x" * 5000)
        call_args = scheduler._whatsapp.send_message.call_args
        assert len(call_args[0][1]) <= 4000
