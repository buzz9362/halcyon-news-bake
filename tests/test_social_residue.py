"""Sep 26 2026 (SX): the social-handle rule on the baked path (owner, Appning car: "LE SSERAFIM's
Chaewon | @_chaechae_1/Instagram" was read aloud). GENERATED from the shared vectors that every news app's
SocialHandleRuleTest and the workers' backend/test/social_residue.test.mjs also pin (real summaries from the
baked manifests, worker feeds and raw RSS of every served language, plus one synthetic case per shape).

Run from the repo root:  python -m unittest discover -s tests
Positive control: every non-keep vector is voiced with a handle or credit line by the pre-SX text_for.
"""
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_bake():
    for k, v in (("R2_ACCESS_KEY_ID", "x"), ("R2_SECRET_ACCESS_KEY", "x"), ("R2_ENDPOINT_URL", "https://example.invalid")):
        os.environ.setdefault(k, v)
    spec = importlib.util.spec_from_file_location("bake", os.path.join(ROOT, "bake.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


bake = _load_bake()

VECTORS = [
    ('caption_name_pipe_handle_platform', 'en', 'LE SSERAFIM Chaewon\u2018s recent Instagram post is going viral after having a \u201cICE\u201d message, but it has sparked hugely divided reactions. LE SSERAFIM\u2019s Chaewon | @_chaechae_1/Instagram Amid the group\u2019s ongoing shows in the US, Chaewon shared some photos from her time in Seattle. View this post on Instagram In one of the photos, Chaewon started\u2026Continue',
     'LE SSERAFIM Chaewon\u2018s recent Instagram post is going viral after having a \u201cICE\u201d message, but it has sparked hugely divided reactions. Amid the group\u2019s ongoing shows in the US, Chaewon shared some photos from her time in Seattle. In one of the photos, Chaewon started\u2026Continue'),
    ('caption_pipe_handle_platform_no_name', 'en', 'When recently debuted singer ZO ZAZZ was questioned about plastic surgery, he didn\u2019t hold back on revealing his extensive list of past procedures. | @zozazz_baustelle/Instagram Although ZO ZAZZ is already 40 years old, he didn\u2019t make his debut as a singer until 2025. His quest to look his best, however, started much earlier. ZO ZAZZ\u2026Continue',
     'When recently debuted singer ZO ZAZZ was questioned about plastic surgery, he didn\u2019t hold back on revealing his extensive list of past procedures. Although ZO ZAZZ is already 40 years old, he didn\u2019t make his debut as a singer until 2025. His quest to look his best, however, started much earlier. ZO ZAZZ\u2026Continue'),
    ('caption_repeated_credit', 'en', 'on Instagram View this post on Instagram Kwak Min Jeong is a 1994 liner, born on January 23. She was 24 years old when her beauty became a hot topic online. | @minjeong_kwak94/Instagram | @minjeong_kwak94/Instagram She\u2026Continue reading on Koreaboo',
     'on Instagram Kwak Min Jeong is a 1994 liner, born on January 23. She was 24 years old when her beauty became a hot topic online. She\u2026Continue reading on Koreaboo'),
    ('caption_handle_slash_x', 'en', '22, Gunwook and Seok Matthew appeared as guests on MBC\u2019s Close Friends, hosted by ZEROBASEONE\u2019s Taerae ZEROBASEONE\u2019s Gunwook, Taerae, and Seok Matthew | @mbcbf_bf/X During the episode, Gunwook and Matthew spoke, and Gunwook complimented Matthew. At one point, Gunwook turned his head,\u2026Continue reading on Koreaboo',
     '22, Gunwook and Seok Matthew appeared as guests on MBC\u2019s Close Friends, hosted by ZEROBASEONE\u2019s Taerae ZEROBASEONE\u2019s Gunwook, Taerae, and Seok Matthew During the episode, Gunwook and Matthew spoke, and Gunwook complimented Matthew. At one point, Gunwook turned his head,\u2026Continue reading on Koreaboo'),
    ('caption_pipe_platform_only', 'en', 'Former KAT-TUN member and actor Taguchi Junnosuke has become a father. Taguchi Junnosuke | Pinterest In a video published on his YouTube channel, Taguchi revealed that he had married a non-celebrity. In the same announcement, Taguchi stated that he waited to make',
     'Former KAT-TUN member and actor Taguchi Junnosuke has become a father. In a video published on his YouTube channel, Taguchi revealed that he had married a non-celebrity. In the same announcement, Taguchi stated that he waited to make'),
    ('tweet_credit_no_dash', 'en', 'hoax, Ukraine call hoax, E. Jean Carroll hoax, Mar-a-lago raid hoax, lawfare hoaxes, etc. etc. and they wonder why the pushback. Too bad. Commentary Trump Daily Posts (@TrumpDailyPosts) September 26, 2026 The White House\u2019s daily guidance and press schedule for Saturda',
     'hoax, Ukraine call hoax, E. Jean Carroll hoax, Mar-a-lago raid hoax, lawfare hoaxes, etc. etc. and they wonder why the pushback. Too bad. The White House\u2019s daily guidance and press schedule for Saturda'),
    ('paren_handle_in_prose', 'en', 'In August, Kristan Hawkins (@kristanmercerhawkins), who identifies herself as president of Students for Life of America and CEO of Pro-Life Generation (both pro-life and anti-abortion groups), uploaded a TikTok',
     'In August, Kristan Hawkins, who identifies herself as president of Students for Life of America and CEO of Pro-Life Generation (both pro-life and anti-abortion groups), uploaded a TikTok'),
    ('embed_view_post_shared_by', 'en', 'serious, but then this was like, oh, this is like really mainstream and commercial and really fun and had a thrill element to it, which people will watch.\u201d View this post on Instagram A post shared by Kindling Pictures (@kindlingindia) Ashi credited Rao and producer-writer Tanaji Dasgupta for presenting the story in a way that immediately connected with the team. \u201cAnd instantly when she narrated,',
     'serious, but then this was like, oh, this is like really mainstream and commercial and really fun and had a thrill element to it, which people will watch.\u201d Ashi credited Rao and producer-writer Tanaji Dasgupta for presenting the story in a way that immediately connected with the team. \u201cAnd instantly when she narrated,'),
    ('handle_run_follow', 'en', 'coming to Arizona Financial Theatre on October 17 with for The X: Nexus World Tour! Enter now to win 2 tickets for you and a friend to attend!How to enter:1. Follow @kpopwise_official @livenationphx and @arizonafinancialtheatre2. Tag 1 friend in the comments in the Instagram post here3. Answer with the song that you want to hear at the showWinner will be randomly chosen on October 7. Can\u2019t',
     'coming to Arizona Financial Theatre on October 17 with for The X: Nexus World Tour! Enter now to win 2 tickets for you and a friend to attend!How to enter:1. Follow. Tag 1 friend in the comments in the Instagram post here3. Answer with the song that you want to hear at the showWinner will be randomly chosen on October 7. Can\u2019t'),
    ('platform_then_lone_handle', 'en', "on a custom image sensor that could arrive as soon as next year with the 20th-anniversary iPhone. See more of Tyler's work over on his YouTube channel or on X @stalman. The MacRumors Show has its own YouTube channel, so make sure you're subscribed to keep up with new episodes and clips. Subscribe to The MacRumors Show YouTube",
     "on a custom image sensor that could arrive as soon as next year with the 20th-anniversary iPhone. See more of Tyler's work over on his YouTube channel or on X. The MacRumors Show has its own YouTube channel, so make sure you're subscribed to keep up with new episodes and clips. Subscribe to The MacRumors Show YouTube"),
    ('via_handle_paren', 'en', "node, Naga Chandrasekaran, the chief technology and operations officer as well as general manager of Intel Foundry, told investment banking firm KeyBanc (via @Alex_Intel_ ). Given TSMC's track record of delivering steady performance, power, and area (PPA) gains with every new node, this might sound like entirely good news. However,",
     "node, Naga Chandrasekaran, the chief technology and operations officer as well as general manager of Intel Foundry, told investment banking firm KeyBanc. Given TSMC's track record of delivering steady performance, power, and area (PPA) gains with every new node, this might sound like entirely good news. However,"),
    ('platform_label_links', 'en', '(commercial music) \u2192 Jojo\u2019s Bizarre Adventure/Sonic Racing (game music) The Ghost In The Shell Official Accounts Official Website: theghostintheshell-anime.jp X (Japan): @thegits_anime X (Global): @thegits_animeEN Instagram: @thegits_anime [en]Source: [/en][es]Fuente: [/es]Official Press Release [ad_bottom class="mt40"]',
     '(commercial music) \u2192 Jojo\u2019s Bizarre Adventure/Sonic Racing (game music) The Ghost In The Shell Official Accounts Official Website: theghostintheshell-anime.jp [en]Source: [/en][es]Fuente: [/es]Official Press Release [ad_bottom class="mt40"]'),
    ('platform_pipe_list', 'en', 'following their second mini album poppop and third mini album COLOR, further solidifying their position as one of K-pop\u2019s most promising new-generation acts. Follow NCT WISH: TikTok | X | Instagram | YouTube | Facebook The post NCT WISH says \u201cI SPY\u201d for their next mini album release appeared first on K-POPPED!.',
     'following their second mini album poppop and third mini album COLOR, further solidifying their position as one of K-pop\u2019s most promising new-generation acts. The post NCT WISH says \u201cI SPY\u201d for their next mini album release appeared first on K-POPPED!.'),
    ('es_embed_publicacion_compartida', 'es', '36 a\xf1os aborda vivencias personales sobre el impacto de la fama, los procesos de arrepentimiento y las cr\xedticas dirigidas hacia sus presentaciones art\xedsticas. Ver esta publicaci\xf3n en Instagram Una publicaci\xf3n compartida por Taylor Swift (@taylorswift) Entre las novedades de esta producci\xf3n, explora la superaci\xf3n de un relaci\xf3n tormentosa en \u2018Patient Zero\u2019, canci\xf3n en la que compara la vivencia con un proceso',
     '36 a\xf1os aborda vivencias personales sobre el impacto de la fama, los procesos de arrepentimiento y las cr\xedticas dirigidas hacia sus presentaciones art\xedsticas. Entre las novedades de esta producci\xf3n, explora la superaci\xf3n de un relaci\xf3n tormentosa en \u2018Patient Zero\u2019, canci\xf3n en la que compara la vivencia con un proceso'),
    ('es_lone_handle_dotted', 'es', '\u2014 Kpop Verse (@kpopverse_es) September 18, 2026 As\xed mismo, el anuncio de ganadores ser\xe1 oficialmente a trav\xe9s de las redes sociales ( Instagram y X ) de @kpopverse.es el 21 de septiembre (lunes) a las 20:00. Consulta las redes sociales de la organizadora para no perderte ning\xfan detalle, \xa1porque tambi\xe9n habr\xe1 eventos especiales para',
     '\u2014 As\xed mismo, el anuncio de ganadores ser\xe1 oficialmente a trav\xe9s de las redes sociales ( Instagram y X ) de el 21 de septiembre (lunes) a las 20:00. Consulta las redes sociales de la organizadora para no perderte ning\xfan detalle, \xa1porque tambi\xe9n habr\xe1 eventos especiales para'),
    ('pt_lone_handle_in_prose', 'pt', 'editor de v\xeddeos cl\xe1ssico da Microsoft, voltou a circular na internet gra\xe7as a um arquivo publicado por uma usu\xe1ria do X. A internauta identificada como Katie, do perfil @skylerdagirl, subiu ao Internet Archive um instalador da vers\xe3o 6.0 do programa, testado e funcional em Windows 7, 10 e 11. O post ultrapassou 200 mil visualiza\xe7\xf5es e acumulou',
     'editor de v\xeddeos cl\xe1ssico da Microsoft, voltou a circular na internet gra\xe7as a um arquivo publicado por uma usu\xe1ria do X. A internauta identificada como Katie, do perfil, subiu ao Internet Archive um instalador da vers\xe3o 6.0 do programa, testado e funcional em Windows 7, 10 e 11. O post ultrapassou 200 mil visualiza\xe7\xf5es e acumulou'),
    ('pt_tweet_credit_no_dash', 'pt', 'para o grupo, marcando o primeiro comeback desde o single digital \u201cFin.K.L\u201d lan\xe7ado em 2005: #FinKL Announces Full-Group Comebackhttps://t.co/czZEv6iWvu Soompi (@soompi) September 21, 2026 Apesar da',
     'para o grupo, marcando o primeiro comeback desde o single digital \u201cFin.K.L\u201d lan\xe7ado em 2005: #FinKL Apesar da'),
    ('pt_reproducao_instagram', 'pt', 'Converse apaga an\xfancio com cantora de K-pop ap\xf3s acusa\xe7\xf5es de racismo Reprodu\xe7\xe3o/Instagram A empresa de t\xeanis Converse retirou uma publicidade das redes sociais ap\xf3s ser acusada de racismo. A foto, publicada no Instagram, mostrava a cantora de K-pop Karina usando',
     'Converse apaga an\xfancio com cantora de K-pop ap\xf3s acusa\xe7\xf5es de racismo A empresa de t\xeanis Converse retirou uma publicidade das redes sociais ap\xf3s ser acusada de racismo. A foto, publicada no Instagram, mostrava a cantora de K-pop Karina usando'),
    ('pt_reproducao_instagram_name', 'pt', 'Roberta Miranda lamentou o aumento de seguidores de Rick somente ap\xf3s a morte do cantor. Reprodu\xe7\xe3o/Instagram/Roberta Miranda A cantora Roberta Miranda criticou o aumento no n\xfamero de seguidores do cantor Rick Sollo, da dupla Rick e Renner, ap\xf3s a morte do sertanejo. O perfil do artista',
     'Roberta Miranda lamentou o aumento de seguidores de Rick somente ap\xf3s a morte do cantor. A cantora Roberta Miranda criticou o aumento no n\xfamero de seguidores do cantor Rick Sollo, da dupla Rick e Renner, ap\xf3s a morte do sertanejo. O perfil do artista'),
    ('pt_foto_no_instagram_embed', 'pt', 'jogos da Sele\xe7\xe3o Brasileira. A partida entre Brasil e Esc\xf3cia na quarta-feira (19) registrou 18,3 milh\xf5es de dispositivos conectados, de acordo com a empresa. Ver essa foto no Instagram Um post compartilhado por Caz\xe9TV (@cazetv) O recorde foi batido pela primeira vez na estreia do Brasil na Copa, contra Marrocos, com pico de 12,7 milh\xf5es de aparelhos. Depois, a marca foi superada no jogo',
     'jogos da Sele\xe7\xe3o Brasileira. A partida entre Brasil e Esc\xf3cia na quarta-feira (19) registrou 18,3 milh\xf5es de dispositivos conectados, de acordo com a empresa. O recorde foi batido pela primeira vez na estreia do Brasil na Copa, contra Marrocos, com pico de 12,7 milh\xf5es de aparelhos. Depois, a marca foi superada no jogo'),
    ('pt_imagem_paren_platform', 'pt', 'sombras tamb\xe9m se cruzem exatamente no mesmo ponto de fuga. Linhas de perspectiva aplicadas sobre imagem real mostram a converg\xeancia exata em um ponto de fuga (Imagem: Reprodu\xe7\xe3o/YouTube/Science Magazine) Em uma imagem aut\xeantica, as linhas paralelas de estruturas f\xedsicas convergem de forma precisa para um \xfanico ponto de fuga. An\xe1lise geom\xe9trica revela que as linhas',
     'sombras tamb\xe9m se cruzem exatamente no mesmo ponto de fuga. Linhas de perspectiva aplicadas sobre imagem real mostram a converg\xeancia exata em um ponto de fuga Em uma imagem aut\xeantica, as linhas paralelas de estruturas f\xedsicas convergem de forma precisa para um \xfanico ponto de fuga. An\xe1lise geom\xe9trica revela que as linhas'),
    ('id_embed_kiriman_dibagikan', 'id', 'Taylor Swift di MTV VMAs tahun ini, di mana ia juga akan menerima penghargaan perdana Artist Director Honors atas kiprahnya dalam penyutradaraan video musik. Lihat postingan ini di Instagram Sebuah kiriman dibagikan oleh Taylor Swift (@taylorswift)',
     'Taylor Swift di MTV VMAs tahun ini, di mana ia juga akan menerima penghargaan perdana Artist Director Honors atas kiprahnya dalam penyutradaraan video musik.'),
    ('id_lone_handle_after_akun', 'id', 'di 12 kota dunia, termasuk Jakarta. Ia menyembunyikan amplop berisi potongan huruf di sejumlah photo booth, kemudian membagikan koordinat lokasinya melalui akun Instagram keduanya, @lennyemeralds. Para penggemar yang berhasil menemukan amplop tersebut kemudian mengumpulkan huruf-hurufnya hingga membentuk judul \u201cDream Fatigue\u201d. Bersamaan dengan pengumuman',
     'di 12 kota dunia, termasuk Jakarta. Ia menyembunyikan amplop berisi potongan huruf di sejumlah photo booth, kemudian membagikan koordinat lokasinya melalui akun Instagram keduanya. Para penggemar yang berhasil menemukan amplop tersebut kemudian mengumpulkan huruf-hurufnya hingga membentuk judul \u201cDream Fatigue\u201d. Bersamaan dengan pengumuman'),
    ('vi_facebook_url', 'vi', 'V\u1eady l\xe0 Samsung \u0111\xe3 th\xe0nh c\xf4ng \u0111i \u0111\u1ea7u trong vi\u1ec7c ph\u1ed5 c\u1eadp Privacy Display ch\u01b0a anh em? M\xecnh c\u0169ng c\xf3 ch\xe9m gi\xf3 c\xf4ng ngh\u1ec7 \u1edf Facebook n\xe0y: https://www.facebook.com/trananhtu57/',
     'V\u1eady l\xe0 Samsung \u0111\xe3 th\xe0nh c\xf4ng \u0111i \u0111\u1ea7u trong vi\u1ec7c ph\u1ed5 c\u1eadp Privacy Display ch\u01b0a anh em? M\xecnh c\u0169ng c\xf3 ch\xe9m gi\xf3 c\xf4ng ngh\u1ec7 \u1edf Facebook n\xe0y:'),
    ('fr_lone_handle', 'fr', 'pas une seule crise financi\xe8re qui a eu lieu sans que l\'on voit une vraie concentration sectorielle c\xf4t\xe9 dette". \U0001f4ac Axel Cabrol, Directeur G\xe9n\xe9ral/CIO de Tobam \U0001f399\ufe0f @GuillSommerer',
     'pas une seule crise financi\xe8re qui a eu lieu sans que l\'on voit une vraie concentration sectorielle c\xf4t\xe9 dette". \U0001f4ac Axel Cabrol, Directeur G\xe9n\xe9ral/CIO de Tobam \U0001f399\ufe0f'),
    ('it_t_co_link', 'it', 'including variable aperture control on the 48MP fusion main camera for depth of field and exposure, plus Apple ProRes recording using pro video storage. Download now from https://t.co/cdCpQ0cCIR pic.twitter.com/Y8Ur3cCM9H \u2014 Blackmagic Design (@Blackmagic_News) September 18, 2026 La prima ad aprire le danze \xe8 stata Blackmagic Camera, una delle app alternative',
     'including variable aperture control on the 48MP fusion main camera for depth of field and exposure, plus Apple ProRes recording using pro video storage. Download now from La prima ad aprire le danze \xe8 stata Blackmagic Camera, una delle app alternative'),
    ('keep_platform_prose_en', 'en', "\u2018Open Your Eyes,\u2019 It\u2019s Time To Stan CLOSE YOUR EYES! that first appeared on The Honey POP and has not been approved for reposting. If you've enjoyed this post, you can follow The Honey POP on Twitter, Instagram, or Facebook. You're just in time for their biggest era yet! You are reading a post \u2018Open Your Eyes,\u2019 It\u2019s Time To Stan CLOSE YOUR EYES! that first appeared on The Honey POP",
     "\u2018Open Your Eyes,\u2019 It\u2019s Time To Stan CLOSE YOUR EYES! that first appeared on The Honey POP and has not been approved for reposting. If you've enjoyed this post, you can follow The Honey POP on Twitter, Instagram, or Facebook. You're just in time for their biggest era yet! You are reading a post \u2018Open Your Eyes,\u2019 It\u2019s Time To Stan CLOSE YOUR EYES! that first appeared on The Honey POP"),
    ('keep_platform_prose_pt', 'pt', 'que transforma documentos, PDFs, artigos e anota\xe7\xf5es em v\xeddeos verticais de cerca de 60 segundos. O formato foi pensado para celulares, com propor\xe7\xe3o 9:16, semelhante aos v\xeddeos vistos no TikTok, YouTube Shorts e Instagram Reels. A novidade busca combater o brain rot, termo usado para descrever o consumo excessivo de conte\xfados curtos e superficiais nas redes sociais. Segundo o Google, a',
     'que transforma documentos, PDFs, artigos e anota\xe7\xf5es em v\xeddeos verticais de cerca de 60 segundos. O formato foi pensado para celulares, com propor\xe7\xe3o 9:16, semelhante aos v\xeddeos vistos no TikTok, YouTube Shorts e Instagram Reels. A novidade busca combater o brain rot, termo usado para descrever o consumo excessivo de conte\xfados curtos e superficiais nas redes sociais. Segundo o Google, a'),
    ('keep_platform_prose_vi', 'vi', 'c\u1ed9ng \u0111\u1ed3ng. Hi\u1ec7n Zhoufam duy tr\xec c\u1ed9ng \u0111\u1ed3ng tr\xean nhi\u1ec1u n\u1ec1n t\u1ea3ng v\u1edbi h\u01a1n 39.000 ng\u01b0\u1eddi theo d\xf5i tr\xean fanpage, h\u01a1n 14.000 th\xe0nh vi\xean trong Facebook Group, h\u01a1n 6.200 ng\u01b0\u1eddi theo d\xf5i tr\xean Threads v\xe0 h\u01a1n 52.300 ng\u01b0\u1eddi theo d\xf5i tr\xean TikTok. V\u1edbi Zhoufam, t\xecnh c\u1ea3m d\xe0nh cho m\u1ed9t ngh\u1ec7 s\u0129 kh\xf4ng nh\u1ea5t thi\u1ebft ch\u1ec9 d\u1eebng l\u1ea1i \u1edf vi\u1ec7c \u1ee7ng h\u1ed9 s\u1ea3n ph\u1ea9m hay s\xe2n kh\u1ea5u c\u1ee7a ng\u01b0\u1eddi \u0111\xf3. Ch\xednh c\u1ed9ng \u0111\u1ed3ng \u0111\u01b0\u1ee3c h\xecnh th\xe0nh t\u1eeb t\xecnh',
     'c\u1ed9ng \u0111\u1ed3ng. Hi\u1ec7n Zhoufam duy tr\xec c\u1ed9ng \u0111\u1ed3ng tr\xean nhi\u1ec1u n\u1ec1n t\u1ea3ng v\u1edbi h\u01a1n 39.000 ng\u01b0\u1eddi theo d\xf5i tr\xean fanpage, h\u01a1n 14.000 th\xe0nh vi\xean trong Facebook Group, h\u01a1n 6.200 ng\u01b0\u1eddi theo d\xf5i tr\xean Threads v\xe0 h\u01a1n 52.300 ng\u01b0\u1eddi theo d\xf5i tr\xean TikTok. V\u1edbi Zhoufam, t\xecnh c\u1ea3m d\xe0nh cho m\u1ed9t ngh\u1ec7 s\u0129 kh\xf4ng nh\u1ea5t thi\u1ebft ch\u1ec9 d\u1eebng l\u1ea1i \u1edf vi\u1ec7c \u1ee7ng h\u1ed9 s\u1ea3n ph\u1ea9m hay s\xe2n kh\u1ea5u c\u1ee7a ng\u01b0\u1eddi \u0111\xf3. Ch\xednh c\u1ed9ng \u0111\u1ed3ng \u0111\u01b0\u1ee3c h\xecnh th\xe0nh t\u1eeb t\xecnh'),
    ('keep_platform_prose_id', 'id', 'Sebelumnya, mereka telah mengumumkan kehamilan tersebut pada Maret 2026 melalui akun Instagram masing-masing',
     'Sebelumnya, mereka telah mengumumkan kehamilan tersebut pada Maret 2026 melalui akun Instagram masing-masing'),
    ('keep_email_pt', 'pt', 'est\xe9tico para quem trabalha pela internet. Para freelancers, MEIs, pequenas empresas, ag\xeancias, lojas virtuais e profissionais de tecnologia, um endere\xe7o como contato@suaempresa.com.br transmite mais confian\xe7a do que uma conta gen\xe9rica gratuita e ainda ajuda a organizar melhor a comunica\xe7\xe3o com clientes, fornecedores e parceiros. Contratar email',
     'est\xe9tico para quem trabalha pela internet. Para freelancers, MEIs, pequenas empresas, ag\xeancias, lojas virtuais e profissionais de tecnologia, um endere\xe7o como contato@suaempresa.com.br transmite mais confian\xe7a do que uma conta gen\xe9rica gratuita e ainda ajuda a organizar melhor a comunica\xe7\xe3o com clientes, fornecedores e parceiros. Contratar email'),
    ('keep_email_domain_pt', 'pt', 'implementada. Al\xe9m disso, a empresa deve promover mudan\xe7as no servi\xe7o e diminuir a sua efic\xe1cia. De acordo com o site TechCrunch, o e-mail alternativo de dom\xednio \u201c@icloud.com\u201d seria trocado por \u201c@private.icloud.com\u201d, o que poderia facilitar o bloqueio de novos cadastros pelos sites. O Gmail tem um truque antigo para criar endere\xe7os alternativos',
     'implementada. Al\xe9m disso, a empresa deve promover mudan\xe7as no servi\xe7o e diminuir a sua efic\xe1cia. De acordo com o site TechCrunch, o e-mail alternativo de dom\xednio \u201c@icloud.com\u201d seria trocado por \u201c@private.icloud.com\u201d, o que poderia facilitar o bloqueio de novos cadastros pelos sites. O Gmail tem um truque antigo para criar endere\xe7os alternativos'),
    ('photo_paren_handle', 'en', 'Jennie attended the show (Photo: @jennierubyjane) in Paris.',
     'Jennie attended the show in Paris.'),
    ('photo_colon_platform_handle', 'en', 'Lisa smiled on stage. Photo: Instagram/@lalalalisa_m The crowd cheered.',
     'Lisa smiled on stage. The crowd cheered.'),
    ('via_handle', 'en', 'The teaser dropped overnight via @BIGHIT_MUSIC and fans reacted.',
     'The teaser dropped overnight and fans reacted.'),
    ('instagram_handle', 'en', 'She shared the photo on Instagram @roses_are_rosie yesterday.',
     'She shared the photo on Instagram yesterday.'),
    ('handle_on_x', 'en', 'Fans can follow @ygofficialblink on X for updates.',
     'Fans can follow on X for updates.'),
    ('pic_twitter', 'en', 'The group thanked fans. pic.twitter.com/Ab12Cd34 The tour starts soon.',
     'The group thanked fans. The tour starts soon.'),
    ('instagram_url', 'en', 'The post is at instagram.com/p/C6o4830yMvE/ and has 2 million likes.',
     'The post is at and has 2 million likes.'),
    ('pipe_instagram_tail', 'en', "The idol shared new photos. BLACKPINK's Jisoo | Instagram",
     'The idol shared new photos.'),
    ('lone_handle', 'en', 'The singer thanked @official_member for the song.',
     'The singer thanked for the song.'),
    ('keep_age_marker_hi', 'en', 'Nick Jonas @34: the singer celebrated his birthday.',
     'Nick Jonas @34: the singer celebrated his birthday.'),
    ('keep_posted_on_instagram', 'en', 'The actor posted on Instagram that the film wraps next week.',
     'The actor posted on Instagram that the film wraps next week.'),
    ('keep_youtube_music', 'en', 'The album is on Spotify | YouTube Music charts this week.',
     'The album is on Spotify | YouTube Music charts this week.'),
    ('id_foto_instagram_handle', 'id', 'Penyanyi itu tampil memukau. Foto: Instagram/@raisa6690 Konser berlangsung meriah.',
     'Penyanyi itu tampil memukau. Konser berlangsung meriah.'),
    ('id_paren_instagram_handle', 'id', 'Raisa mengunggah foto keluarga (Instagram @raisa6690) pada Minggu.',
     'Raisa mengunggah foto keluarga pada Minggu.'),
    ('id_sumber_handle', 'id', 'Aktris itu tampil cantik. Sumber: Instagram @raisa6690',
     'Aktris itu tampil cantik.'),
    ('vi_anh_handle', 'vi', 'Ca s\u0129 g\xe2y s\u1ed1t v\u1edbi b\u1ed9 \u1ea3nh m\u1edbi. \u1ea2nh: @sontungmtp Ng\u01b0\u1eddi h\xe2m m\u1ed9 th\xedch th\xfa.',
     'Ca s\u0129 g\xe2y s\u1ed1t v\u1edbi b\u1ed9 \u1ea3nh m\u1edbi. Ng\u01b0\u1eddi h\xe2m m\u1ed9 th\xedch th\xfa.'),
    ('vi_anh_paren_instagram_handle', 'vi', 'M\u1ef9 T\xe2m khoe \u1ea3nh m\u1edbi (\u1ea2nh: Instagram @mytam.info) khi\u1ebfn fan th\xedch th\xfa.',
     'M\u1ef9 T\xe2m khoe \u1ea3nh m\u1edbi khi\u1ebfn fan th\xedch th\xfa.'),
    ('vi_embed_bai_viet', 'vi', 'Xem b\xe0i vi\u1ebft n\xe0y tr\xean Instagram B\xe0i vi\u1ebft do S\u01a1n T\xf9ng M-TP (@sontungmtp) chia s\u1ebb Ca s\u0129 v\u1eeba ra m\u1eaft MV m\u1edbi.',
     'Ca s\u0129 v\u1eeba ra m\u1eaft MV m\u1edbi.'),
    ('es_foto_handle', 'es', 'La cantante sorprendi\xf3 a sus fans. Foto: @shakira El video ya es viral.',
     'La cantante sorprendi\xf3 a sus fans. El video ya es viral.'),
    ('pt_foto_instagram_handle', 'pt', 'A cantora postou fotos novas (Foto: Instagram/@anitta) nesta segunda.',
     'A cantora postou fotos novas nesta segunda.'),
    ('de_embed', 'de', 'Die Band zeigte neue Fotos. Diesen Beitrag auf Instagram ansehen Ein Beitrag geteilt von BTS (@bts.bighitofficial) Die Tour beginnt.',
     'Die Band zeigte neue Fotos. Die Tour beginnt.'),
    ('fr_embed', 'fr', 'Le groupe a publi\xe9 une photo. Voir cette publication sur Instagram Une publication partag\xe9e par BTS (@bts.bighitofficial)',
     'Le groupe a publi\xe9 une photo.'),
    ('it_embed', 'it', 'La band ha pubblicato nuove foto. Visualizza questo post su Instagram Un post condiviso da BTS (@bts.bighitofficial)',
     'La band ha pubblicato nuove foto.'),
]


def old_text_for(article):
    """text_for before SX (Sep 26): the summary was voiced as clean_text() left it."""
    title = bake.clean_text(article.get("title", ""))
    summary = bake.clean_text(article.get("summary", ""))
    source = bake.spoken_source(bake.clean_text(article.get("source", "")))
    parts = [source + ","] if source else []
    if title:
        parts.append(title)
        if not title.endswith((".", "!", "?")):
            parts.append(".")
    if summary and summary.lower() != title.lower():
        parts.append(summary[:bake.FAIR_USE_SNIPPET])
    return " ".join(parts).strip()[:bake.MAX_TEXT_LEN]


class SocialResidueVectors(unittest.TestCase):
    def test_every_vector_matches_the_app_mirror(self):
        for name, _lang, inp, exp in VECTORS:
            self.assertEqual(bake.strip_social_residue(inp), exp, name)

    def test_no_handle_survives_and_keep_vectors_stay_whole(self):
        for name, _lang, inp, exp in VECTORS:
            self.assertIsNone(bake.SOCIAL_HANDLE_RE.search(exp), name)
            if name.startswith("keep_"):
                self.assertEqual(inp, exp, name)
            else:
                self.assertNotEqual(inp, exp, name)

    def test_idempotent(self):
        for name, _lang, _inp, exp in VECTORS:
            self.assertEqual(bake.strip_social_residue(exp), exp, name)

    def test_every_first_class_language_has_a_sample(self):
        self.assertTrue({"en", "es", "pt", "id", "vi"} <= {lang for _n, lang, _i, _e in VECTORS})


class TextForNeverVoicesAHandle(unittest.TestCase):
    OWNER = {"source": "Koreaboo", "title": "LE SSERAFIM Chaewon's Instagram post sparks divided reactions",
             "summary": "It has sparked hugely divided reactions. LE SSERAFIM\u2019s Chaewon | @_chaechae_1/Instagram "
                        "Amid the group\u2019s ongoing shows in the US, Chaewon shared some photos."}

    def test_positive_control_old_text_for_voiced_the_handle(self):
        self.assertIsNotNone(bake.SOCIAL_HANDLE_RE.search(old_text_for(self.OWNER)))

    def test_text_for_drops_the_credit_and_its_caption(self):
        t = bake.text_for(self.OWNER)
        self.assertIsNone(bake.SOCIAL_HANDLE_RE.search(t))
        self.assertNotIn("Chaewon |", t)
        self.assertIn("reactions. Amid the group", t)

    def test_every_vector_through_text_for(self):
        for name, _lang, inp, _exp in VECTORS:
            t = bake.text_for({"source": "Src", "title": "Title", "summary": inp})
            self.assertIsNone(bake.SOCIAL_HANDLE_RE.search(t), name)
            self.assertTrue(t.startswith("Src, Title ."), name)

    def test_title_and_source_are_untouched(self):
        a = {"source": "Soompi", "title": "BTS wins big", "summary": "Plain summary."}
        self.assertEqual(bake.text_for(a), old_text_for(a))

    def test_handle_check_keeps_email_and_age_markers(self):
        for s in ("contato@suaempresa.com.br", "Nick Jonas @34: birthday", "dom\u00ednio \u201c@icloud.com\u201d"):
            self.assertIsNone(bake.SOCIAL_HANDLE_RE.search(s), s)
        for s in ("| @_chaechae_1/Instagram", "de @kpopverse.es el 21"):
            self.assertIsNotNone(bake.SOCIAL_HANDLE_RE.search(s), s)


if __name__ == "__main__":
    unittest.main()
