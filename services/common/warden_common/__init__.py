"""warden_common — shared ledger, models, and config for Warden.

This package is imported by BOTH the sandboxed agent and the permissioned
runner. It deliberately contains *no* code that can write to GitHub. The only
GitHub write client in the entire codebase lives in ``warden_runner`` and is
never importable from here. Separation is structural, not a policy flag.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
