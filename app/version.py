"""Single source of truth for the application version.

Kept boot-free (no imports of app.main / soul gates) so ops tooling — the release
preflight, status command, and deploy scripts — can read the version without booting
the app or holding secrets.
"""

__version__ = "0.2.0"
