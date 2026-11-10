from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class BeliefHypothesis(BaseModel):
    id: str
    proposition: str
    probability: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_refs: List[str] = Field(default_factory=list)


class BeliefVariable(BaseModel):
    id: str
    label: str
    hypotheses: List[BeliefHypothesis] = Field(default_factory=list)


class ElicitationAnswerOption(BaseModel):
    id: str
    label: str
    allows_free_text: bool = False


class HypothesisAnswerPrediction(BaseModel):
    hypothesis_id: str
    option_probabilities: Dict[str, float] = Field(default_factory=dict)


class QuestionLikelihoodModel(BaseModel):
    id: str
    weight: float = Field(default=1.0, gt=0.0)
    predictions: List[HypothesisAnswerPrediction] = Field(default_factory=list)


class DecisionWorld(BaseModel):
    id: str
    label: str
    probability: float = Field(default=0.0, ge=0.0, le=1.0)
    hypothesis_assignments: Dict[str, str] = Field(default_factory=dict)


class DecisionAction(BaseModel):
    id: str
    label: str
    loss_by_world: Dict[str, float] = Field(default_factory=dict)


class AdaptiveElicitationQuestion(BaseModel):
    id: str
    target_variable_id: str
    question: str
    why_it_matters: str = ""
    gap_id: Optional[str] = None
    gap_type: Optional[str] = None
    evidence_refs: List[str] = Field(default_factory=list)
    resolution_rationale: str = ""
    alternative_resolution: str = ""
    answer_options: List[ElicitationAnswerOption] = Field(default_factory=list)
    predictions: List[HypothesisAnswerPrediction] = Field(default_factory=list)
    likelihood_models: List[QuestionLikelihoodModel] = Field(default_factory=list)
    decision_relevance: float = Field(default=0.8, ge=0.0, le=1.0)
    answerability: float = Field(default=0.9, ge=0.0, le=1.0)
    estimated_effort_seconds: float = Field(default=20.0, ge=1.0, le=600.0)
    question_cost: Optional[float] = Field(default=None, ge=0.0)
    expected_information_gain: float = 0.0
    expected_geodesic_gain: float = 0.0
    geometric_novelty: float = 1.0
    target_normalized_uncertainty: float = 0.0
    expected_bayes_risk_reduction: float = 0.0
    robust_bayes_risk_reduction: float = 0.0
    probability_of_action_change: float = 0.0
    net_value: float = 0.0
    selection_score: float = 0.0
    selection_rationale: str = ""
    status: Literal["candidate", "answered", "skipped"] = "candidate"


class AdaptiveElicitationAnswer(BaseModel):
    question_id: str
    option_id: str
    option_label: str
    free_text: str = ""
    entropy_before: float
    entropy_after: float
    information_gain: float
    belief_shift: float = 0.0


class AdaptiveElicitationSession(BaseModel):
    id: str
    workspace_key: str
    context_digest: str = ""
    belief_variables: List[BeliefVariable] = Field(default_factory=list)
    decision_worlds: List[DecisionWorld] = Field(default_factory=list)
    decision_actions: List[DecisionAction] = Field(default_factory=list)
    decision_model_source: Literal["explicit", "derived"] = "derived"
    candidate_questions: List[AdaptiveElicitationQuestion] = Field(default_factory=list)
    current_question_id: Optional[str] = None
    answer_history: List[AdaptiveElicitationAnswer] = Field(default_factory=list)
    initial_entropy: float = 0.0
    current_entropy: float = 0.0
    uncertainty_reduction: float = 0.0
    initial_normalized_uncertainty: float = 0.0
    normalized_uncertainty: float = 0.0
    initial_bayes_risk: float = 0.0
    current_bayes_risk: float = 0.0
    bayes_risk_reduction: float = 0.0
    current_best_action_id: Optional[str] = None
    status: Literal["active", "complete"] = "active"
    selection_mode: Literal["discrimination", "discovery", "complete"] = "discrimination"
    stopping_reason: Optional[str] = None
    generation_source: Literal["harness", "model", "fallback"] = "fallback"
    epistemic_trace: Dict[str, Any] = Field(default_factory=dict)
    max_questions: int = Field(default=8, ge=1, le=30)
    min_information_gain: float = Field(default=0.04, ge=0.0, le=1.0)
    min_geodesic_gain: float = Field(default=0.02, ge=0.0, le=10.0)
    max_normalized_uncertainty_for_stop: float = Field(default=0.55, ge=0.0, le=1.0)
    robust_quantile: float = Field(default=0.1, ge=0.0, le=1.0)
    cost_per_second: float = Field(default=0.001, ge=0.0)
    min_net_value: float = 0.0


class StartAdaptiveElicitationRequest(BaseModel):
    workspace_key: str
    explicit_state: Dict[str, Any] = Field(default_factory=dict)
    max_questions: int = Field(default=8, ge=1, le=30)
    min_information_gain: float = Field(default=0.04, ge=0.0, le=1.0)
    min_geodesic_gain: float = Field(default=0.02, ge=0.0, le=10.0)
    max_normalized_uncertainty_for_stop: float = Field(default=0.55, ge=0.0, le=1.0)
    robust_quantile: float = Field(default=0.1, ge=0.0, le=1.0)
    cost_per_second: float = Field(default=0.001, ge=0.0)
    min_net_value: float = 0.0
    require_generative: bool = False


class AnswerAdaptiveElicitationRequest(BaseModel):
    session: AdaptiveElicitationSession
    question_id: str
    option_id: str
    free_text: str = ""


class AdaptiveElicitationResponse(BaseModel):
    session: AdaptiveElicitationSession


