"""UniversalDRM: view PDFs, images, text and video in the browser without handing over the file.

Server side, :class:`Renderer` turns documents into page images with a watermark
burned into the pixels. Client side, ``static/universal-drm.js`` displays them on
canvases and adds the viewer protections. See README.md for what this does and
does not protect against.
"""
import os
from .render import IMAGE_MIMES, PAGE_MIMES, Renderer, kind
from .watermark import burn

__version__ = "0.1.0"
__all__ = ["IMAGE_MIMES", "PAGE_MIMES", "Renderer", "burn", "kind", "static_dir"]


def static_dir():
    """Directory holding universal-drm.js and universal-drm.css, for your web framework to serve."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
