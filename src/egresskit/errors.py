"""Machine-readable exceptions with payload-free messages."""

from __future__ import annotations

from typing import Any

from .models import Decision


class EgressKitError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message}}


class PolicyLoadError(EgressKitError):
    def __init__(self, code: str, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(code, message)
        self.__cause__ = cause


class EgressRefused(EgressKitError):
    def __init__(self, decision: Decision) -> None:
        super().__init__("egress_refused", "egress policy refused the request")
        self.decision = decision

    def to_dict(self) -> dict[str, Any]:
        value = super().to_dict()
        value["error"]["decision"] = self.decision.model_dump(mode="json")
        return value


class SerializationFailed(EgressKitError):
    def __init__(self, *, cause: Exception) -> None:
        super().__init__("serialization_failed", "payload serialization failed after authorization")
        self.__cause__ = cause
