from __future__ import annotations

import errno


APP_NAME = "AI Proxy Hub"
APP_SLUG = "ai-proxy-hub"
APP_VERSION = "0.3.2"
APP_AUTHOR = "weicj"
APP_LICENSE_NAME = "Apache-2.0"
APP_LICENSE_URL = "https://www.apache.org/licenses/LICENSE-2.0"
APP_SOURCE_HOST = "GitHub"
APP_REPOSITORY_URL = "https://github.com/weicj/ai-proxy-hub"
APP_RELEASES_URL = "https://github.com/weicj/ai-proxy-hub/releases"
APP_UPDATE_CHANNEL = "manual"
CONFIG_VERSION = 7
DEFAULT_LISTEN_HOST = "127.0.0.1"
DEFAULT_LISTEN_PORT = 8787
DEFAULT_TIMEOUT = 120
DEFAULT_COOLDOWN = 60
DEFAULT_CONFIG_FILENAME = "api-config.json"
DEFAULT_RUNTIME_STATE_SUFFIX = "-state.json"
DEFAULT_CODEX_SWITCH_BACKUP_FILENAME = "codex-switch-backup.json"
DEFAULT_CLAUDE_SWITCH_BACKUP_FILENAME = "claude-switch-backup.json"
DEFAULT_GEMINI_SWITCH_BACKUP_FILENAME = "gemini-switch-backup.json"
LEGACY_APP_NAMES = ("AI API Local Hub",)
LEGACY_APP_SLUGS = ("ai-api-local-hub", "openai-upstream-hub")
STATIC_DIR_ENV_VAR = "AI_PROXY_HUB_STATIC_DIR"
CONFIG_PATH_ENV_VAR = "AI_PROXY_HUB_CONFIG"
LEGACY_STATIC_DIR_ENV_VARS = ("AI_API_LOCAL_HUB_STATIC_DIR",)
LEGACY_CONFIG_PATH_ENV_VARS = ("AI_API_LOCAL_HUB_CONFIG",)
DEFAULT_RETRYABLE_STATUSES = [401, 403, 408, 409, 425, 429, 500, 502, 503, 504]
DEFAULT_ROUTING_MODE = "priority"
DEFAULT_DEFAULT_MODEL_MODE = "upstream"
DEFAULT_ENDPOINT_MODE = "shared"
DEFAULT_WEB_UI_PORT_OFFSET = 10
DEFAULT_SHARED_API_PREFIXES = {
    "openai": "/openai",
    "anthropic": "/claude",
    "gemini": "/gemini",
    "local_llm": "/local",
}
LEGACY_SHARED_API_PREFIXES = {
    "openai": ("/v1",),
    "anthropic": ("/anthropic",),
    "gemini": ("/gemini",),
    "local_llm": (),
}
NATIVE_API_PREFIXES = {
    "openai": "/v1",
    "anthropic": "/v1",
    "gemini": "/v1beta",
    "local_llm": "/v1",
}
DEFAULT_SPLIT_API_PORTS = {
    "openai": DEFAULT_LISTEN_PORT,
    "anthropic": DEFAULT_LISTEN_PORT + 1,
    "gemini": DEFAULT_LISTEN_PORT + 2,
    "local_llm": DEFAULT_LISTEN_PORT + 3,
}
SUPPORTED_UI_LANGUAGES = {"auto", "zh", "en", "ja", "ru", "fr", "de", "es", "pt", "ar"}
SUPPORTED_THEME_MODES = {"auto", "dark", "light", "blue", "green", "amber", "rose", "teal"}
SUPPORTED_CLI_THEME_MODES = {"auto", "dark", "light", "blue", "green", "amber", "rose", "teal"}
UPSTREAM_PROTOCOLS = {"openai", "anthropic", "gemini", "local_llm"}
ROUTING_PROTOCOLS = ("openai", "anthropic", "gemini", "local_llm")
PROTOCOL_TO_CLIENT = {
    "openai": "codex",
    "anthropic": "claude",
    "gemini": "gemini",
    "local_llm": "local_llm",
}
ADDRESS_IN_USE_ERRNOS = {errno.EADDRINUSE, 48, 98, 10048}
IGNORED_SOCKET_ERRNOS = {32, 53, 54, 104, 10053, 10054}
UPSTREAM_PROTOCOL_ORDER = ("openai", "anthropic", "gemini", "local_llm")
UPSTREAM_PROTOCOL_LABELS = {
    "openai": "OpenAI",
    "anthropic": "Claude / Anthropic",
    "gemini": "Gemini",
    "local_llm": "Local LLM",
}
LOCAL_LLM_UPSTREAM_PROTOCOLS = ("openai", "anthropic", "gemini")
ROUTING_MODE_LABELS = {
    "priority": "顺序优先",
    "round_robin": "轮询负载",
    "latency": "网络质量优先",
}
DEFAULT_MODEL_MODE_LABELS = {
    "global": "统一默认模型",
    "upstream": "按上游配置默认",
}
USAGE_RANGE_CONFIGS = {
    "minute": {"window_seconds": 3600, "bucket_seconds": 60, "bucket_count": 60},
    "hour": {"window_seconds": 86400, "bucket_seconds": 3600, "bucket_count": 24},
    "day": {"window_seconds": 2592000, "bucket_seconds": 86400, "bucket_count": 30},
    "week": {"window_seconds": 7257600, "bucket_seconds": 604800, "bucket_count": 12},
}
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}
MODEL_AWARE_PATHS = {
    "/v1/chat/completions",
    "/v1/completions",
    "/v1/responses",
    "/v1/embeddings",
    "/v1/images/generations",
    "/v1/audio/transcriptions",
    "/v1/audio/translations",
    "/v1/audio/speech",
    "/v1/moderations",
}
ANTHROPIC_MODEL_AWARE_PATHS = {
    "/v1/messages",
    "/v1/messages/count_tokens",
}
EXPECTED_CLIENT_DISCONNECT_EXCEPTIONS = (
    BrokenPipeError,
    ConnectionResetError,
    ConnectionAbortedError,
)

