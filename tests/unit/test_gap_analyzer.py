"""
Tests for Componente 1 — GapAnalyzer.

Validates:
  1. Gaps below threshold are not actionable.
  2. Gaps at or above threshold (3+) are actionable.
  3. Gaps grouped correctly by suggested_capability.
  4. Classification integration (type + confidence).
  5. Resolved/closed gaps excluded (only "open" counts).
  6. Custom threshold works.
  7. Unknown capability handled gracefully.
"""
from __future__ import annotations

import unittest

from system.core.self_improvement.gap_analyzer import GapAnalyzer
from system.integrations.classifier import IntegrationClassifier
from system.integrations.detector import IntegrationDetector


class TestGapAnalyzerBasic(unittest.TestCase):

    def test_no_gaps_returns_empty(self):
        detector = IntegrationDetector()
        analyzer = GapAnalyzer(detector)
        self.assertEqual(analyzer.get_actionable_gaps(), [])

    def test_below_threshold_not_actionable(self):
        detector = IntegrationDetector()
        detector.record_gap("send email", suggested_capability="send_email")
        detector.record_gap("send email", suggested_capability="send_email")
        analyzer = GapAnalyzer(detector)
        self.assertEqual(analyzer.get_actionable_gaps(), [])

    def test_at_threshold_becomes_actionable(self):
        detector = IntegrationDetector()
        for _ in range(3):
            detector.record_gap("send email via gmail", suggested_capability="send_email")
        analyzer = GapAnalyzer(detector)
        gaps = analyzer.get_actionable_gaps()
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["capability_id"], "send_email")
        self.assertEqual(gaps[0]["frequency"], 3)

    def test_above_threshold_still_actionable(self):
        detector = IntegrationDetector()
        for _ in range(7):
            detector.record_gap("post to slack api", suggested_capability="post_slack_message")
        analyzer = GapAnalyzer(detector)
        gaps = analyzer.get_actionable_gaps()
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["frequency"], 7)

    def test_multiple_capabilities_grouped(self):
        detector = IntegrationDetector()
        for _ in range(3):
            detector.record_gap("send email", suggested_capability="send_email")
        for _ in range(4):
            detector.record_gap("read spreadsheet csv file", suggested_capability="read_spreadsheet")
        detector.record_gap("other thing", suggested_capability="other_cap")
        analyzer = GapAnalyzer(detector)
        gaps = analyzer.get_actionable_gaps()
        ids = {g["capability_id"] for g in gaps}
        self.assertEqual(ids, {"send_email", "read_spreadsheet"})
        self.assertNotIn("other_cap", ids)


class TestGapAnalyzerClassification(unittest.TestCase):

    def test_classification_type_included(self):
        detector = IntegrationDetector()
        for _ in range(3):
            detector.record_gap("open website in browser page", suggested_capability="open_website")
        analyzer = GapAnalyzer(detector)
        gaps = analyzer.get_actionable_gaps()
        self.assertEqual(gaps[0]["suggested_integration_type"], "web_app")

    def test_classification_confidence_included(self):
        detector = IntegrationDetector()
        for _ in range(3):
            detector.record_gap("call REST API endpoint JSON", suggested_capability="call_api")
        analyzer = GapAnalyzer(detector)
        gaps = analyzer.get_actionable_gaps()
        self.assertIn(gaps[0]["classification_confidence"], {"high", "medium", "low"})

    def test_sample_intent_from_first_gap(self):
        detector = IntegrationDetector()
        detector.record_gap("first intent", suggested_capability="my_cap")
        detector.record_gap("second intent", suggested_capability="my_cap")
        detector.record_gap("third intent", suggested_capability="my_cap")
        analyzer = GapAnalyzer(detector)
        gaps = analyzer.get_actionable_gaps()
        self.assertEqual(gaps[0]["sample_intent"], "first intent")


class TestGapAnalyzerFiltering(unittest.TestCase):

    def test_resolved_gaps_excluded(self):
        detector = IntegrationDetector()
        g1 = detector.record_gap("intent a", suggested_capability="cap_a")
        detector.record_gap("intent a", suggested_capability="cap_a")
        detector.record_gap("intent a", suggested_capability="cap_a")
        detector.resolve_gap(g1["id"], "some_integration")
        analyzer = GapAnalyzer(detector)
        gaps = analyzer.get_actionable_gaps()
        # One resolved → only 2 open → below threshold
        self.assertEqual(len(gaps), 0)

    def test_closed_gaps_excluded(self):
        detector = IntegrationDetector()
        g1 = detector.record_gap("intent b", suggested_capability="cap_b")
        detector.record_gap("intent b", suggested_capability="cap_b")
        detector.record_gap("intent b", suggested_capability="cap_b")
        detector.close_gap(g1["id"], "not needed")
        analyzer = GapAnalyzer(detector)
        gaps = analyzer.get_actionable_gaps()
        self.assertEqual(len(gaps), 0)


class TestGapAnalyzerCustomThreshold(unittest.TestCase):

    def test_custom_threshold_of_1(self):
        detector = IntegrationDetector()
        detector.record_gap("single gap", suggested_capability="rare_cap")
        analyzer = GapAnalyzer(detector, threshold=1)
        gaps = analyzer.get_actionable_gaps()
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["capability_id"], "rare_cap")

    def test_custom_threshold_of_5(self):
        detector = IntegrationDetector()
        for _ in range(4):
            detector.record_gap("x", suggested_capability="high_cap")
        analyzer = GapAnalyzer(detector, threshold=5)
        self.assertEqual(len(analyzer.get_actionable_gaps()), 0)

        detector.record_gap("x", suggested_capability="high_cap")
        self.assertEqual(len(analyzer.get_actionable_gaps()), 1)

    def test_threshold_property(self):
        analyzer = GapAnalyzer(IntegrationDetector(), threshold=7)
        self.assertEqual(analyzer.threshold, 7)


class TestGapAnalyzerEdgeCases(unittest.TestCase):

    def test_none_suggested_capability_grouped_as_unknown(self):
        detector = IntegrationDetector()
        for _ in range(3):
            detector.record_gap("mystery request", suggested_capability=None)
        analyzer = GapAnalyzer(detector)
        gaps = analyzer.get_actionable_gaps()
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["capability_id"], "unknown")

    def test_gap_ids_included(self):
        detector = IntegrationDetector()
        recorded_ids = []
        for _ in range(3):
            g = detector.record_gap("repeated intent", suggested_capability="repeated_cap")
            recorded_ids.append(g["id"])
        analyzer = GapAnalyzer(detector)
        gaps = analyzer.get_actionable_gaps()
        self.assertEqual(set(gaps[0]["gap_ids"]), set(recorded_ids))

    def test_mixed_capabilities_some_actionable(self):
        detector = IntegrationDetector()
        for _ in range(3):
            detector.record_gap("a", suggested_capability="actionable_cap")
        for _ in range(2):
            detector.record_gap("b", suggested_capability="not_yet_cap")
        analyzer = GapAnalyzer(detector)
        gaps = analyzer.get_actionable_gaps()
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["capability_id"], "actionable_cap")


if __name__ == "__main__":
    unittest.main()
