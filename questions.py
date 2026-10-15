"""Savollar bazasi. Serverda turadi: to'g'ri javob mijozga (brauzerga) hech qachon yuborilmaydi.
Format: (savol, [A, B, C, D], to'g'ri javob indeksi)
Katta loyihada buni DB jadvaliga ko'chiring."""

BANK: dict[str, list[tuple[str, list[str], int]]] = {
    "math": [
        ("12 × 8 nechaga teng?", ["86", "96", "108", "98"], 1),
        ("√144 nechaga teng?", ["11", "13", "12", "14"], 2),
        ("2 ning 10-darajasi?", ["512", "1024", "2048", "1000"], 1),
        ("200 ning 15% i nechaga teng?", ["20", "25", "30", "35"], 2),
        ("Uchburchak ichki burchaklari yig'indisi?", ["90°", "180°", "270°", "360°"], 1),
    ],
    "hist": [
        ("Amir Temur qaysi yilda tug'ilgan?", ["1336", "1405", "1245", "1380"], 0),
        ("O'zbekiston mustaqilligi qaysi yili e'lon qilingan?", ["1989", "1990", "1991", "1992"], 2),
        ("Ikkinchi jahon urushi qaysi yili tugagan?", ["1943", "1945", "1947", "1941"], 1),
        ("Registon maydoni qaysi shaharda?", ["Buxoro", "Samarqand", "Xiva", "Toshkent"], 1),
        ("Birinchi jahon urushi qaysi yili boshlangan?", ["1912", "1914", "1916", "1918"], 1),
    ],
    "ona": [
        ("\"Kitob\" qaysi so'z turkumi?", ["Fe'l", "Ot", "Sifat", "Son"], 1),
        ("Unli tovushlar qaysi qatorda?", ["a, o, i", "b, d, g", "s, sh, ch", "k, q, x"], 0),
        ("\"Katta\" so'zining antonimi?", ["Baland", "Kichik", "Uzun", "Keng"], 1),
        ("Sifat nimani bildiradi?", ["Predmet belgisini", "Harakatni", "Predmet nomini", "Miqdorni"], 0),
        ("\"Gul\" so'zida nechta bo'g'in bor?", ["1", "2", "3", "4"], 0),
    ],
    "rus": [
        ("\"Спасибо\" nima degani?", ["Salom", "Rahmat", "Xayr", "Kechirasiz"], 1),
        ("\"Дом\" so'zining tarjimasi?", ["Uy", "Stol", "Kitob", "Maktab"], 0),
        ("Rus alifbosida nechta harf bor?", ["30", "33", "36", "28"], 1),
        ("\"Привет\" nima degani?", ["Xayr", "Salom", "Ha", "Yo'q"], 1),
        ("\"Книга\" tarjimasi?", ["Daftar", "Qalam", "Kitob", "Stul"], 2),
    ],
    "eng": [
        ("\"Apple\" tarjimasi?", ["Anor", "Olma", "Uzum", "Nok"], 1),
        ("I ___ a student.", ["is", "am", "are", "be"], 1),
        ("\"Book\" so'zining ko'plik shakli?", ["Bookes", "Books", "Bookies", "Bookz"], 1),
        ("\"Beautiful\" antonimi?", ["Ugly", "Nice", "Big", "Fast"], 0),
        ("\"Go\" fe'lining o'tgan zamon shakli?", ["goed", "went", "gone", "going"], 1),
    ],
    "adab": [
        ("\"O'tkan kunlar\" romani muallifi?", ["Cho'lpon", "A. Qodiriy", "Oybek", "Hamza"], 1),
        ("\"Kecha va kunduz\" romani muallifi?", ["Cho'lpon", "A. Qodiriy", "Oybek", "Hamza"], 0),
        ("Navoiyning \"Xamsa\"si nechta dostondan iborat?", ["3", "4", "5", "6"], 2),
        ("\"Boburnoma\" muallifi kim?", ["Bobur", "Navoiy", "Fuzuliy", "Ulug'bek"], 0),
        ("\"Mehrobdan chayon\" muallifi?", ["Cho'lpon", "A. Qodiriy", "Oybek", "G'. G'ulom"], 1),
    ],
    "fiz": [
        ("Yorug'lik tezligi taxminan qancha?", ["300 000 km/s", "30 000 km/s", "3 000 km/s", "150 000 km/s"], 0),
        ("Kuch birligi qaysi?", ["Nyuton", "Joul", "Vatt", "Paskal"], 0),
        ("Erkin tushish tezlanishi?", ["9,8 m/s²", "8,9 m/s²", "10,8 m/s²", "6,7 m/s²"], 0),
    ],
    "kim": [
        ("Suvning kimyoviy formulasi?", ["CO₂", "H₂O", "O₂", "NaCl"], 1),
        ("Oltinning kimyoviy belgisi?", ["Ag", "Au", "Fe", "Cu"], 1),
        ("Osh tuzining formulasi?", ["NaCl", "KCl", "CaCO₃", "HCl"], 0),
    ],
    "bio": [
        ("Insonda nechta xromosoma bor?", ["44", "48", "46", "42"], 2),
        ("Fotosintezda o'simlik qaysi gazni yutadi?", ["O₂", "CO₂", "N₂", "H₂"], 1),
        ("Qon aylanishining markaziy a'zosi?", ["Yurak", "Jigar", "Miya", "O'pka"], 0),
    ],
    "geo": [
        ("O'zbekiston poytaxti?", ["Samarqand", "Buxoro", "Toshkent", "Namangan"], 2),
        ("Eng katta okean?", ["Atlantika", "Tinch", "Hind", "Shimoliy Muz"], 1),
        ("Eng baland cho'qqi?", ["K2", "Everest", "Elbrus", "Kilimanjaro"], 1),
    ],
    "inf": [
        ("1 bayt nechta bitdan iborat?", ["4", "16", "8", "2"], 2),
        ("HTML nima?", ["Dasturlash tili", "Belgilash tili", "Operatsion tizim", "Brauzer"], 1),
        ("CPU nima?", ["Protsessor", "Xotira", "Monitor", "Sichqoncha"], 0),
    ],
    "astro": [
        ("Quyosh tizimidagi eng katta sayyora?", ["Saturn", "Yupiter", "Neptun", "Yer"], 1),
        ("Quyoshga eng yaqin sayyora?", ["Venera", "Merkuriy", "Mars", "Yer"], 1),
        ("Yerning tabiiy yo'ldoshi?", ["Oy", "Fobos", "Evropa", "Titan"], 0),
    ],
}


# ---- Fanlar (frontenddagi kalitlar bilan bir xil) ----
SUBJECTS = {"math": "Matematika", "hist": "Tarix", "ona": "Ona tili", "rus": "Rus tili", "eng": "Ingliz tili",
            "adab": "Adabiyot", "fiz": "Fizika", "kim": "Kimyo", "bio": "Biologiya", "geo": "Geografiya",
            "inf": "Informatika", "astro": "Astronomiya"}
_EXTRA = {"history": "hist", "english": "eng", "russian": "rus", "physics": "fiz", "chemistry": "kim",
          "biology": "bio", "geography": "geo", "informatics": "inf", "astronomy": "astro",
          "literature": "adab", "ona tili": "ona", "rus tili": "rus", "ingliz tili": "eng"}
_ALIAS = {**{k: k for k in SUBJECTS}, **{v.lower(): k for k, v in SUBJECTS.items()}, **_EXTRA}


def norm_subject(x: str | None) -> str | None:
    """'Matematika', 'math', 'Ona_tili' ... -> kalit ('math', 'ona' ...). Noma'lum bo'lsa None."""
    k = (x or "").strip().lower().replace("’", "'").replace("_", " ").replace("-", " ")
    return _ALIAS.get(k)
