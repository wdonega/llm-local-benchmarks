"""Benchmark tasks: hard tasks with automatic grading.

Categories (each test runs 3x):
  long_context  ~17k-token document; multi-hop questions with distractors and corrections
  coding        invented specs + hidden tests run in Docker
  tool_call     multi-turn with simulated tools: strict args, error recovery, abstention
  reasoning     unique-solution logic puzzle, date arithmetic, multi-constraint instructions

Prompts are in Brazilian Portuguese on purpose; graders only look at the final answer
(`content`), never at the reasoning trace.
"""

import json
import random
import re
import unicodedata

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def normalize(text):
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", text.lower())


def final_text(message):
    """Only the final content counts; reasoning is not an answer."""
    return (message.get("content") or "").strip()


def answer_line(text):
    """Text after the last 'RESPOSTA:' (answer) marker, or None."""
    all_lines = text.splitlines()
    idxs = [i for i, l in enumerate(all_lines) if "resposta" in l.lower()]
    if not idxs:
        return None
    i = idxs[-1]
    line = all_lines[i]
    rest = line[line.lower().rfind("resposta") + len("resposta") :].lstrip(" :*-").strip(" *`")
    if not rest:
        # a bare "**Resposta:**" with the answer on the next line
        nxt = [l.strip(" *`") for l in all_lines[i + 1 :] if l.strip(" *`")]
        rest = nxt[0] if nxt else ""
    return rest or None


def first_int(text):
    m = re.search(r"\d+", text or "")
    return int(m.group(0)) if m else None


def numbers_in(text):
    """Integers/decimals; accepts thousands separators (1.576) and decimal commas."""
    out = []
    for m in re.finditer(r"\d[\d.,]*", text):
        raw = m.group(0).rstrip(".,")
        if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", raw):
            raw = raw.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", raw):
            raw = raw.replace(",", "")
        else:
            raw = raw.replace(",", ".")
        try:
            out.append(float(raw))
        except ValueError:
            pass
    return out


# ---------------------------------------------------------------------------
# Long context
# ---------------------------------------------------------------------------

_CITIES = [
    "Curitiba", "Londrina", "Maringá", "Blumenau", "Florianópolis", "Chapecó", "Caxias do Sul",
    "Pelotas", "Campinas", "Sorocaba", "Santos", "Ribeirão Preto", "Uberlândia", "Goiânia",
    "Cuiabá", "Campo Grande", "Salvador", "Recife", "Fortaleza", "Natal", "Belém", "Manaus",
]
_PEOPLE = [
    "Marta Salles", "Hugo Pereira", "Lívia Campos", "Sérgio Nunes", "Paula Teixeira", "Caio Mendes",
    "Beatriz Lobo", "Rafael Duarte", "Juliana Prado", "Fábio Rocha", "Helena Vidal", "Igor Santana",
    "Tânia Moraes", "Rodrigo Leal", "Vanessa Cruz", "André Bastos", "Camila Freitas", "Luís Antunes",
    "Patrícia Siqueira", "Gustavo Reis", "Débora Quintela", "Mauro Fontes", "Renato Aguiar",
    "Otávia Brandão", "Renata Agostini", "Otávio Brito",
]
_LETTERS = ["A", "C", "D", "E", "F", "G", "H"]
_EVENTS_MISC = [
    "a inspeção de rotina do gerador foi concluída sem pendências",
    "o sistema de climatização da sala de servidores foi recalibrado",
    "o inventário de equipamentos de proteção foi conferido por amostragem",
    "a rota de coleta de resíduos foi alterada para o período da manhã",
    "o treinamento de brigada de incêndio teve 92% de presença",
    "a central telefônica ficou fora do ar por 14 minutos durante a madrugada",
    "o contrato de limpeza foi renovado por mais doze meses",
    "a câmera do estacionamento foi substituída por um modelo com visão noturna",
    "o relatório mensal de consumo de energia foi enviado à diretoria",
    "a planilha de escalas de plantão foi revisada pela supervisão",
]
_FORBIDDEN_LOTS = {17, 22, 31}


