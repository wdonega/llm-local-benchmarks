"""Suite v1 tasks: needle in a haystack, trivial coding and single-shot tool calling.

Prompts are in Brazilian Portuguese on purpose (the models are used in Portuguese).
"""

import json
import random
import re
import unicodedata

# ---------------------------------------------------------------------------
# Needle in a haystack
# ---------------------------------------------------------------------------

NEEDLE_CODES = ["X7K-9421", "P3M-8802", "Q9T-1174"]
NEEDLE_DEPTHS = [0.10, 0.50, 0.90]

_FILLER = [
    "A rede de sensores da fábrica envia leituras a cada quinze segundos para o servidor de telemetria.",
    "A manutenção preventiva reduz paradas não planejadas e prolonga a vida útil dos equipamentos.",
    "O setor de logística reorganizou as rotas de entrega para diminuir o consumo de combustível.",
    "Os arquivos históricos são compactados semanalmente e copiados para uma unidade externa.",
    "A equipe de suporte registra cada chamado em um sistema com prazos e níveis de prioridade.",
    "O laboratório mantém amostras refrigeradas e confere a temperatura três vezes ao dia.",
    "A iluminação das salas foi ajustada para reduzir o cansaço visual dos operadores.",
    "O inventário é revisado no fim de cada mês, com conferência por amostragem.",
    "Os treinamentos de segurança acontecem trimestralmente e têm presença obrigatória.",
    "A central de monitoramento acompanha os alarmes e aciona a equipe de plantão.",
    "O depósito utiliza etiquetas com código de barras para agilizar a separação de pedidos.",
    "As reuniões de planejamento definem metas de curto prazo e revisam os resultados anteriores.",
    "O sistema de ventilação passa por limpeza periódica para manter a qualidade do ar.",
    "Os relatórios financeiros são consolidados e enviados à diretoria toda segunda-feira.",
    "A biblioteca digital indexa documentos por assunto, autor e data de publicação.",
    "O calendário de férias é organizado para não deixar setores sem cobertura.",
    "Os equipamentos de medição recebem calibração anual e certificados de conformidade.",
    "A cozinha industrial segue um protocolo rígido de higiene e controle de validade.",
    "O time de desenvolvimento revisa o código em pares antes de integrar novas mudanças.",
    "A oficina separa ferramentas por bancada e mantém um quadro de empréstimos.",
    "Os testes de qualidade verificam resistência, dimensões e acabamento de cada lote.",
    "O arquivo de contratos fica em armário climatizado e com acesso controlado.",
    "A distribuição de energia é acompanhada por medidores instalados em cada setor.",
    "O serviço de atendimento funciona em dois turnos e registra a satisfação dos clientes.",
    "A horta comunitária é cuidada por voluntários em escala organizada por semana.",
    "Os mapas de risco são atualizados sempre que uma nova área é incorporada.",
    "A frota passa por inspeção antes de cada viagem longa, com checklist assinado.",
    "O centro de treinamento dispõe de salas equipadas para cursos presenciais e remotos.",
    "As compras de insumos seguem cotação prévia e aprovação do setor responsável.",
    "O painel de indicadores mostra metas, resultados parciais e desvios do período.",
]


def make_needle_context(code, depth, target_chars=32000, seed=0):
    rng = random.Random(seed)
    paragraphs = []
    total = 0
    idx = 1
    while total < target_chars:
        sentences = rng.sample(_FILLER, 5)
        p = f"Registro {idx}: " + " ".join(sentences)
        paragraphs.append(p)
        total += len(p) + 2
        idx += 1
    text = "\n\n".join(paragraphs)
    pos = int(len(text) * depth)
    boundary = text.find("\n\n", pos)
    if boundary == -1:
        boundary = len(text)
    needle = f"O código de acesso do cofre é {code}."
    return text[:boundary] + "\n\n" + needle + "\n\n" + text[boundary:]


def needle_messages(run_index):
    depth = NEEDLE_DEPTHS[run_index]
    code = NEEDLE_CODES[run_index]
    context = make_needle_context(code, depth, seed=1000 + run_index)
    messages = [
        {
            "role": "system",
            "content": "Você é um assistente preciso. Responda somente com o que for pedido.",
        },
        {
            "role": "user",
            "content": context
            + "\n\n---\n\nPergunta: Qual é o código de acesso do cofre? "
            "Responda apenas com o código, sem explicações.",
        },
    ]
    meta = {"code": code, "depth": depth, "context_chars": len(context)}
    return messages, meta


# ---------------------------------------------------------------------------
# Coding
# ---------------------------------------------------------------------------

