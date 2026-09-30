"""UniversalDRM Python SDK (§20.1)."""
from .client import Client
from .assets import AssetsModule
from .shares import SharesModule

__all__ = ["Client", "AssetsModule", "SharesModule"]
