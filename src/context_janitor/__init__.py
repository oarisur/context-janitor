"""Context Janitor package."""

import logging

__version__ = "1.0.0rc5"

logging.getLogger("context_janitor").addHandler(logging.NullHandler())