CODING_TASKS = [
    {
        "id": "soma_pares",
        "prompt": (
            "Escreva apenas um bloco de código Python (```python ... ```) com a função "
            "`soma_pares(nums)`, que recebe uma lista de números e retorna a soma de todos "
            "os números pares. Para lista vazia, retorne 0. Não inclua explicações, "
            "exemplos ou testes."
        ),
        "tests": """
import json
from solution import soma_pares
cases = [([], 0), ([1, 2, 3, 4], 6), ([-2, -1, 0, 2], 0), ([10], 10), ([1, 3, 5], 0)]
res = []
for inp, exp in cases:
    try:
        got = soma_pares(inp)
        res.append({"input": inp, "expected": exp, "got": got, "ok": got == exp})
    except Exception as e:
        res.append({"input": inp, "expected": exp, "error": repr(e), "ok": False})
print(json.dumps({"ok": all(r["ok"] for r in res), "results": res}))
""",
    },
    {
        "id": "conta_vogais",
        "prompt": (
            "Escreva apenas um bloco de código Python (```python ... ```) com a função "
            "`conta_vogais(texto)`, que retorna quantas vogais (a, e, i, o, u) existem no "
            "texto, sem diferenciar maiúsculas de minúsculas. Não inclua explicações, "
            "exemplos ou testes."
        ),
        "tests": """
import json
from solution import conta_vogais
cases = [("", 0), ("Python", 1), ("Programar em Python", 5), ("AEIOU", 5), ("xyz", 0)]
res = []
for inp, exp in cases:
    try:
        got = conta_vogais(inp)
        res.append({"input": inp, "expected": exp, "got": got, "ok": got == exp})
    except Exception as e:
        res.append({"input": inp, "expected": exp, "error": repr(e), "ok": False})
print(json.dumps({"ok": all(r["ok"] for r in res), "results": res}))
""",
    },
]


def coding_messages(task):
    return [
        {"role": "system", "content": "Você é um programador. Siga exatamente o formato pedido."},
        {"role": "user", "content": task["prompt"]},
    ]


def extract_code(text):
    if not text:
        return ""
    blocks = re.findall(r"```(?:python)?\s*(.*?)```", text, re.S | re.I)
    if blocks:
        return blocks[-1].strip()
    idx = text.find("def ")
    return text[idx:].strip() if idx >= 0 else text.strip()


# ---------------------------------------------------------------------------
# Tool calling
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Obtém a temperatura atual de uma cidade.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "Nome da cidade"},
                    "unit": {"type": "string", "enum": ["c", "f"], "description": "Unidade desejada"},
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": "Busca documentação interna.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Consulta"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_reminder",
            "description": "Cria um lembrete.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "O que lembrar"},
                    "when": {"type": "string", "description": "Quando lembrar"},
                },
                "required": ["text", "when"],
            },
        },
    },
]

TOOL_TASKS = [
    {
        "id": "weather",
        "prompt": "Qual é a temperatura agora em São Paulo? Use a ferramenta de clima.",
        "expected_name": "get_weather",
        "check": lambda args: "saopaulo" in normalize(args.get("city", "")),
    },
    {
        "id": "reminder",
        "prompt": "Crie um lembrete para amanhã às 9h para ligar para o dentista.",
        "expected_name": "create_reminder",
        "check": lambda args: (
            "dentista" in normalize(args.get("text", ""))
            and ("amanha" in normalize(args.get("when", "")) or "9" in str(args.get("when", "")))
        ),
    },
]


def tool_messages(task):
    return [
        {
            "role": "system",
            "content": "Use as ferramentas fornecidas quando forem necessárias. Não invente resultados.",
        },
        {"role": "user", "content": task["prompt"]},
    ]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def normalize(text):
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", text.lower())


def score_needle(message, code):
    answer = message.get("content") or message.get("reasoning_content") or ""
    return normalize(code) in normalize(answer)


def parse_tool_call(message):
    calls = message.get("tool_calls") or []
    if calls:
        fn = calls[0].get("function", {})
        try:
            args = json.loads(fn.get("arguments", "{}"))
        except Exception:
            args = {}
        return fn.get("name"), args, True

    content = message.get("content") or message.get("reasoning_content") or ""
    for match in re.finditer(r"\{.*?\}", content, re.S):
        try:
            obj = json.loads(match.group(0))
        except Exception:
            continue
        if isinstance(obj, dict) and "name" in obj:
            args = obj.get("arguments", obj.get("parameters", {}))
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            return obj.get("name"), args, False
    return None, {}, False


def score_tool(task, message):
    name, args, native = parse_tool_call(message)
    ok = bool(native and name == task["expected_name"] and task["check"](args))
    return ok, {"name": name, "arguments": args, "native": native}