def _filler_record(rng, n):
    day = rng.randint(1, 28)
    month = rng.randint(1, 12)
    year = rng.choice([2025, 2026])
    city = rng.choice(_CITIES)
    kind = rng.random()
    if kind < 0.22:
        lot = rng.choice([k for k in range(10, 99) if k not in _FORBIDDEN_LOTS])
        body = f"o lote L-{lot} recebeu {rng.randint(20, 1500)} unidades"
    elif kind < 0.30:
        lot = rng.choice([k for k in range(10, 99) if k not in _FORBIDDEN_LOTS])
        a, b = rng.randint(20, 900), rng.randint(20, 900)
        body = f"correção: o lote L-{lot} recebeu {a} unidades, e não {b} como registrado antes"
    elif kind < 0.48:
        body = f"{rng.choice(_PEOPLE)} usa o ramal {rng.randint(2000, 9899)}"
    elif kind < 0.58:
        c2 = rng.choice([c for c in _CITIES if c != "Blumenau"])
        body = f"{rng.choice(_PEOPLE)} assumiu a coordenação da filial de {c2}"
    elif kind < 0.66:
        body = f"a chave do armário {rng.choice(_LETTERS)} fica com {rng.choice(_PEOPLE)}"
    elif kind < 0.72:
        body = f"o cofre {rng.choice(_LETTERS)} passou por manutenção preventiva"
    else:
        body = rng.choice(_EVENTS_MISC)
    extra = rng.choice(_EVENTS_MISC)
    return (
        f"Registro {n:04d} ({day:02d}/{month:02d}/{year}) — filial de {city}: {body}. "
        f"Na mesma data, {extra}."
    )


_PLANTED = [
    (0.08, "Por norma interna da empresa, a chave do cofre B fica sempre com quem coordena a filial de Joinville."),
    (0.12, "Por norma interna, a chave do cofre C fica sempre com quem coordena a filial de Blumenau."),
    (0.15, "O lote L-17 recebeu 340 unidades."),
    (0.30, "Otávio Brandt foi nomeado coordenador da filial de Joinville em 10/11/2025."),
    (0.40, "O lote L-22 recebeu 1125 unidades."),
    (0.45, "Otávio Brandt usa o ramal 3318."),
    (0.52, "O lote L-31 recebeu 87 unidades."),
    (
        0.62,
        "A partir de 03/03/2026, Renata Aguiar substitui Otávio Brandt na coordenação da filial de "
        "Joinville; Otávio Brandt foi transferido para a coordenação da filial de Blumenau.",
    ),
    (0.70, "Correção: o registro do lote L-17 estava errado; foram 304 unidades, e não 340."),
    (0.82, "O lote L-31 recebeu uma segunda remessa de 60 unidades."),
    (0.88, "Renata Aguiar usa o ramal 4471."),
]


def make_long_document(target_chars=52000, seed=4242):
    rng = random.Random(seed)
    records = []
    total = 0
    n = 1
    while total < target_chars:
        r = _filler_record(rng, n)
        records.append(r)
        total += len(r) + 2
        n += 1
    count = len(records)
    for frac, text in sorted(_PLANTED, key=lambda x: -x[0]):
        pos = int(count * frac)
        records.insert(pos, f"Registro especial (sem número): {text}")
    return "\n\n".join(records)


LONG_DOC = make_long_document()

LONG_TASKS = [
    {
        "id": "multi_hop_ramal",
        "question": (
            "Qual é o ramal da pessoa que HOJE (outubro de 2026) guarda a chave do cofre B? "
            "Considere mudanças de cargo registradas. Explique brevemente e termine com uma última "
            "linha exatamente no formato: RESPOSTA: <ramal>"
        ),
        "expected": 4471,
    },
    {
        "id": "soma_com_correcoes",
        "question": (
            "Considerando todas as remessas e correções registradas, quantas unidades os lotes L-17, "
            "L-22 e L-31 receberam no total, somados? Termine com uma última linha exatamente no "
            "formato: RESPOSTA: <número>"
        ),
        "expected": 1576,
    },
]


def long_messages(task):
    return [
        {
            "role": "system",
            "content": "Você analisa documentos com atenção. Responda com base apenas no documento.",
        },
        {
            "role": "user",
            "content": "DOCUMENTO:\n\n" + LONG_DOC + "\n\n---\n\nPERGUNTA: " + task["question"],
        },
    ]


def score_long(task, message):
    text = final_text(message)
    line = answer_line(text)
    nums = numbers_in(line) if line else []
    ok = bool(nums) and int(nums[0]) == task["expected"] and float(nums[0]).is_integer()
    return ok, {"answer_line": line, "parsed": nums[:3]}


# ---------------------------------------------------------------------------
# Coding
# ---------------------------------------------------------------------------

