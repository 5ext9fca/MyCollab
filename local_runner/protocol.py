"""复用无 Django 依赖的版本化协议，避免两端校验漂移。"""
from backend.agent_bridge.protocol import (  # noqa: F401
    KINDS, INPUT_LIMIT, RESULT_LIMIT, ProtocolError, bounded_json, validate_result, validate_evidence,
)
