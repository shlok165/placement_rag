import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

WEIGHTS_FILE = Path(__file__).with_name("weights.toml")


class FusionConfig(BaseModel):
    method: Literal["rrf", "weighted"] = "rrf"
    rrf_k: int = Field(60, ge=1)
    semantic_weight: float = Field(1.0, ge=0)
    keyword_weight: float = Field(1.0, ge=0)


class RerankConfig(BaseModel):
    relevance: float = Field(ge=0)
    skills: float = Field(ge=0)
    preferences: float = Field(ge=0)
    profile: float = Field(ge=0)
    urgency: float = Field(ge=0)
    # Closeness to the postings the student saved, applied to or liked. 0 turns it off.
    taste: float = Field(0.0, ge=0)
    urgency_window_days: int = Field(14, ge=1)
    similarity_floor: float = 0.5
    similarity_ceiling: float = 0.85

    @model_validator(mode="after")
    def _urgency_is_smallest(self) -> "RerankConfig":
        weights = (self.relevance, self.skills, self.preferences, self.profile, self.taste)
        others = [w for w in weights if w > 0]
        if self.urgency and any(self.urgency >= w for w in others):
            raise ValueError("urgency must stay below the other weights")
        return self


class TasteConfig(BaseModel):
    """How events become a taste vector. Weights are per kind; thumb_down is subtracted."""

    enabled: bool = True
    half_life_days: float = Field(30.0, gt=0)
    lookback_days: int = Field(180, ge=1)
    max_events: int = Field(200, ge=1)
    save: float = Field(1.0, ge=0)
    apply_clicked: float = Field(1.5, ge=0)
    thumb_up: float = Field(1.0, ge=0)
    thumb_down: float = Field(0.5, ge=0)

    def weight(self, kind: str) -> float:
        signed = {
            "save": self.save,
            "apply_clicked": self.apply_clicked,
            "thumb_up": self.thumb_up,
            "thumb_down": -self.thumb_down,
        }
        return signed.get(kind, 0.0)


class CrossEncoderConfig(BaseModel):
    enabled: bool = False
    model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    top_n: int = Field(20, ge=2, le=100)


class SearchConfig(BaseModel):
    candidates: int = Field(50, ge=1, le=200)
    min_similarity: float = 0.0
    weak_similarity: float = 0.58
    fusion: FusionConfig
    rerank: RerankConfig
    taste: TasteConfig = TasteConfig()
    cross_encoder: CrossEncoderConfig = CrossEncoderConfig()

    def override(self, changes: dict[str, Any]) -> "SearchConfig":
        """Copy with dotted-key changes, for example {"fusion.rrf_k": 30}."""
        data = self.model_dump()
        for key, value in changes.items():
            target = data
            *parents, leaf = key.split(".")
            for parent in parents:
                target = target[parent]
            if leaf not in target:
                raise KeyError(key)
            target[leaf] = value
        return SearchConfig.model_validate(data)


@lru_cache
def get_search_config() -> SearchConfig:
    return SearchConfig.model_validate(tomllib.loads(WEIGHTS_FILE.read_text("utf-8")))