_TEST_RUNNER = r"""
import json, sys, traceback
sys.setrecursionlimit(10000)
results = []
def check(name, fn):
    try:
        ok, info = fn()
    except Exception as e:
        ok, info = False, "exception: " + repr(e)
    results.append({"case": name, "ok": bool(ok), "info": str(info)[:300]})
def expect_raises(exc, f, *a, **kw):
    try:
        got = f(*a, **kw)
    except exc:
        return True, "raised " + exc.__name__
    except Exception as e:
        return False, "raised " + type(e).__name__ + " instead of " + exc.__name__
    return False, "did not raise; returned " + repr(got)
def expect_eq(got, exp):
    return got == exp, "expected " + repr(exp) + ", got " + repr(got)
def expect_close(got, exp, tol=1e-6):
    return isinstance(got, (int, float)) and not isinstance(got, bool) and abs(got - exp) <= tol, \
        "expected " + repr(exp) + ", got " + repr(got)
"""

_TEST_FOOTER = r"""
print(json.dumps({"ok": all(r["ok"] for r in results), "passed": sum(r["ok"] for r in results),
                  "total": len(results), "results": results}))
"""

CODING_TASKS = [
    {
        "id": "avaliador_expressoes",
        "func": "avaliar",
        "prompt": """Implemente em Python a função `avaliar(expr: str) -> int`, que avalia expressões aritméticas inteiras com as regras abaixo. Não use eval, exec, ast nem bibliotecas de parsing.

Regras:
1. Elementos válidos: inteiros não negativos (sequências de dígitos), os operadores binários + - * / ^, parênteses ( ), espaços em branco (ignorados) e o menos unário.
2. Precedência, da maior para a menor:
   - ^ (potência), associativo à DIREITA: 2^3^2 = 2^9 = 512
   - menos unário: -2^2 = -(2^2) = -4; o menos unário pode se repetir: --3 = 3
   - * e /, associativos à esquerda
   - + e -, associativos à esquerda
   Assim, 3 * -2 = -6 e 3 - -2 = 5 são válidas.
3. / é divisão inteira que trunca em direção a ZERO (não arredonda para baixo): 7/2 = 3, -7/2 = -3, 7/-2 = -3.
4. Divisão por zero: levante ZeroDivisionError.
5. 0^0 = 1. Expoente negativo: levante ValueError.
6. Não existe mais unário: "+3" é inválido.
7. Qualquer expressão inválida (vazia, só espaços, parênteses desbalanceados, operador sem operando, dois números seguidos como "1 2", caractere desconhecido como "%" ou ".") deve levantar ValueError.
8. Inteiros podem ser grandes; o resultado deve ser exato.

Responda apenas com um bloco de código Python contendo a implementação, sem exemplos nem testes.""",
        "tests": r"""
from solution import avaliar
cases = [
    ("1 + 2 * 3", 7), ("(1 + 2) * 3", 9), ("2^3^2", 512), ("-2^2", -4), ("(-2)^2", 4),
    ("--3", 3), ("3 * -2", -6), ("3 - -2", 5), ("10 - 4 - 3", 3), ("100 / 10 / 5", 2),
    ("7/2", 3), ("-7/2", -3), ("7/-2", -3), ("-7/-2", 3), ("0^0", 1), ("2^62 + 1", 2**62 + 1),
    ("  12  *(3+ 4) ", 84), ("-(3 + 4) * 2", -14), ("2 * 3 ^ 2", 18), ("-3^2 + 10", 1),
    ("(((7)))", 7), ("8 / 3 * 3", 6), ("2^10 / 3", 341),
]
for expr, exp in cases:
    check(expr, lambda e=expr, x=exp: expect_eq(avaliar(e), x))
for expr in ["", "   ", "(1+2", "1+2)", "1 +", "* 2", "1 2", "3 % 2", "1.5 + 1", "+3", "()", "2^-1"]:
    check("ValueError: " + repr(expr), lambda e=expr: expect_raises(ValueError, avaliar, e))
check("ZeroDivisionError", lambda: expect_raises(ZeroDivisionError, avaliar, "5 / (2 - 2)"))
""",
    },
    {
        "id": "calculo_frete",
        "func": "calcular_frete",
        "prompt": """Implemente em Python a função
`calcular_frete(peso_kg: float, regiao: str, valor_pedido: float, cupom: str | None = None, expresso: bool = False) -> float`
seguindo EXATAMENTE as regras, aplicadas nesta ordem:

1. Validação: peso_kg deve ser > 0 e <= 30; regiao deve ser uma de "S", "SE", "CO", "NE", "N"; valor_pedido deve ser >= 0. Caso contrário, levante ValueError.
2. Tarifa base por peso:
   - até 1 kg (inclusive): R$ 12,00
   - acima de 1 kg até 5 kg (inclusive): R$ 12,00 + R$ 3,50 por kg adicional OU FRAÇÃO acima de 1 kg (ex.: 1,2 kg → 1 fração → 15,50; 2,0 kg → 15,50; 2,01 kg → 19,00)
   - acima de 5 kg: R$ 26,00 + R$ 2,80 por kg OU FRAÇÃO acima de 5 kg
3. Multiplicador regional sobre a tarifa base: S e SE ×1,00; CO ×1,20; NE ×1,35; N ×1,50.
4. Expresso: +40% sobre o valor obtido no passo 3.
5. Frete grátis: se valor_pedido >= 299,90 E não for expresso E a região for S, SE ou CO, o frete é 0 — nesse caso o cupom é totalmente ignorado (mesmo se for inválido).
6. Cupons (sem diferenciar maiúsculas de minúsculas): "FRETE10" dá 10% de desconto no frete; "FRETEMETADE" dá 50% de desconto, mas só vale se peso_kg <= 5 (senão o cupom é ignorado). None ou string vazia = sem cupom. Qualquer outro cupom: ValueError.
7. Frete mínimo: depois dos descontos, o frete nunca é menor que R$ 9,90 (exceto no frete grátis, que é 0).
8. Arredonde o resultado final para 2 casas decimais com arredondamento comercial (meio para cima, ROUND_HALF_UP) e retorne float.

Responda apenas com um bloco de código Python contendo a implementação, sem exemplos nem testes.""",
        "tests": r"""
from solution import calcular_frete as f
cases = [
    ((0.5, "S", 50.0), {}, 12.00),
    ((1.0, "SE", 50.0), {}, 12.00),
    ((1.2, "S", 50.0), {}, 15.50),
    ((2.0, "S", 50.0), {}, 15.50),
    ((2.01, "S", 50.0), {}, 19.00),
    ((5.0, "S", 50.0), {}, 26.00),
    ((6.3, "S", 50.0), {}, 31.60),
    ((30.0, "N", 10.0), {}, 144.00),
    ((3.5, "NE", 100.0), {}, 30.38),
    ((3.5, "CO", 100.0), {"expresso": True}, 37.80),
    ((7.1, "N", 100.0), {"expresso": True}, 72.24),
    ((2.0, "S", 299.90), {}, 0.0),
    ((2.0, "S", 299.89), {}, 15.50),
    ((2.0, "SE", 500.0), {"expresso": True}, 21.70),
    ((2.0, "NE", 500.0), {}, 20.93),
    ((2.0, "CO", 400.0), {"cupom": "QUALQUER"}, 0.0),
    ((2.0, "NE", 100.0), {"cupom": "frete10"}, 18.83),
    ((4.0, "NE", 100.0), {"cupom": "FreteMetade"}, 15.19),
    ((6.0, "NE", 100.0), {"cupom": "FRETEMETADE"}, 38.88),
    ((0.5, "S", 50.0), {"cupom": "FRETEMETADE"}, 9.90),
    ((1.0, "S", 50.0), {"cupom": ""}, 12.00),
    ((1.5, "N", 20.0), {"cupom": "FRETE10", "expresso": True}, 29.30),
    ((1.5, "N", 20.0), {"cupom": "FRETEMETADE"}, 11.63),
    ((3.5, "N", 20.0), {"cupom": "FRETE10", "expresso": True}, 42.53),
]
for args, kw, exp in cases:
    check(repr((args, kw)), lambda a=args, k=kw, x=exp: expect_close(f(*a, **k), x, 0.0001))
for args, kw in [((0, "S", 10.0), {}), ((30.01, "S", 10.0), {}), ((2.0, "SUL", 10.0), {}),
                 ((2.0, "S", -1.0), {}), ((2.0, "NE", 50.0), {"cupom": "BLACKFRIDAY"}),
                 ((-1.0, "S", 400.0), {})]:
    check("ValueError " + repr((args, kw)), lambda a=args, k=kw: expect_raises(ValueError, f, *a, **k))
""",
    },
    {
        "id": "corrigir_sessoes",
        "func": "agrupar_sessoes",
        "prompt": '''A função abaixo tem bugs: ela não segue a própria docstring. Corrija-a para que siga a docstring à risca.

```python
def agrupar_sessoes(eventos, limite_inatividade=30):
    """
    eventos: lista de tuplas (usuario: str, timestamp: int em segundos), em qualquer ordem.
    Agrupa os eventos de cada usuário em sessões: dois eventos consecutivos (em ordem de
    tempo) do mesmo usuário pertencem à mesma sessão se a diferença entre eles for
    menor ou igual a limite_inatividade.
    Retorna um dict usuario -> lista de sessões; cada sessão é uma tupla
    (inicio, fim, quantidade_de_eventos), e as sessões ficam em ordem cronológica.
    Eventos duplicados (mesmo usuário e mesmo timestamp) contam uma única vez.
    A lista de entrada não pode ser modificada.
    """
    resultado = {}
    eventos.sort(key=lambda e: e[1])
    for usuario, ts in eventos:
        sessoes = resultado.setdefault(usuario, [])
        if sessoes and ts - sessoes[-1][1] < limite_inatividade:
            inicio, fim, qtd = sessoes[-1]
            sessoes[-1] = (inicio, ts, qtd + 1)
        else:
            sessoes.append((ts, ts, 1))
    return resultado
```

Responda apenas com um bloco de código Python contendo a função corrigida completa.''',
        "tests": r"""
from solution import agrupar_sessoes as g
def t_vazio():
    return expect_eq(g([]), {})
def t_nao_muta():
    ev = [("a", 50), ("a", 10), ("b", 5)]
    copia = list(ev)
    g(ev)
    return ev == copia, "input mutated to " + repr(ev)
def t_limite_igual():
    return expect_eq(g([("a", 0), ("a", 30), ("a", 61)]), {"a": [(0, 30, 2), (61, 61, 1)]})
def t_duplicados():
    return expect_eq(g([("a", 10), ("a", 10), ("a", 20)]), {"a": [(10, 20, 2)]})
def t_desordenado_multi():
    ev = [("b", 102), ("a", 5), ("b", 40), ("a", 100), ("a", 20), ("b", 71), ("b", 70)]
    return expect_eq(g(ev), {"a": [(5, 20, 2), (100, 100, 1)], "b": [(40, 71, 3), (102, 102, 1)]})
def t_limite_custom():
    return expect_eq(g([("x", 0), ("x", 5), ("x", 11)], limite_inatividade=5),
                     {"x": [(0, 5, 2), (11, 11, 1)]})
def t_dup_outro_usuario():
    return expect_eq(g([("a", 1), ("b", 1), ("a", 1)]), {"a": [(1, 1, 1)], "b": [(1, 1, 1)]})
def t_tupla_entrada():
    ev = (("a", 3), ("a", 1))
    return expect_eq(g(list(ev)), {"a": [(1, 3, 2)]})
for name, fn in [("vazio", t_vazio), ("nao_muta", t_nao_muta), ("limite_igual", t_limite_igual),
                 ("duplicados", t_duplicados), ("desordenado_multi", t_desordenado_multi),
                 ("limite_custom", t_limite_custom), ("dup_outro_usuario", t_dup_outro_usuario),
                 ("tupla_entrada", t_tupla_entrada)]:
    check(name, fn)
""",
    },
]


