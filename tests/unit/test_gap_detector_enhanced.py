"""Tests for enhanced GapDetector — tool failure detection and summary."""

from unittest.mock import MagicMock
from system.core.supervisor.gap_detector import GapDetector


def _make_history_mock(entries):
    mock = MagicMock()
    mock.get_recent.return_value = entries
    return mock


class TestToolFailureDetection:
    def test_detects_repeated_tool_failures(self):
        entries = [
            {"status": "error", "intent": "read file", "messages": [
                {"role": "tool", "name": "filesystem_read_file", "content": "error: file not found"},
            ]},
            {"status": "error", "intent": "read file", "messages": [
                {"role": "tool", "name": "filesystem_read_file", "content": "error: permission denied"},
            ]},
            {"status": "error", "intent": "read file", "messages": [
                {"role": "tool", "name": "filesystem_read_file", "content": "error: timeout"},
            ]},
        ]
        detector = GapDetector(execution_history=_make_history_mock(entries), threshold=3)
        gaps = detector.scan_now()
        tool_gaps = [g for g in gaps if g.get("type") == "tool_failure"]
        assert len(tool_gaps) >= 1
        assert tool_gaps[0]["tool_id"] == "filesystem_read_file"

    def test_ignores_below_threshold(self):
        entries = [
            {"status": "error", "intent": "x", "messages": [
                {"role": "tool", "name": "some_tool", "content": "error: fail"},
            ]},
        ]
        detector = GapDetector(execution_history=_make_history_mock(entries), threshold=3)
        gaps = detector.scan_now()
        tool_gaps = [g for g in gaps if g.get("type") == "tool_failure"]
        assert len(tool_gaps) == 0

    def test_capability_gaps_still_detected(self):
        entries = [
            {"status": "unknown", "intent": "convert pdf to text", "messages": []},
            {"status": "unknown", "intent": "convert pdf to text", "messages": []},
            {"status": "unknown", "intent": "convert pdf to text", "messages": []},
        ]
        detector = GapDetector(execution_history=_make_history_mock(entries), threshold=3)
        gaps = detector.scan_now()
        cap_gaps = [g for g in gaps if g.get("type") == "capability_gap"]
        assert len(cap_gaps) >= 1


class TestGetSummary:
    def test_empty_summary(self):
        detector = GapDetector(threshold=3)
        summary = detector.get_summary()
        assert summary["total_gaps"] == 0
        assert summary["capability_gaps"] == 0
        assert summary["tool_failure_gaps"] == 0
        assert summary["auto_created"] == 0
        assert summary["top_patterns"] == []

    def test_summary_with_gaps(self):
        entries = [
            {"status": "unknown", "intent": "send email", "messages": []},
            {"status": "unknown", "intent": "send email", "messages": []},
            {"status": "unknown", "intent": "send email", "messages": []},
            {"status": "error", "intent": "x", "messages": [
                {"role": "tool", "name": "bad_tool", "content": "error: broken"},
                {"role": "tool", "name": "bad_tool", "content": "error: broken"},
                {"role": "tool", "name": "bad_tool", "content": "error: broken"},
            ]},
        ]
        detector = GapDetector(execution_history=_make_history_mock(entries), threshold=3)
        detector.scan_now()
        summary = detector.get_summary()
        assert summary["total_gaps"] >= 1
        assert len(summary["top_patterns"]) >= 1


class TestNormalization:
    def test_normalizes_suffixes(self):
        result = GapDetector._normalize("converting files and running tests")
        assert "convert" in result
        assert "runn" in result

    def test_normalizes_numbers(self):
        result = GapDetector._normalize("read file 42 from disk")
        assert "N" in result
        assert "42" not in result

    def test_normalizes_quoted_strings(self):
        result = GapDetector._normalize('read "important.txt" now')
        assert "X" in result
        assert "important" not in result
