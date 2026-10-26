# Benchmark results

Settings: ctx 32768 (24576 fallback; see the Ctx column), KV cache q8_0, reasoning budget 6144 tokens, temperature 0.6, timeout 300s per call.

## Scoreboard

| Config | Ctx | KV cache | Long context | Coding | Tool call | Reasoning | Total | Timeouts | Prompt t/s | Gen t/s | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| flint-39.8B-A2.5B UD-Q3_K_XL (dual) | 32k | q8_0 | 5/6 | 8/9 | 12/12 | 6/9 | **31/36** | 0 | 115 | 28.5 | complete |
| Ornith-1.5-35B-A3B Q4_K_M (dual) | 32k | q8_0 | 6/6 | 5/9 | 12/12 | 5/9 | **28/36** | 0 | 190 | 37.9 | complete |
| Ornith-1.5-35B-A3B IQ2_S (single) | 32k | q8_0 | 6/6 | 6/9 | 12/12 | 3/9 | **27/36** | 0 | 149 | 38.9 | complete |
| Qwen3.6-35B-A3B UD-Q4_K_M (dual) | 32k | q8_0 | 6/6 | 4/9 | 11/12 | 6/9 | **27/36** | 0 | 195 | 37.0 | complete |
| flint-39.8B-A2.5B UD-IQ2_XXS (single) | 32k | q8_0 | 6/6 | 6/9 | 12/12 | 2/9 | **26/36** | 0 | 110 | 31.7 | complete |
| Ornith-1.5-35B-A3B IQ2_S (dual-same) | 32k | q8_0 | 6/6 | 3/9 | 12/12 | 4/9 | **25/36** | 0 | 157 | 35.7 | complete |
| Qwen3.5-4B Q8_0 (single) | 32k | q8_0 | 5/6 | 5/9 | 12/12 | 3/9 | **25/36** | 6 | 204 | 29.0 | complete |
| Qwen3.6-35B-A3B UD-IQ2_XXS (single) | 32k | q8_0 | 6/6 | 5/9 | 11/12 | 3/9 | **25/36** | 0 | 138 | 34.3 | complete |
| LFM2.5-24B-A2B UD-Q5_K_XL (dual) | 32k | q8_0 | 5/6 | 3/9 | 12/12 | 4/9 | **24/36** | 0 | 245 | 44.8 | complete |
| LFM2.5-24B-A2B UD-Q3_K_XL (single) | 32k | q8_0 | 4/6 | 3/9 | 12/12 | 2/9 | **21/36** | 0 | 183 | 49.0 | complete |
| Nemotron-3.5-Bolt-E4B UD-Q6_K_XL (single) | 32k | q8_0 | 5/6 | 3/9 | 11/12 | 1/9 | **20/36** | 1 | 214 | 26.1 | complete |
| Ornith-1.5-9B Q6_K (single) | 32k | q8_0 | 6/6 | 1/9 | 12/12 | 0/9 | **19/36** | 14 | 103 | 18.5 | complete |
| Qwen3.8-27B UD-Q4_K_M (dual) | 32k | q8_0 | 5/6 | 0/9 | 12/12 | 2/9 | **19/36** | 17 | 36 | 7.5 | complete |
| Qwen3.8-27B UD-Q2_K_XL (single) | 32k | q8_0 | 4/6 | 1/9 | 12/12 | 2/9 | **19/36** | 17 | 45 | 7.7 | complete |
| Gemma-4-12B-it Q6_K (single) | 32k | q8_0 | 6/6 | 0/9 | 12/12 | 0/9 | **18/36** | 18 | 75 | 12.5 | complete |
| Qwen3.5-9B Q6_K (single) | 32k | q8_0 | 4/6 | 2/9 | 12/12 | 0/9 | **18/36** | 17 | 103 | 18.7 | complete |
| Qwen3.8-27B-Fusion-NEO-CODER (DavidAU) NEO-CODER-MAX-Q4_K_M (dual) | 32k | q8_0 | 4/6 | 1/9 | 12/12 | 1/9 | **18/36** | 16 | 31 | 7.0 | complete |
| Qwen3.8-27B-Fusion-NEO-CODER (DavidAU) NEO-CODER-MAX-IQ2_M (single) | 32k | q8_0 | 4/6 | 0/9 | 12/12 | 2/9 | **18/36** | 17 | 36 | 6.7 | complete |
| Qwen3-Coder-30B-A3B Q4_K_M (dual) | 32k | q8_0 | 6/6 | 3/9 | 6/12 | 0/9 | **15/36** | 0 | 202 | 39.1 | complete |
| Qwen3-Coder-30B-A3B UD-IQ2_M (single) | 32k | q8_0 | 5/6 | 2/9 | 6/12 | 0/9 | **13/36** | 1 | 128 | 35.1 | complete |

