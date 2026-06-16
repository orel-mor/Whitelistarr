"""Encrypted JSON config store on the data volume.

Non-secret values are stored as-is; secret fields (per ``config_schema``) are
Fernet-encrypted with ``PAL_SECRET_KEY``. Values mirror the env-var string forms so
they pass straight into ``Settings(**values)``.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.config_schema import secret_keys

log = logging.getLogger(__name__)


class ConfigStore:
    def __init__(self, path: str, secret_key: str) -> None:
        if not secret_key:
            raise ValueError("ConfigStore requires a non-empty secret key (PAL_SECRET_KEY).")
        self._path = path
        self._fernet = Fernet(secret_key.encode())
        self._secret_keys = set(secret_keys())

    def exists(self) -> bool:
        return os.path.exists(self._path)

    def _read_raw(self) -> dict[str, Any]:
        if not self.exists():
            return {}
        try:
            with open(self._path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            log.exception("Failed to read config store at %s", self._path)
            return {}

    def load(self) -> dict[str, Any]:
        """Return the stored config with secret fields decrypted to plaintext."""
        data = self._read_raw()
        for field in self._secret_keys:
            token = data.get(field)
            if not token:
                continue
            try:
                data[field] = self._fernet.decrypt(token.encode()).decode()
            except (InvalidToken, AttributeError):
                log.warning("Could not decrypt %s (wrong PAL_SECRET_KEY?); treating as unset", field)
                data[field] = ""
        return data

    def save(self, values: dict[str, Any]) -> None:
        """Merge ``values`` into the store, encrypting secret fields, atomically."""
        merged = self.load()  # decrypted current state, so secrets aren't double-encrypted
        merged.update(values)
        for field in self._secret_keys:
            plain = merged.get(field)
            if plain:
                merged[field] = self._fernet.encrypt(str(plain).encode()).decode()
            elif field in merged:
                merged[field] = ""  # keep empty secrets empty (not encrypted)

        parent = os.path.dirname(self._path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = f"{self._path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, indent=2)
        os.replace(tmp, self._path)
        try:
            os.chmod(self._path, 0o600)
        except OSError:  # e.g. Windows / unsupported fs — best effort
            pass
