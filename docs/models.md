# Groq Models Reference

Base URL: `https://api.groq.com/openai/v1`
OpenAI-compatible API (use openai SDK with custom base_url)

## Production Models

| Model | Model ID | Speed | Input (1M) | Output (1M) | Context | Max Output | Rate Limits (Dev) |
|-------|----------|-------|------------|-------------|---------|------------|-------------------|
| GPT OSS 120B | `openai/gpt-oss-120b` | 500 TPS | $0.15 | $0.60 | 131k | 65k | 250K TPM, 1K RPM |
| GPT OSS 20B | `openai/gpt-oss-20b` | 1000 TPS | $0.075 | $0.30 | 131k | 65k | 250K TPM, 1K RPM |
| Llama 3.3 70B | `llama-3.3-70b-versatile` | 280 TPS | $0.59 | $0.79 | 131k | 32k | 300K TPM, 1K RPM |
| Llama 3.1 8B | `llama-3.1-8b-instant` | 560 TPS | $0.05 | $0.08 | 131k | 131k | 250K TPM, 1K RPM |

## Preview Models (not for production)

| Model | Model ID | Speed | Input (1M) | Output (1M) | Context | Rate Limits |
|-------|----------|-------|------------|-------------|---------|-------------|
| Llama 4 Scout 17Bx16E | `meta-llama/llama-4-scout-17b-16e-instruct` | 750 TPS | $0.11 | $0.34 | 131k | 300K TPM, 1K RPM |
| Qwen3 32B | `qwen/qwen3-32b` | 400 TPS | $0.29 | $0.59 | 131k | 41k | 300K TPM, 1K RPM |
| Kimi K2 | `moonshotai/kimi-k2-instruct-0905` | 200 TPS | $1.00 | $3.00 | 262k | 16k | 250K TPM, 1K RPM |
| GPT OSS 20B Safeguard | `openai/gpt-oss-safeguard-20b` | 1000 TPS | $0.075 | $0.30 | 131k | 65k | 150K TPM, 1K RPM |

## Systems (with built-in tools)

| System | Model ID | Speed | Rate Limits | Notes |
|--------|----------|-------|-------------|-------|
| Groq Compound | `groq/compound` | 450 TPS | 200K TPM, 200 RPM | web search, code execution |
| Groq Compound Mini | `groq/compound-mini` | 450 TPS | 200K TPM, 200 RPM | lighter version |

## Prompt Caching (discount on cache hit)

| Model | Uncached Input | Cached Input | Output |
|-------|---------------|--------------|--------|
| `openai/gpt-oss-120b` | $0.15 | $0.075 | $0.60 |
| `openai/gpt-oss-20b` | $0.075 | $0.0375 | $0.30 |
| `moonshotai/kimi-k2-instruct-0905` | $1.00 | $0.50 | $3.00 |

## Batch API
- 50% cost reduction
- No impact to standard rate limits
- Processing window: 24 hours to 7 days

## Built-in Tools (additional cost)

| Tool | Price | Parameter |
|------|-------|-----------|
| Basic Search | $5 / 1K requests | `web_search` |
| Advanced Search | $8 / 1K requests | `web_search` |
| Visit Website | $1 / 1K requests | `visit_website` |
| Code Execution | $0.18 / hour | `code_interpreter` |

## Default for this project

`openai/gpt-oss-120b` — основная модель для extraction, generation, evaluation.
`openai/gpt-oss-20b` — быстрая/дешевая альтернатива если нужен bulk.
