"""A fixed-weights language model in the model role (spec §17; roadmap EXP-002; ADR-0022).

The adapter is deliberately narrow. The model is a **proposer**: it is shown the genome's grammar
(padded to the scaffolding target), a fixed number of worked examples, and a task's *visible*
examples; it answers with text; the genome's projection parses the text into a K0 term; the
term is typechecked and run on the visible examples. That is the whole tool interface (`none`
in the identity): no code execution, no tool calls, no channel by which the model could reach
the evaluator, and no hidden input on any surface it sees. The repair loop feeds back a failing
*visible* example only. Hidden inputs stay behind the evaluator, sealed ones doubly so
(`evaluator/holdout.py`).

Backends are the second layer. `ScriptedBackend` is deterministic and stdlib-only, for tests
and for proving the ADR-0007 interface property. `HTTPBackend` talks to any OpenAI-compatible
endpoint (a local `llama.cpp` or vLLM server, or a hosted model) with `urllib` — no new
dependency, per ADR-0002. The candidate sandbox denies it network access, and that denial is
correct: a model that needs the network is called **outside** the boundary through
`RecordingBackend`, which writes every prompt and completion to a `Transcript`, and the
condition job **inside** the boundary re-derives every scientific quantity from that transcript
through `ReplayBackend`. The transcript is an artifact: content-hashed, leak-checked, and the
thing a replay is checked against.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import urllib.error
import urllib.request
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from ..bsir.projections import Projection, get_projection, token_count
from ..kernel import Kernel, OpSig, Program
from ..kernel.typecheck import is_well_typed
from ..kernel.values import render
from ..solver import SearchBudget, SearchResult
from ..tasks.families import Task
from .identity import ModelIdentity

#: Filler used to pad a grammar description up to the scaffolding target. Carries no
#: operation-specific information, which is the scaffolding matcher's requirement.
NEUTRAL_FILLER = "pad"


# --- completions and backends -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    #: `reported` when the backend returned real usage, `proxy` when counted by the surface
    #: tokenizer. A ledger built on proxy counts says so (ADR-0007's residual, restated).
    usage_source: str = "reported"
    finish_reason: str = "stop"


class Backend(Protocol):
    name: str
    requires_network: bool

    def complete(
        self, prompt: str, *, max_tokens: int, temperature: float, seed: int,
        context: Mapping[str, Any] | None = None,
    ) -> Completion:  # pragma: no cover - protocol
        ...


def proxy_tokens(text: str) -> int:
    return token_count(text)


class ScriptedBackend:
    """Deterministic backend for tests: `script(prompt, seed) -> text`."""

    name = "scripted"
    requires_network = False

    def __init__(self, script: Callable[[str, int], str]) -> None:
        self.script = script
        self.calls = 0

    def complete(self, prompt, *, max_tokens, temperature, seed, context=None) -> Completion:
        self.calls += 1
        text = self.script(prompt, seed)
        return Completion(text, proxy_tokens(prompt), proxy_tokens(text), usage_source="proxy")


class TranscriptMiss(RuntimeError):
    """A replay asked for a prompt the transcript never saw. Never absorbed: a job that
    silently substitutes an empty completion is not a replay."""


@dataclass(slots=True)
class Transcript:
    """Every prompt and completion of one `(condition, seed)`, in order."""

    model_identity_hash: str
    backend: str = ""
    exchanges: list[dict] = field(default_factory=list)

    def record(
        self, *, prompt: str, completion: Completion, context: Mapping[str, Any] | None
    ) -> None:
        context = dict(context or {})
        self.exchanges.append({
            "task_id": context.get("task_id"),
            "sample_index": context.get("sample_index"),
            "prompt_sha256": prompt_hash(prompt),
            "prompt": prompt,
            "response": completion.text,
            "input_tokens": completion.input_tokens,
            "output_tokens": completion.output_tokens,
            "usage_source": completion.usage_source,
            "finish_reason": completion.finish_reason,
        })

    def content_hash(self) -> str:
        payload = json.dumps(self.exchanges, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def visible_text(self) -> str:
        """Everything the model saw and said, for the leak check."""
        return "\n".join(f"{e['prompt']}\n{e['response']}" for e in self.exchanges)

    def to_record(self) -> dict:
        return {
            "model_identity_hash": self.model_identity_hash,
            "backend": self.backend,
            "exchanges": list(self.exchanges),
            "content_hash": self.content_hash(),
        }

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_record(), indent=1, sort_keys=True))
        return path

    @classmethod
    def load(cls, path: Path) -> "Transcript":
        data = json.loads(Path(path).read_text())
        transcript = cls(data["model_identity_hash"], data.get("backend", ""),
                         list(data["exchanges"]))
        expected = data.get("content_hash")
        if expected and expected != transcript.content_hash():
            raise ValueError(f"transcript {path} does not hash to the value it carries")
        return transcript


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()


class ReplayBackend:
    """Serve recorded completions, in recorded order, keyed by prompt hash."""

    name = "replay"
    requires_network = False

    def __init__(self, transcript: Transcript) -> None:
        self.transcript = transcript
        self._queues: dict[str, deque] = {}
        for exchange in transcript.exchanges:
            self._queues.setdefault(exchange["prompt_sha256"], deque()).append(exchange)

    def complete(self, prompt, *, max_tokens, temperature, seed, context=None) -> Completion:
        queue = self._queues.get(prompt_hash(prompt))
        if not queue:
            raise TranscriptMiss(
                f"no recorded completion for this prompt (task {dict(context or {}).get('task_id')}"
                f", sample {dict(context or {}).get('sample_index')}); the transcript was "
                "recorded against a different prompt, model or scaffolding"
            )
        e = queue.popleft()
        return Completion(e["response"], int(e["input_tokens"]), int(e["output_tokens"]),
                          e.get("usage_source", "reported"), e.get("finish_reason", "stop"))


class RecordingBackend:
    """Wrap a live backend and write everything to a transcript."""

    def __init__(self, inner: Backend, transcript: Transcript) -> None:
        self.inner = inner
        self.transcript = transcript
        self.name = f"recording({inner.name})"
        self.requires_network = inner.requires_network
        transcript.backend = inner.name

    def complete(self, prompt, *, max_tokens, temperature, seed, context=None) -> Completion:
        completion = self.inner.complete(
            prompt, max_tokens=max_tokens, temperature=temperature, seed=seed, context=context
        )
        self.transcript.record(prompt=prompt, completion=completion, context=context)
        return completion


class HTTPBackend:
    """An OpenAI-compatible chat-completions endpoint, via the standard library.

    The API key is read from an environment variable, never passed as a value: `run_isolated`
    clears the child's environment, and a key that must be in the environment to work cannot
    be in the environment of a process behind the candidate boundary. Inside the sandbox the
    very first `urllib.Request` audit event is denied — `tests/integrity/test_model_boundary.py`
    pins that.
    """

    name = "http"
    requires_network = True

    def __init__(
        self,
        endpoint: str,
        model: str,
        *,
        api_key_env: str = "BESTSAD_MODEL_API_KEY",
        timeout_s: float = 120.0,
        path: str = "/v1/chat/completions",
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key_env = api_key_env
        self.timeout_s = timeout_s
        self.path = path

    def complete(self, prompt, *, max_tokens, temperature, seed, context=None) -> Completion:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "seed": seed,
        }
        headers = {"Content-Type": "application/json"}
        key = os.environ.get(self.api_key_env)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        request = urllib.request.Request(
            self.endpoint + self.path, data=json.dumps(payload).encode(), headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            body = json.load(response)
        choice = body["choices"][0]
        text = choice.get("message", {}).get("content") or choice.get("text") or ""
        usage = body.get("usage") or {}
        if "prompt_tokens" in usage and "completion_tokens" in usage:
            return Completion(text, int(usage["prompt_tokens"]), int(usage["completion_tokens"]),
                              "reported", choice.get("finish_reason", "stop"))
        return Completion(text, proxy_tokens(prompt), proxy_tokens(text), "proxy",
                          choice.get("finish_reason", "stop"))


# --- the adapter -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SampleBudget:
    """How much a task may cost in model calls. Declared per run and recorded in the manifest."""

    #: Total completions per task, feedback rounds included.
    max_samples: int = 8
    #: How many failed attempts per task are shown their failing *visible* example. Beyond
    #: this, further samples are fresh draws with no feedback.
    repair_rounds: int = 2
    max_output_tokens: int = 256
    temperature: float = 0.2

    def __post_init__(self) -> None:
        if self.max_samples < 1:
            raise ValueError("max_samples must be at least 1")
        if self.repair_rounds < 0:
            raise ValueError("repair_rounds cannot be negative")


def _sample_seed(seed: int, task_id: str, index: int) -> int:
    digest = hashlib.sha256(f"{seed}:{task_id}:{index}".encode()).hexdigest()
    return int(digest[:8], 16)


_FENCE = re.compile(r"```[a-zA-Z0-9_-]*\n(.*?)```", re.S)
_LABEL = re.compile(r"^\s*(program|answer|output)\s*[:=]\s*", re.I)


def extract_program_text(text: str) -> str:
    """The one line of program in a completion: the first fenced block if any, else the first
    non-empty line, with a leading `Program:` label stripped."""
    fenced = _FENCE.search(text)
    body = fenced.group(1) if fenced else text
    for line in body.splitlines():
        line = _LABEL.sub("", line).strip()
        if line:
            return line
    return ""


def primitive_symbol(primitive_id: str) -> str:
    """A lexer-safe surface symbol for a genome primitive.

    Primitive ids are `prim:<name>`, and `:` is one of the projection lexer's structural
    characters, so an id rendered as-is splits into three tokens and cannot be parsed back.
    The enumerator never parses, only renders for token counting, which is why this went
    unnoticed; a model's output must round-trip.
    """
    return primitive_id.replace(":", "_")


def projection_for(name: str, primitive_sigs: Mapping[str, OpSig] | None) -> Projection:
    """The genome's projection with a symbol and an arity for each primitive, so a primitive
    application renders as one token and parses back into the same term."""
    sigs = dict(primitive_sigs or {})
    projection = get_projection(name, {op: primitive_symbol(op) for op in sigs})
    arities = getattr(projection, "_primitive_arity", None)
    if arities is not None and sigs:
        arities.update({op: len(sig.params) for op, sig in sigs.items()})
    return projection


class LLMAdapter:
    """A fixed-weights language model proposing programs in a genome's projection."""

    def __init__(
        self,
        *,
        kernel: Kernel,
        projection: Projection,
        vocabulary: Sequence[str],
        primitive_sigs: Mapping[str, OpSig] | None,
        identity: ModelIdentity,
        backend: Backend,
        budget: SampleBudget,
        kernel_fuel: int,
        seed: int,
        scaffolding: Mapping[str, Any] | None = None,
        worked_examples: Sequence[tuple[Task, Program]] = (),
    ) -> None:
        if not identity.is_language_model:
            raise ValueError("LLMAdapter needs a fixed_weights_llm identity")
        if projection.name not in identity.supported_projections:
            raise ValueError(
                f"model {identity.model_id} does not support projection {projection.name!r}"
            )
        self.kernel = kernel
        self.projection = projection
        self.vocabulary = tuple(vocabulary)
        self.primitive_sigs = dict(primitive_sigs or {})
        self.identity = identity
        self.backend = backend
        self.budget = budget
        self.fuel = kernel_fuel
        self.seed = seed
        self.scaffolding = dict(scaffolding or {})
        self.worked_examples = tuple(worked_examples)

    # -- prompt construction ---------------------------------------------------------------

    def grammar_description(self) -> str:
        """The grammar, padded to the scaffolding target (condition H, confound C3). Padding
        is with neutral filler; the target is what the matcher logged as delivered."""
        text = self.projection.describe_grammar()
        target = int(self.scaffolding.get("grammar_description_tokens") or 0)
        have = token_count(text)
        if target > have:
            text = text + "\n" + " ".join([NEUTRAL_FILLER] * (target - have))
        return text

    def delivered_grammar_tokens(self) -> int:
        return token_count(self.grammar_description())

    def prompt_header(self) -> str:
        count = int(self.scaffolding.get("worked_example_count") or len(self.worked_examples))
        lines = [
            f"You write programs for the K0 kernel in the `{self.projection.name}` projection.",
            "Operations available:",
            self.grammar_description(),
            "Answer with exactly one program body on one line and nothing else.",
            "",
        ]
        for task, program in self.worked_examples[:count]:
            lines.append(f"Example task ({self._signature(task)}):")
            for inputs in task.train_inputs:
                out = self.kernel.execute(task.reference, list(inputs), fuel=self.fuel)
                lines.append(f"  {render_inputs(inputs)} -> {out}")
            lines.append(f"Program: {self.projection.render(program.body)}")
            lines.append("")
        return "\n".join(lines)

    def task_prompt(self, task: Task, expected: Sequence[Any], feedback: Sequence[str]) -> str:
        lines = [f"Task ({self._signature(task)}):"]
        for inputs, out in zip(task.train_inputs, expected):
            lines.append(f"  {render_inputs(inputs)} -> {out}")
        for note in feedback:
            lines.append(note)
        lines.append("Program:")
        return "\n".join(lines)

    @staticmethod
    def _signature(task: Task) -> str:
        params = ", ".join(f"{n}: {t}" for n, t in task.params)
        return f"({params}) -> {task.result_type}"

    # -- solving -----------------------------------------------------------------------------

    def solve(self, task: Task) -> SearchResult:
        """Propose, parse, typecheck, check on the visible examples; repeat within budget.

        The model never sees hidden inputs. Generalisation to the hidden set is decided by the
        evaluator, exactly as for the enumerative synthesizer.
        """
        result = SearchResult(program=None, solved_train=False)
        result.vocabulary_size = len(self.vocabulary)
        expected = []
        for inputs in task.train_inputs:
            outcome = self.kernel.execute(task.reference, list(inputs), fuel=self.fuel)
            result.kernel_steps += outcome.steps
            expected.append(outcome)

        header = self.prompt_header()
        feedback: list[str] = []
        for index in range(self.budget.max_samples):
            prompt = header + self.task_prompt(task, expected, feedback)
            limit = self.identity.context_budget_tokens
            if limit and token_count(prompt) > limit:
                break
            completion = self.backend.complete(
                prompt,
                max_tokens=self.budget.max_output_tokens,
                temperature=self.budget.temperature,
                seed=_sample_seed(self.seed, task.task_id, index),
                context={"task_id": task.task_id, "sample_index": index},
            )
            result.samples += 1
            result.model_input_tokens += completion.input_tokens
            result.model_output_tokens += completion.output_tokens

            text = extract_program_text(completion.text)
            program = self._parse(task, text)
            if program is None:
                result.parse_failures += 1
                self._feed_back(feedback, f"Your answer `{text}` was not a well-typed program.")
                continue

            result.candidates_considered += 1
            result.evaluations += 1
            mismatch = None
            for inputs, want in zip(task.train_inputs, expected):
                got = self.kernel.execute(program, list(inputs), fuel=self.fuel)
                result.kernel_steps += got.steps
                if not want.same_outcome(got):
                    mismatch = (inputs, want, got)
                    break
            if mismatch is None:
                result.program = program
                result.solved_train = True
                result.emitted_size = program.size()
                result.tokens_at_solve = result.model_input_tokens + result.model_output_tokens
                return result
            inputs, want, got = mismatch
            self._feed_back(
                feedback,
                f"Your answer `{text}` was wrong on {render_inputs(inputs)}: expected {want}, "
                f"got {got}.",
            )
        return result

    def _feed_back(self, feedback: list[str], note: str) -> None:
        if len(feedback) < self.budget.repair_rounds:
            feedback.append(note)
        else:
            feedback.clear()

    def _parse(self, task: Task, text: str) -> Program | None:
        if not text:
            return None
        try:
            term = self.projection.parse(text)
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            return None
        program = Program(task.params, term, task.result_type)
        try:
            if not is_well_typed(program, self.primitive_sigs):
                return None
        except (KeyError, IndexError, AttributeError, RecursionError):
            return None
        return program

    # -- contract ----------------------------------------------------------------------------

    def contract(self) -> dict:
        return {
            "kind": self.identity.kind,
            "model_identity_hash": self.identity.hash(),
            "supported_projections": list(self.identity.supported_projections),
            "projection": self.projection.name,
            "context_budget_tokens": self.identity.context_budget_tokens,
            "tokenizer_id": self.identity.tokenizer_id,
            "constrained_decoding": self.identity.constrained_decoding,
            "logprob_access": self.identity.logprob_access,
            "mode": self.identity.mode,
            "deterministic": not self.backend.requires_network,
            "tool_interface": self.identity.tool_interface,
            "backend": self.backend.name,
            "requires_network": self.backend.requires_network,
            "sample_budget": asdict(self.budget),
            "delivered_grammar_tokens": self.delivered_grammar_tokens(),
            "worked_examples": len(self.worked_examples),
        }