def _slug(value: Any, fallback: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")[:64]
    return clean or fallback


def _normalize(values: List[float]) -> List[float]:
    clean = [max(float(value or 0.0), 0.0) for value in values]
    total = sum(clean)
    if total <= 0.0:
        return [1.0 / len(clean)] * len(clean) if clean else []
    return [value / total for value in clean]


def entropy(probabilities: List[float]) -> float:
    return -sum(probability * math.log2(probability) for probability in probabilities if probability > 0.0)


def normalized_entropy(probabilities: List[float]) -> float:
    probabilities = _normalize(probabilities)
    if len(probabilities) < 2:
        return 0.0
    return entropy(probabilities) / math.log2(len(probabilities))


def fisher_rao_distance(left: List[float], right: List[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Fisher-Rao distance requires distributions over the same hypotheses.")
    left = _normalize(left)
    right = _normalize(right)
    affinity = sum(math.sqrt(max(left[index] * right[index], 0.0)) for index in range(len(left)))
    return 2.0 * math.acos(min(max(affinity, 0.0), 1.0))


def session_entropy(session: AdaptiveElicitationSession) -> float:
    return sum(entropy([item.probability for item in variable.hypotheses]) for variable in session.belief_variables)


def session_normalized_uncertainty(session: AdaptiveElicitationSession) -> float:
    weighted_uncertainty = 0.0
    total_weight = 0.0
    for variable in session.belief_variables:
        relevance = max(
            (question.decision_relevance for question in session.candidate_questions if question.target_variable_id == variable.id),
            default=1.0,
        )
        weighted_uncertainty += relevance * normalized_entropy([item.probability for item in variable.hypotheses])
        total_weight += relevance
    return weighted_uncertainty / total_weight if total_weight > 0.0 else 0.0


def _variable(session: AdaptiveElicitationSession, variable_id: str) -> Optional[BeliefVariable]:
    return next((item for item in session.belief_variables if item.id == variable_id), None)


def _prediction_map(
    question: AdaptiveElicitationQuestion,
    predictions: Optional[List[HypothesisAnswerPrediction]] = None,
) -> Dict[str, Dict[str, float]]:
    """Return an answerability-adjusted likelihood model for a question.

    ``answerability`` is not a second utility multiplier: it controls how often
    the predicted response is informative.  The remaining mass is mixed with a
    uniform response, which makes difficult questions less valuable through the
    likelihood itself.
    """
    option_ids = [option.id for option in question.answer_options]
    if not option_ids:
        return {}
    uniform = 1.0 / len(option_ids)
    result: Dict[str, Dict[str, float]] = {}
    for prediction in predictions if predictions is not None else question.predictions:
        normalized = _normalize(
            [max(float(prediction.option_probabilities.get(option_id, 0.0)), 0.0) for option_id in option_ids]
        )
        result[prediction.hypothesis_id] = {
            option_id: question.answerability * normalized[index] + (1.0 - question.answerability) * uniform
            for index, option_id in enumerate(option_ids)
        }
    return result


def _likelihood_model_maps(
    question: AdaptiveElicitationQuestion,
) -> List[tuple[str, float, Dict[str, Dict[str, float]]]]:
    models = [("nominal", 1.0, _prediction_map(question))]
    models.extend(
        (model.id, model.weight, _prediction_map(question, model.predictions))
        for model in question.likelihood_models
        if model.predictions
    )
    return models


def _combined_prediction_map(question: AdaptiveElicitationQuestion) -> Dict[str, Dict[str, float]]:
    models = _likelihood_model_maps(question)
    total_weight = sum(weight for _, weight, _ in models)
    hypothesis_ids = {hypothesis_id for _, _, model in models for hypothesis_id in model}
    option_ids = [option.id for option in question.answer_options]
    return {
        hypothesis_id: {
            option_id: sum(
                weight * model.get(hypothesis_id, {}).get(option_id, 1.0 / max(len(option_ids), 1))
                for _, weight, model in models
            )
            / total_weight
            for option_id in option_ids
        }
        for hypothesis_id in hypothesis_ids
    }


def _weighted_lower_quantile(values: List[tuple[float, float]], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted((value, max(weight, 0.0)) for value, weight in values)
    total_weight = sum(weight for _, weight in ordered)
    if total_weight <= 0.0:
        return ordered[0][0]
    threshold = min(max(quantile, 0.0), 1.0) * total_weight
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return ordered[-1][0]


def bayes_risk(
    worlds: List[DecisionWorld],
    actions: List[DecisionAction],
    probabilities: Optional[List[float]] = None,
) -> tuple[float, Optional[str]]:
    if not worlds or not actions:
        return 0.0, None
    belief = _normalize(probabilities if probabilities is not None else [world.probability for world in worlds])
    scored = [
        (
            sum(
                belief[index] * max(float(action.loss_by_world.get(world.id, 1.0)), 0.0)
                for index, world in enumerate(worlds)
            ),
            action.id,
        )
        for action in actions
    ]
    return min(scored, key=lambda item: (item[0], item[1]))


def _world_answer_posteriors(
    session: AdaptiveElicitationSession,
    question: AdaptiveElicitationQuestion,
    predictions: Dict[str, Dict[str, float]],
) -> tuple[List[float], List[tuple[str, float, List[float]]]]:
    prior = _normalize([world.probability for world in session.decision_worlds])
    default_likelihood = 1.0 / max(len(question.answer_options), 1)
    outcomes: List[tuple[str, float, List[float]]] = []
    for option in question.answer_options:
        likelihoods = [
            max(
                float(
                    predictions.get(
                        world.hypothesis_assignments.get(question.target_variable_id, ""), {}
                    ).get(option.id, default_likelihood)
                ),
                0.0,
            )
            for world in session.decision_worlds
        ]
        answer_probability = sum(prior[index] * likelihoods[index] for index in range(len(prior)))
        if answer_probability <= 0.0:
            continue
        posterior = _normalize([prior[index] * likelihoods[index] for index in range(len(prior))])
        outcomes.append((option.id, answer_probability, posterior))
    return prior, outcomes


def decision_value_metrics(
    session: AdaptiveElicitationSession,
    question: AdaptiveElicitationQuestion,
    predictions: Optional[Dict[str, Dict[str, float]]] = None,
) -> tuple[float, float]:
    """Return expected Bayes-risk reduction and action-change probability."""
    if not session.decision_worlds or not session.decision_actions:
        return 0.0, 0.0
    prior, outcomes = _world_answer_posteriors(session, question, predictions or _prediction_map(question))
    current_risk, current_action_id = bayes_risk(session.decision_worlds, session.decision_actions, prior)
    expected_posterior_risk = 0.0
    probability_of_action_change = 0.0
    for _, answer_probability, posterior in outcomes:
        posterior_risk, posterior_action_id = bayes_risk(
            session.decision_worlds, session.decision_actions, posterior
        )
        expected_posterior_risk += answer_probability * posterior_risk
        if posterior_action_id != current_action_id:
            probability_of_action_change += answer_probability
    return max(current_risk - expected_posterior_risk, 0.0), min(max(probability_of_action_change, 0.0), 1.0)


def _answer_posteriors(
    variable: BeliefVariable,
    question: AdaptiveElicitationQuestion,
) -> tuple[List[float], List[tuple[float, List[float]]]]:
    prior = _normalize([item.probability for item in variable.hypotheses])
    predictions = _prediction_map(question)
    default_likelihood = 1.0 / len(question.answer_options)
    outcomes: List[tuple[float, List[float]]] = []
    for option in question.answer_options:
        likelihoods = [
            max(float(predictions.get(hypothesis.id, {}).get(option.id, default_likelihood)), 0.0)
            for hypothesis in variable.hypotheses
        ]
        answer_probability = sum(prior[index] * likelihoods[index] for index in range(len(prior)))
        if answer_probability <= 0.0:
            continue
        posterior = _normalize([prior[index] * likelihoods[index] for index in range(len(prior))])
        outcomes.append((answer_probability, posterior))
    return prior, outcomes


def expected_information_gain(variable: BeliefVariable, question: AdaptiveElicitationQuestion) -> float:
    if len(variable.hypotheses) < 2 or len(question.answer_options) < 2:
        return 0.0
    prior, outcomes = _answer_posteriors(variable, question)
    expected_posterior_entropy = sum(answer_probability * entropy(posterior) for answer_probability, posterior in outcomes)
    return max(entropy(prior) - expected_posterior_entropy, 0.0)


def expected_fisher_rao_gain(variable: BeliefVariable, question: AdaptiveElicitationQuestion) -> float:
    if len(variable.hypotheses) < 2 or len(question.answer_options) < 2:
        return 0.0
    prior, outcomes = _answer_posteriors(variable, question)
    return sum(
        answer_probability * fisher_rao_distance(prior, posterior) ** 2
        for answer_probability, posterior in outcomes
    )


def question_direction_matrix(variable: BeliefVariable, question: AdaptiveElicitationQuestion) -> List[List[float]]:
    prior, outcomes = _answer_posteriors(variable, question)
    size = len(prior)
    matrix = [[0.0 for _ in range(size)] for _ in range(size)]
    for answer_probability, posterior in outcomes:
        direction = [
            (posterior[index] - prior[index]) / math.sqrt(max(prior[index], 1e-9))
            for index in range(size)
        ]
        for row in range(size):
            for column in range(size):
                matrix[row][column] += answer_probability * direction[row] * direction[column]
    return matrix


def _matrix_similarity(left: List[List[float]], right: List[List[float]]) -> float:
    if len(left) != len(right):
        return 0.0
    inner = sum(left[row][column] * right[row][column] for row in range(len(left)) for column in range(len(left)))
    left_norm = math.sqrt(sum(value * value for row in left for value in row))
    right_norm = math.sqrt(sum(value * value for row in right for value in row))
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return min(max(inner / (left_norm * right_norm), 0.0), 1.0)


def geometric_novelty(
    session: AdaptiveElicitationSession,
    variable: BeliefVariable,
    question: AdaptiveElicitationQuestion,
) -> float:
    answered = [
        item
        for item in session.candidate_questions
        if item.status == "answered" and item.target_variable_id == question.target_variable_id
    ]
    if not answered:
        return 1.0
    candidate_matrix = question_direction_matrix(variable, question)
    similarity = max(
        (_matrix_similarity(candidate_matrix, question_direction_matrix(variable, item)) for item in answered),
        default=0.0,
    )
    return 1.0 - similarity


def _score_question(
    session: AdaptiveElicitationSession,
    variable: BeliefVariable,
    question: AdaptiveElicitationQuestion,
) -> AdaptiveElicitationQuestion:
    information_gain = expected_information_gain(variable, question)
    geodesic_gain = expected_fisher_rao_gain(variable, question)
    novelty = geometric_novelty(session, variable, question)
    nominal_evsi, probability_of_action_change = decision_value_metrics(session, question)
    model_values = [
        (decision_value_metrics(session, question, prediction_map)[0], weight)
        for _, weight, prediction_map in _likelihood_model_maps(question)
    ]
    robust_evsi = _weighted_lower_quantile(model_values, session.robust_quantile)
    question_cost = (
        question.question_cost
        if question.question_cost is not None
        else question.estimated_effort_seconds * session.cost_per_second
    )
    net_value = robust_evsi - question_cost
    return question.model_copy(
        update={
            "expected_information_gain": round(information_gain, 6),
            "expected_geodesic_gain": round(geodesic_gain, 6),
            "geometric_novelty": round(novelty, 6),
            "target_normalized_uncertainty": round(
                normalized_entropy([item.probability for item in variable.hypotheses]), 6
            ),
            "expected_bayes_risk_reduction": round(nominal_evsi, 6),
            "robust_bayes_risk_reduction": round(robust_evsi, 6),
            "probability_of_action_change": round(probability_of_action_change, 6),
            "question_cost": round(question_cost, 6),
            "net_value": round(net_value, 6),
            "selection_score": round(net_value, 6),
            "selection_rationale": (
                f"Targets {variable.label}; robust expected decision-risk reduction {robust_evsi:.3f} "
                f"(nominal {nominal_evsi:.3f}), cost {question_cost:.3f}, net value {net_value:.3f}, "
                f"and {probability_of_action_change:.0%} probability of changing the preferred action. "
                f"Diagnostics: {information_gain:.2f} bits, {geodesic_gain:.2f} Fisher-Rao movement, "
                f"and {novelty:.0%} geometric novelty."
            ),
        }
    )


def _discovery_question(variable: BeliefVariable) -> AdaptiveElicitationQuestion:
    question_id = f"discover_{variable.id}"
    options = [
        ElicitationAnswerOption(id="complete", label="The current alternatives cover my view"),
        ElicitationAnswerOption(id="missing", label="An important alternative is missing", allows_free_text=True),
    ]
    predictions = [
        HypothesisAnswerPrediction(
            hypothesis_id=hypothesis.id,
            option_probabilities={"complete": 0.8, "missing": 0.2},
        )
        for hypothesis in variable.hypotheses
    ]
    return AdaptiveElicitationQuestion(
        id=question_id,
        target_variable_id=variable.id,
        question=f"Is an important alternative missing from the current model of {variable.label.lower()}?",
        why_it_matters=(
            "Uncertainty remains high, but the available structured questions cannot distinguish the current hypotheses. "
            "A missing alternative should be added before elicitation stops."
        ),
        answer_options=options,
        predictions=predictions,
        decision_relevance=1.0,
        answerability=0.95,
        estimated_effort_seconds=20.0,
        selection_rationale="Discovery mode: expand or confirm the hypothesis space before stopping.",
    )


def _activate_discovery(session: AdaptiveElicitationSession) -> bool:
    variables = sorted(
        session.belief_variables,
        key=lambda item: normalized_entropy([hypothesis.probability for hypothesis in item.hypotheses]),
        reverse=True,
    )
    for variable in variables:
        question_id = f"discover_{variable.id}"
        existing = next((item for item in session.candidate_questions if item.id == question_id), None)
        if existing and existing.status != "candidate":
            continue
        if not existing:
            existing = _discovery_question(variable)
            session.candidate_questions.append(existing)
        session.status = "active"
        session.selection_mode = "discovery"
        session.current_question_id = existing.id
        session.stopping_reason = None
        return True
    return False


def _discovered_hypothesis_question(
    variable: BeliefVariable,
    discovered: BeliefHypothesis,
    previous_leader: BeliefHypothesis,
) -> AdaptiveElicitationQuestion:
    options = [
        ElicitationAnswerOption(id="discovered", label=discovered.proposition[:120]),
        ElicitationAnswerOption(id="previous", label=previous_leader.proposition[:120]),
        ElicitationAnswerOption(id="contextual", label="It depends on the decision context"),
    ]
    predictions: List[HypothesisAnswerPrediction] = []
    for hypothesis in variable.hypotheses:
        if hypothesis.id == discovered.id:
            probabilities = {"discovered": 0.8, "previous": 0.1, "contextual": 0.1}
        elif hypothesis.id == previous_leader.id:
            probabilities = {"discovered": 0.1, "previous": 0.8, "contextual": 0.1}
        else:
            probabilities = {"discovered": 0.15, "previous": 0.25, "contextual": 0.6}
        predictions.append(
            HypothesisAnswerPrediction(hypothesis_id=hypothesis.id, option_probabilities=probabilities)
        )
    return AdaptiveElicitationQuestion(
        id=f"discriminate_{discovered.id}",
        target_variable_id=variable.id,
        question="When the newly supplied alternative conflicts with the previous leading interpretation, which should govern the next decision?",
        why_it_matters="This places the newly discovered alternative relative to the existing belief model.",
        answer_options=options,
        predictions=predictions,
        decision_relevance=1.0,
        answerability=0.9,
        estimated_effort_seconds=20.0,
    )


def select_next_question(session: AdaptiveElicitationSession) -> AdaptiveElicitationSession:
    _ensure_decision_model(session)
    scored: List[AdaptiveElicitationQuestion] = []
    for question in session.candidate_questions:
        if question.status != "candidate":
            scored.append(question)
            continue
        variable = _variable(session, question.target_variable_id)
        scored.append(
            _score_question(session, variable, question)
            if variable
            else question.model_copy(update={"selection_score": 0.0})
        )

    session.candidate_questions = scored
    session.current_entropy = round(session_entropy(session), 6)
    session.uncertainty_reduction = round(max(session.initial_entropy - session.current_entropy, 0.0), 6)
    session.normalized_uncertainty = round(session_normalized_uncertainty(session), 6)
    current_risk, current_action_id = bayes_risk(session.decision_worlds, session.decision_actions)
    session.current_bayes_risk = round(current_risk, 6)
    session.bayes_risk_reduction = round(max(session.initial_bayes_risk - current_risk, 0.0), 6)
    session.current_best_action_id = current_action_id
    remaining = sorted(
        (item for item in scored if item.status == "candidate"),
        key=lambda item: (
            item.net_value,
            item.robust_bayes_risk_reduction,
            item.expected_information_gain,
            item.expected_geodesic_gain,
        ),
        reverse=True,
    )

    if len(session.answer_history) >= session.max_questions:
        session.status = "complete"
        session.selection_mode = "complete"
        session.current_question_id = None
        session.stopping_reason = f"Question budget of {session.max_questions} reached."
    elif remaining and (
        remaining[0].expected_information_gain >= session.min_information_gain
        or remaining[0].expected_geodesic_gain >= session.min_geodesic_gain
    ) and remaining[0].net_value > session.min_net_value:
        session.status = "active"
        session.selection_mode = "discrimination"
        session.current_question_id = remaining[0].id
        session.stopping_reason = None
    elif (
        session.normalized_uncertainty > session.max_normalized_uncertainty_for_stop
        and remaining
        and all(
            item.expected_information_gain < session.min_information_gain
            and item.expected_geodesic_gain < session.min_geodesic_gain
            for item in remaining
        )
        and _activate_discovery(session)
    ):
        pass
    else:
        session.status = "complete"
        session.selection_mode = "complete"
        session.current_question_id = None
        if remaining and remaining[0].robust_bayes_risk_reduction > 0.0 and remaining[0].net_value <= session.min_net_value:
            session.stopping_reason = (
                f"Best remaining question has net decision value {remaining[0].net_value:.3f}: "
                f"robust risk reduction {remaining[0].robust_bayes_risk_reduction:.3f} "
                f"minus cost {remaining[0].question_cost:.3f}. Asking is not better than stopping."
            )
        elif session.normalized_uncertainty <= session.max_normalized_uncertainty_for_stop:
            session.stopping_reason = (
                f"Normalized uncertainty is {session.normalized_uncertainty:.0%}, within the configured stopping range."
            )
        elif not remaining:
            session.stopping_reason = "No unanswered question spans a new informative direction."
        else:
            session.stopping_reason = (
                "Remaining questions provide too little information or Fisher-Rao movement and discovery has been exhausted."
            )
    return session


def _normalize_variable(raw: Dict[str, Any], index: int) -> Optional[BeliefVariable]:
    raw_hypotheses = raw.get("hypotheses") if isinstance(raw.get("hypotheses"), list) else []
    hypotheses: List[BeliefHypothesis] = []
    for hypothesis_index, item in enumerate(raw_hypotheses[:5]):
        if not isinstance(item, dict) or not str(item.get("proposition") or "").strip():
            continue
        hypotheses.append(
            BeliefHypothesis(
                id=_slug(item.get("id"), f"h_{index + 1}_{hypothesis_index + 1}"),
                proposition=str(item.get("proposition") or "").strip(),
                probability=min(max(float(item.get("probability") or 0.0), 0.0), 1.0),
                evidence_refs=[str(value).strip() for value in (item.get("evidence_refs") or []) if str(value).strip()][:4],
            )
        )
    if len(hypotheses) < 2:
        return None
    probabilities = _normalize([item.probability for item in hypotheses])
    hypotheses = [item.model_copy(update={"probability": probabilities[i]}) for i, item in enumerate(hypotheses)]
    return BeliefVariable(
        id=_slug(raw.get("id"), f"variable_{index + 1}"),
        label=str(raw.get("label") or f"Belief variable {index + 1}").strip(),
        hypotheses=hypotheses,
    )


def _normalize_question(
    raw: Dict[str, Any],
    index: int,
    variables: Dict[str, BeliefVariable],
) -> Optional[AdaptiveElicitationQuestion]:
    target_id = _slug(raw.get("target_variable_id"), "")
    variable = variables.get(target_id)
    if not variable or not str(raw.get("question") or "").strip():
        return None

    options: List[ElicitationAnswerOption] = []
    for option_index, item in enumerate((raw.get("answer_options") or [])[:6]):
        if not isinstance(item, dict) or not str(item.get("label") or "").strip():
            continue
        options.append(
            ElicitationAnswerOption(
                id=_slug(item.get("id"), f"option_{option_index + 1}"),
                label=str(item.get("label") or "").strip(),
                allows_free_text=bool(item.get("allows_free_text")),
            )
        )
    if len(options) < 2:
        return None

    option_ids = {item.id for item in options}
    raw_predictions = raw.get("predictions") if isinstance(raw.get("predictions"), list) else []
    predictions_by_hypothesis = {
        _slug(item.get("hypothesis_id"), ""): item.get("option_probabilities") or {}
        for item in raw_predictions
        if isinstance(item, dict)
    }
    predictions: List[HypothesisAnswerPrediction] = []
    for hypothesis in variable.hypotheses:
        source = predictions_by_hypothesis.get(hypothesis.id, {})
        normalized = _normalize([max(float(source.get(option.id) or 0.0), 0.0) for option in options])
        predictions.append(
            HypothesisAnswerPrediction(
                hypothesis_id=hypothesis.id,
                option_probabilities={option.id: normalized[i] for i, option in enumerate(options) if option.id in option_ids},
            )
        )

    likelihood_models: List[QuestionLikelihoodModel] = []
    for model_index, raw_model in enumerate((raw.get("likelihood_models") or [])[:8]):
        if not isinstance(raw_model, dict):
            continue
        raw_model_predictions = (
            raw_model.get("predictions") if isinstance(raw_model.get("predictions"), list) else []
        )
        source_by_hypothesis = {
            _slug(item.get("hypothesis_id"), ""): item.get("option_probabilities") or {}
            for item in raw_model_predictions
            if isinstance(item, dict)
        }
        model_predictions: List[HypothesisAnswerPrediction] = []
        for hypothesis in variable.hypotheses:
            source = source_by_hypothesis.get(hypothesis.id, {})
            normalized = _normalize(
                [max(float(source.get(option.id) or 0.0), 0.0) for option in options]
            )
            model_predictions.append(
                HypothesisAnswerPrediction(
                    hypothesis_id=hypothesis.id,
                    option_probabilities={option.id: normalized[i] for i, option in enumerate(options)},
                )
            )
        likelihood_models.append(
            QuestionLikelihoodModel(
                id=_slug(raw_model.get("id"), f"likelihood_{model_index + 1}"),
                weight=max(float(raw_model.get("weight") or 1.0), 1e-6),
                predictions=model_predictions,
            )
        )

    return AdaptiveElicitationQuestion(
        id=_slug(raw.get("id"), f"question_{index + 1}"),
        target_variable_id=target_id,
        question=str(raw.get("question") or "").strip(),
        why_it_matters=str(raw.get("why_it_matters") or "").strip(),
        gap_id=_slug(raw.get("gap_id"), "") or None,
        gap_type=str(raw.get("gap_type") or "").strip() or None,
        evidence_refs=[str(value).strip() for value in (raw.get("evidence_refs") or []) if str(value).strip()][:12],
        resolution_rationale=str(raw.get("resolution_rationale") or "").strip(),
        alternative_resolution=str(raw.get("alternative_resolution") or "").strip(),
        answer_options=options,
        predictions=predictions,
        likelihood_models=likelihood_models,
        decision_relevance=min(max(float(raw.get("decision_relevance") or 0.8), 0.0), 1.0),
        answerability=min(max(float(raw.get("answerability") or 0.9), 0.0), 1.0),
        estimated_effort_seconds=min(max(float(raw.get("estimated_effort_seconds") or 20.0), 1.0), 600.0),
        question_cost=(
            max(float(raw.get("question_cost")), 0.0)
            if raw.get("question_cost") is not None
            else None
        ),
    )


def _derive_worlds(variables: List[BeliefVariable]) -> List[DecisionWorld]:
    worlds: List[DecisionWorld] = []
    hypothesis_sets = [variable.hypotheses for variable in variables]
    for combination in itertools.islice(itertools.product(*hypothesis_sets), 64):
        assignments = {variables[index].id: hypothesis.id for index, hypothesis in enumerate(combination)}
        world_id = "world_" + hashlib.sha256(
            json.dumps(assignments, sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]
        worlds.append(
            DecisionWorld(
                id=world_id,
                label="; ".join(hypothesis.proposition for hypothesis in combination),
                probability=math.prod(hypothesis.probability for hypothesis in combination),
                hypothesis_assignments=assignments,
            )
        )
    probabilities = _normalize([world.probability for world in worlds])
    return [world.model_copy(update={"probability": probabilities[index]}) for index, world in enumerate(worlds)]


def _normalize_worlds(
    raw_worlds: Any,
    variables: List[BeliefVariable],
) -> List[DecisionWorld]:
    if not isinstance(raw_worlds, list):
        return []
    hypothesis_ids = {
        variable.id: {hypothesis.id for hypothesis in variable.hypotheses}
        for variable in variables
    }
    worlds: List[DecisionWorld] = []
    for index, raw_world in enumerate(raw_worlds[:64]):
        if not isinstance(raw_world, dict):
            continue
        assignments = {
            _slug(variable_id, ""): _slug(hypothesis_id, "")
            for variable_id, hypothesis_id in (raw_world.get("hypothesis_assignments") or {}).items()
        }
        if any(assignments.get(variable.id) not in hypothesis_ids[variable.id] for variable in variables):
            continue
        worlds.append(
            DecisionWorld(
                id=_slug(raw_world.get("id"), f"world_{index + 1}"),
                label=str(raw_world.get("label") or f"Decision world {index + 1}").strip(),
                probability=max(float(raw_world.get("probability") or 0.0), 0.0),
                hypothesis_assignments=assignments,
            )
        )
    probabilities = _normalize([world.probability for world in worlds])
    return [world.model_copy(update={"probability": probabilities[index]}) for index, world in enumerate(worlds)]


def _variable_weights(
    variables: List[BeliefVariable],
    questions: List[AdaptiveElicitationQuestion],
) -> Dict[str, float]:
    return {
        variable.id: max(
            (question.decision_relevance for question in questions if question.target_variable_id == variable.id),
            default=1.0,
        )
        for variable in variables
    }


def _derive_actions(
    worlds: List[DecisionWorld],
    variable_weights: Dict[str, float],
) -> List[DecisionAction]:
    total_weight = sum(variable_weights.values()) or 1.0
    return [
        DecisionAction(
            id=f"act_{world.id}",
            label=f"Proceed under: {world.label}",
            loss_by_world={
                actual.id: sum(
                    weight
                    for variable_id, weight in variable_weights.items()
                    if actual.hypothesis_assignments.get(variable_id)
                    != world.hypothesis_assignments.get(variable_id)
                )
                / total_weight
                for actual in worlds
            },
        )
        for world in worlds
    ]


def _normalize_actions(
    raw_actions: Any,
    worlds: List[DecisionWorld],
) -> List[DecisionAction]:
    if not isinstance(raw_actions, list):
        return []
    actions: List[DecisionAction] = []
    for index, raw_action in enumerate(raw_actions[:32]):
        if not isinstance(raw_action, dict):
            continue
        raw_world_losses = raw_action.get("loss_by_world") or {}
        raw_hypothesis_losses = raw_action.get("loss_by_hypothesis") or {}
        loss_by_world: Dict[str, float] = {}
        for world in worlds:
            if world.id in raw_world_losses:
                loss = float(raw_world_losses[world.id])
            else:
                matched_losses = [
                    float(raw_hypothesis_losses[hypothesis_id])
                    for hypothesis_id in world.hypothesis_assignments.values()
                    if hypothesis_id in raw_hypothesis_losses
                ]
                loss = sum(matched_losses) / len(matched_losses) if matched_losses else 1.0
            loss_by_world[world.id] = max(loss, 0.0)
        if not loss_by_world:
            continue
        actions.append(
            DecisionAction(
                id=_slug(raw_action.get("id"), f"action_{index + 1}"),
                label=str(raw_action.get("label") or f"Decision action {index + 1}").strip(),
                loss_by_world=loss_by_world,
            )
        )
    return actions


def create_session(
    *,
    workspace_key: str,
    context_digest: str,
    raw_payload: Dict[str, Any],
    generation_source: Literal["harness", "model", "fallback"],
    max_questions: int,
    min_information_gain: float,
    min_geodesic_gain: float = 0.02,
    max_normalized_uncertainty_for_stop: float = 0.55,
    robust_quantile: float = 0.1,
    cost_per_second: float = 0.001,
    min_net_value: float = 0.0,
) -> AdaptiveElicitationSession:
    if generation_source == "harness" and raw_payload.get("resolution_only") is True:
        if any(raw_payload.get(key) for key in ("belief_variables", "candidate_questions", "decision_actions")):
            raise ValueError("A resolution-only plan cannot also contain elicitation content.")
        digest = hashlib.sha256(f"{workspace_key}:{context_digest}".encode("utf-8")).hexdigest()[:16]
        return AdaptiveElicitationSession(
            id=f"elicitation_{digest}", workspace_key=workspace_key,
            context_digest=context_digest[:12000], generation_source="harness",
            status="complete", selection_mode="complete",
            stopping_reason="No user question is indicated by the current gap analysis. Review the resolution steps below; research may still be unresolved.",
            max_questions=max_questions, min_information_gain=min_information_gain,
            min_geodesic_gain=min_geodesic_gain,
            max_normalized_uncertainty_for_stop=max_normalized_uncertainty_for_stop,
            robust_quantile=robust_quantile, cost_per_second=cost_per_second,
            min_net_value=min_net_value,
        )
    variables = [
        variable
        for index, raw in enumerate((raw_payload.get("belief_variables") or [])[:6])
        if isinstance(raw, dict) and (variable := _normalize_variable(raw, index)) is not None
    ]
    variable_map = {item.id: item for item in variables}
    questions = [
        question
        for index, raw in enumerate((raw_payload.get("candidate_questions") or [])[:12])
        if isinstance(raw, dict) and (question := _normalize_question(raw, index, variable_map)) is not None
    ]
    if not variables or not questions:
        raise ValueError("Elicitation payload did not contain usable belief variables and questions.")

    explicit_worlds = _normalize_worlds(raw_payload.get("decision_worlds"), variables)
    worlds = explicit_worlds or _derive_worlds(variables)
    explicit_actions = _normalize_actions(raw_payload.get("decision_actions"), worlds)
    actions = explicit_actions or _derive_actions(worlds, _variable_weights(variables, questions))
    if not worlds or not actions:
        raise ValueError("Elicitation payload did not produce a usable decision model.")

    digest = hashlib.sha256(f"{workspace_key}:{context_digest}".encode("utf-8")).hexdigest()[:16]
    session = AdaptiveElicitationSession(
        id=f"elicitation_{digest}",
        workspace_key=workspace_key,
        context_digest=context_digest[:12000],
        belief_variables=variables,
        decision_worlds=worlds,
        decision_actions=actions,
        decision_model_source="explicit" if explicit_worlds or explicit_actions else "derived",
        candidate_questions=questions,
        generation_source=generation_source,
        max_questions=max_questions,
        min_information_gain=min_information_gain,
        min_geodesic_gain=min_geodesic_gain,
        max_normalized_uncertainty_for_stop=max_normalized_uncertainty_for_stop,
        robust_quantile=robust_quantile,
        cost_per_second=cost_per_second,
        min_net_value=min_net_value,
    )
    session.initial_entropy = round(session_entropy(session), 6)
    session.current_entropy = session.initial_entropy
    session.initial_normalized_uncertainty = round(session_normalized_uncertainty(session), 6)
    session.normalized_uncertainty = session.initial_normalized_uncertainty
    initial_risk, initial_action_id = bayes_risk(session.decision_worlds, session.decision_actions)
    session.initial_bayes_risk = round(initial_risk, 6)
    session.current_bayes_risk = session.initial_bayes_risk
    session.current_best_action_id = initial_action_id
    return select_next_question(session)


def _ensure_decision_model(session: AdaptiveElicitationSession) -> None:
    if not session.decision_worlds:
        session.decision_worlds = _derive_worlds(session.belief_variables)
    if not session.decision_actions:
        session.decision_actions = _derive_actions(
            session.decision_worlds,
            _variable_weights(session.belief_variables, session.candidate_questions),
        )
    if session.initial_bayes_risk == 0.0:
        risk, action_id = bayes_risk(session.decision_worlds, session.decision_actions)
        session.initial_bayes_risk = round(risk, 6)
        session.current_bayes_risk = round(risk, 6)
        session.current_best_action_id = action_id


def _sync_marginals_from_worlds(session: AdaptiveElicitationSession) -> None:
    for variable in session.belief_variables:
        probability_by_hypothesis = {
            hypothesis.id: sum(
                world.probability
                for world in session.decision_worlds
                if world.hypothesis_assignments.get(variable.id) == hypothesis.id
            )
            for hypothesis in variable.hypotheses
        }
        normalized = _normalize(list(probability_by_hypothesis.values()))
        variable.hypotheses = [
            hypothesis.model_copy(update={"probability": normalized[index]})
            for index, hypothesis in enumerate(variable.hypotheses)
        ]


def _update_world_belief(
    session: AdaptiveElicitationSession,
    question: AdaptiveElicitationQuestion,
    option_id: str,
) -> None:
    predictions = _combined_prediction_map(question)
    default_likelihood = 1.0 / max(len(question.answer_options), 1)
    unnormalized = [
        world.probability
        * max(
            predictions.get(
                world.hypothesis_assignments.get(question.target_variable_id, ""), {}
            ).get(option_id, default_likelihood),
            1e-6,
        )
        for world in session.decision_worlds
    ]
    posterior = _normalize(unnormalized)
    session.decision_worlds = [
        world.model_copy(update={"probability": posterior[index]})
        for index, world in enumerate(session.decision_worlds)
    ]
    _sync_marginals_from_worlds(session)


def answer_question(request: AnswerAdaptiveElicitationRequest) -> AdaptiveElicitationSession:
    session = request.session.model_copy(deep=True)
    _ensure_decision_model(session)
    question = next((item for item in session.candidate_questions if item.id == request.question_id), None)
    if not question:
        raise ValueError("Question does not belong to this elicitation session.")
    if question.status != "candidate":
        raise ValueError("Question has already been answered or skipped.")
    option = next((item for item in question.answer_options if item.id == request.option_id), None)
    if not option:
        raise ValueError("Answer option does not belong to this question.")
    if option.allows_free_text and not request.free_text.strip():
        raise ValueError("This answer option requires a short explanation.")
    variable = _variable(session, question.target_variable_id)
    if not variable:
        raise ValueError("Question target variable is missing.")

    entropy_before = session_entropy(session)
    prior_by_id = {hypothesis.id: hypothesis.probability for hypothesis in variable.hypotheses}
    _update_world_belief(session, question, option.id)
    if option.allows_free_text and request.free_text.strip():
        previous_leader = max(variable.hypotheses, key=lambda hypothesis: hypothesis.probability)
        discovery_probability = 0.7
        variable.hypotheses = [
            hypothesis.model_copy(update={"probability": hypothesis.probability * (1.0 - discovery_probability)})
            for hypothesis in variable.hypotheses
        ]
        discovery_id = hashlib.sha256(request.free_text.strip().lower().encode("utf-8")).hexdigest()[:10]
        discovered = BeliefHypothesis(
            id=f"discovered_{discovery_id}",
            proposition=request.free_text.strip(),
            probability=discovery_probability,
            evidence_refs=[f"User supplied an alternative while answering: {question.question}"],
        )
        variable.hypotheses.append(discovered)
        session.decision_worlds = _derive_worlds(session.belief_variables)
        session.decision_actions = _derive_actions(
            session.decision_worlds,
            _variable_weights(session.belief_variables, session.candidate_questions),
        )
        session.decision_model_source = "derived"
        discriminator = _discovered_hypothesis_question(variable, discovered, previous_leader)
        if not any(item.id == discriminator.id for item in session.candidate_questions):
            session.candidate_questions.append(discriminator)
    entropy_after = session_entropy(session)
    hypothesis_ids = [hypothesis.id for hypothesis in variable.hypotheses]
    belief_shift = fisher_rao_distance(
        [prior_by_id.get(hypothesis_id, 0.0) for hypothesis_id in hypothesis_ids],
        [hypothesis.probability for hypothesis in variable.hypotheses],
    )

    session.candidate_questions = [
        item.model_copy(update={"status": "answered"}) if item.id == question.id else item
        for item in session.candidate_questions
    ]
    session.answer_history.append(
        AdaptiveElicitationAnswer(
            question_id=question.id,
            option_id=option.id,
            option_label=option.label,
            free_text=request.free_text.strip(),
            entropy_before=round(entropy_before, 6),
            entropy_after=round(entropy_after, 6),
            information_gain=round(max(entropy_before - entropy_after, 0.0), 6),
            belief_shift=round(belief_shift, 6),
        )
    )
    return select_next_question(session)


def build_generation_prompt(explicit_state: Dict[str, Any]) -> str:
    serialized = json.dumps(explicit_state, ensure_ascii=False, default=str)
    if len(serialized) > 12000:
        serialized = serialized[:12000]
    return f"""
You design adaptive questions that elicit a scientist's hidden decision model.

From the explicit workspace state below, create:
1. Three to five independent belief variables. Each variable must contain two to four mutually exclusive hypotheses.
2. Two to five feasible downstream decision actions, with a 0-to-1 loss for every hypothesis.
3. Five to nine concise multiple-choice questions that discriminate among hypotheses for exactly one variable.
4. For every hypothesis-question pair, a probability distribution over that question's answer option ids.

Rules:
- Model hidden objectives, constraints, evidence standards, transfer assumptions, causal beliefs, or redlines.
- Do not model trivia or presentation preferences unless they change a project decision.
- Hypothesis probabilities within each variable must sum to 1.
- Option probabilities for each hypothesis must sum to 1.
- Include an `other` option with `allows_free_text: true` where the hypothesis space could be incomplete.
- Questions must be answerable by the user and should not ask for facts already explicit in the state.
- A decision action's loss_by_hypothesis must use hypothesis ids from belief_variables; 0 is ideal and 1 is worst.
- Use stable snake_case ids.

Explicit workspace state:
{serialized}

Return this JSON shape:
{{
  "belief_variables": [
    {{
      "id": "primary_objective",
      "label": "Primary objective",
      "hypotheses": [
        {{"id": "speed", "proposition": "Rapid proof of concept matters most", "probability": 0.34, "evidence_refs": ["specific signal"]}}
      ]
    }}
  ],
  "decision_actions": [
    {{
      "id": "prioritize_speed",
      "label": "Prioritize a rapid proof of concept",
      "loss_by_hypothesis": {{"speed": 0.0, "performance": 0.7, "scale": 0.8}}
    }}
  ],
  "candidate_questions": [
    {{
      "id": "success_outcome",
      "target_variable_id": "primary_objective",
      "question": "Which outcome would make the next phase successful?",
      "why_it_matters": "The answer changes which work is prioritized.",
      "answer_options": [
        {{"id": "fast", "label": "Fast proof of concept", "allows_free_text": false}},
        {{"id": "other", "label": "Something else", "allows_free_text": true}}
      ],
      "predictions": [
        {{"hypothesis_id": "speed", "option_probabilities": {{"fast": 0.9, "other": 0.1}}}}
      ],
      "decision_relevance": 0.95,
      "answerability": 0.95,
      "estimated_effort_seconds": 15
    }}
  ]
}}
""".strip()


def fallback_payload(explicit_state: Dict[str, Any]) -> Dict[str, Any]:
    context = json.dumps(explicit_state, ensure_ascii=False, default=str).lower()

    outcome_weights = [1.0, 1.0, 1.0]
    for term in ["quick", "rapid", "fast", "time", "sprint"]:
        if term in context:
            outcome_weights[0] += 0.5
    for term in ["yield", "titer", "performance", "productivity", "maximum"]:
        if term in context:
            outcome_weights[1] += 0.5
    for term in ["scale", "cost", "economics", "commercial", "cogs"]:
        if term in context:
            outcome_weights[2] += 0.5
    outcome_probabilities = _normalize(outcome_weights)

    return {
        "belief_variables": [
            {
                "id": "primary_outcome",
                "label": "Primary project outcome",
                "hypotheses": [
                    {"id": "speed", "proposition": "Rapid proof of concept matters most", "probability": outcome_probabilities[0], "evidence_refs": []},
                    {"id": "performance", "proposition": "Maximum technical performance matters most", "probability": outcome_probabilities[1], "evidence_refs": []},
                    {"id": "scale", "proposition": "Scale and economic viability matter most", "probability": outcome_probabilities[2], "evidence_refs": []},
                ],
            },
            {
                "id": "evidence_bar",
                "label": "Evidence threshold",
                "hypotheses": [
                    {"id": "directional", "proposition": "Directional evidence is enough to choose the next exploration", "probability": 0.34, "evidence_refs": []},
                    {"id": "mechanistic", "proposition": "A plausible mechanism is required before acting", "probability": 0.33, "evidence_refs": []},
                    {"id": "decision_grade", "proposition": "Reproducible quantitative evidence is required", "probability": 0.33, "evidence_refs": []},
                ],
            },
            {
                "id": "transfer_posture",
                "label": "Transferability posture",
                "hypotheses": [
                    {"id": "direct", "proposition": "Close literature analogues can be treated as directly transferable", "probability": 0.25, "evidence_refs": []},
                    {"id": "analogy", "proposition": "Analogues are useful only as directional evidence", "probability": 0.40, "evidence_refs": []},
                    {"id": "validate", "proposition": "Transfer assumptions require explicit validation before use", "probability": 0.35, "evidence_refs": []},
                ],
            },
        ],
        "candidate_questions": [
            {
                "id": "next_phase_success",
                "target_variable_id": "primary_outcome",
                "question": "Which outcome would make the next phase successful?",
                "why_it_matters": "This determines which evidence and actions the workspace should prioritize.",
                "answer_options": [
                    {"id": "fast", "label": "A fast proof of concept", "allows_free_text": False},
                    {"id": "best", "label": "The strongest technical performance", "allows_free_text": False},
                    {"id": "scalable", "label": "A credible scale and cost path", "allows_free_text": False},
                    {"id": "other", "label": "A different outcome", "allows_free_text": True},
                ],
                "predictions": [
                    {"hypothesis_id": "speed", "option_probabilities": {"fast": 0.82, "best": 0.06, "scalable": 0.06, "other": 0.06}},
                    {"hypothesis_id": "performance", "option_probabilities": {"fast": 0.06, "best": 0.82, "scalable": 0.06, "other": 0.06}},
                    {"hypothesis_id": "scale", "option_probabilities": {"fast": 0.06, "best": 0.06, "scalable": 0.82, "other": 0.06}},
                ],
                "decision_relevance": 1.0,
                "answerability": 0.95,
                "estimated_effort_seconds": 15,
            },
            {
                "id": "minimum_evidence",
                "target_variable_id": "evidence_bar",
                "question": "What is the minimum evidence needed before the team should act?",
                "why_it_matters": "This sets the threshold for literature claims and validation work.",
                "answer_options": [
                    {"id": "direction", "label": "A credible directional signal", "allows_free_text": False},
                    {"id": "mechanism", "label": "A mechanism that explains the effect", "allows_free_text": False},
                    {"id": "replication", "label": "Reproducible quantitative evidence", "allows_free_text": False},
                    {"id": "other", "label": "Another evidence threshold", "allows_free_text": True},
                ],
                "predictions": [
                    {"hypothesis_id": "directional", "option_probabilities": {"direction": 0.8, "mechanism": 0.1, "replication": 0.05, "other": 0.05}},
                    {"hypothesis_id": "mechanistic", "option_probabilities": {"direction": 0.08, "mechanism": 0.8, "replication": 0.07, "other": 0.05}},
                    {"hypothesis_id": "decision_grade", "option_probabilities": {"direction": 0.05, "mechanism": 0.08, "replication": 0.82, "other": 0.05}},
                ],
                "decision_relevance": 0.9,
                "answerability": 0.9,
                "estimated_effort_seconds": 20,
            },
            {
                "id": "literature_transfer",
                "target_variable_id": "transfer_posture",
                "question": "How should a close literature analogue be used when it differs from this project in host or conditions?",
                "why_it_matters": "The answer controls whether evidence is treated as an input, analogy, or validation target.",
                "answer_options": [
                    {"id": "use", "label": "Use it directly unless contradicted", "allows_free_text": False},
                    {"id": "direction", "label": "Use it only for directional guidance", "allows_free_text": False},
                    {"id": "test", "label": "Require a transferability test first", "allows_free_text": False},
                    {"id": "other", "label": "Use another rule", "allows_free_text": True},
                ],
                "predictions": [
                    {"hypothesis_id": "direct", "option_probabilities": {"use": 0.82, "direction": 0.08, "test": 0.05, "other": 0.05}},
                    {"hypothesis_id": "analogy", "option_probabilities": {"use": 0.07, "direction": 0.8, "test": 0.08, "other": 0.05}},
                    {"hypothesis_id": "validate", "option_probabilities": {"use": 0.05, "direction": 0.08, "test": 0.82, "other": 0.05}},
                ],
                "decision_relevance": 0.95,
                "answerability": 0.9,
                "estimated_effort_seconds": 20,
            },
        ],
    }