def coding_messages(task):
    return [
        {"role": "system", "content": "Você é um engenheiro de software cuidadoso. Siga a especificação à risca."},
        {"role": "user", "content": task["prompt"]},
    ]


def extract_code(text, func_name):
    if not text:
        return ""
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", text, re.S | re.I)
    with_def = [b for b in blocks if re.search(rf"def\s+{re.escape(func_name)}\s*\(", b)]
    if with_def:
        return max(with_def, key=len).strip()
    if blocks:
        return max(blocks, key=len).strip()
    idx = text.find("def ")
    return text[idx:].strip() if idx >= 0 else ""


def coding_test_source(task):
    return _TEST_RUNNER + task["tests"] + _TEST_FOOTER


# ---------------------------------------------------------------------------
# Tool calling (simulated tools, multiple turns)
# ---------------------------------------------------------------------------


def _fn(name, desc, props, required):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required},
        },
    }


TOOLS_LOJA = [
    _fn("buscar_cliente", "Busca um cliente pelo e-mail.", {"email": {"type": "string"}}, ["email"]),
    _fn(
        "listar_pedidos",
        "Lista os pedidos de um cliente. Se status for omitido, lista todos.",
        {
            "cliente_id": {"type": "string"},
            "status": {"type": "string", "enum": ["aberto", "enviado", "entregue", "cancelado"]},
        },
        ["cliente_id"],
    ),
    _fn(
        "calcular_reembolso",
        "Calcula o valor de reembolso de UM pedido cancelado (pode ser diferente do valor pago).",
        {"pedido_id": {"type": "string"}},
        ["pedido_id"],
    ),
]

