from __future__ import annotations

import re


PASSWORD_POLICY_MESSAGE = "密码必须至少 8 位，并包含大写字母、小写字母和数字"

_PASSWORD_POLICY_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$")


def get_password_validation_error(password: str) -> str | None:
    normalized_password = password.strip()
    if not normalized_password:
        return "密码不能为空"
    if not _PASSWORD_POLICY_PATTERN.match(normalized_password):
        return PASSWORD_POLICY_MESSAGE
    return None
