"""Use-case suite: one group of tests per LiteLLM route served by the BC-250 (thinking off).

Each route keeps its own temperature, max_tokens and timeout (ROUTES); top_p/top_k/min_p and
penalties come from the model (the "sampling_nothink" entry in the models file). Every test is
graded automatically from the final answer; the route's timeout counts as a failure.

Routes:
  voice-chat       spoken answers: correct, short, no markdown/emoji, under 15 s end to end
  subtitles        SRT translation EN -> PT-BR: cues, timestamps and tags intact, line limits
  prompt-enhancer  short request -> one detailed image prompt that keeps every requested element
  owui-tasks       Open WebUI background tasks: title, tags, follow-ups, search queries (JSON)
  simple-chat      everyday chat: arithmetic, constrained e-mail, short explanation, summary
"""

import json
import re
import unicodedata

ROUTES = {
    "voice-chat": {"temperature": 0.7, "max_tokens": 150, "timeout": 15},
    "subtitles": {"temperature": 0.2, "max_tokens": 2048, "timeout": 600},
    "prompt-enhancer": {"temperature": 0.7, "max_tokens": 800, "timeout": 600},
    "owui-tasks": {"temperature": 0.3, "max_tokens": 512, "timeout": 600},
    "simple-chat": {"temperature": 0.7, "max_tokens": 2048, "timeout": 300},
}

EN_WORDS = {"the", "and", "you", "your", "with", "for", "we", "to", "of", "is", "now", "please",
            "what", "are", "it", "this", "that", "here", "i", "me", "my", "he", "she", "they"}
# words that only exist in Portuguese (no "a", "no", "as", "do": English has them too)
PT_WORDS = {"de", "que", "e", "o", "um", "uma", "para", "com", "em", "na", "os", "da", "por", "seu",
            "sua", "nao", "mais", "dos", "das", "pelo", "pela"}

EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF\u2B50\u2B06\u2194-\u21FF]")


def plain(text):
    text = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def words(text):
    return re.findall(r"[a-zà-ÿ0-9']+", str(text).lower())


def numbers(text):
    out = []
    for m in re.finditer(r"\d+(?:[.,]\d+)?", text):
        try:
            out.append(float(m.group(0).replace(",", ".")))
        except ValueError:
            pass
    return out


def has_markdown(text):
    return bool(re.search(r"\*\*|__|^#+\s|^\s*[-*•]\s|^\s*\d+[.)]\s|`", text, re.M))


def check_all(checks, **extra):
    failed = [k for k, v in checks.items() if not v]
    return not failed, {"failed": failed, **extra}


# ---------------------------------------------------------------------------
# voice-chat
# ---------------------------------------------------------------------------

VOICE_SYSTEM = (
    "Você é um assistente de voz. Suas respostas serão convertidas em fala. Responda em "
    "português do Brasil, em no máximo duas frases curtas, sem markdown, listas, emojis ou "
    "símbolos."
)


def _voice(answer_check):
    def score(text, wall_s):
        w = words(text)
        checks = {
            "answer": answer_check(text),
            "max_40_words": len(w) <= 40,
            "no_markdown": not has_markdown(text),
            "no_emoji": not EMOJI.search(text),
            "portuguese": sum(x in EN_WORDS for x in w) <= 1,
            "under_15s": wall_s is not None and wall_s <= 15,
        }
        return check_all(checks, words=len(w))
    return score


VOICE_TASKS = [
    {"id": "voz_porcentagem", "prompt": "Quanto é 15% de 80?",
     "score": _voice(lambda t: 12 in [int(n) for n in numbers(t) if n.is_integer()] or "doze" in plain(t))},
    {"id": "voz_conversao", "prompt": "Converte 5 milhas pra quilômetros.",
     "score": _voice(lambda t: any(7.9 <= n <= 8.1 for n in numbers(t)) or "oito" in plain(t))},
    {"id": "voz_fato", "prompt": "Qual é a capital da Austrália?",
     "score": _voice(lambda t: "canberra" in plain(t))},
    {"id": "voz_dica", "prompt": "Me dá uma dica rápida pra dormir melhor.",
     "score": _voice(lambda t: len(words(t)) >= 5)},
]