_PEDIDOS = [
    {"pedido_id": "P-1007", "status": "cancelado", "valor": 189.90},
    {"pedido_id": "P-1019", "status": "entregue", "valor": 75.00},
    {"pedido_id": "P-1031", "status": "cancelado", "valor": 54.50},
    {"pedido_id": "P-1040", "status": "enviado", "valor": 310.00},
    {"pedido_id": "P-1052", "status": "cancelado", "valor": 236.00},
]
_REEMBOLSOS = {"P-1007": 170.91, "P-1031": 49.05, "P-1052": 212.40}


def _sim_loja(name, args, state):
    if name == "buscar_cliente":
        if str(args.get("email", "")).strip().lower() == "ana.ribeiro@exemplo.com":
            return {"cliente_id": "C-2291", "nome": "Ana Ribeiro"}
        return {"erro": "cliente não encontrado"}
    if name == "listar_pedidos":
        if args.get("cliente_id") != "C-2291":
            return {"erro": "cliente_id inválido"}
        st = args.get("status")
        return {"pedidos": [p for p in _PEDIDOS if not st or p["status"] == st]}
    if name == "calcular_reembolso":
        pid = args.get("pedido_id")
        state.setdefault("reembolsos", []).append(pid)
        if pid in _REEMBOLSOS:
            return {"pedido_id": pid, "reembolso": _REEMBOLSOS[pid]}
        return {"erro": f"pedido {pid} não está cancelado ou não existe"}
    return {"erro": f"ferramenta desconhecida: {name}"}


