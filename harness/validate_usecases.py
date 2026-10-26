#!/usr/bin/env python3
"""Validate the use-case graders: a good answer passes, typical bad answers fail. Must print ALL OK."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usecases as U  # noqa: E402

FAILS = []


def expect(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def task(group, tid):
    return next(t for t in group if t["id"] == tid)


def check(group, tid, good, bads, wall=3.0):
    t = task(group, tid)
    ok, d = t["score"](good, wall)
    expect(ok, f"{tid}: good answer passes {d.get('failed')}")
    for name, txt, *w in bads:
        expect(not t["score"](txt, w[0] if w else wall)[0], f"{tid}: rejects {name}")


GOOD_SRT_1 = """1
00:00:01,200 --> 00:00:03,400
Ei, você vem pra estreia hoje à noite?

2
00:00:03,600 --> 00:00:06,100
Já vou. Só estou terminando
a última cena.

3
00:00:06,300 --> 00:00:08,000
<i>Boa sorte!</i>

4
00:00:08,200 --> 00:00:11,500
Na verdade, estou meio nervoso.
É meu primeiro papel principal.

5
00:00:11,700 --> 00:00:13,900
Você vai arrasar. Confia em mim.
"""

GOOD_SRT_2 = """1
00:01:05,000 --> 00:01:08,200
A tempestade deixou 12.500 casas
sem energia na terça-feira.

2
00:01:08,400 --> 00:01:11,000
As equipes esperam religar
até as 18h de amanhã.

3
00:01:11,200 --> 00:01:14,600
<i>As autoridades pedem que os
moradores evitem as ruas.</i>

