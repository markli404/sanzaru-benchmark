"""Rendering: the result page the browser reads, and the console log the terminal reads."""

from .log import block, compile_text
from .page import write_page

__all__ = ["block", "compile_text", "write_page"]