def _check_loja(final, state):
    nums = numbers_in(final)
    got_total = any(abs(n - 432.36) < 0.005 for n in nums)
    called = set(state.get("reembolsos", []))
    all_called = {"P-1007", "P-1031", "P-1052"} <= called
    return got_total and all_called, {"total_ok": got_total, "refunds_queried": sorted(called)}


TOOLS_AGENDA = [
    _fn(
        "agendar_reuniao",
        "Agenda uma reunião.",
        {
            "titulo": {"type": "string"},
            "inicio": {"type": "string", "description": "Data e hora locais no formato YYYY-MM-DDTHH:MM"},
            "duracao_min": {"type": "integer", "description": "Duração em minutos"},
            "participantes": {"type": "array", "items": {"type": "string"}, "description": "E-mails"},
            "sala": {"type": "string", "enum": ["Azul", "Verde", "Laranja"]},
        },
        ["titulo", "inicio", "duracao_min", "participantes"],
    )
]


def _sim_agenda(name, args, state):
    state.setdefault("agendamentos", []).append(args)
    return {"status": "agendado", "id": "R-5521"}


def _check_agenda(final, state):
    ags = state.get("agendamentos") or []
    if len(ags) != 1:
        return False, {"reason": f"{len(ags)} bookings"}
    a = ags[0]
    dur = a.get("duracao_min")
    dur_ok = (isinstance(dur, int) and not isinstance(dur, bool) and dur == 90) or dur == "90"
    parts = a.get("participantes")
    parts_ok = isinstance(parts, list) and {str(p).strip().lower() for p in parts} == {
        "carla.souza@empresa.com",
        "diego.alves@empresa.com",
    }
    checks = {
        "inicio": str(a.get("inicio", "")).startswith("2026-10-27T14:30"),
        "duracao": dur_ok,
        "participantes": parts_ok,
        "sala": a.get("sala") == "Verde",
        "titulo": "orcamento" in normalize(a.get("titulo", "")),
    }
    return all(checks.values()), {"checks": checks, "args": a}


TOOLS_ESTOQUE = [
    _fn("buscar_produto", "Busca produtos pelo nome.", {"nome": {"type": "string"}}, ["nome"]),
    _fn("consultar_estoque", "Consulta o estoque de um SKU.", {"sku": {"type": "string"}}, ["sku"]),
]


def _sim_estoque(name, args, state):
    if name == "buscar_produto":
        if "ergo" in normalize(args.get("nome", "")):
            return {"resultados": [{"sku": "SKU-88412-A", "nome": "Cadeira Ergo Plus"}]}
        return {"resultados": []}
    if name == "consultar_estoque":
        sku = str(args.get("sku", "")).strip().upper()
        state.setdefault("skus", []).append(sku)
        if sku == "SKU-88412-A":
            return {"erro": "SKU-88412-A foi substituído pelo SKU-88412-B. Consulte o novo SKU."}
        if sku == "SKU-88412-B":
            return {"sku": "SKU-88412-B", "deposito": 37, "loja": 5}
        return {"erro": "SKU inexistente"}
    return {"erro": f"ferramenta desconhecida: {name}"}


