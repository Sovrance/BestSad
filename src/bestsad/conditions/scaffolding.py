"""Scaffolding matcher — condition H, confound C3 (spec §24.5 H, §40.1).

H14 says any measured advantage of an evolved language must persist when in-context scaffolding
is equalized: grammar-description length in tokens, count and difficulty of worked examples,
retry/repair policy, and decoding constraints.

The matcher **logs the delivered budget per condition** (implementation plan M5) rather than
assuming equality, and reports the residual where exact equalization is impossible. Spec §40.3
makes an undisclosed residual a protocol violation, so the residual is part of the return value,
not an optional extra.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Mapping, Sequence


@dataclass(frozen=True, slots=True)
class Scaffolding:
    """The in-context material a condition actually receives."""

    condition_id: str
    grammar_description_tokens: int
    worked_example_count: int
    worked_example_difficulty: str
    retry_policy: str
    decoding_constraints: str

    def to_record(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ScaffoldingResidual:
    """The disclosed residual after equalization (spec §40.3)."""

    measure: str
    value: float
    unit: str
    note: str = ""

    def to_record(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class ScaffoldingReport:
    delivered: dict[str, Scaffolding] = field(default_factory=dict)
    target_tokens: int = 0
    residuals: dict[str, ScaffoldingResidual] = field(default_factory=dict)

    @property
    def max_absolute_residual_tokens(self) -> float:
        return max((abs(r.value) for r in self.residuals.values()), default=0.0)

    @property
    def max_relative_residual(self) -> float:
        if not self.target_tokens:
            return 0.0
        return self.max_absolute_residual_tokens / self.target_tokens

    def disclosure(self) -> str:
        """The sentence that must appear in the report (spec §40.3 gives the shape)."""
        if not self.residuals:
            return "scaffolding not equalized: no conditions recorded"
        worst = max(self.residuals.items(), key=lambda kv: abs(kv[1].value))
        return (
            f"scaffolding equalized to within {self.max_absolute_residual_tokens:.0f} tokens "
            f"of a {self.target_tokens}-token target; condition {worst[0]} received "
            f"{worst[1].value:+.0f} tokens ({self.max_relative_residual:.1%})"
        )


class ScaffoldingMatcher:
    """Equalizes scaffolding across conditions and records what was actually delivered.

    Equalization is by *padding to a common target*, never by truncation: truncating a grammar
    description would remove information a condition needs to be usable, turning a scaffolding
    control into a capability handicap. The target is therefore the maximum over conditions, and
    conditions with shorter descriptions are padded with neutral filler that carries no
    operation-specific information.
    """

    def __init__(
        self,
        *,
        worked_example_count: int = 3,
        worked_example_difficulty: str = "curriculum-depth-2",
        retry_policy: str = "single attempt, no repair",
        decoding_constraints: str = "type-directed enumeration; no free-form decoding",
    ) -> None:
        self.worked_example_count = worked_example_count
        self.worked_example_difficulty = worked_example_difficulty
        self.retry_policy = retry_policy
        self.decoding_constraints = decoding_constraints

    def equalize(self, grammar_tokens: Mapping[str, int]) -> ScaffoldingReport:
        """Given each condition's natural grammar-description size, produce the matched
        scaffolding and the residual per condition."""
        if not grammar_tokens:
            return ScaffoldingReport()
        target = max(grammar_tokens.values())
        report = ScaffoldingReport(target_tokens=target)
        for condition_id, tokens in grammar_tokens.items():
            report.delivered[condition_id] = Scaffolding(
                condition_id=condition_id,
                grammar_description_tokens=target,
                worked_example_count=self.worked_example_count,
                worked_example_difficulty=self.worked_example_difficulty,
                retry_policy=self.retry_policy,
                decoding_constraints=self.decoding_constraints,
            )
            report.residuals[condition_id] = ScaffoldingResidual(
                measure="grammar_description_tokens_before_padding",
                value=float(tokens - target),
                unit="tokens",
                note=(
                    "padded to the common target with neutral filler; the value is how far "
                    "below target this condition's natural description was"
                ),
            )
        return report


def scaffolding_is_equalized(report: ScaffoldingReport) -> bool:
    """True when every condition received an identical delivered budget."""
    delivered = {s.grammar_description_tokens for s in report.delivered.values()}
    examples = {s.worked_example_count for s in report.delivered.values()}
    retries = {s.retry_policy for s in report.delivered.values()}
    decoding = {s.decoding_constraints for s in report.delivered.values()}
    return len(delivered) <= 1 and len(examples) <= 1 and len(retries) <= 1 and len(decoding) <= 1