def render_inputs(inputs: Sequence[Any]) -> str:
    return ", ".join(render(v) for v in inputs)


# --- specs -----------------------------------------------------------------------------------


def resolve_script(dotted: str) -> Callable[[str, int], str]:
    """`module:function` — a scripted backend must be nameable in JSON so it can cross the
    process boundary and sit in a checkpoint key."""
    module_name, _, attr = dotted.partition(":")
    if not module_name or not attr:
        raise ValueError(f"script must be 'module:function', got {dotted!r}")
    return getattr(importlib.import_module(module_name), attr)


def build_backend(spec: Mapping[str, Any] | None) -> Backend:
    spec = dict(spec or {})
    kind = spec.get("kind")
    if kind == "scripted":
        return ScriptedBackend(resolve_script(spec["script"]))
    if kind == "replay":
        return ReplayBackend(Transcript.load(Path(spec["transcript"])))
    if kind == "http":
        return HTTPBackend(
            spec["endpoint"], spec["model"],
            api_key_env=spec.get("api_key_env", "BESTSAD_MODEL_API_KEY"),
            timeout_s=float(spec.get("timeout_s", 120.0)),
            path=spec.get("path", "/v1/chat/completions"),
        )
    raise ValueError(f"unknown backend kind {kind!r}; expected scripted, replay or http")