# ---------------------------------------------------------------------------
# subtitles
# ---------------------------------------------------------------------------

SUBTITLE_PROMPT = (
    "Traduza as legendas SRT abaixo do inglês para o português do Brasil. Regras: mantenha a "
    "numeração, os timestamps e as tags (como <i>) exatamente como estão; não junte nem divida "
    "legendas; no máximo 2 linhas por legenda e 42 caracteres por linha; use linguagem natural "
    "de legenda brasileira. Responda apenas com o SRT traduzido.\n\n"
)

SRT_1 = """1
00:00:01,200 --> 00:00:03,400
Hey, are you coming to the premiere tonight?

2
00:00:03,600 --> 00:00:06,100
I'm on it. Just finishing
the last scene.

3
00:00:06,300 --> 00:00:08,000
<i>Break a leg!</i>

4
00:00:08,200 --> 00:00:11,500
Actually, I'm a bit nervous.
It's my first lead role.

5
00:00:11,700 --> 00:00:13,900
You'll nail it. Trust me.
"""

SRT_2 = """1
00:01:05,000 --> 00:01:08,200
The storm knocked out power
to 12,500 homes on Tuesday.

2
00:01:08,400 --> 00:01:11,000
Crews expect to restore it
by 6 p.m. tomorrow.

3
00:01:11,200 --> 00:01:14,600
<i>Officials urge residents
to stay off the roads.</i>

4
00:01:14,800 --> 00:01:17,300
For updates, visit the city website.
"""

SRT_CUE = re.compile(r"(\d+)\s*\n(\d\d:\d\d:\d\d,\d{3} --> \d\d:\d\d:\d\d,\d{3})\s*\n(.*?)(?=\n\s*\n\d+\s*\n\d\d:|\Z)", re.S)


def parse_srt(text):
    text = text.strip().strip("`").replace("\r\n", "\n")
    text = re.sub(r"^(srt|text)\n", "", text)
    return [(int(i), ts, body.strip()) for i, ts, body in SRT_CUE.findall(text.strip() + "\n")]


def _subtitle_score(source, require, forbid):
    src = parse_srt(source)

    def score(text, wall_s):
        cues = parse_srt(text)
        body = "\n".join(b for _, _, b in cues)
        p = plain(body)
        lines = [ln for _, _, b in cues for ln in b.split("\n")]
        checks = {
            "same_cues": [(i, ts) for i, ts, _ in cues] == [(i, ts) for i, ts, _ in src],
            "tags_kept": body.count("<i>") == source.count("<i>") and body.count("</i>") == source.count("</i>"),
            "max_2_lines": all(len(b.split("\n")) <= 2 for _, _, b in cues),
            "max_42_chars": all(len(re.sub(r"</?i>", "", ln)) <= 42 for ln in lines),
            "translated": sum(x in EN_WORDS for x in words(re.sub(r"</?i>", " ", body))) <= 1,
        }
        checks.update({f"require:{n}": bool(re.search(rx, p)) for n, rx in require})
        checks.update({f"forbid:{n}": not re.search(rx, p) for n, rx in forbid})
        return check_all(checks, cues=len(cues))
    return score


SUBTITLE_TASKS = [
    {"id": "legenda_dialogo", "prompt": SUBTITLE_PROMPT + SRT_1,
     "score": _subtitle_score(SRT_1,
                              require=[("estreia", r"estreia"), ("break_a_leg", r"boa sorte|merda|arrasa|manda ver|vai com tudo"),
                                       ("lead_role", r"protagonista|papel principal|primeiro papel")],
                              forbid=[("quebre_a_perna", r"quebr\w* (a|uma|sua) perna"), ("atualmente", r"\batualmente\b"),
                                      ("estou_nele", r"estou nele|to nele|estou em cima disso")])},
    {"id": "legenda_noticia", "prompt": SUBTITLE_PROMPT + SRT_2,
     "score": _subtitle_score(SRT_2,
                              require=[("numero_pt", r"12\.500|12 500|12 mil"), ("terca", r"terca"), ("18h", r"\b18 ?h|18:00|seis da tarde")],
                              forbid=[("numero_en", r"12,500"), ("pm", r"\bp\.?m\b")])},
]


