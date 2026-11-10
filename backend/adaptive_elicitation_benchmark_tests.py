"""Focused tests for the deterministic adaptive-elicitation benchmark."""

import unittest

from adaptive_elicitation_benchmark import POLICIES, RESPONSE_SETTINGS, run_benchmark, run_episode


class AdaptiveElicitationBenchmarkTests(unittest.TestCase):
    def test_benchmark_is_reproducible(self):
        self.assertEqual(run_benchmark(seeds_per_world=2), run_benchmark(seeds_per_world=2))

    def test_benchmark_reports_every_policy_and_required_metric(self):
        result = run_benchmark(seeds_per_world=2)

        self.assertEqual(set(result["policy_metrics"]), set(POLICIES))
        self.assertEqual(result["config"]["total_episodes"], len(POLICIES) * len(RESPONSE_SETTINGS) * 4 * 2)
        for metrics in result["policy_metrics"].values():
            for key in (
                "mean_terminal_regret",
                "mean_questions_asked",
                "mean_total_elicitation_cost",
                "premature_stopping_rate",
                "late_stopping_rate",
                "mean_combined_loss",
            ):
                self.assertIn(key, metrics)

    def test_robust_evsi_outperforms_nominal_under_proxy_misspecification(self):
        result = run_benchmark(seeds_per_world=8)
        robust = result["policy_metrics"]["robust_evsi"]["by_response_setting"]["misspecified_proxy"]
        nominal = result["policy_metrics"]["nominal_evsi"]["by_response_setting"]["misspecified_proxy"]

        self.assertLess(robust["mean_terminal_regret"], nominal["mean_terminal_regret"])
        self.assertLess(robust["mean_combined_loss"], nominal["mean_combined_loss"])

    def test_cost_blind_fixed_policy_is_marked_as_late(self):
        episode = run_episode(
            policy="fixed_order",
            true_world_id="world_speed_directional",
            response_setting="calibrated",
            seed=0,
        )

        self.assertEqual(episode["questions_asked"], 4)
        self.assertTrue(episode["late_stopping"])
        self.assertGreater(episode["late_questions"], 0)


if __name__ == "__main__":
    unittest.main()
