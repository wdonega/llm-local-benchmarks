# Suite v2 — hard suite

Settings: ctx 32768, reasoning budget 6144 tokens, temperature 0.6, timeout 300s per call.

## Scoreboard

| Config | Long context | Coding | Tool call | Reasoning | Total | Timeouts | Prompt t/s | Gen t/s | Status |
|---|---|---|---|---|---|---|---|---|---|
| Ornith-1.5-35B-A3B IQ2_S (single) | 2/2 | 2/3 | 4/4 | 1/3 | **9/12** | 0 | 164 | 38.1 | complete |
| Qwen3-Coder-30B-A3B UD-IQ2_M (single) | 2/2 | 0/3 | 2/4 | 0/3 | **4/12** | 0 | 159 | 35.5 | complete |

## Correct per test (out of 3 runs; T = timeouts)

| Test | Ornith-1.5-35B-A3B IQ2_S (single) | Qwen3-Coder-30B-A3B UD-IQ2_M (single) |
|---|---|---|
| long_context/multi_hop_ramal | 1/1 | 1/1 |
| long_context/soma_com_correcoes | 1/1 | 1/1 |
| coding/avaliador_expressoes | 0/1 | 0/1 |
| coding/calculo_frete | 1/1 | 0/1 |
| coding/corrigir_sessoes | 1/1 | 0/1 |
| tool_call/multi_etapas_reembolso | 1/1 | 1/1 |
| tool_call/args_estritos_agenda | 1/1 | 0/1 |
| tool_call/recuperacao_erro_estoque | 1/1 | 0/1 |
| tool_call/abster_sem_dados_pix | 1/1 | 1/1 |
| reasoning/logica_5_pessoas | 0/1 | 0/1 |
| reasoning/aritmetica_datas | 1/1 | 0/1 |
| reasoning/instrucoes_multiplas | 0/1 | 0/1 |
