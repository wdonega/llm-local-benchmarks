#!/usr/bin/env python3
"""Validate the suite: reference solutions, negative controls and graders.

Run this after changing any task. It must end with "ALL OK".
"""

import os
import re
import shutil
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import common as rb  # noqa: E402
import tasks as T  # noqa: E402

FAILS = []


def expect(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


REF = {
    "avaliar": r'''
def avaliar(expr):
    if not isinstance(expr, str):
        raise ValueError("tipo")
    toks = []
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch.isspace():
            i += 1
        elif ch.isdigit():
            j = i
            while j < len(expr) and expr[j].isdigit():
                j += 1
            toks.append(("n", int(expr[i:j])))
            i = j
        elif ch in "+-*/^()":
            toks.append(("o", ch))
            i += 1
        else:
            raise ValueError("caractere inválido")
    pos = [0]
    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else (None, None)
    def take():
        t = peek(); pos[0] += 1; return t
    def expr_():
        v = term()
        while peek() in (("o", "+"), ("o", "-")):
            op = take()[1]; r = term()
            v = v + r if op == "+" else v - r
        return v
    def term():
        v = unary()
        while peek() in (("o", "*"), ("o", "/")):
            op = take()[1]; r = unary()
            if op == "*":
                v = v * r
            else:
                if r == 0:
                    raise ZeroDivisionError
                q = abs(v) // abs(r)
                v = q if (v >= 0) == (r >= 0) else -q
        return v
    def unary():
        if peek() == ("o", "-"):
            take(); return -unary()
        return power()
    def power():
        b = primary()
        if peek() == ("o", "^"):
            take(); e = unary()
            if e < 0:
                raise ValueError("expoente negativo")
            return b ** e
        return b
    def primary():
        t = take()
        if t[0] == "n":
            return t[1]
        if t == ("o", "("):
            v = expr_()
            if take() != ("o", ")"):
                raise ValueError("parêntese")
            return v
        raise ValueError("token inesperado")
    v = expr_()
    if pos[0] != len(toks):
        raise ValueError("sobrou token")
    return v
''',
    "calcular_frete": r'''
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING
def calcular_frete(peso_kg, regiao, valor_pedido, cupom=None, expresso=False):
    if not (peso_kg > 0 and peso_kg <= 30):
        raise ValueError("peso")
    mult = {"S": "1.00", "SE": "1.00", "CO": "1.20", "NE": "1.35", "N": "1.50"}
    if regiao not in mult:
        raise ValueError("regiao")
    if valor_pedido < 0:
        raise ValueError("valor")
    p = Decimal(str(peso_kg))
    if p <= 1:
        base = Decimal("12.00")
    elif p <= 5:
        base = Decimal("12.00") + Decimal("3.50") * (p - 1).to_integral_value(ROUND_CEILING)
    else:
        base = Decimal("26.00") + Decimal("2.80") * (p - 5).to_integral_value(ROUND_CEILING)
    v = base * Decimal(mult[regiao])
    if expresso:
        v = v * Decimal("1.4")
    if Decimal(str(valor_pedido)) >= Decimal("299.90") and not expresso and regiao in ("S", "SE", "CO"):
        return 0.0
    c = (cupom or "").upper()
    if c == "FRETE10":
        v = v * Decimal("0.9")
    elif c == "FRETEMETADE":
        if p <= 5:
            v = v * Decimal("0.5")
    elif c:
        raise ValueError("cupom")
    if v < Decimal("9.90"):
        v = Decimal("9.90")
    return float(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
''',
    "agrupar_sessoes": r'''
def agrupar_sessoes(eventos, limite_inatividade=30):
    resultado = {}
    for usuario, ts in sorted(set(eventos), key=lambda e: (e[1], e[0])):
        sessoes = resultado.setdefault(usuario, [])
        if sessoes and ts - sessoes[-1][1] <= limite_inatividade:
            inicio, fim, qtd = sessoes[-1]
            sessoes[-1] = (inicio, ts, qtd + 1)
        else:
            sessoes.append((ts, ts, 1))
    return resultado
''',
}

# Typical mistakes the suite MUST catch
NEGATIVE = {
    "avaliar": [
        ("division with // (floors)", REF["avaliar"].replace(
            "q = abs(v) // abs(r)\n                v = q if (v >= 0) == (r >= 0) else -q", "v = v // r")),
        ("left-associative ^", REF["avaliar"].replace(
            "        b = primary()\n        if peek() == (\"o\", \"^\"):\n            take(); e = unary()",
            "        b = primary()\n        while peek() == (\"o\", \"^\"):\n            take(); e = primary()")),
        ("unary minus binds tighter than ^", REF["avaliar"].replace(
            "        if peek() == (\"o\", \"-\"):\n            take(); return -unary()\n        return power()",
            "        if peek() == (\"o\", \"-\"):\n            take(); return power_neg()\n        return power()\n"
            "    def power_neg():\n        b = -primary()\n        if peek() == (\"o\", \"^\"):\n"
            "            take(); e = unary()\n            return b ** e\n        return b")),
        ("plain eval()", "def avaliar(expr):\n    return int(eval(expr.replace('^', '**').replace('/', '//')))\n"),
    ],
    "calcular_frete": [
        ("float + built-in round() instead of HALF_UP", r'''
import math
def calcular_frete(peso_kg, regiao, valor_pedido, cupom=None, expresso=False):
    if not (0 < peso_kg <= 30) or regiao not in ("S", "SE", "CO", "NE", "N") or valor_pedido < 0:
        raise ValueError
    if peso_kg <= 1:
        base = 12.0
    elif peso_kg <= 5:
        base = 12.0 + 3.5 * math.ceil(peso_kg - 1)
    else:
        base = 26.0 + 2.8 * math.ceil(peso_kg - 5)
    v = base * {"S": 1.0, "SE": 1.0, "CO": 1.2, "NE": 1.35, "N": 1.5}[regiao]
    if expresso:
        v *= 1.4
    if valor_pedido >= 299.90 and not expresso and regiao in ("S", "SE", "CO"):
        return 0.0
    c = (cupom or "").upper()
    if c == "FRETE10":
        v *= 0.9
    elif c == "FRETEMETADE":
        if peso_kg <= 5:
            v *= 0.5
    elif c:
        raise ValueError
    return round(max(v, 9.90), 2)
'''),
        ("coupon validated before the free-shipping rule", REF["calcular_frete"].replace(
            "    c = (cupom or \"\").upper()\n", "").replace(
            "    if Decimal(str(valor_pedido))",
            "    c = (cupom or \"\").upper()\n    if c and c not in (\"FRETE10\", \"FRETEMETADE\"):\n"
            "        raise ValueError(\"cupom\")\n    if Decimal(str(valor_pedido))")),
        ("no minimum shipping fee", REF["calcular_frete"].replace(
            "    if v < Decimal(\"9.90\"):\n        v = Decimal(\"9.90\")\n", "")),
        ("kg fraction not rounded up", REF["calcular_frete"].replace(
            "(p - 1).to_integral_value(ROUND_CEILING)", "(p - 1)").replace(
            "(p - 5).to_integral_value(ROUND_CEILING)", "(p - 5)")),
    ],
    "agrupar_sessoes": [
        ("original buggy code", re.search(r"```python\n(.*?)```", T.CODING_TASKS[2]["prompt"], re.S).group(1)),
        ("only fixes < to <=", re.search(r"```python\n(.*?)```", T.CODING_TASKS[2]["prompt"], re.S).group(1)
         .replace("< limite_inatividade", "<= limite_inatividade")),
        ("fixes everything but duplicates", REF["agrupar_sessoes"].replace("sorted(set(eventos)", "sorted(list(eventos)")),
    ],
}


def run_tests(task, code):
    wd = tempfile.mkdtemp(dir=rb.WORK)
    try:
        return rb.run_docker_tests(code, T.coding_test_source(task), wd)
    finally:
        shutil.rmtree(wd, ignore_errors=True)


def validate_coding():
    print("== coding: reference must pass 100%")
    for task in T.CODING_TASKS:
        ok, d = run_tests(task, REF[task["func"]])
        bad = [r for r in d.get("results", []) if not r["ok"]]
        expect(ok, f"{task['id']}: reference {d.get('passed')}/{d.get('total')}" +
               (f" failures={bad[:3]}" if bad else "") + (f" error={d.get('error')}" if d.get("error") else ""))
    print("== coding: typical mistakes must fail")
    for task in T.CODING_TASKS:
        for name, code in NEGATIVE[task["func"]]:
            ok, d = run_tests(task, code)
            expect(not ok, f"{task['id']}: '{name}' rejected ({d.get('passed')}/{d.get('total')})")


def validate_long():
    print("== long context")
    doc = T.LONG_DOC
    est = len(doc) / 3.0
    expect(14000 <= est <= 20000, f"size ~{est:.0f} tokens ({len(doc)} chars)")
    for needle, n in [("L-17 ", 2), ("L-22 ", 1), ("L-31 ", 2), ("cofre B", 1), ("Renata Aguiar", 2),
                      ("Otávio Brandt", 4), ("4471", 1), ("3318", 1), ("Joinville", 3)]:
        c = doc.count(needle)
        expect(c == n, f"'{needle}' appears {c}x (expected {n})")
    pos = {k: doc.find(k) for k in ["chave do cofre B", "Renata Aguiar substitui", "Renata Aguiar usa"]}
    expect(pos["chave do cofre B"] < pos["Renata Aguiar substitui"] < pos["Renata Aguiar usa"], "clue order")
    for task, good, bad in [
        (T.LONG_TASKS[0], "Explicação...\nRESPOSTA: 4471", "RESPOSTA: 3318"),
        (T.LONG_TASKS[1], "Total.\n**RESPOSTA:** 1.576", "RESPOSTA: 1612"),
    ]:
        expect(T.score_long(task, {"content": good})[0], f"{task['id']}: accepts the right answer")
        expect(not T.score_long(task, {"content": bad})[0], f"{task['id']}: rejects the distractor")
        expect(not T.score_long(task, {"content": "", "reasoning_content": good})[0],
               f"{task['id']}: reasoning without a final answer does not count")


def validate_reasoning():
    print("== reasoning")
    s = T.score_reasoning
    expect(s("logica_5_pessoas", {"content": "...\nRESPOSTA: Carla; Natal; 2"})[0], "logic: accepts right answer")
    expect(s("logica_5_pessoas", {"content": "**Resposta:**\nCarla; Natal; 2º andar"})[0], "logic: accepts answer on the next line")
    expect(not s("logica_5_pessoas", {"content": "RESPOSTA: Carla; Recife; 2"})[0], "logic: rejects wrong answer")
    expect(s("aritmetica_datas", {"content": "RESPOSTA: 2029-07-20; sexta-feira; 1"})[0], "dates: accepts right answer")
    expect(s("aritmetica_datas", {"content": "RESPOSTA: 2029-07-20; Sexta; 1 (29/02/2028)"})[0], "dates: accepts answer with a comment")
    expect(not s("aritmetica_datas", {"content": "RESPOSTA: 2029-07-21; sábado; 1"})[0], "dates: rejects off-by-one")
    good = ("Manter servidores exige rotina e backup diário. Antes de cada mudança faça um backup completo. "
            "Planeje janelas de manutenção com a equipe. Enfim a disciplina garante o fim.")
    ok, d = s("instrucoes_multiplas", {"content": good})
    expect(ok, f"instructions: accepts a valid text {d}")
    for name, txt in [
        ("comma", good.replace("rotina e", "rotina,")),
        ("letter z", good.replace("exige", "fazem")),
        ("backup 3x", good.replace("equipe", "equipe e backup")),
        ("final", good[:-4] + "fim!"),
        ("initials", good.replace("Antes", "Depois")),
    ]:
        expect(not s("instrucoes_multiplas", {"content": txt})[0], f"instructions: rejects {name}")


def validate_tools():
    print("== tool call: simulators + graders")
    t = {x["id"]: x for x in T.TOOL_TASKS}
    st = {}
    sim = t["multi_etapas_reembolso"]["simulate"]
    sim("buscar_cliente", {"email": "ana.ribeiro@exemplo.com"}, st)
    ped = sim("listar_pedidos", {"cliente_id": "C-2291", "status": "cancelado"}, st)
    for p in ped["pedidos"]:
        sim("calcular_reembolso", {"pedido_id": p["pedido_id"]}, st)
    expect(t["multi_etapas_reembolso"]["check"]("O total é R$ 432,36.", st)[0], "refund: correct flow passes")
    expect(not t["multi_etapas_reembolso"]["check"]("O total é R$ 480,40.", st)[0], "refund: summing paid amounts fails")
    expect(not t["multi_etapas_reembolso"]["check"]("O total é R$ 432,36.", {})[0], "refund: not calling the tool fails")

    st = {}
    t["args_estritos_agenda"]["simulate"]("agendar_reuniao", {
        "titulo": "Revisão do orçamento", "inicio": "2026-10-27T14:30", "duracao_min": 90,
        "participantes": ["carla.souza@empresa.com", "diego.alves@empresa.com"], "sala": "Verde"}, st)
    expect(t["args_estritos_agenda"]["check"]("", st)[0], "calendar: correct args pass")
    for name, patch in [("wrong date", {"inicio": "2026-10-28T14:30"}), ("duration 1.5", {"duracao_min": 1.5}),
                        ("lowercase room", {"sala": "verde"}), ("extra attendee", {"participantes": [
                            "carla.souza@empresa.com", "diego.alves@empresa.com", "bruno.lima@empresa.com"]})]:
        st2 = {"agendamentos": [dict(st["agendamentos"][0], **patch)]}
        expect(not t["args_estritos_agenda"]["check"]("", st2)[0], f"calendar: rejects {name}")

    st = {}
    sim = t["recuperacao_erro_estoque"]["simulate"]
    sim("buscar_produto", {"nome": "Cadeira Ergo Plus"}, st)
    sim("consultar_estoque", {"sku": "SKU-88412-A"}, st)
    sim("consultar_estoque", {"sku": "SKU-88412-B"}, st)
    expect(t["recuperacao_erro_estoque"]["check"]("Há 37 unidades no depósito.", st)[0], "stock: recovery passes")
    expect(not t["recuperacao_erro_estoque"]["check"]("Há 42 unidades.", st)[0], "stock: summing store+warehouse fails")
    expect(not t["recuperacao_erro_estoque"]["check"]("Há 37 unidades.", {"skus": ["SKU-88412-A"]})[0],
           "stock: not querying the new SKU fails")

    expect(t["abster_sem_dados_pix"]["check"]("Qual a chave PIX e o valor?", {})[0], "pix: asking for the details passes")
    expect(not t["abster_sem_dados_pix"]["check"]("Feito!", {"chamadas": ["transferir_pix"]})[0], "pix: transferring fails")
    expect(T.content_tool_call({"content": '{"name": "transferir_pix", "arguments": {}}'}) == "transferir_pix",
           "detects a tool call written as text")


def validate_translation():
    print("== translation")
    t1, t2 = T.TRANSLATION_TASKS
    for t in (t1, t2):
        ok, d = T.score_translation(t, {"content": t["reference"]})
        expect(ok, f"{t['id']}: reference passes {d['failed']}")
    alt1 = (t1["reference"].replace("Na verdade, lançamos", "Já lançamos")
            .replace("Agora a decisão é sua.", "A bola está com você agora.")
            .replace("um valor aproximado", "uma estimativa"))
    expect(T.score_translation(t1, {"content": alt1})[0], f"{t1['id']}: accepts a valid alternative wording")
    alt2 = (t2["reference"].replace("participa de", "frequenta").replace("sensata", "acertada")
            .replace("foi moleza", "foi fácil"))
    expect(T.score_translation(t2, {"content": alt2})[0], f"{t2['id']}: accepts a valid alternative wording")
    for name, txt in [
        ("false friends (atualmente/eventualmente)", t1["reference"].replace("Na verdade, lançamos", "Atualmente lançamos")
         .replace("vai chegar a todas as contas", "vai eventualmente chegar a todas as contas")),
        ("US number format", t1["reference"].replace("1.250,75", "1,250.75")),
        ("English date", t1["reference"].replace("3 de março de 2027", "March 3, 2027")),
        ("placeholder translated", t1["reference"].replace("{customer_name}", "{nome_do_cliente}")),
        ("inline code changed", t1["reference"].replace("`npm install cloudsync-cli@4.2.0`", "npm install cloudsync-cli@4.2.0")),
        ("bold dropped", t1["reference"].replace("**Importante:**", "Importante:")),
        ("literal ballpark", t1["reference"].replace("um valor aproximado", "um número de estádio")),
        ("sentence left in English", t1["reference"].replace("Avise se quiser seguir em frente.",
                                                              "Let us know if you'd like to move forward with the plan.")),
        ("summary instead of translation", "Olá, {customer_name}. A correção sai até 3 de março de 2027."),
    ]:
        expect(not T.score_translation(t1, {"content": txt})[0], f"{t1['id']}: rejects {name}")
    for name, txt in [
        ("parentes", t2["reference"].replace("Meus pais", "Meus parentes")),
        ("livraria", t2["reference"].replace("biblioteca pública", "livraria pública")),
        ("pretende", t2["reference"].replace("finge que não gosta", "pretende que não gosta")),
        ("atende", t2["reference"].replace("participa de", "atende")),
        ("sensível", t2["reference"].replace("sensata", "sensível")),
        ("pedaço de bolo", t2["reference"].replace("foi moleza", "foi um pedaço de bolo")),
        ("untranslated", t2["source"]),
    ]:
        expect(not T.score_translation(t2, {"content": txt})[0], f"{t2['id']}: rejects {name}")
    expect(not T.score_translation(t1, {"content": "", "reasoning_content": t1["reference"]})[0],
           f"{t1['id']}: reasoning without a final answer does not count")


def validate_extract():
    print("== code extraction")
    txt = "Aqui:\n```python\ndef avaliar(e):\n    return 1\n```\nUso:\n```python\nprint(avaliar('1'))\n```"
    expect(T.extract_code(txt, "avaliar").startswith("def avaliar"), "picks the block with the function")


if __name__ == "__main__":
    os.makedirs(rb.WORK, exist_ok=True)
    validate_long()
    validate_reasoning()
    validate_tools()
    validate_translation()
    validate_extract()
    validate_coding()
    print()
    print(f"{len(FAILS)} failure(s)" if FAILS else "ALL OK")
    sys.exit(1 if FAILS else 0)