4
00:01:14,800 --> 00:01:17,300
Para atualizações, acesse o site
da prefeitura.
"""

if __name__ == "__main__":
    print("== voice-chat")
    V = U.VOICE_TASKS
    check(V, "voz_porcentagem", "Quinze por cento de oitenta é 12.",
          [("wrong number", "Quinze por cento de oitenta é 15."),
           ("markdown", "**12**. Quinze por cento de oitenta dá 12."),
           ("too slow", "Dá 12.", 16.2),
           ("too long", "Para calcular quinze por cento de oitenta " + "você multiplica e depois divide " * 6 + "e chega em 12.")])
    check(V, "voz_conversao", "Cinco milhas dão cerca de 8 quilômetros.",
          [("wrong", "Cinco milhas dão cerca de 3 quilômetros."), ("emoji", "Cerca de 8 quilômetros 🚗.")])
    check(V, "voz_fato", "A capital da Austrália é Canberra.",
          [("sydney", "A capital da Austrália é Sydney."), ("english", "The capital of Australia is Canberra.")])
    check(V, "voz_dica", "Evite telas uma hora antes de deitar e mantenha o quarto escuro e fresco.",
          [("list", "- Evite telas antes de deitar\n- Mantenha o quarto escuro"), ("empty", "")])

    print("== subtitles")
    S = U.SUBTITLE_TASKS
    check(S, "legenda_dialogo", GOOD_SRT_1,
          [("literal idiom", GOOD_SRT_1.replace("Boa sorte!", "Quebre a perna!")),
           ("false friend", GOOD_SRT_1.replace("Na verdade", "Atualmente")),
           ("timestamp changed", GOOD_SRT_1.replace("00:00:06,300", "00:00:06,400")),
           ("tag dropped", GOOD_SRT_1.replace("<i>Boa sorte!</i>", "Boa sorte!")),
           ("cues merged", GOOD_SRT_1.replace("\n\n5\n00:00:11,700 --> 00:00:13,900\n", "\n")),
           ("line too long", GOOD_SRT_1.replace("Na verdade, estou meio nervoso.", "Na verdade, eu estou um pouco nervoso agora mesmo.")),
           ("three lines", GOOD_SRT_1.replace("Já vou. Só estou terminando\na última cena.", "Já vou.\nSó estou terminando\na última cena.")),
           ("untranslated", U.SRT_1)])
    check(S, "legenda_noticia", GOOD_SRT_2,
          [("US number", GOOD_SRT_2.replace("12.500", "12,500")),
           ("p.m.", GOOD_SRT_2.replace("até as 18h de amanhã", "até as 6 p.m. de amanhã"))])

    print("== prompt-enhancer")
    E = U.ENHANCER_TASKS
    good_cat = ("A curious orange cat in a detailed white astronaut suit floats weightlessly near Saturn, its rings "
                "glowing in soft golden light. Delicate watercolor painting with loose washes, visible paper texture "
                "and gentle color bleeds, deep indigo space dotted with tiny stars, the cat centered in a wide "
                "composition with Saturn filling the upper right corner, dreamy and whimsical mood.")
    check(E, "prompt_gato_astronauta", good_cat,
          [("dropped watercolor", good_cat.replace("watercolor painting", "digital painting")),
           ("preamble", "Here is your enhanced prompt: " + good_cat),
           ("portuguese", "Um gato curioso de traje espacial flutua perto de Saturno, com os anéis brilhando em luz dourada suave. "
                          "Pintura em aquarela com lavagens soltas, textura de papel visível e cores suaves, espaço azul escuro "
                          "com pequenas estrelas, composição ampla com o gato no centro e Saturno no canto, clima sonhador."),
           ("too short", "A cat astronaut near Saturn, watercolor.")])
    good_logo = ("Minimalist logo for a coffee shop named \"Grão Fino\", a single coffee bean drawn with one clean line "
                 "merging into elegant lowercase lettering, warm brown on a plain white background, flat vector style, "
                 "generous negative space, balanced centered composition, modern and refined, no gradients, no shadows, "
                 "crisp edges suitable for print and signage.")
    check(E, "prompt_logo", good_logo,
          [("lost name", good_logo.replace("\"Grão Fino\"", "\"Bean House\"")),
           ("dark background", good_logo.replace("on a plain white background", "on a dark background"))])
    good_paris = ("An empty cobblestone street in Paris at early morning, fine drizzle falling, wet stones reflecting "
                  "the pale blue light of dawn, Haussmann buildings with wrought-iron balconies lining both sides, "
                  "closed café shutters, street lamps still glowing softly, deserted, no people in sight, cinematic "
                  "wide-angle photograph, soft mist, muted colors, calm and melancholic mood.")
    check(E, "prompt_sem_pessoas", good_paris,
          [("adds pedestrians", good_paris.replace("closed café shutters", "a few pedestrians with umbrellas")),
           ("drops no-people", good_paris.replace("An empty cobblestone", "A cobblestone").replace("deserted, no people in sight, ", ""))])

    print("== owui-tasks")
    O = U.OWUI_TASKS
    check(O, "owui_title", '{ "title": "💾 Backup do Postgres no S3" }',
          [("no emoji", '{ "title": "Backup do Postgres no S3" }'),
           ("too long", '{ "title": "💾 Como fazer backup diário do Postgres e enviar ao S3" }'),
           ("english", '{ "title": "💾 Postgres Backup to the S3" }'),
           ("not json", "💾 Backup do Postgres no S3")])
    expect(U.OWUI_TASKS[0]["score"]('```json\n{ "title": "💾 Backup do Postgres no S3" }\n```', 1)[0],
           "owui_title: accepts fenced JSON (Open WebUI parses it)")
    check(O, "owui_tags", '{ "tags": ["Banco de dados", "DevOps", "PostgreSQL", "AWS S3"] }',
          [("one tag", '{ "tags": ["Banco de dados"] }'), ("wrong key", '{ "tag": ["Banco de dados", "DevOps"] }')])
    check(O, "owui_follow_ups",
          '{ "follow_ups": ["Como criptografo os backups antes de enviar ao S3?", "Como restauro um backup do S3?", '
          '"Dá pra usar o aws s3 sync no cron?"] }',
          [("not questions", '{ "follow_ups": ["Criptografia dos backups", "Restauração", "Sincronização"] }'),
           ("english", '{ "follow_ups": ["How do I encrypt the backups?", "How do I restore from S3?", "Can I use the s3 sync?"] }'),
           ("two only", '{ "follow_ups": ["Como restauro um backup do S3?", "Como criptografo os backups?"] }')])
    check(O, "owui_queries", '{ "queries": ["enviar backup pg_dump para bucket S3", "aws s3 cp cron postgres backup"] }',
          [("off topic", '{ "queries": ["como instalar ubuntu", "cron sintaxe"] }'),
           ("too many", '{ "queries": ["s3 backup", "postgres backup", "pg_dump s3", "aws cli s3"] }')])

    print("== simple-chat")
    C = U.CHAT_TASKS
    check(C, "chat_contagem_dias", "Março tem 31 dias, abril 30 e maio 31, então são 92 dias.",
          [("off by one", "São 93 dias."), ("no number", "São cerca de três meses.")])
    good_mail = ("Prezado João,\n\nInformo que a reunião prevista para quinta-feira foi remarcada para sexta-feira, às 10h, "
                 "no mesmo local. Peço, por gentileza, que confirme sua disponibilidade.\n\nAtenciosamente,\nMaria")
    check(C, "chat_email_formal", good_mail,
          [("desculpa", good_mail.replace("Informo que", "Desculpa, mas")),
           ("wrong day", good_mail.replace("sexta-feira", "segunda-feira")),
           ("too long", good_mail + " Lembro ainda que " + "a pauta inclui os resultados do trimestre e os próximos passos " * 6)])
    good_tcp = ("O TCP é orientado a conexão e garante a entrega e a ordem dos pacotes, retransmitindo o que se perde.\n"
                "O UDP não estabelece conexão nem garante entrega, por isso tem menor latência.\n"
                "TCP serve para web e e-mail; UDP para jogos, voz e streaming.")
    check(C, "chat_tcp_udp", good_tcp,
          [("too many lines", "\n".join(["linha"] * 6) + "\n" + good_tcp),
           ("no udp property", "O TCP é orientado a conexão e garante a entrega.\nO UDP é outro protocolo da camada de transporte.")])
    good_sum = "A linha Interbairros II, de Curitiba, terá 18 ônibus elétricos a partir de 1º de março, sem mudar a tarifa."
    check(C, "chat_resumo", good_sum,
          [("two sentences", "A linha Interbairros II terá ônibus elétricos. A tarifa não muda."),
           ("invented number", good_sum.replace("18 ônibus", "25 ônibus")),
           ("too long", good_sum[:-1] + ", segundo a prefeitura, que espera cortar 1.200 toneladas de CO2 por ano com a troca da frota inteira.")])

    print()
    print(f"{len(FAILS)} failure(s)" if FAILS else "ALL OK")
    sys.exit(1 if FAILS else 0)