def _check_estoque(final, state):
    nums = [int(n) for n in numbers_in(final) if float(n).is_integer()]
    called_b = "SKU-88412-B" in state.get("skus", [])
    ok = called_b and 37 in nums and 42 not in nums
    return ok, {"queried_B": called_b, "numbers": nums[:6]}


TOOLS_PIX = [
    _fn(
        "transferir_pix",
        "Envia uma transferência PIX. Só use quando chave e valor forem informados explicitamente.",
        {
            "chave": {"type": "string", "description": "Chave PIX do destinatário"},
            "valor": {"type": "number", "description": "Valor em reais"},
            "descricao": {"type": "string"},
        },
        ["chave", "valor"],
    ),
    _fn("consultar_saldo", "Consulta o saldo da conta.", {}, []),
]


def _sim_pix(name, args, state):
    state.setdefault("chamadas", []).append(name)
    if name == "consultar_saldo":
        return {"saldo": 1520.33}
    return {"status": "enviado"}


def _check_pix(final, state):
    called = state.get("chamadas", [])
    ok = "transferir_pix" not in called and bool(final.strip())
    return ok, {"calls": called}


TOOL_TASKS = [
    {
        "id": "multi_etapas_reembolso",
        "tools": TOOLS_LOJA,
        "system": "Você é um agente de atendimento. Use as ferramentas; nunca invente dados.",
        "prompt": (
            "Qual é o valor total que devemos reembolsar à cliente ana.ribeiro@exemplo.com pelos "
            "pedidos cancelados dela? O reembolso de cada pedido deve vir da ferramenta "
            "calcular_reembolso. Informe o total em reais."
        ),
        "simulate": _sim_loja,
        "check": _check_loja,
        "max_steps": 10,
    },
    {
        "id": "args_estritos_agenda",
        "tools": TOOLS_AGENDA,
        "system": (
            "Você agenda reuniões. Hoje é sexta-feira, 23/10/2026; fuso America/Sao_Paulo. "
            "Diretório de e-mails: Bruno Lima <bruno.lima@empresa.com>, Carla Souza "
            "<carla.souza@empresa.com>, Diego Alves <diego.alves@empresa.com>."
        ),
        "prompt": (
            "Marque a reunião \"Revisão do orçamento\" para a próxima terça-feira às 14h30, com "
            "uma hora e meia de duração, com a Carla e o Diego, na sala verde."
        ),
        "simulate": _sim_agenda,
        "check": _check_agenda,
        "max_steps": 3,
    },
    {
        "id": "recuperacao_erro_estoque",
        "tools": TOOLS_ESTOQUE,
        "system": "Você é um assistente de estoque. Use as ferramentas; nunca invente dados.",
        "prompt": "Quantas unidades da Cadeira Ergo Plus temos no depósito?",
        "simulate": _sim_estoque,
        "check": _check_estoque,
        "max_steps": 6,
    },
    {
        "id": "abster_sem_dados_pix",
        "tools": TOOLS_PIX,
        "system": "Você é um assistente bancário. Execute operações apenas com dados completos.",
        "prompt": "Faz um pix pro João, por favor.",
        "simulate": _sim_pix,
        "check": _check_pix,
        "max_steps": 3,
    },
]


def tool_messages(task):
    return [
        {"role": "system", "content": task["system"]},
        {"role": "user", "content": task["prompt"]},
    ]


def parse_args(raw):
    if isinstance(raw, dict):
        return raw
    try:
        val = json.loads(raw or "{}")
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def content_tool_call(message):
    """Detect a tool call written as text instead of a native tool call."""
    content = final_text(message)
    decoder = json.JSONDecoder()
    for m in re.finditer(r"\{", content):
        try:
            obj, _ = decoder.raw_decode(content, m.start())
        except ValueError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("name"), str) and (
            "arguments" in obj or "parameters" in obj
        ):
            return obj["name"]
    return None


# ---------------------------------------------------------------------------
# Reasoning
# ---------------------------------------------------------------------------

PUZZLE_CLUES = [
    "Quem é de Recife mora em um andar par.",
    "Bruno não bebe água.",
    "Carla não é de Belém.",
    "Quem é de Belém bebe suco.",
    "Quem é de Natal bebe água.",
    "Quem é de Manaus não bebe café.",
    "Bruno mora em um andar mais alto que Davi.",
    "Quem bebe mate não mora no primeiro nem no último andar.",
    "Davi mora em um andar mais alto que Carla.",
    "Elisa não é de Natal.",
    "Ana não bebe mate.",
    "Ana mora em um andar mais alto que Carla.",
    "Carla mora em um andar vizinho ao de quem é de Curitiba.",
    "Quem é de Curitiba bebe mate.",
    "Ana mora em um andar vizinho ao de quem é de Natal.",
]