__all__ = [
    "ADDRESS_IN_USE_ERRNOS",
    "ANTHROPIC_MODEL_AWARE_PATHS",
    "APP_NAME",
    "APP_SLUG",
    "APP_VERSION",
    "APP_AUTHOR",
    "APP_LICENSE_NAME",
    "APP_LICENSE_URL",
    "APP_SOURCE_HOST",
    "APP_REPOSITORY_URL",
    "APP_RELEASES_URL",
    "APP_UPDATE_CHANNEL",
    "CONFIG_PATH_ENV_VAR",
    "CONFIG_VERSION",
    "DEFAULT_CLAUDE_SWITCH_BACKUP_FILENAME",
    "DEFAULT_CODEX_SWITCH_BACKUP_FILENAME",
    "DEFAULT_COOLDOWN",
    "DEFAULT_CONFIG_FILENAME",
    "DEFAULT_DEFAULT_MODEL_MODE",
    "DEFAULT_ENDPOINT_MODE",
    "DEFAULT_GEMINI_SWITCH_BACKUP_FILENAME",
    "DEFAULT_LISTEN_HOST",
    "DEFAULT_LISTEN_PORT",
    "DEFAULT_MODEL_MODE_LABELS",
    "DEFAULT_RETRYABLE_STATUSES",
    "DEFAULT_ROUTING_MODE",
    "DEFAULT_RUNTIME_STATE_SUFFIX",
    "DEFAULT_SHARED_API_PREFIXES",
    "DEFAULT_SPLIT_API_PORTS",
    "DEFAULT_TIMEOUT",
    "DEFAULT_WEB_UI_PORT_OFFSET",
    "EXPECTED_CLIENT_DISCONNECT_EXCEPTIONS",
    "HOP_BY_HOP_HEADERS",
    "IGNORED_SOCKET_ERRNOS",
    "LEGACY_APP_NAMES",
    "LEGACY_APP_SLUGS",
    "LEGACY_CONFIG_PATH_ENV_VARS",
    "LEGACY_SHARED_API_PREFIXES",
    "LEGACY_STATIC_DIR_ENV_VARS",
    "LOCAL_LLM_UPSTREAM_PROTOCOLS",
    "MODEL_AWARE_PATHS",
    "NATIVE_API_PREFIXES",
    "PROTOCOL_TO_CLIENT",
    "ROUTING_MODE_LABELS",
    "ROUTING_PROTOCOLS",
    "STATIC_DIR_ENV_VAR",
    "SUPPORTED_THEME_MODES",
    "SUPPORTED_CLI_THEME_MODES",
    "SUPPORTED_UI_LANGUAGES",
    "UPSTREAM_PROTOCOL_LABELS",
    "UPSTREAM_PROTOCOL_ORDER",
    "UPSTREAM_PROTOCOLS",
    "USAGE_RANGE_CONFIGS",
]