# ---------------------------------------------------------------------------
# prompt-enhancer
# ---------------------------------------------------------------------------

ENHANCER_SYSTEM = (
    "Você melhora prompts para um gerador de imagens. Reescreva o pedido do usuário como um "
    "único prompt detalhado, em inglês, num só parágrafo de 40 a 150 palavras: descreva sujeito, "
    "cenário, iluminação, estilo e composição. Mantenha todos os elementos pedidos e não "
    "contradiga nenhum. Responda apenas com o prompt, sem comentários, títulos ou aspas."
)


def _enhancer_score(require, forbid=()):
    def score(text, wall_s):
        t = text.strip()
        p = plain(t)
        w = words(t)
        checks = {
            "one_paragraph": "\n\n" not in t and not has_markdown(t),
            "40_to_150_words": 40 <= len(w) <= 150,
            "english": sum(x in PT_WORDS for x in w) <= 3,
            "no_preamble": not re.match(r"^(here|aqui|sure|claro|prompt|enhanced|melhorado)\b", p),
        }
        checks.update({f"keeps:{n}": bool(re.search(rx, p)) for n, rx in require})
        checks.update({f"avoids:{n}": not re.search(rx, p) for n, rx in forbid})
        return check_all(checks, words=len(w))
    return score


ENHANCER_TASKS = [
    {"id": "prompt_gato_astronauta", "prompt": "um gato astronauta flutuando perto de saturno, estilo aquarela",
     "score": _enhancer_score([("cat", r"\bcats?\b|kitten|feline"), ("astronaut", r"astronaut|space ?suit"),
                               ("saturn", r"saturn"), ("watercolor", r"watercolou?r")])},
    {"id": "prompt_logo", "prompt": "logo minimalista de uma cafeteria chamada Grão Fino, fundo branco",
     "score": _enhancer_score([("logo", r"\blogo"), ("minimal", r"minimal"), ("name", r"grao fino"),
                               ("white_bg", r"white background|plain white|on white")],
                              forbid=[("busy_bg", r"(dark|black|colorful|busy) background")])},
    {"id": "prompt_sem_pessoas", "prompt": "rua de paris de manhã cedo, chuva fina, sem nenhuma pessoa",
     "score": _enhancer_score([("paris", r"paris"), ("morning", r"morning|dawn|sunrise"), ("rain", r"rain|drizzl"),
                               ("no_people", r"no people|without (any )?people|empty|deserted|devoid of|no one|nobody|unpopulated")],
                              forbid=[("people", r"\b(pedestrians?|passers?-?by|crowds?|a (man|woman|couple)|people (walk|stroll)|figures? (walk|hurr))")])},
]


# ---------------------------------------------------------------------------
# owui-tasks (prompts modelled on Open WebUI's default task templates)
# ---------------------------------------------------------------------------

OWUI_CHAT = """USER: Como faço backup automático diário do meu banco Postgres num servidor Ubuntu?
ASSISTANT: Você pode usar o pg_dump agendado no cron. Crie um script que rode pg_dump com compressão, salve o arquivo com a data no nome e apague backups com mais de 7 dias. Depois agende no crontab para rodar às 2h.
USER: E como eu mando esses backups pra um bucket S3 depois?"""

_OWUI_RULES = (
    "- Your entire response must consist solely of the JSON object, without any introductory or "
    "concluding text.\n- The output must be a single, raw JSON object, without any markdown code "
    "fences or other encapsulating text.\n"
)

