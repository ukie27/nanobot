"""Errors raised by deterministic Career domain rules."""


class CareerDomainError(Exception):
    """Base error that can be safely mapped to a public Problem Details response."""

    code = "career_domain_error"
    status_code = 422

    def __init__(self, detail: str, *, code: str | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        if code is not None:
            self.code = code
