import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Config:
    enabled: bool = False
    vlm_enabled: bool = False
    endpoint: str = ""
    model: str = ""
    api_key: str = field(default="", repr=False)
    timeout_s: float = 20
    concurrency: int = 2
    max_image_dimension: int = 640
    cooldown_s: float = 30
    requests_per_minute: int = 6
    max_tracks_per_request: int = 4
    max_objects: int = 8
    max_references: int = 3
    response_ttl_s: float = 5
    max_attempts: int = 2
    acceptance: str = "manual"
    gap_s: float = 1
    track_ttl_s: float = 3
    temporal_similarity: float = 0.97
    overlap_iou: float = 0.25
    input_usd_per_million: float | None = None
    output_usd_per_million: float | None = None

    def __post_init__(self):
        import math

        for key in (
            "timeout_s",
            "cooldown_s",
            "response_ttl_s",
            "gap_s",
            "track_ttl_s",
        ):
            value = getattr(self, key)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{key} must be positive and finite")
        for key in (
            "concurrency",
            "requests_per_minute",
            "max_tracks_per_request",
            "max_objects",
            "max_references",
        ):
            if not 1 <= getattr(self, key) <= 100:
                raise ValueError(f"{key} must be 1..100")
        if not 64 <= self.max_image_dimension <= 2048:
            raise ValueError("max_image_dimension must be 64..2048")
        if self.acceptance not in ("manual", "corroborated"):
            raise ValueError("Unsupported acceptance policy")
        if not 0 <= self.temporal_similarity <= 1 or not 0 < self.overlap_iou <= 1:
            raise ValueError("Invalid association gates")
        if self.max_attempts < 1 or self.track_ttl_s < self.gap_s:
            raise ValueError("Invalid retention/attempt limits")
        for value in (self.input_usd_per_million, self.output_usd_per_million):
            if value is not None and (not math.isfinite(value) or value < 0):
                raise ValueError("Invalid API price")
        if self.vlm_enabled:
            u = urlsplit(self.endpoint)
            if (
                u.scheme not in ("http", "https")
                or not u.hostname
                or u.username
                or u.password
                or u.query
                or u.fragment
            ):
                raise ValueError(
                    "IDENTITY_VLM_ENDPOINT must be a credential-free HTTP(S) base URL"
                )
            if not self.model:
                raise ValueError("IDENTITY_VLM_MODEL is required")

    @classmethod
    def from_env(cls):
        def flag(k):
            v = os.getenv(k, "false").lower()
            if v not in ("true", "false", "1", "0"):
                raise ValueError(k + " must be true/false")
            return v in ("true", "1")

        args = {
            "enabled": flag("IDENTITY_EXPERIMENT_ENABLED"),
            "vlm_enabled": flag("IDENTITY_VLM_ENABLED"),
        }
        mapping = {
            "endpoint": ("ENDPOINT", str),
            "model": ("MODEL", str),
            "api_key": ("API_KEY", str),
            "timeout_s": ("TIMEOUT_S", float),
            "concurrency": ("CONCURRENCY", int),
            "max_image_dimension": ("MAX_IMAGE_DIMENSION", int),
            "cooldown_s": ("COOLDOWN_S", float),
            "requests_per_minute": ("REQUESTS_PER_MINUTE", int),
            "response_ttl_s": ("RESPONSE_TTL_S", float),
            "input_usd_per_million": ("INPUT_USD_PER_MILLION", float),
            "output_usd_per_million": ("OUTPUT_USD_PER_MILLION", float),
        }
        for key, (suffix, cast) in mapping.items():
            if "IDENTITY_VLM_" + suffix in os.environ:
                args[key] = cast(os.environ["IDENTITY_VLM_" + suffix])
        args["acceptance"] = os.getenv("IDENTITY_ACCEPTANCE", "manual")
        return cls(**args)

    def public(self):
        from dataclasses import asdict

        d = asdict(self)
        d.pop("api_key")
        d.pop("endpoint")
        d["endpoint_configured"] = bool(self.endpoint)
        return d