OWUI_PROMPTS = {
    "title": ("### Task:\nGenerate a concise, 3-5 word title with an emoji summarizing the chat history.\n"
              "### Guidelines:\n- The title should clearly represent the main theme or subject of the conversation.\n"
              "- Use emojis that enhance understanding of the topic, but avoid quotation marks or special formatting.\n"
              "- Write the title in the chat's primary language; default to English if multilingual.\n"
              + _OWUI_RULES + '### Output:\nJSON format: { "title": "your concise title here" }\n'),
    "tags": ("### Task:\nGenerate 1-3 broad tags categorizing the main themes of the chat history, along with "
             "1-3 more specific subtopic tags.\n### Guidelines:\n- Start with high-level domains.\n"
             "- Consider including relevant subfields/subdomains if they are strongly represented.\n"
             "- Use the chat's primary language; default to English if multilingual.\n"
             + _OWUI_RULES + '### Output:\nJSON format: { "tags": ["tag1", "tag2", "tag3"] }\n'),
    "follow_ups": ("### Task:\nSuggest 3-5 relevant follow-up questions or prompts that the user might naturally "
                   "ask next in this conversation, based on the chat history.\n### Guidelines:\n"
                   "- Write all follow-up questions from the user's point of view, directed to the assistant.\n"
                   "- Make questions concise, clear, and directly related to the discussed topic(s).\n"
                   "- Use the conversation's primary language; default to English if multilingual.\n"
                   + _OWUI_RULES + '### Output:\nJSON format: { "follow_ups": ["Question 1?", "Question 2?", "Question 3?"] }\n'),
    "queries": ("### Task:\nAnalyze the chat history to determine the necessity of generating search queries, "
                "in the given language. By default, prioritize generating 1-3 broad and relevant search queries.\n"
                "### Guidelines:\n- Respond EXCLUSIVELY with a JSON object.\n"
                "- Each query should be concise and focused on the latest question.\n"
                + _OWUI_RULES + '### Output:\nJSON format: { "queries": ["query1", "query2"] }\n'),
}


def owui_messages(kind):
    return [{"role": "user", "content": OWUI_PROMPTS[kind] + "### Chat History:\n<chat_history>\n"
             + OWUI_CHAT + "\n</chat_history>"}]


def parse_json_object(text):
    """Open WebUI takes the substring between the first '{' and the last '}'."""
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        obj = json.loads(text[i:j + 1])
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _owui_score(kind):
    def score(text, wall_s):
        obj = parse_json_object(text)
        raw = text.strip()
        # Open WebUI cuts from the first "{" to the last "}", so a fenced JSON still works:
        # recorded, but not a failure
        info = {"raw_json_only": raw.startswith("{") and raw.endswith("}")}
        checks = {"json": obj is not None}
        if obj is None:
            return check_all(checks, **info)
        if kind == "title":
            title = obj.get("title")
            ok = isinstance(title, str)
            w = words(EMOJI.sub(" ", title)) if ok else []
            checks.update({"title_str": ok, "3_to_5_words": 3 <= len(w) <= 5, "has_emoji": ok and bool(EMOJI.search(title)),
                           "on_topic": ok and bool(re.search(r"backup|postgres|s3|pg_dump", plain(title))),
                           "portuguese": ok and not (set(w) & EN_WORDS)})
        elif kind == "tags":
            tags = obj.get("tags")
            ok = isinstance(tags, list) and all(isinstance(x, str) for x in tags)
            checks.update({"tags_list": ok, "2_to_6_tags": ok and 2 <= len(tags) <= 6,
                           "on_topic": ok and any(re.search(r"banco|dados|database|postgres|backup|aws|s3|nuvem|cloud|linux|devops", plain(x)) for x in tags)})
        elif kind == "follow_ups":
            qs = obj.get("follow_ups")
            ok = isinstance(qs, list) and all(isinstance(x, str) for x in qs)
            checks.update({"list": ok, "3_to_5": ok and 3 <= len(qs) <= 5,
                           "questions": ok and all(x.strip().endswith("?") for x in qs),
                           "portuguese": ok and sum(x in EN_WORDS for q in qs for x in words(q)) <= 1,
                           "on_topic": ok and sum(bool(re.search(r"s3|backup|bucket|aws|cron|pg_dump|restaur|criptograf", plain(q))) for q in qs) >= 2})
        elif kind == "queries":
            qs = obj.get("queries")
            ok = isinstance(qs, list) and all(isinstance(x, str) for x in qs)
            checks.update({"list": ok, "1_to_3": ok and 1 <= len(qs) <= 3,
                           "about_s3": ok and any(re.search(r"\bs3\b|bucket", plain(q)) for q in qs),
                           "about_postgres_backup": ok and any(re.search(r"postgres|pg_dump|backup", plain(q)) for q in qs)})
        return check_all(checks, **info)
    return score


