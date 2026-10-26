# Use-case results (LiteLLM routes, thinking off)

Settings: ctx 65536, KV cache q8_0, thinking off; per route temperature / max_tokens / timeout: voice-chat 0.7/150/15s, subtitles 0.2/2048/600s, prompt-enhancer 0.7/800/600s, owui-tasks 0.3/512/600s, simple-chat 0.7/2048/300s; top_p/top_k/min_p/penalties from each model card.

## Scoreboard

| Config | voice-chat | subtitles | prompt-enhancer | owui-tasks | simple-chat | Total | Timeouts | Voice p95 latency | Gen t/s | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.6-35B-A3B UD-IQ2_XXS (single) | 12/12 | 3/6 | 9/9 | 12/12 | 12/12 | **48/51** | 0 | 1.1s | 39.6 | complete |
| Qwen3.6-35B-A3B UD-Q4_K_M (dual) | 12/12 | 4/6 | 8/9 | 12/12 | 11/12 | **47/51** | 0 | 1.6s | 35.6 | complete |
| flint-39.8B-A2.5B UD-IQ2_XXS (single) | 12/12 | 2/6 | 9/9 | 12/12 | 8/12 | **43/51** | 0 | 0.8s | 43.6 | complete |
| Ornith-1.5-35B-A3B Q4_K_M (dual) | 12/12 | 3/6 | 8/9 | 12/12 | 7/12 | **42/51** | 0 | 1.3s | 41.7 | complete |
| flint-39.8B-A2.5B UD-Q3_K_XL (dual) | 12/12 | 1/6 | 7/9 | 9/12 | 10/12 | **39/51** | 0 | 1.1s | 36.7 | complete |
| Ornith-1.5-35B-A3B IQ2_S (single) | 10/12 | 0/6 | 8/9 | 11/12 | 6/12 | **35/51** | 0 | 0.6s | 48.6 | complete |
| LFM2.5-24B-A2B UD-Q5_K_XL (dual) | 10/12 | 0/6 | 5/9 | 3/12 | 9/12 | **27/51** | 0 | 1.1s | 50.0 | complete |
| LFM2.5-24B-A2B UD-Q3_K_XL (single) | 9/12 | 0/6 | 3/9 | 0/12 | 9/12 | **21/51** | 0 | 0.9s | 60.6 | complete |

## Latency per route (median wall time per call, seconds)

| Config | voice-chat | subtitles | prompt-enhancer | owui-tasks | simple-chat |
|---|---|---|---|---|---|
| Qwen3.6-35B-A3B UD-IQ2_XXS (single) | 0.6 | 5.5 | 3.6 | 2.1 | 2.6 |
| Qwen3.6-35B-A3B UD-Q4_K_M (dual) | 1.1 | 6.2 | 4.3 | 2.0 | 3.5 |
| flint-39.8B-A2.5B UD-IQ2_XXS (single) | 0.6 | 3.5 | 2.1 | 1.7 | 3.0 |
| Ornith-1.5-35B-A3B Q4_K_M (dual) | 1.1 | 5.8 | 3.5 | 2.1 | 3.3 |
| flint-39.8B-A2.5B UD-Q3_K_XL (dual) | 0.8 | 4.7 | 2.8 | 1.9 | 3.5 |
| Ornith-1.5-35B-A3B IQ2_S (single) | 0.4 | 4.4 | 1.9 | 2.0 | 2.2 |
| LFM2.5-24B-A2B UD-Q5_K_XL (dual) | 0.6 | 3.5 | 3.9 | 11.2 | 2.2 |
| LFM2.5-24B-A2B UD-Q3_K_XL (single) | 0.4 | 2.6 | 4.3 | 9.3 | 2.3 |

## Correct per test (out of 3 runs; T = timeouts)

| Test | Qwen3.6-35B-A3B UD-IQ2_XXS (single) | Qwen3.6-35B-A3B UD-Q4_K_M (dual) | flint-39.8B-A2.5B UD-IQ2_XXS (single) | Ornith-1.5-35B-A3B Q4_K_M (dual) | flint-39.8B-A2.5B UD-Q3_K_XL (dual) | Ornith-1.5-35B-A3B IQ2_S (single) | LFM2.5-24B-A2B UD-Q5_K_XL (dual) | LFM2.5-24B-A2B UD-Q3_K_XL (single) |
|---|---|---|---|---|---|---|---|---|
| voice-chat/voz_porcentagem | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| voice-chat/voz_conversao | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| voice-chat/voz_fato | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 1/3 | 1/3 | 0/3 |
| voice-chat/voz_dica | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| subtitles/legenda_dialogo | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| subtitles/legenda_noticia | 0/3 | 1/3 | 2/3 | 3/3 | 1/3 | 0/3 | 0/3 | 0/3 |
| prompt-enhancer/prompt_gato_astronauta | 3/3 | 3/3 | 3/3 | 2/3 | 2/3 | 3/3 | 2/3 | 0/3 |
| prompt-enhancer/prompt_logo | 3/3 | 2/3 | 3/3 | 3/3 | 2/3 | 2/3 | 0/3 | 1/3 |
| prompt-enhancer/prompt_sem_pessoas | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 |
| owui-tasks/owui_title | 3/3 | 3/3 | 3/3 | 3/3 | 0/3 | 3/3 | 0/3 | 0/3 |
| owui-tasks/owui_tags | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 0/3 | 0/3 |
| owui-tasks/owui_follow_ups | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 0/3 |
| owui-tasks/owui_queries | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| simple-chat/chat_contagem_dias | 3/3 | 3/3 | 2/3 | 1/3 | 2/3 | 1/3 | 1/3 | 1/3 |
| simple-chat/chat_email_formal | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 |
| simple-chat/chat_tcp_udp | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| simple-chat/chat_resumo | 3/3 | 3/3 | 0/3 | 0/3 | 2/3 | 0/3 | 2/3 | 2/3 |