## Correct per test (out of 3 runs; T = timeouts)

| Test | flint-39.8B-A2.5B UD-Q3_K_XL (dual) | Ornith-1.5-35B-A3B Q4_K_M (dual) | Ornith-1.5-35B-A3B IQ2_S (single) | Qwen3.6-35B-A3B UD-Q4_K_M (dual) | flint-39.8B-A2.5B UD-IQ2_XXS (single) | Ornith-1.5-35B-A3B IQ2_S (dual-same) | Qwen3.5-4B Q8_0 (single) | Qwen3.6-35B-A3B UD-IQ2_XXS (single) | LFM2.5-24B-A2B UD-Q5_K_XL (dual) | LFM2.5-24B-A2B UD-Q3_K_XL (single) | Nemotron-3.5-Bolt-E4B UD-Q6_K_XL (single) | Ornith-1.5-9B Q6_K (single) | Qwen3.8-27B UD-Q4_K_M (dual) | Qwen3.8-27B UD-Q2_K_XL (single) | Gemma-4-12B-it Q6_K (single) | Qwen3.5-9B Q6_K (single) | Qwen3.8-27B-Fusion-NEO-CODER (DavidAU) NEO-CODER-MAX-Q4_K_M (dual) | Qwen3.8-27B-Fusion-NEO-CODER (DavidAU) NEO-CODER-MAX-IQ2_M (single) | Qwen3-Coder-30B-A3B Q4_K_M (dual) | Qwen3-Coder-30B-A3B UD-IQ2_M (single) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| long_context/multi_hop_ramal | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 T1 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 T1 | 2/3 T1 | 3/3 | 2/3 T1 | 1/3 T2 | 2/3 T1 | 3/3 | 3/3 |
| long_context/soma_com_correcoes | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 1/3 | 2/3 | 3/3 | 3/3 | 2/3 T1 | 3/3 | 2/3 T1 | 3/3 | 2/3 T1 | 3/3 | 2/3 |
| coding/avaliador_expressoes | 3/3 | 2/3 | 0/3 | 1/3 | 2/3 | 1/3 | 0/3 T1 | 1/3 | 0/3 | 1/3 | 0/3 | 0/3 T3 | 0/3 T3 | 0/3 T3 | 0/3 T3 | 0/3 T3 | 0/3 T3 | 0/3 T3 | 0/3 | 0/3 |
| coding/calculo_frete | 2/3 | 1/3 | 3/3 | 0/3 | 1/3 | 0/3 | 2/3 | 1/3 | 0/3 | 0/3 | 0/3 | 0/3 T3 | 0/3 T3 | 0/3 T3 | 0/3 T3 | 0/3 T3 | 0/3 T3 | 0/3 T3 | 0/3 | 0/3 |
| coding/corrigir_sessoes | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 1/3 T2 | 0/3 T3 | 1/3 T2 | 0/3 T3 | 2/3 | 1/3 T2 | 0/3 T3 | 3/3 | 2/3 |
| tool_call/multi_etapas_reembolso | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| tool_call/args_estritos_agenda | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| tool_call/recuperacao_erro_estoque | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| tool_call/abster_sem_dados_pix | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| reasoning/logica_5_pessoas | 0/3 | 1/3 | 0/3 | 2/3 | 0/3 | 0/3 | 0/3 T3 | 0/3 | 0/3 | 0/3 | 0/3 T1 | 0/3 T3 | 0/3 T3 | 0/3 T3 | 0/3 T3 | 0/3 T3 | 0/3 T3 | 0/3 T3 | 0/3 | 0/3 T1 |
| reasoning/aritmetica_datas | 3/3 | 3/3 | 2/3 | 3/3 | 0/3 | 3/3 | 0/3 T1 | 2/3 | 1/3 | 0/3 | 0/3 | 0/3 T3 | 0/3 T3 | 0/3 T3 | 0/3 T3 | 0/3 T3 | 0/3 T3 | 2/3 T1 | 0/3 | 0/3 |
| reasoning/instrucoes_multiplas | 3/3 | 1/3 | 1/3 | 1/3 | 2/3 | 1/3 | 3/3 | 1/3 | 3/3 | 2/3 | 1/3 | 0/3 | 2/3 T1 | 2/3 T1 | 0/3 T3 | 0/3 T3 | 1/3 | 0/3 T2 | 0/3 | 0/3 |
