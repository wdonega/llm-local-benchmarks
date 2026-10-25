# Benchmark results

Settings: ctx 32768 (24576 fallback; see the Ctx column), KV cache q8_0, reasoning budget 6144 tokens, temperature 0.6, timeout 300s per call.

## Scoreboard

| Config | Ctx | KV cache | Long context | Coding | Tool call | Reasoning | Total | Timeouts | Prompt t/s | Gen t/s | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Ornith-1.5-35B-A3B IQ2_S (single) | 32k | q8_0 | 6/6 | 6/9 | 12/12 | 3/9 | **27/36** | 0 | 149 | 38.9 | complete |
| flint-39.8B-A2.5B UD-IQ2_XXS (single) | 32k | q8_0 | 6/6 | 6/9 | 12/12 | 2/9 | **26/36** | 0 | 110 | 31.7 | complete |
| Qwen3.6-35B-A3B UD-IQ2_XXS (single) | 32k | q8_0 | 6/6 | 5/9 | 11/12 | 3/9 | **25/36** | 0 | 138 | 34.3 | complete |
| LFM2.5-24B-A2B UD-Q3_K_XL (single) | 32k | q8_0 | 4/6 | 3/9 | 12/12 | 2/9 | **21/36** | 0 | 183 | 49.0 | complete |

## Correct per test (out of 3 runs; T = timeouts)

| Test | Ornith-1.5-35B-A3B IQ2_S (single) | flint-39.8B-A2.5B UD-IQ2_XXS (single) | Qwen3.6-35B-A3B UD-IQ2_XXS (single) | LFM2.5-24B-A2B UD-Q3_K_XL (single) |
|---|---|---|---|---|
| long_context/multi_hop_ramal | 3/3 | 3/3 | 3/3 | 3/3 |
| long_context/soma_com_correcoes | 3/3 | 3/3 | 3/3 | 1/3 |
| coding/avaliador_expressoes | 0/3 | 2/3 | 1/3 | 1/3 |
| coding/calculo_frete | 3/3 | 1/3 | 1/3 | 0/3 |
| coding/corrigir_sessoes | 3/3 | 3/3 | 3/3 | 2/3 |
| tool_call/multi_etapas_reembolso | 3/3 | 3/3 | 3/3 | 3/3 |
| tool_call/args_estritos_agenda | 3/3 | 3/3 | 2/3 | 3/3 |
| tool_call/recuperacao_erro_estoque | 3/3 | 3/3 | 3/3 | 3/3 |
| tool_call/abster_sem_dados_pix | 3/3 | 3/3 | 3/3 | 3/3 |
| reasoning/logica_5_pessoas | 0/3 | 0/3 | 0/3 | 0/3 |
| reasoning/aritmetica_datas | 2/3 | 0/3 | 2/3 | 0/3 |
| reasoning/instrucoes_multiplas | 1/3 | 2/3 | 1/3 | 2/3 |
