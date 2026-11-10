"""Deterministic benchmark for adaptive-elicitation question policies.

The hidden user world and response process are deliberately separate from the
policy's likelihood model.  This makes likelihood misspecification observable
without using an LLM or training a policy.  Run from the repository root with:

    python backend/adaptive_elicitation_benchmark.py

The default JSON output is written outside application data directories to
``artifacts/adaptive_elicitation/benchmark_summary.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Literal, Optional

from adaptive_elicitation import (
    AdaptiveElicitationQuestion,
    AdaptiveElicitationSession,
    AnswerAdaptiveElicitationRequest,
    answer_question,
    bayes_risk,
    create_session,
)


PolicyName = Literal["random", "fixed_order", "greedy_eig", "nominal_evsi", "robust_evsi"]
ResponseSetting = Literal["calibrated", "noisy", "misspecified_proxy"]

POLICIES: List[PolicyName] = ["random", "fixed_order", "greedy_eig", "nominal_evsi", "robust_evsi"]
RESPONSE_SETTINGS: List[ResponseSetting] = ["calibrated", "noisy", "misspecified_proxy"]
FIXED_ORDER = ["objective_proxy", "objective_case", "evidence_proxy", "evidence_case"]


def benchmark_payload() -> Dict[str, Any]:
    variables = [
        {
            "id": "objective",
            "label": "Primary objective",
            "hypotheses": [
                {"id": "speed", "proposition": "Speed matters most", "probability": 0.5},
                {"id": "quality", "proposition": "Quality matters most", "probability": 0.5},
            ],
        },
        {
            "id": "evidence",
            "label": "Evidence threshold",
            "hypotheses": [
                {"id": "directional", "proposition": "Directional evidence is sufficient", "probability": 0.5},
                {"id": "strict", "proposition": "Reproducible evidence is required", "probability": 0.5},
            ],
        },
    ]
    worlds = []
    for objective in ("speed", "quality"):
        for evidence in ("directional", "strict"):
            worlds.append(
                {
                    "id": f"world_{objective}_{evidence}",
                    "label": f"{objective} with {evidence} evidence",
                    "probability": 0.25,
                    "hypothesis_assignments": {"objective": objective, "evidence": evidence},
                }
            )
    actions = []
    for intended in worlds:
        intended_assignments = intended["hypothesis_assignments"]
        actions.append(
            {
                "id": f"choose_{intended['id'].removeprefix('world_')}",
                "label": f"Act for {intended['label']}",
                "loss_by_world": {
                    actual["id"]: sum(
                        intended_assignments[variable_id] != actual["hypothesis_assignments"][variable_id]
                        for variable_id in ("objective", "evidence")
                    )
                    / 2.0
                    for actual in worlds
                },
            }
        )

    def binary_question(
        *,
        question_id: str,
        target: str,
        left: str,
        right: str,
        accuracy: float,
        cost: float,
        ambiguous_alternative: bool,
    ) -> Dict[str, Any]:
        question: Dict[str, Any] = {
            "id": question_id,
            "target_variable_id": target,
            "question": f"Which is closer to your view of {target}?",
            "why_it_matters": f"This distinguishes the two {target} states.",
            "answer_options": [
                {"id": left, "label": left.replace("_", " ").title()},
                {"id": right, "label": right.replace("_", " ").title()},
            ],
            "predictions": [
                {"hypothesis_id": left, "option_probabilities": {left: accuracy, right: 1.0 - accuracy}},
                {"hypothesis_id": right, "option_probabilities": {left: 1.0 - accuracy, right: accuracy}},
            ],
            "answerability": 1.0,
            "decision_relevance": 1.0,
            "estimated_effort_seconds": 10.0,
            "question_cost": cost,
        }
        if ambiguous_alternative:
            question["likelihood_models"] = [
                {
                    "id": "uninformative_alternative",
                    "weight": 1.0,
                    "predictions": [
                        {"hypothesis_id": left, "option_probabilities": {left: 0.5, right: 0.5}},
                        {"hypothesis_id": right, "option_probabilities": {left: 0.5, right: 0.5}},
                    ],
                }
            ]
        else:
            alternative_accuracy = max(accuracy - 0.1, 0.5)
            question["likelihood_models"] = [
                {
                    "id": "moderately_noisy_alternative",
                    "weight": 1.0,
                    "predictions": [
                        {
                            "hypothesis_id": left,
                            "option_probabilities": {left: alternative_accuracy, right: 1.0 - alternative_accuracy},
                        },
                        {
                            "hypothesis_id": right,
                            "option_probabilities": {left: 1.0 - alternative_accuracy, right: alternative_accuracy},
                        },
                    ],
                }
            ]
        return question

    return {
        "belief_variables": variables,
        "decision_worlds": worlds,
        "decision_actions": actions,
        "candidate_questions": [
            binary_question(
                question_id="objective_proxy",
                target="objective",
                left="speed",
                right="quality",
                accuracy=0.98,
                cost=0.05,
                ambiguous_alternative=True,
            ),
            binary_question(
                question_id="objective_case",
                target="objective",
                left="speed",
                right="quality",
                accuracy=0.85,
                cost=0.08,
                ambiguous_alternative=False,
            ),
            binary_question(
                question_id="evidence_proxy",
                target="evidence",
                left="directional",
                right="strict",
                accuracy=0.98,
                cost=0.05,
                ambiguous_alternative=True,
            ),
            binary_question(
                question_id="evidence_case",
                target="evidence",
                left="directional",
                right="strict",
                accuracy=0.85,
                cost=0.08,
                ambiguous_alternative=False,
            ),
        ],
    }


def create_benchmark_session() -> AdaptiveElicitationSession:
    return create_session(
        workspace_key="adaptive-elicitation-benchmark",
        context_digest="two-factor deterministic benchmark",
        raw_payload=benchmark_payload(),
        generation_source="fallback",
        max_questions=len(FIXED_ORDER),
        min_information_gain=0.0,
        min_geodesic_gain=0.0,
        max_normalized_uncertainty_for_stop=1.0,
        robust_quantile=0.1,
        cost_per_second=0.0,
        min_net_value=0.0,
    )


def _available_questions(session: AdaptiveElicitationSession) -> List[AdaptiveElicitationQuestion]:
    return [question for question in session.candidate_questions if question.status == "candidate"]


def _choose_question(
    policy: PolicyName,
    session: AdaptiveElicitationSession,
    rng: random.Random,
) -> Optional[AdaptiveElicitationQuestion]:
    available = _available_questions(session)
    if not available:
        return None
    if policy == "random":
        return rng.choice(available)
    if policy == "fixed_order":
        order = {question_id: index for index, question_id in enumerate(FIXED_ORDER)}
        return min(available, key=lambda question: order.get(question.id, len(order)))
    if policy == "greedy_eig":
        selected = max(available, key=lambda question: (question.expected_information_gain, question.id))
        return selected if selected.expected_information_gain > 1e-12 else None
    if policy == "nominal_evsi":
        selected = max(
            available,
            key=lambda question: (
                question.expected_bayes_risk_reduction - float(question.question_cost or 0.0),
                question.id,
            ),
        )
        nominal_net = selected.expected_bayes_risk_reduction - float(selected.question_cost or 0.0)
        return selected if nominal_net > 0.0 else None
    selected = max(available, key=lambda question: (question.net_value, question.id))
    return selected if selected.net_value > session.min_net_value else None


def _nominal_distribution(
    question: AdaptiveElicitationQuestion,
    hypothesis_id: str,
) -> Dict[str, float]:
    prediction = next(item for item in question.predictions if item.hypothesis_id == hypothesis_id)
    return dict(prediction.option_probabilities)


def _true_response_distribution(
    question: AdaptiveElicitationQuestion,
    hypothesis_id: str,
    setting: ResponseSetting,
) -> Dict[str, float]:
    distribution = _nominal_distribution(question, hypothesis_id)
    option_ids = [option.id for option in question.answer_options]
    if setting == "noisy":
        noise = 0.35
        uniform = 1.0 / len(option_ids)
        return {
            option_id: (1.0 - noise) * distribution[option_id] + noise * uniform
            for option_id in option_ids
        }
    if setting == "misspecified_proxy" and question.id.endswith("_proxy"):
        reversed_values = list(reversed([distribution[option_id] for option_id in option_ids]))
        return {option_id: reversed_values[index] for index, option_id in enumerate(option_ids)}
    if setting == "misspecified_proxy":
        noise = 0.1
        uniform = 1.0 / len(option_ids)
        return {
            option_id: (1.0 - noise) * distribution[option_id] + noise * uniform
            for option_id in option_ids
        }
    return distribution


def _stable_rng(*parts: object) -> random.Random:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _sample_option(
    question: AdaptiveElicitationQuestion,
    distribution: Dict[str, float],
    rng: random.Random,
) -> str:
    draw = rng.random()
    cumulative = 0.0
    for option in question.answer_options:
        cumulative += distribution.get(option.id, 0.0)
        if draw <= cumulative:
            return option.id
    return question.answer_options[-1].id


def run_episode(
    *,
    policy: PolicyName,
    true_world_id: str,
    response_setting: ResponseSetting,
    seed: int,
) -> Dict[str, Any]:
    session = create_benchmark_session()
    true_world = next(world for world in session.decision_worlds if world.id == true_world_id)
    policy_rng = _stable_rng("policy", policy, true_world_id, response_setting, seed)
    total_cost = 0.0
    late_questions = 0
    asked: List[str] = []
    premature_stopping = False

    while len(asked) < session.max_questions:
        available = _available_questions(session)
        robust_question_available = any(
            question.net_value > session.min_net_value for question in available
        )
        question = _choose_question(policy, session, policy_rng)
        if question is None:
            premature_stopping = robust_question_available
            break
        if question.net_value <= session.min_net_value:
            late_questions += 1
        hypothesis_id = true_world.hypothesis_assignments[question.target_variable_id]
        distribution = _true_response_distribution(question, hypothesis_id, response_setting)
        response_rng = _stable_rng("response", true_world_id, response_setting, seed, question.id)
        option_id = _sample_option(question, distribution, response_rng)
        total_cost += float(question.question_cost or 0.0)
        asked.append(question.id)
        session = answer_question(
            AnswerAdaptiveElicitationRequest(
                session=session,
                question_id=question.id,
                option_id=option_id,
            )
        )

    terminal_bayes_risk, selected_action_id = bayes_risk(
        session.decision_worlds, session.decision_actions
    )
    selected_action = next(action for action in session.decision_actions if action.id == selected_action_id)
    terminal_decision_loss = selected_action.loss_by_world[true_world_id]
    oracle_loss = min(action.loss_by_world[true_world_id] for action in session.decision_actions)
    terminal_regret = terminal_decision_loss - oracle_loss
    return {
        "policy": policy,
        "true_world_id": true_world_id,
        "response_setting": response_setting,
        "seed": seed,
        "selected_action_id": selected_action_id,
        "terminal_bayes_risk": round(terminal_bayes_risk, 6),
        "terminal_decision_loss": round(terminal_decision_loss, 6),
        "terminal_regret": round(terminal_regret, 6),
        "questions_asked": len(asked),
        "question_ids": asked,
        "total_elicitation_cost": round(total_cost, 6),
        "premature_stopping": premature_stopping,
        "late_stopping": late_questions > 0,
        "late_questions": late_questions,
        "combined_loss": round(terminal_regret + total_cost, 6),
    }


def _aggregate(episodes: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(episodes)
    return {
        "episodes": len(rows),
        "mean_terminal_bayes_risk": round(mean(row["terminal_bayes_risk"] for row in rows), 6),
        "mean_terminal_decision_loss": round(mean(row["terminal_decision_loss"] for row in rows), 6),
        "mean_terminal_regret": round(mean(row["terminal_regret"] for row in rows), 6),
        "mean_questions_asked": round(mean(row["questions_asked"] for row in rows), 6),
        "mean_total_elicitation_cost": round(mean(row["total_elicitation_cost"] for row in rows), 6),
        "premature_stopping_rate": round(mean(float(row["premature_stopping"]) for row in rows), 6),
        "late_stopping_rate": round(mean(float(row["late_stopping"]) for row in rows), 6),
        "mean_late_questions": round(mean(row["late_questions"] for row in rows), 6),
        "mean_combined_loss": round(mean(row["combined_loss"] for row in rows), 6),
    }


def run_benchmark(seeds_per_world: int = 8) -> Dict[str, Any]:
    if seeds_per_world < 1:
        raise ValueError("seeds_per_world must be at least 1")
    session = create_benchmark_session()
    episodes = [
        run_episode(
            policy=policy,
            true_world_id=world.id,
            response_setting=setting,
            seed=seed,
        )
        for policy in POLICIES
        for setting in RESPONSE_SETTINGS
        for world in session.decision_worlds
        for seed in range(seeds_per_world)
    ]
    by_policy: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_policy_setting: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for episode in episodes:
        by_policy[episode["policy"]].append(episode)
        by_policy_setting[episode["policy"]][episode["response_setting"]].append(episode)

    policy_metrics = {
        policy: {
            **_aggregate(by_policy[policy]),
            "by_response_setting": {
                setting: _aggregate(by_policy_setting[policy][setting])
                for setting in RESPONSE_SETTINGS
            },
        }
        for policy in POLICIES
    }
    ranking = sorted(
        POLICIES,
        key=lambda policy: (
            policy_metrics[policy]["mean_combined_loss"],
            policy_metrics[policy]["mean_terminal_regret"],
            policy,
        ),
    )
    return {
        "schema_version": 1,
        "benchmark": "adaptive_elicitation_decision_world_v1",
        "objective": "terminal regret plus elicitation cost; lower is better",
        "config": {
            "policies": POLICIES,
            "response_settings": RESPONSE_SETTINGS,
            "worlds": [world.id for world in session.decision_worlds],
            "seeds_per_world": seeds_per_world,
            "episodes_per_policy": len(by_policy[POLICIES[0]]),
            "total_episodes": len(episodes),
        },
        "policy_metrics": policy_metrics,
        "policy_ranking": ranking,
    }


def _print_summary(result: Dict[str, Any]) -> None:
    print("policy           regret   questions   cost    premature   late    combined")
    for policy in result["policy_ranking"]:
        metrics = result["policy_metrics"][policy]
        print(
            f"{policy:<16} {metrics['mean_terminal_regret']:<8.3f} "
            f"{metrics['mean_questions_asked']:<11.2f} {metrics['mean_total_elicitation_cost']:<7.3f} "
            f"{metrics['premature_stopping_rate']:<11.3f} {metrics['late_stopping_rate']:<7.3f} "
            f"{metrics['mean_combined_loss']:.3f}"
        )


def main() -> None:
    default_output = (
        Path(__file__).resolve().parent.parent
        / "artifacts"
        / "adaptive_elicitation"
        / "benchmark_summary.json"
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds-per-world", type=int, default=8)
    parser.add_argument("--output", type=Path, default=default_output)
    args = parser.parse_args()

    result = run_benchmark(seeds_per_world=args.seeds_per_world)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _print_summary(result)
    print(f"\nWrote {args.output.resolve()}")


if __name__ == "__main__":
    main()
