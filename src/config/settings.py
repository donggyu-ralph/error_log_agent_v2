"""Configuration management using Pydantic Settings."""
import os
import re
from pathlib import Path
from functools import lru_cache

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


def _resolve_env_vars(obj):
    """Recursively resolve ${ENV_VAR} placeholders with environment variables."""
    if isinstance(obj, str):
        pattern = re.compile(r'\$\{(\w+)\}')
        def replace(m):
            return os.environ.get(m.group(1), m.group(0))
        return pattern.sub(replace, obj)
    elif isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_env_vars(item) for item in obj]
    return obj


def _load_yaml_config() -> dict:
    config_path = Path(__file__).parent.parent.parent / "config.yaml"
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}
    return _resolve_env_vars(raw)


class LogSourceConfig(BaseSettings):
    type: str = "k8s_pod"
    namespace: str = ""
    label_selector: str = ""
    since_seconds: int = 120
    host: str = ""
    user: str = ""
    log_path: str = ""


class LogCollectorSettings(BaseSettings):
    interval_seconds: int = 120
    sources: list[dict] = []
    log_levels: list[str] = ["ERROR", "CRITICAL"]


class K8sTargetSettings(BaseSettings):
    namespace: str = "pipeline"
    deployment: str = "data-pipeline"
    staging_namespace: str = "pipeline-staging"


class HarborTargetSettings(BaseSettings):
    project: str = "custom"
    image_name: str = "data-pipeline"


class TargetProjectSettings(BaseSettings):
    name: str = "data-pipeline-service"
    git_repo: str = ""
    root_path: str = "/workspace/data-pipeline-service"
    k8s: K8sTargetSettings = K8sTargetSettings()
    harbor: HarborTargetSettings = HarborTargetSettings()
    exclude_paths: list[str] = ["venv/", "__pycache__/", ".git/", "k8s/"]


class LLMSettings(BaseSettings):
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    max_tokens: int = 4096
    temperature: float = 0.0


class WebSearchSettings(BaseSettings):
    enabled: bool = True
    provider: str = "tavily"
    max_results: int = 5


class SlackSettings(BaseSettings):
    enabled: bool = True
    channel: str = "#error-log-agent"
    approval_timeout_seconds: int = 3600
    app_token: str = Field(default="", alias="SLACK_APP_TOKEN")
    bot_token: str = Field(default="", alias="SLACK_BOT_TOKEN")
    signing_secret: str = Field(default="", alias="SLACK_SIGNING_SECRET")

    model_config = {"populate_by_name": True, "extra": "ignore"}


class DeployerSettings(BaseSettings):
    staging_verify_seconds: int = 60
    staging_timeout_seconds: int = 120
    production_rollout_timeout: int = 300
    auto_rollback: bool = True


class DatabaseSettings(BaseSettings):
    host: str = "postgres.data.svc"
    port: int = 5432
    database: str = "error_log_agent"
    user: str = Field(default="admin", alias="PG_USER")
    password: str = Field(default="", alias="PG_PASSWORD")

    model_config = {"populate_by_name": True, "extra": "ignore"}

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class HarborSettings(BaseSettings):
    url: str = Field(default="http://192.168.50.10:8880", alias="HARBOR_URL")
    user: str = Field(default="admin", alias="HARBOR_USER")
    password: str = Field(default="", alias="HARBOR_PASSWORD")


class GitHubSettings(BaseSettings):
    token: str = Field(default="", alias="GITHUB_TOKEN")
    user: str = Field(default="", alias="GITHUB_USER")

    model_config = {"populate_by_name": True, "extra": "ignore"}


class DashboardSettings(BaseSettings):
    enabled: bool = True
    port: int = 3000


class Settings(BaseSettings):
    agent_name: str = "error-log-agent-v2"
    agent_version: str = "2.0.0"

    log_collector: LogCollectorSettings = LogCollectorSettings()
    target_projects: list[TargetProjectSettings] = [TargetProjectSettings()]
    llm: LLMSettings = LLMSettings()
    web_search: WebSearchSettings = WebSearchSettings()
    slack: SlackSettings = SlackSettings()
    deployer: DeployerSettings = DeployerSettings()
    database: DatabaseSettings = DatabaseSettings()
    harbor: HarborSettings = HarborSettings()
    github: GitHubSettings = GitHubSettings()
    dashboard: DashboardSettings = DashboardSettings()

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    yaml_config = _load_yaml_config()
    overrides = {}

    agent = yaml_config.get("agent", {})
    if "name" in agent:
        overrides["agent_name"] = agent["name"]
    if "version" in agent:
        overrides["agent_version"] = agent["version"]

    if "log_collector" in yaml_config:
        overrides["log_collector"] = LogCollectorSettings(**yaml_config["log_collector"])

    if "target_projects" in yaml_config:
        projects = []
        for tp in yaml_config["target_projects"]:
            k8s = K8sTargetSettings(**tp.pop("k8s", {}))
            harbor = HarborTargetSettings(**tp.pop("harbor", {}))
            projects.append(TargetProjectSettings(k8s=k8s, harbor=harbor, **tp))
        overrides["target_projects"] = projects

    for key in ("llm", "web_search", "deployer", "dashboard"):
        if key in yaml_config:
            cls = {"llm": LLMSettings, "web_search": WebSearchSettings,
                   "deployer": DeployerSettings, "dashboard": DashboardSettings}[key]
            overrides[key] = cls(**yaml_config[key])

    if "slack" in yaml_config:
        overrides["slack"] = SlackSettings(**yaml_config["slack"])

    if "database" in yaml_config:
        overrides["database"] = DatabaseSettings(**yaml_config["database"])

    return Settings(**overrides)
