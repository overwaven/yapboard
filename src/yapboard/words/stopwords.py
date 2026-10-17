"""Curated English and Russian stopwords for the word-frequency board.

The lists deliberately contain *function* words and conversational filler only:
pronouns, articles, prepositions, conjunctions, particles, auxiliary verbs,
interjections and greetings.  Content words (nouns, verbs, adjectives) are not
removed, even when they are common — ``работа``, ``кот``, ``deploy`` or
``meeting`` should still appear on the board.

All entries are lowercase and use ``е`` instead of ``ё``; the normalizer applies
the same folding before comparing.
"""

from __future__ import annotations

ENGLISH: frozenset[str] = frozenset(
    """
    a an the
    i me my mine myself we us our ours ourselves you your yours yourself
    yourselves he him his himself she her hers herself it its itself they them
    their theirs themselves this that these those
    am is are was were be been being
    have has had having do does did doing done
    will would shall should can could may might must ought
    and or but if because as than so yet nor
    of in on at to for from by with without about into over under between
    through during before after above below up down out off again further then
    once here there when where why how
    all any both each few more most other some such no not only own same too
    very just also even still ever never always often sometimes
    really actually literally basically probably maybe perhaps
    oh ah uh um hmm huh mm meh yeah yep yup nope nah yes ok okay lol lmao rofl
    haha hehe wow oops hey hi hello thanks thank please sorry
    like
    im ive id ill youre youve youd youll hes shes its were theyre thats theres
    whats lets dont doesnt didnt cant couldnt wouldnt shouldnt isnt arent wasnt
    werent havent hasnt hadnt wont aint
    gonna wanna gotta kinda sorta dunno
    u ur r pls plz thx ty np btw omg idk tbh imo imho rn af fr ngl smh wtf
    """.split()  # noqa: SIM905
)

RUSSIAN: frozenset[str] = frozenset(
    """
    я меня мне мной мною ты тебя тебе тобой тобою он его ему им нем него она
    ее ей ею нее оно они их них ими ними мы нас нам нами вы вас вам вами себя
    себе собой собою
    свой своя свое свои своего своей своих своим своими мой моя мое мои моего
    моей моих моим моими твой твоя твое твои твоего твоей твоих твоим твоими
    наш наша наше наши нашего нашей наших нашим нашими ваш ваша ваше ваши
    вашего вашей ваших вашим вашими
    этот эта это эти этого этой этих этому этом этим этими тот та то те того
    той том тех тому тем теми такой такая такое такие такого такой таком таких
    такому таким такими
    весь вся все всего всей всех всем всеми каждый каждая каждое каждые каждого
    каждой каждом каждому каждых любой любая любое любые любого любой любом
    любому любых
    который которая которое которые которого которой котором которому которых
    которым которыми которую чей чья чье чьи чьего чьей чьем чьему чьих чьим
    чьими
    сам сама само сами самого самой самом самому самих самим самими
    другой другая другое другие другого другой другом другому других другим
    другими
    какой какая какое какие какого каких каким какими каком какому
    никакой никакая никакое никакие никакого никакой никаком никакому никаких
    никаким никакими
    никто никого никому никем ничего ничему ничем ничто нечего некого некому
    нечем
    кто-то кто-нибудь кто-либо что-то что-нибудь что-либо где-то где-нибудь
    когда-то когда-нибудь как-то как-нибудь почему-то почему-нибудь зачем-то
    куда-то откуда-то сколько-то какой-то какая-то какое-то какие-то
    быть был была было были буду будешь будет будем будете будут будь будьте
    есть мочь могу можешь может можем можете могут мог могла могло могли
    является являются являлся являлась являлось являлись
    в во без безо для до из изо к ко на над надо о об обо от ото по под подо
    при про с со у через между перед передо за из-за из-под около возле после
    кроме ради сквозь среди вдоль мимо вокруг против согласно благодаря
    и а но да или либо ни не нет же ли бы б ведь вот вон уж уже еще только даже
    именно как что чтобы чтоб когда если хотя пока потому поэтому оттого так
    также тоже там тут здесь туда сюда где куда откуда зачем почему сколько
    насколько нельзя можно надо нужно
    всегда никогда иногда часто редко обычно снова опять раньше потом теперь
    сейчас щас
    ну ой ай ах ох эх ух ага угу ммм мм хм хмм блин черт капец жесть типа
    короче вообще просто прямо реально буквально собственно значит наверное
    наверно конечно кстати вроде якобы мол дескать однако впрочем итак ваще че
    шо по-моему по-твоему по-нашему по-вашему все-таки
    очень слишком совсем почти достаточно довольно немного
    привет здравствуйте здравствуй хай хелло пока спасибо пожалуйста извини
    извините сорри спс пж
    ок окей норм
    """.split()  # noqa: SIM905
)

STOPWORDS: frozenset[str] = ENGLISH | RUSSIAN

__all__ = ["ENGLISH", "RUSSIAN", "STOPWORDS"]
