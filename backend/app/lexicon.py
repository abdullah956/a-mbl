"""Word and phrase lists for the lexicon baseline classifier.

These lists exist to flag possibly harmful language for HUMAN review inside a
cyberbullying-awareness prototype. They are deliberately small, English-only,
and biased toward high-precision phrases. The trained TF-IDF model planned in
docs/MOBILE_APP_ROADMAP.md §12 replaces this module without changing the API.
"""

THREAT_PHRASES = [
    "kill you", "kill u", "kill yourself", "kys", "go kill yourself",
    "hurt you", "hurt u", "beat you up", "beat u up", "jump you",
    "you're dead", "youre dead", "you are dead", "ur dead", "u r dead",
    "watch your back", "watch ur back",
    "i know where you live", "know where u live", "i know your address",
    "gonna get you", "going to get you", "come after you", "coming for you",
    "make you pay", "you will regret", "youll regret", "you'll regret",
    "smash your face", "break your face", "punch you", "stab you", "shoot you",
    "end you", "destroy you",
    "you should die", "go die", "hope you die", "wish you were dead",
    "no one would miss you", "nobody would miss you",
    "i will find you", "we will find you",
]

HATE_PHRASES = [
    "go back to your country", "go back to ur country",
    "your kind doesn't belong", "your kind doesnt belong", "your kind",
    "you people are", "subhuman", "vermin",
    "doesn't deserve rights", "doesnt deserve rights", "dont deserve rights",
]

# Identity terms only count toward hate speech when paired with an attack term.
IDENTITY_TERMS = [
    "muslim", "muslims", "jew", "jews", "jewish", "christian", "christians",
    "black people", "white people", "asian", "asians", "arab", "arabs",
    "mexican", "mexicans", "african", "africans", "immigrant", "immigrants",
    "refugee", "refugees", "foreigner", "foreigners",
    "gay", "gays", "lesbian", "lesbians", "trans", "queer",
    "girls", "women", "boys", "men", "disabled", "autistic",
]

IDENTITY_ATTACK_TERMS = [
    "hate", "disgusting", "disgust me", "vermin", "subhuman", "animals",
    "criminals", "trash", "garbage", "should die", "should be banned",
    "dont belong", "don't belong", "not welcome", "are a disease", "parasites",
    "are stupid", "are dumb", "are inferior", "cant be trusted", "can't be trusted",
]

HARASSMENT_PHRASES = [
    "nobody likes you", "no one likes you", "everyone hates you",
    "everybody hates you", "we all hate you",
    "you have no friends", "u have no friends",
    "you're worthless", "youre worthless", "you are worthless",
    "you're pathetic", "youre pathetic", "you are pathetic",
    "you're disgusting", "youre disgusting", "you are disgusting",
    "you're nothing", "youre nothing", "you are nothing",
    "you make me sick", "waste of space", "waste of air",
    "you don't belong here", "you dont belong here",
    "get out of our school", "get out of this school",
    "everyone is laughing at you", "everyone laughs at you",
    "why are you still here", "no one wants you here", "nobody wants you here",
    "i hate you", "we hate you", "we all laugh at you",
    "no one cares about you", "nobody cares about you",
]

OFFENSIVE_TERMS = [
    "idiot", "stupid", "dumb", "dumbass", "loser", "ugly", "moron", "jerk",
    "freak", "trash", "garbage", "pathetic", "gross", "creep", "weirdo",
    "clown", "disgusting", "shut up", "screw you", "suck", "sucks",
    "fuck", "fucking", "fck", "shit", "bitch", "asshole", "bastard", "dick",
    "prick", "crap", "piss off", "wtf", "stfu", "gtfo",
]

BODY_SHAMING_TERMS = [
    "fat", "fatty", "fatso", "whale", "obese", "fat pig", "lardass",
    "skinny", "anorexic", "bony", "stick figure",
    "lose some weight", "skip a meal", "eat a salad", "stop eating",
    "ugly body", "look like a whale", "look pregnant",
    "double chin", "thunder thighs",
]
