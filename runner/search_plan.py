"""Closed, versioned search plan. An example/draft is never an authorization."""
from hashlib import sha256
from typing import Literal, Annotated, Self
from pydantic import Field, model_validator
import rfc8785
from schemas.contracts import ClosedModel, Seed, Identifier, ExperimentConfig, Config, config_hash
from schemas.split import SPLIT_ID, split_hash

EVALUATION_HASH = '68d34bb53116e8d1debc77b65b08320c52836a5b31414a7a32239b33b5d79bc7'


class Parameters(ClosedModel):
    learning_rate: Literal[0.0003, 0.001, 0.003]
    weight_decay: Literal[0.0, 0.0001, 0.001]
    augmentation: Literal['none', 'basic']

    @model_validator(mode='before')
    @classmethod
    def reject_bool(cls, value):
        if isinstance(value, dict) and any(type(value.get(k)) is bool for k in ('learning_rate','weight_decay')):
            raise ValueError('boolean is not a numeric parameter')
        return value


class Trial(ClosedModel):
    arm: Literal['random', 'ai']
    seed: Seed
    random_parameters: Parameters | None

    @model_validator(mode='after')
    def frozen_random(self) -> Self:
        if (self.arm == 'random') != (self.random_parameters is not None):
            raise ValueError('random trials need precommitted parameters; AI trials do not')
        return self


class SearchPlan(ClosedModel):
    plan_version: Literal['1.0.0']
    status: Literal['draft', 'approved_for_future_execution']
    campaign_id: Annotated[Identifier, Field(max_length=55)]
    task_id: Identifier
    role: Identifier
    worker_id: Literal['worker-01', 'worker-02']
    max_starts: Annotated[int, Field(ge=1,le=6)]
    epochs: Annotated[int, Field(ge=3,le=3)]
    batch_size: Annotated[int, Field(ge=128,le=128)]
    split_seed: Annotated[int, Field(ge=20261003,le=20261003)]
    split_id: Literal['cifar10-train45000-val5000-pcg64-v1']
    split_indices_hash: str
    model: Literal['small-cnn-v1']
    dataset: Literal['cifar10-python-v1']
    timeout_seconds: Annotated[int, Field(ge=300,le=300)]
    evaluation_sha256: Literal['68d34bb53116e8d1debc77b65b08320c52836a5b31414a7a32239b33b5d79bc7']
    candidate_space: dict[str, list[float | str]]
    trials: tuple[Trial, ...]

    @model_validator(mode='after')
    def exact_scope(self) -> Self:
        expected={'learning_rate':[0.0003,0.001,0.003], 'weight_decay':[0.0,0.0001,0.001], 'augmentation':['none','basic']}
        if self.candidate_space != expected:
            raise ValueError('candidate space must equal the closed 18-member grid')
        if len(self.trials) != self.max_starts:
            raise ValueError('trial schedule must match max_starts')
        if any(sum(t.arm==arm for t in self.trials)>3 for arm in ('random','ai')):
            raise ValueError('at most three starts per arm per worker')
        if self.split_indices_hash != split_hash():
            raise ValueError('split hash differs from fixed contract')
        if self.status=='approved_for_future_execution' and self.role=='UNASSIGNED':
            raise ValueError('worker role must be resolved before future approval')
        return self

    def digest(self):
        return sha256(rfc8785.dumps(self.model_dump(mode='json'))).hexdigest()


def bind_request(plan, number, raw_parameters, commit, worker_id, role):
    """Same pure binding runs on both sides of the process boundary."""
    if (plan.worker_id,plan.role)!=(worker_id,role):
        raise ValueError('plan worker/role mismatch')
    if not 1<=number<=plan.max_starts:
        raise ValueError('plan start limit exceeded')
    parameters=Parameters.model_validate_json(raw_parameters)
    trial=plan.trials[number-1]
    if trial.arm=='random' and parameters!=trial.random_parameters:
        raise ValueError('random request differs from precommitted draw')
    cfg=Config.model_validate_json(__import__('json').dumps({**parameters.model_dump(), 'seed':trial.seed,
        'epochs':plan.epochs,'batch_size':plan.batch_size,'split_seed':plan.split_seed,
        'model':plan.model,'dataset':plan.dataset,'timeout_seconds':plan.timeout_seconds}))
    identity=f'{plan.campaign_id}-s{number}'
    obj={'schema_version':'1.0.0','experiment_id':identity,'seed':trial.seed,'config':cfg.model_dump(),
        'code_version':commit,'config_hash':config_hash(cfg),'status':'approved',
        'validation':{'split_id':SPLIT_ID,'split_indices_hash':split_hash(),'metric':'accuracy','objective':'maximize'},
        'runtime':{'timeout_seconds':300,'device_class':'cuda'}}
    return ExperimentConfig.model_validate_json(__import__('json').dumps(obj))
