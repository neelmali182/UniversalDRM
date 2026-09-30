"""UniversalDRM watermarking — visible and forensic."""
from .visible import burn_visible
from .forensic import embed_forensic, extract_forensic

__all__ = ["burn_visible", "embed_forensic", "extract_forensic"]
