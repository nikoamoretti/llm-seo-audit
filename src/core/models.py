from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class CanonicalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BusinessInput(CanonicalModel):
    business_name: str
    industry: str
    city: str
    website_url: Optional[str] = None
    phone: Optional[str] = None
    demo: bool = False


class BusinessEntity(CanonicalModel):
    business_name: str
    industry: str
    city: str
    website_url: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    service_areas: List[str] = Field(default_factory=list)
    hours: List[str] = Field(default_factory=list)
    service_names: List[str] = Field(default_factory=list)
    faq_questions: List[str] = Field(default_factory=list)
    trust_signals: List[str] = Field(default_factory=list)
    schema_types: List[str] = Field(default_factory=list)
    has_booking_cta: Optional[bool] = None
    has_contact_cta: Optional[bool] = None
    confidence: Dict[str, float] = Field(default_factory=dict)


class CitationRecord(CanonicalModel):
    label: str
    url: Optional[str] = None
    domain: Optional[str] = None
    citation_type: Optional[str] = None
    is_official_domain: Optional[bool] = None


class PromptResult(CanonicalModel):
    provider: str
    query: str
    cluster: Optional[str] = None
    response: Optional[str] = None
    raw_text: Optional[str] = None
    latency_ms: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    mentioned: bool = False
    recommended: bool = False
    cited: bool = False
    cited_official_domain: bool = False
    cited_third_party_domain: bool = False
    position: Optional[int] = None
    visibility_score: float = 0.0
    sentiment: Optional[float] = None
    competitors: List[str] = Field(default_factory=list)
    attributes: List[str] = Field(default_factory=list)
    citations: List[CitationRecord] = Field(default_factory=list)


class CheckDimension(CanonicalModel):
    score: int = 0
    label: str
    description: str
    weight: float = 0.0
    weighted_score: float = 0.0
    checks: Dict[str, Optional[bool]] = Field(default_factory=dict)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    evidence: List[str] = Field(default_factory=list)


class ReadinessResult(CanonicalModel):
    score: int = 0
    dimensions: Dict[str, CheckDimension] = Field(default_factory=dict)


class ProviderVisibility(CanonicalModel):
    visibility_score: float = 0.0
    mention_rate: float = 0.0
    citation_rate: float = 0.0
    avg_position: Optional[float] = None
    total_queries: int = 0
    times_mentioned: int = 0
    times_cited: int = 0
    top_competitors: Dict[str, int] = Field(default_factory=dict)
    attributes_cited: List[str] = Field(default_factory=list)


class ClusterVisibility(CanonicalModel):
    avg_score: float = 0.0
    query_count: int = 0


class VisibilityResult(CanonicalModel):
    score: float = 0.0
    overall_mention_rate: float = 0.0
    dimensions: Dict[str, CheckDimension] = Field(default_factory=dict)
    per_llm: Dict[str, ProviderVisibility] = Field(default_factory=dict)
    per_cluster: Dict[str, ClusterVisibility] = Field(default_factory=dict)
    top_competitors: Dict[str, int] = Field(default_factory=dict)
    attributes_cited: List[str] = Field(default_factory=list)
    prompt_results: List[PromptResult] = Field(default_factory=list)


class Recommendation(CanonicalModel):
    priority: Literal["P0", "P1", "P2"]
    category: str
    title: str
    detail: str = ""
    why_it_matters: str = ""
    evidence: List[str] = Field(default_factory=list)
    impacted_components: List[str] = Field(default_factory=list)
    implementation_hint: str = ""


class ScoreBreakdown(CanonicalModel):
    final: int = 0
    readiness: int = 0
    visibility: float = 0.0
    version: str = "score_v2"
    formula: Optional[str] = None
    penalties: List[Dict[str, Any]] = Field(default_factory=list)


class AuditRun(CanonicalModel):
    mode: Literal["live", "demo"]
    timestamp: datetime
    input: BusinessInput
    entity: BusinessEntity
    score: ScoreBreakdown
    readiness: ReadinessResult
    visibility: VisibilityResult
    recommendations: List[Recommendation] = Field(default_factory=list)
    web_presence: Dict[str, Any] = Field(default_factory=dict)
    api_keys_used: List[str] = Field(default_factory=list)
    queries: List[str] = Field(default_factory=list)
