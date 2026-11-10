"""HTTP pieces shared by the FastAPI services: errors as problem documents and the request log."""

from aireuskadi_http.problems import (
    INVALID_REQUEST,
    NOT_FOUND,
    Problem,
    ValidationProblem,
    install_problem_documents,
    problem,
)
from aireuskadi_http.request_log import install_request_log

__all__ = [
    "INVALID_REQUEST",
    "NOT_FOUND",
    "Problem",
    "ValidationProblem",
    "install_problem_documents",
    "install_request_log",
    "problem",
]
