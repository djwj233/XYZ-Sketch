import json
import tempfile
import unittest
from pathlib import Path

from figure2 import constants as const
from figure2.plotting import (
    _combined_svg, _curve_segments, _plottable_rows, _svg, render_figure2,
)


class PlottingTests(unittest.TestCase):
    def test_paper_main_renders_without_matplotlib(self):
        algorithms = ("xyz", "minisketch", "external_iblt", "project_iblt", "riblt", "cpisync")
        rows = []
        for algorithm_index, algorithm in enumerate(algorithms):
            for d in (100, 1000):
                rows.append({
                    "algorithm": algorithm, "d": d, "R_w30": 1.0 + algorithm_index / 10,
                    "status": "confirmed", "timing_status": "complete",
                    "successful_datasets": const.TIMING_DATASETS,
                    "update_ns_per_input_conditional_mean": 10.0 + algorithm_index,
                    "update_ci_low": 9.0 + algorithm_index, "update_ci_high": 11.0 + algorithm_index,
                    "decode_ns_per_difference_conditional_mean": 20.0 + algorithm_index,
                    "decode_ci_low": 19.0 + algorithm_index, "decode_ci_high": 21.0 + algorithm_index,
                })
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "run_state.json").write_text('{"status":"complete"}\n')
            (root / "aggregate.json").write_text(json.dumps({"points": rows}))
            manifest = render_figure2(root, None)
            self.assertEqual(12, len(manifest["outputs"]))
            self.assertTrue((root / "figure2a.png").is_file())
            self.assertTrue((root / "figure2-combined.png").is_file())

    def test_combined_figure_has_three_panels_and_one_shared_legend(self):
        rows = [self._row(d) for d in (100, 300)]
        svg = _combined_svg(rows, ("xyz",))
        for title in ("Space overhead", "Update time", "Decode time"):
            self.assertEqual(1, svg.count(">%s</text>" % title))
        self.assertEqual(1, svg.count(">XYZ-Sketch</text>"))
        self.assertIn('width="1500" height="600"', svg)

    def test_nonconfirmed_and_incomplete_points_are_not_plottable(self):
        valid = {
            "algorithm": "xyz", "d": 100, "status": "confirmed", "R_w30": 1.0,
            "timing_status": "complete", "successful_datasets": const.TIMING_DATASETS,
            "update_ns_per_input_conditional_mean": 10.0,
            "update_ci_low": 9.0, "update_ci_high": 11.0,
            "decode_ns_per_difference_conditional_mean": 20.0,
            "decode_ci_low": 19.0, "decode_ci_high": 21.0,
        }
        rows = [valid]
        for d, status in zip((300, 1000, 3000, 10000), (
            "confirmation_failed", "resource_out_of_grid", "timeout", "oom"
        )):
            row = dict(valid, d=d, status=status)
            rows.append(row)
        for d, timing_status in zip((30000, 100000), ("timeout", "oom")):
            row = dict(
                valid, d=d, timing_status=timing_status,
                successful_datasets=const.TIMING_DATASETS - 1,
            )
            rows.append(row)
        self.assertEqual([100, 30000, 100000], [
            row["d"] for row in _plottable_rows(rows, ("xyz",), "R_w30")
        ])
        for field in (
            "update_ns_per_input_conditional_mean",
            "decode_ns_per_difference_conditional_mean",
        ):
            self.assertEqual([100], [
                row["d"] for row in _plottable_rows(rows, ("xyz",), field)
            ])

    @staticmethod
    def _row(
        d, *, status="confirmed", timing_status="complete", successes=const.TIMING_DATASETS
    ):
        return {
            "algorithm": "xyz", "d": d, "status": status, "R_w30": 1.0,
            "timing_status": timing_status, "successful_datasets": successes,
            "update_ns_per_input_conditional_mean": 10.0,
            "update_ci_low": 9.0, "update_ci_high": 11.0,
            "decode_ns_per_difference_conditional_mean": 20.0,
            "decode_ci_low": 19.0, "decode_ci_high": 21.0,
        }

    def test_space_curve_breaks_across_missing_registered_d(self):
        rows = [
            self._row(100), self._row(300, status="confirmation_failed"), self._row(1000),
        ]
        available = _plottable_rows(rows, ("xyz",), "R_w30")
        self.assertEqual([(100,), (1000,)], [
            tuple(row["d"] for row in segment)
            for segment in _curve_segments(available, "xyz")
        ])
        svg = _svg(rows, ("xyz",), "R_w30", "Communication rate R", False)
        self.assertEqual(0, svg.count("<polyline"))
        self.assertEqual(3, svg.count("<circle"))

    def test_timing_curve_breaks_across_incomplete_d(self):
        rows = [
            self._row(100), self._row(
                300, timing_status="timeout", successes=const.TIMING_DATASETS - 1
            ),
            self._row(1000),
        ]
        field = "decode_ns_per_difference_conditional_mean"
        available = _plottable_rows(rows, ("xyz",), field)
        self.assertEqual([(100,), (1000,)], [
            tuple(row["d"] for row in segment)
            for segment in _curve_segments(available, "xyz")
        ])
        svg = _svg(rows, ("xyz",), field, "Conditional decode CPU", True)
        self.assertEqual(0, svg.count("<polyline"))
        self.assertEqual(0, svg.count("<polygon"))

    def test_contiguous_timing_segment_has_one_line_and_no_band(self):
        rows = [self._row(100), self._row(300)]
        svg = _svg(
            rows, ("xyz",), "decode_ns_per_difference_conditional_mean",
            "Conditional decode CPU", True,
        )
        self.assertEqual(1, svg.count("<polyline"))
        self.assertEqual(0, svg.count("<polygon"))

    def test_timing_axes_convert_nanoseconds_to_seconds(self):
        svg = _svg(
            [self._row(100)], ("xyz",), "decode_ns_per_difference_conditional_mean",
            "Decode time per difference (s)", True,
        )
        self.assertIn("Decode time per difference (s)", svg)
        self.assertIn("10^-8", svg)

    def test_singleton_panel_renders_marker_without_division_by_zero(self):
        svg = _svg(
            [self._row(100)], ("xyz",), "R_w30", "Communication rate R", False
        )
        self.assertEqual(0, svg.count("<polyline"))
        self.assertEqual(2, svg.count("<circle"))

    def test_space_axis_expands_for_large_interactive_protocol_overhead(self):
        row = self._row(100)
        row["R_w30"] = 350.0
        svg = _svg([row], ("xyz",), "R_w30", "Space overhead R", True)
        self.assertIn(">100</text>", svg)
        self.assertIn(">200</text>", svg)


if __name__ == "__main__":
    unittest.main()
