import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    """Runtime settings, read from the environment by ``Settings.from_env``."""

    mongodb_uri: str
    api_token: str
    mongodb_db: str = "travel_planner"
    web_origins: list[str] = field(default_factory=lambda: ["http://localhost:3001"])
    link_previews: bool = True

    @classmethod
    def from_env(cls) -> Settings:
        missing = [name for name in ("MONGODB_URI", "API_TOKEN") if not os.environ.get(name)]
        if missing:
            raise RuntimeError(
                f"Missing required environment variable(s): {', '.join(missing)}. "
                "Copy .env.example to .env and fill it in."
            )
        origins = os.environ.get("WEB_ORIGIN", "http://localhost:3001")
        return cls(
            mongodb_uri=os.environ["MONGODB_URI"],
            api_token=os.environ["API_TOKEN"],
            mongodb_db=os.environ.get("MONGODB_DB", "travel_planner"),
            web_origins=[o.strip() for o in origins.split(",") if o.strip()],
            link_previews=os.environ.get("LINK_PREVIEWS", "true").lower()
            not in ("0", "false", "no"),
        )