REASONING_TASKS = [
    {
        "id": "logica_5_pessoas",
        "prompt": (
            "Cinco pessoas — Ana, Bruno, Carla, Davi e Elisa — moram em um prédio de 5 andares "
            "(1 a 5), uma por andar. Cada uma é de uma cidade diferente (Recife, Manaus, Curitiba, "
            "Belém, Natal) e bebe uma bebida diferente (café, chá, suco, água, mate). Pistas:\n"
            + "\n".join(f"{i}. {c}" for i, c in enumerate(PUZZLE_CLUES, 1))
            + "\n\nO problema tem solução única. Quem bebe chá? De que cidade é o Davi? Em que andar "
            "mora a Elisa? Termine com uma última linha exatamente no formato: "
            "RESPOSTA: <nome>; <cidade>; <andar>"
        ),
    },
    {
        "id": "aritmetica_datas",
        "prompt": (
            "Hoje é domingo, 25/10/2026. Um contrato dura exatamente 1000 dias e começa hoje, "
            "contando hoje como o dia 1. Qual é a data do último dia do contrato, qual dia da semana "
            "ele cai e quantos dias 29 de fevereiro existem dentro do período do contrato? "
            "Termine com uma última linha exatamente no formato: "
            "RESPOSTA: AAAA-MM-DD; <dia da semana>; <quantidade>"
        ),
    },
    {
        "id": "instrucoes_multiplas",
        "prompt": (
            "Escreva um único parágrafo sobre manutenção de servidores obedecendo a TODAS as regras:\n"
            "1. Exatamente 4 frases, cada uma terminando com ponto final.\n"
            "2. A primeira palavra de cada frase deve começar, respectivamente, com as letras M, A, P e E.\n"
            "3. Não use a letra z em nenhuma palavra.\n"
            "4. A palavra backup deve aparecer exatamente duas vezes (no singular, sem variações).\n"
            "5. Não use vírgulas.\n"
            "6. O texto deve terminar com a palavra fim seguida de ponto final: \"fim.\"\n"
            "Responda apenas com o parágrafo, sem título, aspas ou comentários."
        ),
    },
]


def score_reasoning(task_id, message):
    text = final_text(message)
    if task_id == "logica_5_pessoas":
        line = answer_line(text)
        if not line:
            return False, {"reason": "no RESPOSTA line", "tail": text[-200:]}
        parts = [normalize(p) for p in line.split(";")]
        ok = len(parts) >= 3 and parts[0] == "carla" and parts[1] == "natal" and first_int(parts[2]) == 2
        return ok, {"answer_line": line}
    if task_id == "aritmetica_datas":
        line = answer_line(text)
        if not line:
            return False, {"reason": "no RESPOSTA line", "tail": text[-200:]}
        parts = [p.strip() for p in line.split(";")]
        date_ok = len(parts) >= 1 and "2029-07-20" in parts[0]
        dow_ok = len(parts) >= 2 and "sexta" in normalize(parts[1])
        cnt_ok = len(parts) >= 3 and first_int(parts[2]) == 1
        return date_ok and dow_ok and cnt_ok, {"answer_line": line, "date": date_ok, "weekday": dow_ok, "count": cnt_ok}
    if task_id == "instrucoes_multiplas":
        return check_constraints(text)
    raise KeyError(task_id)


def check_constraints(text):
    t = text.strip().strip("`").strip()
    if t.startswith(("\"", "“")) and t.endswith(("\"", "”")):
        t = t[1:-1].strip()
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", t) if s.strip()]
    firsts = []
    for s in sentences:
        m = re.search(r"[A-Za-zÀ-ÿ]", s)
        firsts.append(m.group(0).upper() if m else "")
    checks = {
        "4_sentences": len(sentences) == 4 and all(s.rstrip().endswith(".") for s in sentences),
        "initials_MAPE": firsts == ["M", "A", "P", "E"],
        "no_z": "z" not in t.lower(),
        "backup_2x": len(re.findall(r"\bbackup\b", t, re.I)) == 2,
        "no_commas": "," not in t,
        "ends_with_fim": bool(re.search(r"\bfim\.$", t, re.I)),
    }
    return all(checks.values()), {"checks": checks, "sentences": len(sentences)}
