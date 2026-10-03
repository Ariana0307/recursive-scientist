"""G1 v1: strict, finite, closed contracts. No executable agent inputs."""
from hashlib import sha256
from typing import Annotated, Literal, Self
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator, field_validator
import rfc8785
from .split import split_hash

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Commit = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]
Seed = Annotated[int, Field(ge=0, le=2**32-1)]
Seconds = Annotated[float, Field(ge=0)]
Accuracy = Annotated[float, Field(ge=0, le=1)]

class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False, frozen=True)

class Config(ClosedModel):
    seed: Seed
    learning_rate: Annotated[float, Field(ge=1e-5, le=0.1)]
    weight_decay: Annotated[float, Field(ge=0, le=0.01)]
    augmentation: Literal["none", "basic"]
    epochs: Annotated[int, Field(ge=1, le=3)]
    batch_size: Literal[16, 32, 64, 128, 256]
    split_seed: Literal[20261003]
    model: Literal["small-cnn-v1"]
    dataset: Literal["cifar10-python-v1"]
    timeout_seconds: Annotated[int, Field(ge=1, le=300)]

    @field_validator("batch_size", "split_seed", mode="before")
    @classmethod
    def strict_literal_integer(cls, value):
        if type(value) is not int:
            raise ValueError("integer literal required")
        return value

def config_hash(config: Config) -> str:
    """Hash all resolved config fields with the established RFC8785 library."""
    return sha256(rfc8785.dumps(config.model_dump(mode="json"))).hexdigest()

class Identity(ClosedModel):
    schema_version: Literal["1.0.0"]
    experiment_id: Identifier
    seed: Seed
    config: Config
    code_version: Commit
    config_hash: Digest

    @model_validator(mode="after")
    def check_identity(self) -> Self:
        if self.seed != self.config.seed:
            raise ValueError("seed differs from config.seed")
        if self.config_hash != config_hash(self.config):
            raise ValueError("config_hash does not match RFC8785 config bytes")
        return self

class Split(ClosedModel):
    split_id: Literal["cifar10-train45000-val5000-pcg64-v1"]
    split_indices_hash: Digest

    @model_validator(mode="after")
    def check_split(self) -> Self:
        if self.split_indices_hash != split_hash():
            raise ValueError("split_indices_hash does not match the fixed split")
        return self

class ValidationSpec(Split):
    metric: Literal["accuracy"]
    objective: Literal["maximize"]

class RuntimeRequest(ClosedModel):
    timeout_seconds: Annotated[int, Field(ge=1, le=300)]
    device_class: Literal["cuda"]

class ExperimentConfig(Identity):
    status: Literal["proposed", "approved"]
    validation: ValidationSpec
    runtime: RuntimeRequest

    @model_validator(mode="after")
    def check_timeout(self) -> Self:
        if self.runtime.timeout_seconds != self.config.timeout_seconds:
            raise ValueError("runtime timeout differs from hashed config")
        return self

class Metrics(ClosedModel):
    accuracy: Accuracy | None
    loss: Annotated[float, Field(ge=0)] | None

class ValidationResult(Split):
    metrics: Metrics

class RuntimeResult(ClosedModel):
    elapsed_seconds: Seconds | None
    started_at: AwareDatetime | None
    finished_at: AwareDatetime | None
    actual_device: Literal["cuda", "cpu"] | None

    @model_validator(mode="after")
    def check_times(self) -> Self:
        if self.started_at is not None and self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("finished_at precedes started_at")
        return self

class Error(ClosedModel):
    kind: Literal["timeout", "validation", "environment", "execution", "cancelled"]
    message: Annotated[str, Field(min_length=1, max_length=512)]

class Result(Identity):
    status: Literal["succeeded", "failed", "cancelled", "timed_out"]
    validation: ValidationResult
    runtime: RuntimeResult
    error: Error | None

    @model_validator(mode="after")
    def check_outcome(self) -> Self:
        if self.status == "succeeded":
            if self.error is not None or self.validation.metrics.accuracy is None or self.validation.metrics.loss is None:
                raise ValueError("success requires measured accuracy/loss and no error")
            if any(getattr(self.runtime, k) is None for k in ("elapsed_seconds", "started_at", "finished_at", "actual_device")):
                raise ValueError("success requires complete runtime evidence")
            if self.runtime.elapsed_seconds > self.config.timeout_seconds:
                raise ValueError("success cannot exceed the hard timeout")
        else:
            if self.error is None or self.validation.metrics.accuracy is not None or self.validation.metrics.loss is not None:
                raise ValueError("non-success requires error and null metrics; no partial metrics in v1")
            expected = {"timed_out": "timeout", "cancelled": "cancelled"}.get(self.status)
            if expected and self.error.kind != expected:
                raise ValueError("error kind does not match terminal status")
            if self.status == "failed" and self.error.kind in ("timeout", "cancelled"):
                raise ValueError("use explicit timed_out/cancelled status")
        return self

class DecisionValidation(Split):
    metrics: Metrics
    objective: Literal["maximize"]

class DecisionRuntime(ClosedModel):
    elapsed_seconds: Seconds | None

class Decision(Identity):
    status: Literal["propose_next", "stop", "needs_review"]
    validation: DecisionValidation
    runtime: DecisionRuntime
    rationale: Annotated[str, Field(min_length=1, max_length=2000)]
    evidence_result_id: Identifier
    next_experiment_id: Identifier | None
    strategy_version: Identifier

    @model_validator(mode="after")
    def check_next(self) -> Self:
        if self.evidence_result_id != self.experiment_id:
            raise ValueError("v1 evidence_result_id is the source experiment_id")
        if self.status == "propose_next":
            if self.next_experiment_id is None or self.next_experiment_id == self.experiment_id:
                raise ValueError("propose_next requires a new experiment ID")
        elif self.next_experiment_id is not None:
            raise ValueError("stop/needs_review cannot dispatch a next experiment")
        return self

def match_result(request: ExperimentConfig, result: Result) -> None:
    """Required at ingestion; standalone validation cannot establish provenance."""
    for key in ("schema_version", "experiment_id", "seed", "config", "code_version", "config_hash"):
        if getattr(request, key) != getattr(result, key):
            raise ValueError(f"result/request mismatch: {key}")
    if request.validation.split_indices_hash != result.validation.split_indices_hash:
        raise ValueError("result/request split mismatch")
    if result.status == "succeeded" and result.runtime.actual_device != request.runtime.device_class:
        raise ValueError("successful result ran on an unapproved device")

def retry_action(existing: ExperimentConfig, incoming: ExperimentConfig,
                 prior_status: Literal["running", "succeeded", "failed", "cancelled", "timed_out"]) -> str:
    """Pure admission decision; runner must hold a per-ID lock when calling."""
    if existing != incoming:
        raise ValueError("experiment_id conflict: retry must match the complete original request")
    if prior_status == "running":
        return "in_progress"
    if prior_status == "succeeded":
        return "reuse"
    if prior_status in ("failed", "cancelled", "timed_out"):
        return "retry"
    raise ValueError("unknown prior status")
