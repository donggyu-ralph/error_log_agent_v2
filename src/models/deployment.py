"""Deployment models."""
from typing import Optional

from pydantic import BaseModel


class DeploymentInfo(BaseModel):
    staging_namespace: str = ""
    staging_deployment: str = ""
    production_namespace: str = ""
    production_deployment: str = ""
    image_tag: str = ""
    harbor_image: str = ""  # harbor:8880/custom/xxx:tag
    previous_image: Optional[str] = None  # For rollback
