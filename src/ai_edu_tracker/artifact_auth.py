"""Canonical HMAC authentication for validated artifacts."""

from __future__ import annotations

import hmac
import json
from hashlib import sha256

from .models import ValidatedArtifact
from .state import artifact_hmac_key


def sign_artifact(artifact: ValidatedArtifact) -> ValidatedArtifact:
    """Return a copy carrying an HMAC over every field except the MAC itself."""
    mac = hmac.new(artifact_hmac_key(), _canonical_payload(artifact), sha256).hexdigest()
    return artifact.model_copy(update={"mac": mac})


def verify_artifact(artifact: ValidatedArtifact) -> bool:
    """Constant-time check of an artifact MAC before any replay-related processing."""
    expected = hmac.new(artifact_hmac_key(), _canonical_payload(artifact), sha256).hexdigest()
    return hmac.compare_digest(expected, artifact.mac)


def _canonical_payload(artifact: ValidatedArtifact) -> bytes:
    payload = artifact.model_dump(mode="json", exclude={"mac"})
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
