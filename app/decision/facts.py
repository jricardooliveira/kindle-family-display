"""Small built-in rotation of curiosities for quiet moments on the family screen."""

from datetime import date

_FACTS: tuple[tuple[str, str], ...] = (
    ("Espaço", "A luz do Sol demora cerca de 8 minutos a chegar à Terra."),
    ("Natureza", "Os polvos têm três corações e sangue azul."),
    ("História", "A Universidade de Coimbra, fundada em 1290, é uma das mais antigas da Europa."),
    ("Ciência", "O corpo humano adulto tem 206 ossos; um bebé nasce com cerca de 300."),
    (
        "Geografia",
        "O ponto mais alto de Portugal é a montanha do Pico, nos Açores, com 2351 metros.",
    ),
    ("Tecnologia", "O primeiro SMS foi enviado em 1992 e dizia «Merry Christmas»."),
    ("Espaço", "Um dia em Vénus dura mais do que um ano em Vénus."),
    ("Natureza", "As abelhas indicam umas às outras onde estão as flores através de uma dança."),
    (
        "História",
        "A Livraria Bertrand, em Lisboa, abriu em 1732 e é a mais antiga do mundo em funcionamento.",
    ),
    ("Ciência", "O som viaja cerca de quatro vezes mais depressa na água do que no ar."),
    ("Geografia", "O Cabo da Roca é o ponto mais ocidental da Europa continental."),
    ("Tecnologia", "O primeiro site da Internet foi publicado em 1991 e ainda pode ser visitado."),
    ("Espaço", "Júpiter é tão grande que caberiam lá dentro mais de mil Terras."),
    ("Natureza", "As girafas têm sete vértebras no pescoço, tantas como os humanos."),
    ("História", "As pirâmides de Gizé já tinham mais de dois mil anos quando Cleópatra nasceu."),
    ("Ciência", "O diamante e a grafite do lápis são feitos do mesmo elemento: carbono."),
    ("Geografia", "O Oceano Pacífico cobre cerca de um terço da superfície da Terra."),
    (
        "Tecnologia",
        "O código QR foi inventado no Japão em 1994 para seguir peças de automóveis.",
    ),
    ("Espaço", "A Lua afasta-se da Terra cerca de 3,8 centímetros por ano."),
    ("Natureza", "Os golfinhos dormem com metade do cérebro de cada vez."),
    ("História", "Vasco da Gama chegou à Índia por mar em 1498."),
    ("Ciência", "As bananas são ligeiramente radioativas por causa do potássio."),
    ("Geografia", "O rio Douro nasce em Espanha e percorre quase 900 quilómetros até ao Porto."),
    (
        "Tecnologia",
        "A Via Verde, criada em Portugal em 1991, foi pioneira nas portagens eletrónicas.",
    ),
    ("Espaço", "Na Lua não há vento: as pegadas dos astronautas podem durar milhões de anos."),
    ("Natureza", "O sobreiro é a árvore nacional de Portugal; a cortiça volta a crescer."),
    (
        "História",
        "Gago Coutinho e Sacadura Cabral fizeram a primeira travessia aérea do Atlântico Sul, em 1922.",
    ),
    ("Ciência", "O coração humano bate cerca de 100 mil vezes por dia."),
    ("Geografia", "A Antártida é o maior deserto do mundo."),
    ("Tecnologia", "O primeiro rato de computador, de 1964, era feito de madeira."),
    ("Natureza", "Um raio é cerca de cinco vezes mais quente do que a superfície do Sol."),
    ("Geografia", "A Rússia tem onze fusos horários."),
    (
        "Tecnologia",
        "O GPS depende de relógios atómicos em satélites a cerca de 20 mil quilómetros de altitude.",
    ),
    ("Natureza", "O mel não se estraga: já se encontrou mel comestível com milhares de anos."),
    ("Geografia", "A ponte Vasco da Gama, em Lisboa, tem mais de 12 quilómetros de comprimento."),
)


def fact_for(day: date) -> tuple[str, str]:
    """Return the (category, text) curiosity for a calendar day; each day gets the next one."""
    return _FACTS[day.toordinal() % len(_FACTS)]