OWUI_TASKS = [{"id": f"owui_{k}", "kind": k, "score": _owui_score(k)} for k in ("title", "tags", "follow_ups", "queries")]


# ---------------------------------------------------------------------------
# simple-chat
# ---------------------------------------------------------------------------

SUMMARY_TEXT = (
    "A prefeitura de Curitiba anunciou nesta segunda-feira que a linha de ônibus Interbairros II "
    "vai operar com veículos elétricos a partir de 1º de março. Serão 18 ônibus, comprados com "
    "financiamento do BNDES, e a tarifa continua a mesma. Segundo a prefeitura, a troca deve "
    "reduzir em 1.200 toneladas por ano as emissões de CO2 da linha."
)


def _chat_days(text, wall_s):
    p = plain(text)
    return check_all({"answer_92": bool(re.search(r"\b92\b", p)) and not re.search(r"\b(91|93)\s*dias\b", p)})


def _chat_email(text, wall_s):
    p = plain(text)
    w = words(text)
    return check_all({
        "max_80_words": len(w) <= 80,
        "friday": "sexta" in p,
        "10h": bool(re.search(r"\b10 ?h|10:00|10 horas|dez horas", p)),
        "no_desculpa": "desculp" not in p,
        "formal": not re.search(r"\b(oi|beleza|abs|valeu)\b", p),
    }, words=len(w))


def _chat_tcp(text, wall_s):
    p = plain(text)
    lines = [ln for ln in text.strip().split("\n") if ln.strip()]
    return check_all({
        "max_5_lines": len(lines) <= 5,
        "tcp_reliable": bool(re.search(r"confiav|garant|ordem|retransmi|conexao", p)),
        "udp_fast": bool(re.search(r"sem conexao|nao garante|mais rapido|menor latencia|leve|baixa latencia", p)),
        "examples_or_contrast": "udp" in p and "tcp" in p,
    }, lines=len(lines))


def _chat_summary(text, wall_s):
    p = plain(text)
    w = words(text)
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    return check_all({
        "one_sentence": len(sentences) == 1,
        "max_25_words": len(w) <= 25,
        "eletricos": "eletric" in p,
        "linha_ou_curitiba": bool(re.search(r"interbairros|curitiba", p)),
        "no_invented_numbers": all(int(n) in {18, 1, 2, 1200} or n == 1.2 for n in numbers(text.replace("1.200", "1200"))),
    }, words=len(w))


CHAT_TASKS = [
    {"id": "chat_contagem_dias", "prompt": "Quantos dias há de 1º de março até 1º de junho de 2027, sem contar o dia final?", "score": _chat_days},
    {"id": "chat_email_formal", "prompt": ("Escreva um e-mail curto, de no máximo 80 palavras e em tom formal, remarcando "
                                          "a reunião de quinta-feira para sexta-feira às 10h. Não use a palavra \"desculpa\"."),
     "score": _chat_email},
    {"id": "chat_tcp_udp", "prompt": "Explique em no máximo 5 linhas a diferença entre TCP e UDP.", "score": _chat_tcp},
    {"id": "chat_resumo", "prompt": "Resuma o texto abaixo em uma única frase de no máximo 25 palavras.\n\n" + SUMMARY_TEXT,
     "score": _chat_summary},
]


# ---------------------------------------------------------------------------

def messages_for(route, task):
    if route == "voice-chat":
        return [{"role": "system", "content": VOICE_SYSTEM}, {"role": "user", "content": task["prompt"]}]
    if route == "prompt-enhancer":
        return [{"role": "system", "content": ENHANCER_SYSTEM}, {"role": "user", "content": task["prompt"]}]
    if route == "owui-tasks":
        return owui_messages(task["kind"])
    return [{"role": "user", "content": task["prompt"]}]


SUITE = [("voice-chat", VOICE_TASKS), ("subtitles", SUBTITLE_TASKS), ("prompt-enhancer", ENHANCER_TASKS),
         ("owui-tasks", OWUI_TASKS), ("simple-chat", CHAT_TASKS)]