def build_llm_adapter(
    spec: Mapping[str, Any],
    *,
    kernel: Kernel,
    vocabulary: Sequence[str],
    primitive_sigs: Mapping[str, OpSig] | None,
    budget: SearchBudget,
    seed: int,
    projection_name: str,
    scaffolding: Mapping[str, Any] | None,
    worked_examples: Sequence[tuple[Task, Program]],
    backend: Backend | None = None,
) -> LLMAdapter:
    identity = ModelIdentity.from_record(spec["identity"])
    return LLMAdapter(
        kernel=kernel,
        projection=projection_for(projection_name, primitive_sigs),
        vocabulary=vocabulary,
        primitive_sigs=primitive_sigs,
        identity=identity,
        backend=backend or build_backend(spec.get("backend")),
        budget=SampleBudget(**dict(spec.get("budget") or {})),
        kernel_fuel=budget.kernel_fuel,
        seed=seed,
        scaffolding=scaffolding,
        worked_examples=worked_examples,
    )


def scaffolding_policy(spec: Mapping[str, Any] | None) -> dict:
    """The `ScaffoldingMatcher` keyword arguments a spec implies, so condition H describes the
    retry and decoding policy the model actually ran under rather than the enumerator's."""
    spec = dict(spec or {})
    if spec.get("kind") != "fixed_weights_llm":
        return {}
    budget = SampleBudget(**dict(spec.get("budget") or {}))
    return {
        "retry_policy": (
            f"up to {budget.max_samples} samples per task; the first {budget.repair_rounds} "
            "failures are shown their failing visible example"
        ),
        "decoding_constraints": (
            f"free-form text at temperature {budget.temperature}, parsed by the genome "
            "projection and typechecked before execution; no grammar-constrained decoding"
        ),
    }
