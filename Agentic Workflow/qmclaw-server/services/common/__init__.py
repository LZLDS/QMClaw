"""
services/common/ - 公共模块

所有服务共享的工具和定义。
"""

from .logging import setup_logging, log_request, log_response, LogContext
from .config import Config, config
from .fallback_manager import FallbackManager, ConnectionState
from .exceptions import (
    ServiceError,
    ConfigError,
    APIError,
    AuthenticationError,
    RateLimitError,
    TimeoutError,
    ModelNotFoundError,
    ProviderNotAvailableError,
)

__all__ = [
    # Logging
    "setup_logging",
    "log_request",
    "log_response",
    "LogContext",
    # Config
    "Config",
    "config",
    # Fallback
    "FallbackManager",
    "ConnectionState",
    # Exceptions
    "ServiceError",
    "ConfigError",
    "APIError",
    "AuthenticationError",
    "RateLimitError",
    "TimeoutError",
    "ModelNotFoundError",
    "ProviderNotAvailableError",
]
