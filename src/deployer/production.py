"""Production deployment utilities."""
from src.config.logging_config import get_logger

logger = get_logger(__name__)

# Production deployment logic is in src/agent/nodes/k8s_deployer.py
