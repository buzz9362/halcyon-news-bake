"""Sep 26 2026 (JS): a code run in a summary is never voiced, and the manifest stores the summary
without it. Ear test, circuitly_de rss_1l6c716 (PC-Welt, baked 2026-09-26T09:01:59Z): after the headline
the car read about 40 s of JavaScript from PC-Welt's "sticky promo block" (the worker's stripHtml keeps
the text between <script> and </script>).

Vectors are real summaries: the live circuitly_de / tickerly_pt / tickerly_en manifests (Sep 26 2026)
and the raw RSS text harvested by the SX lane (worker-style tag stripping), one per publisher shape.
Positive control: every vector input is flagged by an independent code detector (BROAD) and every
output is not; the pre-JS text_for voices the owner's sample with code, text_for does not.

Run from the repo root:  python -m unittest discover -s tests
"""
import importlib.util
import json
import os
import re
import unittest
from unittest import mock

from gtts import gTTS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_bake():
    for k, v in (("R2_ACCESS_KEY_ID", "x"), ("R2_SECRET_ACCESS_KEY", "x"), ("R2_ENDPOINT_URL", "https://example.invalid")):
        os.environ.setdefault(k, v)
    spec = importlib.util.spec_from_file_location("bake", os.path.join(ROOT, "bake.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


bake = _load_bake()

# An independent detector (not the stripper's own anchors), so the two can disagree.
BROAD = re.compile(r"[{}]|=>|function\s*\(|(?:document|window)\.[A-Za-z_$]|querySelector|addEventListener|"
                   r"dataLayer|(?<![A-Za-z])(?:var|let|const)\s+[A-Za-z_$][\w$]*\s*=|@media|\d+px\s*;|!important|"
                   r"<\s*/?\s*script")

# (name, lang, summary as the worker serves it, summary after strip_code_residue)
VECTORS = [
    ("pcwelt_sticky_promo_truncated", "de",
     "-15 % 40-Watt-Netzteil g\u00fcnstig bei Amazon Haul Nur 7,64 Euro statt 9,99 Euro UVP Jetzt ansehen (function () { document.querySelector(\"#sticky-promo-block a\").addEventListener(\"click\", function(e) { const debug = document.location.host.search(/lndo.site|go-vip.net/)!== -1; const text = this.closest(\"#sticky-promo-block\").querySelector(\"p.promo-title\").textContent; const data = { event: \"stickyConversionUnitClick\", eventCategory: \"Sticky Conversion\", eventAction: \"Click\", eventLabel: text }; if(debug)console.log(\"Sticky Conversion CLick - pushing to dataLayer: \", data); dataLayer.push(data); ret",
     "-15 % 40-Watt-Netzteil g\u00fcnstig bei Amazon Haul Nur 7,64 Euro statt 9,99 Euro UVP Jetzt ansehen"),
    ("moneytimes_tradingview_truncated", "pt",
     "O Ibovespa (IBOV) come\u00e7a o preg\u00e3o desta sexa-feira (25) inst\u00e1vel e caminha para estender a sequ\u00eancia de perdas pela segunda semana consecutiva, em rea\u00e7\u00e3o \u00e0 infla\u00e7\u00e3o mais forte do que o esperado. Por volta de 10h10 (hor\u00e1rio de Bras\u00edlia), o principal \u00edndice da bolsa brasileira operava em alta de 0,08%, aos 184.108,85 pontos. Mas, minutos depois, ol IBOV voltou ao territ\u00f3rio negativo: \u00e0s 10h30, o \u00edndice ca\u00eda 0,60%, aos 182.867,08 pontos. new TradingView.MediumWidget( { \"customer\": \"moneytimescombr\", \"symbols\": [ [ \"IBOV\", \"IBOV\" ] ], \"chartOnly\": false, \"width\": \"100%\", \"height\": \"300\", \"locale\":",
     "O Ibovespa (IBOV) come\u00e7a o preg\u00e3o desta sexa-feira (25) inst\u00e1vel e caminha para estender a sequ\u00eancia de perdas pela segunda semana consecutiva, em rea\u00e7\u00e3o \u00e0 infla\u00e7\u00e3o mais forte do que o esperado. Por volta de 10h10 (hor\u00e1rio de Bras\u00edlia), o principal \u00edndice da bolsa brasileira operava em alta de 0,08%, aos 184.108,85 pontos. Mas, minutos depois, ol IBOV voltou ao territ\u00f3rio negativo: \u00e0s 10h30, o \u00edndice ca\u00eda 0,60%, aos 182.867,08 pontos."),
    ("benzinga_hubspot_form_truncated", "en",
     "The post Myro (MYRO) Price Prediction: 2025, 2026, 2030 by Margaret Jackson appeared first on Benzinga. Visit Benzinga to get more great content like this. MYRO $0.0019 Buy MYRO JOIN THE MOON OR BUST EMAIL LIST Our team is diligently working to keep up with trends in the crypto markets. Keep up to date on the latest news and up-and-coming coins. hbspt.forms.create({ region: 'na1', portalId: '2786381', formId: '5f16b7e9-2a75-474f-84ae-bd83a47223c5', onFormSubmit: (form, res) => { let email = form[0][0].value; localStorage.setItem('mob-email', email); window.Helpers.submitVote(\"myro\", email, win",
     "The post Myro (MYRO) Price Prediction: 2025, 2026, 2030 by Margaret Jackson appeared first on Benzinga. Visit Benzinga to get more great content like this. MYRO $0.0019 Buy MYRO JOIN THE MOON OR BUST EMAIL LIST Our team is diligently working to keep up with trends in the crypto markets. Keep up to date on the latest news and up-and-coming coins."),
    ("macwelt_sticky_promo_then_prose", "de",
     "Wir weisen Sie auch regelm\u00e4\u00dfig hier auf anstehende Premieren hin, sowohl auf neue Serien und Filme als auch auf neue Staffeln erfolgreicher Serien. Holen Sie sich Apple TV f\u00fcr 7 Tage gratis Danach f\u00fcr 9,99 Euro im Monat Serien und Filme schauen Angebot ansehen (function () { document.querySelector(\"#sticky-promo-block a\").addEventListener(\"click\", function(e) { const debug = document.location.host.search(/lndo.site|go-vip.net/) !== -1; const text = this.closest(\"#sticky-promo-block\").querySelector(\"p.promo-title\").textContent; const data = { event: \"stickyConversionUnitClick\", eventCategory: \"",
     "Wir weisen Sie auch regelm\u00e4\u00dfig hier auf anstehende Premieren hin, sowohl auf neue Serien und Filme als auch auf neue Staffeln erfolgreicher Serien. Holen Sie sich Apple TV f\u00fcr 7 Tage gratis Danach f\u00fcr 9,99 Euro im Monat Serien und Filme schauen Angebot ansehen"),
    ("moneytimes_tradingview_closed_then_prose", "pt",
     "O petr\u00f3leo fechou em queda nesta sexta-feira (25), em meio a relatos de que as negocia\u00e7\u00f5es entre Ir\u00e3 e Estados Unidos em Nova York avan\u00e7aram para uma fase mais detalhada de discuss\u00f5es t\u00e9cnicas, com a possibilidade de reabertura do Estreito de Ormuz em um prazo de sete dias. O contrato mais l\u00edquido do petr\u00f3leo Brent , refer\u00eancia para o mercado internacional, para novembro fechou em baixa de 2,14% , a US$ 104,32 o barril, na Intercontinental Exchange (ICE), em Londres. new TradingView.MediumWidget( { \"customer\": \"moneytimescombr\", \"symbols\": [ [ \"UKOIL\", \"UKOIL\" ] ], \"chartOnly\": false, \"width\":",
     "O petr\u00f3leo fechou em queda nesta sexta-feira (25), em meio a relatos de que as negocia\u00e7\u00f5es entre Ir\u00e3 e Estados Unidos em Nova York avan\u00e7aram para uma fase mais detalhada de discuss\u00f5es t\u00e9cnicas, com a possibilidade de reabertura do Estreito de Ormuz em um prazo de sete dias. O contrato mais l\u00edquido do petr\u00f3leo Brent , refer\u00eancia para o mercado internacional, para novembro fechou em baixa de 2,14% , a US$ 104,32 o barril, na Intercontinental Exchange (ICE), em Londres."),
    ("benzinga_window_flag", "en",
     "Meme tokens and play-to-earn (P2E) games have emerged as notable contenders, offering opportunities for earning real money and cryptocurrency rewards. Toncoin (TON) stands out in this dynamic environment and is poised to make waves in the coming years. This blog post delves into TON price predictions for 2024, 2025 and beyond, exploring the driving forces behind its performance. window.LOAD_MODULE_LAYOUT = true; Table of contents [ Show ] Toncoin (TON) Price Prediction Table What Is Toncoin (TON)? Will Toncoin Go Past All-Time Highs? Will Toncoin Reach $10? Toncoin Price History and Market Pos",
     "Meme tokens and play-to-earn (P2E) games have emerged as notable contenders, offering opportunities for earning real money and cryptocurrency rewards. Toncoin (TON) stands out in this dynamic environment and is poised to make waves in the coming years. This blog post delves into TON price predictions for 2024, 2025 and beyond, exploring the driving forces behind its performance. Table of contents [ Show ] Toncoin (TON) Price Prediction Table What Is Toncoin (TON)? Will Toncoin Go Past All-Time Highs? Will Toncoin Reach $10? Toncoin Price History and Market Pos"),
    ("tecnoblog_clipboard_handler", "pt",
     "15% OFF Ver pre\u00e7o 8 Asus Vivobook Go 15 (E1504FA-NJ1288) Desempenho \u00e1gil com Ryzen 5 e 16 GB de RAM, tela Full HD de 16\u201d e apenas 1,63 kg para levar aonde quiser. 9 Asus Vivobook 15 (M1502) Desempenho Ryzen 7 com gr\u00e1ficos Radeon, tela Full HD de 15,6\u201d e apenas 1,7 kg para levar aonde quiser. Ver pre\u00e7o Links seguros. Comprando pelos nossos links, voc\u00ea apoia o Tecnoblog sem pagar nada a mais. if(typeof handle_redirect!=='function'){async function handle_redirect(cupom){try{if(navigator.clipboard&&navigator.clipboard.writeText){await navigator.clipboard.writeText(cupom.textContent);}else{var t=do",
     "15% OFF Ver pre\u00e7o 8 Asus Vivobook Go 15 (E1504FA-NJ1288) Desempenho \u00e1gil com Ryzen 5 e 16 GB de RAM, tela Full HD de 16\u201d e apenas 1,63 kg para levar aonde quiser. 9 Asus Vivobook 15 (M1502) Desempenho Ryzen 7 com gr\u00e1ficos Radeon, tela Full HD de 15,6\u201d e apenas 1,7 kg para levar aonde quiser. Ver pre\u00e7o Links seguros. Comprando pelos nossos links, voc\u00ea apoia o Tecnoblog sem pagar nada a mais."),
    ("ifun_open_amazon", "de",
     "Die GO Ultra kostet regul\u00e4r 429 Euro und nimmt mit ihrem 1/1,28-Zoll-Sensor Videos mit bis zu 4K und 60 Bildern pro Sekunde auf. Wer vor allem Rundum-Aufnahmen sucht, findet mit der Insta360 X6 weiterhin eine 8K-Alternative mit zwei gro\u00dfen Sensoren und austauschbaren Objektiven. function open_amazon(link) { if (navigator.userAgent.indexOf(\"Firefox\") != -1) { window.open(link, '_blank'); } else { var tag = document.createElement('a'); tag.setAttribute('href', link); tag.innerHTML = \"amzn\"; tag.click(); } } Produkthinweis Insta360 GO Ultra Polarwei\u00df - Freih\u00e4ndige 4K Vlogging-Kamera 429,00 EUR fu",
     "Die GO Ultra kostet regul\u00e4r 429 Euro und nimmt mit ihrem 1/1,28-Zoll-Sensor Videos mit bis zu 4K und 60 Bildern pro Sekunde auf. Wer vor allem Rundum-Aufnahmen sucht, findet mit der Insta360 X6 weiterhin eine 8K-Alternative mit zwei gro\u00dfen Sensoren und austauschbaren Objektiven. Produkthinweis Insta360 GO Ultra Polarwei\u00df - Freih\u00e4ndige 4K Vlogging-Kamera 429,00 EUR fu"),
    ("xataka_video_json", "es",
     "El salto se ha acelerado en 2026: Kimi K3 alcanza los 2,8 billones y Alibaba ha situado Qwen3.8-Max en 2,4 billones . Son cantidades totales, y esa \u00faltima palabra importa mucho: no significa que todos esos par\u00e1metros entren en juego en cada paso del procesamiento. Eso es precisamente lo que necesitamos entender a continuaci\u00f3n. {\"videoId\":\"xa41k1q\",\"autoplay\":false,\"title\":\"ChatGPT vs Claude: Prob\u00e9 todo para que no tengas que hacerlo\", \"tag\":\"webedia-prod\", \"duration\":\"634\"} Gigantes que no piensan enteros. La arquitectura no es nueva. En 2023, un an\u00e1lisis de SemiAnalysis apunt\u00f3 a que GPT-4 pod",
     "El salto se ha acelerado en 2026: Kimi K3 alcanza los 2,8 billones y Alibaba ha situado Qwen3.8-Max en 2,4 billones . Son cantidades totales, y esa \u00faltima palabra importa mucho: no significa que todos esos par\u00e1metros entren en juego en cada paso del procesamiento. Eso es precisamente lo que necesitamos entender a continuaci\u00f3n. Gigantes que no piensan enteros. La arquitectura no es nueva. En 2023, un an\u00e1lisis de SemiAnalysis apunt\u00f3 a que GPT-4 pod"),
    ("kiplinger_embed_json", "en",
     "A new seven-year, $11.6 billion deal to provide computing power to AI model leader Anthropic underscores that premise, and the tech stock soared after the deal was announced. The contract includes an option to add another $9 billion and push the total deal value to more than $20 billion should Anthropic require more \"compute.\" Track all markets on TradingView {\"source\":\"singleQuote\",\"id\":\"2fb9edcc-b919-11f1-af65-c5ad7506c563\",\"embedType\":\"iframe\",\"attributes\":[],\"preview\":[],\"position\":\"center\",\"embedtype\":\"iframe\",\"embedCode\":\"\",\"extra\":[],\"colorTheme\":\"light\",\"isTransparent\":false,\"locale\":\"",
     "A new seven-year, $11.6 billion deal to provide computing power to AI model leader Anthropic underscores that premise, and the tech stock soared after the deal was announced. The contract includes an option to add another $9 billion and push the total deal value to more than $20 billion should Anthropic require more \"compute.\" Track all markets on TradingView"),
    ("eco_css_block", "pt",
     "A frase A subida da yield portuguesa n\u00e3o significa uma deteriora\u00e7\u00e3o das contas p\u00fablicas nacionais, mas \u00e9 ditada pela subida das yields dos principais benchmarks internacionais. O risco percebido da d\u00edvida portuguesa n\u00e3o aumentou, uma vez que o spread face \u00e0 Alemanha se mant\u00e9m nos 40 pontos base. Paulo Monteiro Rosa Economista do Banco Carregosa O gr\u00e1fico: .errordiv { padding:10px; margin:10px; border: 1px solid #555555;color: #000000;background-color: #f8f8f8; width:500px; }#advanced_iframe {visibility:visible;opacity:1;vertical-align:top;}.ai-info-bottom-iframe { position: fixed; z-index: 100",
     "A frase A subida da yield portuguesa n\u00e3o significa uma deteriora\u00e7\u00e3o das contas p\u00fablicas nacionais, mas \u00e9 ditada pela subida das yields dos principais benchmarks internacionais. O risco percebido da d\u00edvida portuguesa n\u00e3o aumentou, uma vez que o spread face \u00e0 Alemanha se mant\u00e9m nos 40 pontos base. Paulo Monteiro Rosa Economista do Banco Carregosa O gr\u00e1fico:"),
    ("elcomercio_jsonld_truncated", "es",
     ":icon: 00:34 SI USTED CUMPLE A\u00d1OS HOY ES UNA PERSONA: ADAPTABLE, DE BUEN JUICIO Y T\u00cdMIDA PERO RESPETUOSA DE LA LIBERTAD DE LOS DEM\u00c1S. :fijado: 00:33 Conoce lo que te deparan las estrellas en el trabajo, negocio y amor. \u00bfQu\u00e9 dice tu signo hoy , jueves 24 de setiembre? \u2022 Revi\ufeffsa aqu\u00ed el hor\u00f3scopo del jueves 24 de setiembre : {\"@graph\": [{\"@type\": \"Organization\", \"@id\": \"#organization\", \"name\": \"El Comercio Per\\u00fa\", \"url\": \"https://elcomercio.pe/\", \"sameAs\": [\"https://www.facebook.com/elcomercio.pe\", \"https://www.instagram.com/elcomercio/\", \"https://twitter.com/elcomercio_peru\"], \"logo\": {\"@ty",
     ":icon: 00:34 SI USTED CUMPLE A\u00d1OS HOY ES UNA PERSONA: ADAPTABLE, DE BUEN JUICIO Y T\u00cdMIDA PERO RESPETUOSA DE LA LIBERTAD DE LOS DEM\u00c1S. :fijado: 00:33 Conoce lo que te deparan las estrellas en el trabajo, negocio y amor. \u00bfQu\u00e9 dice tu signo hoy , jueves 24 de setiembre? \u2022 Revi\ufeffsa aqu\u00ed el hor\u00f3scopo del jueves 24 de setiembre :"),
    ("canaltech_template_token", "pt",
     "J\u00e1 a medida provis\u00f3ria produz efeitos a partir de sua publica\u00e7\u00e3o, mas ainda ser\u00e1 analisada pelo Congresso. Uma MP vale inicialmente por 60 dias e pode ser prorrogada uma vez pelo mesmo per\u00edodo; C\u00e2mara e Senado podem aprovar, modificar ou rejeitar o texto. {{WHATSAPP_CHANNEL}}",
     "J\u00e1 a medida provis\u00f3ria produz efeitos a partir de sua publica\u00e7\u00e3o, mas ainda ser\u00e1 analisada pelo Congresso. Uma MP vale inicialmente por 60 dias e pode ser prorrogada uma vez pelo mesmo per\u00edodo; C\u00e2mara e Senado podem aprovar, modificar ou rejeitar o texto."),
]

# Real prose that looks a little like code; it must come back unchanged (the same object).
KEEP = [
    "Microsoft has even been rolling out more advanced editing capabilities that let Copilot make broader changes directly inside a document. Now there is another AI sitting in Word.",
    "“The leak of BTS’s album destroyed the element of surprise,” reads the court document. “The leak was deliberate,” the filing adds.",
    "According to the post, four of the passenger’s friends were injured after the stone hit the window. Families with young children were also seated on both sides.",
    "TestFlight this week with support for landscape orientation, and for macOS 27 Golden Gate’s new resizable iPhone Mirroring window. Here are the details. more…",
    "But as AI hardware development continues, and especially if (or when) specific areas of the hardware bubble pop or deflate, I expect to see more situations like this.",
    "Yadav has also recently criticised the Election Commission over electoral processes and questioned its functioning, while calling for greater scrutiny.",
    "From dysfunctional families and marital warfare to murder, revenge, and desperate struggles for survival, black comedy allows the genre to breathe.",
    "#SongYuqi was seen going to #JacksonWang's house after settling at a hotel.…Continue reading on Koreaboo",
    "Actor Ajay Devgn and Kajol’s Juhu bungalow has come under scrutiny after the Brihanmumbai Municipal Corporation (BMC) issued a stop-work notice.",
    "The manga revealed additional cast and a key visual (pictured) on Thursday. The anime series is scheduled to premiere in January 2027.",
    "Samsung Galaxy S26 Ultra: 12 GB RAM, 256 GB, 6.9 inch; the price is 1.449 Euro (UVP 1.599 Euro).",
]

OWNER_SAMPLE = {
    "id": "rss_1l6c716", "source": "PC-WELT",
    "title": "4 Geräte gleichzeitig laden: USB-C-Netzteil kostet aktuell weniger als 8 Euro",
    "summary": VECTORS[0][2],
}
RUN = VECTORS[0][2][VECTORS[0][2].index("(function"):]


def old_text_for(article):
    """text_for as it was before JS (02f5534): the summary voiced as strip_social_residue left it."""
    title = bake.clean_text(article.get("title", ""))
    summary = bake.strip_social_residue(bake.clean_text(article.get("summary", "")))
    source = bake.spoken_source(bake.clean_text(article.get("source", "")))
    parts = [source + ","] if source else []
    if title:
        parts.append(title)
        if not title.endswith((".", "!", "?")):
            parts.append(".")
    if summary and summary.lower() != title.lower():
        parts.append(summary[:bake.FAIR_USE_SNIPPET])
    return " ".join(parts).strip()[:bake.MAX_TEXT_LEN]


def chunks(text, lang="de"):
    """The gTTS chunks one baked MP3 is made of (the appning BakedHeadlineCut mirrors this tokenizer)."""
    return gTTS("x", lang=lang, lang_check=False)._tokenize(text)


def head_plan(full, head, lang="de"):
    """BakedHeadlineCut.planFor: (chunks that start inside "<source>, <title> .", all chunks)."""
    toks = chunks(full, lang)
    k = pos = 0
    for t in toks:
        i = full.find(t, pos)
        i = pos if i < 0 else i
        if i < len(head.rstrip()) - 1:
            k += 1
        pos = i + len(t)
    return k, toks


class StripVectors(unittest.TestCase):
    def test_every_real_shape(self):
        for name, _lang, inp, exp in VECTORS:
            with self.subTest(name):
                self.assertEqual(bake.strip_code_residue(inp), exp)

    def test_positive_control_inputs_have_code_outputs_do_not(self):
        for name, _lang, inp, exp in VECTORS:
            with self.subTest(name):
                self.assertTrue(BROAD.search(inp) or "{{" in inp, "control: the input must carry code")
                self.assertIsNone(BROAD.search(exp))
                self.assertNotIn("{{", exp)

    def test_prose_before_and_after_the_run_is_kept_verbatim(self):
        for name, _lang, inp, exp in VECTORS:
            with self.subTest(name):
                # Every kept word is from the input, in order, untouched (only seams are re-spaced).
                pos = 0
                for w in exp.split(" "):
                    i = inp.find(w, pos)
                    self.assertGreaterEqual(i, 0, w)
                    pos = i + len(w)

    def test_idempotent(self):
        for name, _lang, inp, _exp in VECTORS:
            with self.subTest(name):
                once = bake.strip_code_residue(inp)
                self.assertEqual(bake.strip_code_residue(once), once)

    def test_prose_comes_back_unchanged(self):
        for s in KEEP:
            with self.subTest(s[:40]):
                self.assertIs(bake.strip_code_residue(s), s)
                self.assertFalse(bake.has_code_residue(s))

    def test_script_and_style_elements(self):
        s = ("Das Netzteil kostet aktuell weniger als 8 Euro und lädt vier Geräte gleichzeitig. "
             "<script>(function () { dataLayer.push({event: \"x\"}); })();</script><style>.promo{display:none}</style>"
             "Mehrere Smartphones sorgen im Alltag schnell für einen Steckdosenmangel.")
        self.assertEqual(bake.strip_code_residue(s),
                         "Das Netzteil kostet aktuell weniger als 8 Euro und lädt vier Geräte gleichzeitig. "
                         "Mehrere Smartphones sorgen im Alltag schnell für einen Steckdosenmangel.")

    def test_regexes_are_portable(self):
        # The apps will mirror this rule (ICU on device, the JVM in unit tests): no \b, (?U), \p{..}, \R, \h.
        for rx in (bake._CR_START, bake._CR_ELEMENT, bake._CR_TAIL):
            for bad in ("\\b", "(?U", "\\p{", "\\R", "\\h"):
                self.assertNotIn(bad, rx.pattern)


class VoicedText(unittest.TestCase):
    def test_owner_sample_no_longer_voices_code(self):
        old, new = old_text_for(OWNER_SAMPLE), bake.text_for(OWNER_SAMPLE)
        self.assertIn("querySelector", old, "control: the pre-JS text voices the code")
        self.assertIsNone(BROAD.search(new))
        self.assertEqual(new, "PC-WELT, 4 Geräte gleichzeitig laden: USB-C-Netzteil kostet aktuell weniger als 8 Euro . "
                              "-15 % 40-Watt-Netzteil günstig bei Amazon Haul Nur 7,64 Euro statt 9,99 Euro UVP Jetzt ansehen")

    def test_headline_chunk_boundary_unchanged(self):
        """The appning cut is the start of the chunk after "<source>, <title> ."; it must not move."""
        head = "PC-WELT, " + OWNER_SAMPLE["title"] + " ."
        old, new = old_text_for(OWNER_SAMPLE), bake.text_for(OWNER_SAMPLE)
        self.assertTrue(old.startswith(head + " ") and new.startswith(head + " "))
        k_old, t_old = head_plan(old, head)
        k_new, t_new = head_plan(new, head)
        self.assertEqual((k_old, k_new), (3, 3))
        self.assertEqual(t_new[:3], ["PC-WELT", "4 Geräte gleichzeitig laden",
                                     "USB-C-Netzteil kostet aktuell weniger als 8 Euro"])
        self.assertEqual(t_old[:3], t_new[:3])
        self.assertGreater(len(t_old), len(t_new), "control: the code added chunks after the headline")
        self.assertEqual(t_new[3:], ["-15 % 40-Watt-Netzteil günstig bei Amazon Haul Nur 7,64 Euro statt 9,99 Euro UVP Jetzt ansehen"])

    def test_every_vector_keeps_its_headline_chunks(self):
        title = "A title: with a colon, and a comma"
        head = "Src, " + title + " ."
        for name, lang, inp, _exp in VECTORS:
            with self.subTest(name):
                a = {"source": "Src", "title": title, "summary": inp}
                k_old, t_old = head_plan(old_text_for(a), head, lang)
                k_new, t_new = head_plan(bake.text_for(a), head, lang)
                self.assertEqual(k_new, 4)
                self.assertEqual((k_old, t_old[:k_old]), (k_new, t_new[:k_new]))

    def test_title_is_never_touched(self):
        title = "Why (function () { x(); })(); and {{TOKEN}} matter"
        a = {"source": "Src", "title": title, "summary": "A plain summary that is long enough to be read after the title."}
        self.assertTrue(bake.text_for(a).startswith("Src, " + title + " . A plain summary"))

    def test_short_remainder_reads_the_headline_only(self):
        a = dict(OWNER_SAMPLE, summary="Jetzt ansehen " + RUN)
        self.assertIn("function", old_text_for(a), "control")
        self.assertEqual(bake.strip_code_residue(a["summary"]), "")
        self.assertEqual(bake.text_for(a), "PC-WELT, " + OWNER_SAMPLE["title"] + " .")

    def test_min_is_the_apps_short_content_gate(self):
        self.assertEqual(bake.MIN_SUMMARY_CHARS, 40)   # Article.MIN_SUMMARY_CHARS in every news app
        self.assertEqual(bake.strip_code_residue("x" * 39 + " " + RUN), "")
        self.assertEqual(bake.strip_code_residue("x" * 40 + " " + RUN), "x" * 40)

    def test_clean_story_voices_exactly_as_before(self):
        for s in KEEP:
            a = {"source": "Src", "title": "Title", "summary": s}
            self.assertEqual(bake.text_for(a), old_text_for(a))


class ManifestSummary(unittest.TestCase):
    """The appning app shows the manifest summary and plans its headline cut on it."""

    def test_sanitize_stores_the_clean_summary_title_untouched(self):
        a = bake.sanitize_article(dict(OWNER_SAMPLE))
        self.assertEqual(a["summary"], VECTORS[0][3])
        self.assertEqual(a["title"], OWNER_SAMPLE["title"])
        self.assertEqual(a["id"], OWNER_SAMPLE["id"])

    def test_voiced_text_is_the_same_from_raw_or_stored_summary(self):
        stored = bake.sanitize_article(dict(OWNER_SAMPLE))
        self.assertEqual(bake.text_for(stored), bake.text_for(OWNER_SAMPLE))

    def test_clean_article_is_the_same_object(self):
        a = {"id": "x", "title": "T", "summary": KEEP[0]}
        self.assertIs(bake.without_code_residue(a), a)

    def test_write_manifest_cleans_carried_items(self):
        clean = {"id": "a", "title": "T", "summary": KEEP[0], "publishedAtMs": 2}
        dirty = dict(OWNER_SAMPLE, publishedAtMs=1)
        with mock.patch.object(bake, "s3") as s3:
            bake.write_manifest("circuitly_de", [clean, dirty])
        items = json.loads(s3.put_object.call_args.kwargs["Body"].decode("utf-8"))["items"]
        self.assertEqual(items[0], clean)
        self.assertEqual(items[1]["summary"], VECTORS[0][3])
        self.assertEqual(items[1]["title"], OWNER_SAMPLE["title"])


if __name__ == "__main__":
    unittest.main()
