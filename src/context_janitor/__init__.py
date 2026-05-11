"""Context Janitor package."""

import logging

__version__ = "0.1.0"

logging.getLogger("context_janitor").addHandler(logging.NullHandler())
