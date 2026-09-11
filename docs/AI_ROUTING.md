# AI continuity routing

Each task owns an ordered provider route. Automatic mode skips disabled, paid-disallowed
or cooling providers. HTTP 429, retryable 5xx, timeouts and network failures move to the
next compatible provider. Repeated failures open a temporary circuit; successful calls
reset it. Routing decisions and sanitized errors are recorded.

Default policy: free-first, paid disabled, maximum four attempts, local Ollama last.
Provider order is editable in the UI. A task may be locked to local providers by removing
cloud providers from its route.

Provider quota is exact only when the upstream reports it. Karna estimates health from
responses but never labels an estimate as an exact balance. Incomplete streaming output
is not combined across models. API keys remain server-side and are never returned by the
status endpoint.
