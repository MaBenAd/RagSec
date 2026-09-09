"""
Router Service — emploi du temps uniquement (RAG en réserve).

Gestion multi-classes :
  - 1 classe  → chargement automatique
  - Plusieurs → détection dans la question ou demande à l'étudiant
"""

import os
import json
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime
from functools import lru_cache
from backend.services.logging_service import logger

_THIS_FILE = os.path.abspath(__file__)
_SERVICES_DIR = os.path.dirname(_THIS_FILE)  # backend/services/
_BACKEND_DIR = os.path.dirname(_SERVICES_DIR)  # backend/

WEAK_MARKERS = [
    "je ne trouve pas", "aucune information", "pas trouvé",
    "❌", "aucun cours",
]

EDT_MARKERS = [
    "emploi du temps", "edt", "planning", "cours", "matiere", "matière",
    "prof", "professeur", "enseignant", "lundi", "mardi", "mercredi", "jeudi",
    "vendredi", "samedi", "aujourd", "demain", "hier", "examen", "rattrapage",
    "partiel", "calendrier", "timetable", "time table", "schedule", "classes",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    "morning", "afternoon", "teacher", "professor", "subject",
]

NON_EDT_MARKERS = [
    "note minimale", "note minimum", "valider un module", "validation module",
    "releve de notes", "relevé de notes", "attestation de scolarite", "attestation de scolarité",
    "inscription", "bourse", "minhaty", "scolarite", "scolarité", "buvette", "restaurant",
    "admission", "admission parallele", "candidater", "bac+2", "bac 2", "prepa",
    "convention de stage", "documents de stage", "qui contacter pour le stage",
    "changer ma classe", "changer mon semestre", "changement de classe", "changement de semestre",
    "ou se situe", "où se situe", "where is", "location", "adresse", "localisation",
    "وين", "اين", "أين", "فين", "العنوان",
    "الاسم الكامل", "متى تم", "تم إنشاء", "انشئت", "أُنشئت", "تابعة", "مرتبطة", "شبكة ensa",
    "المدرسة الوطنية", "الجامعة", "المؤسسة", "الموقع الرسمي",
]

FAQ_MARKERS = [
    "directeur", "email", "e-mail", "site officiel", "portail", "mission",
    "rattach", "universite", "université", "creation", "création", "crée",
    "reseau", "réseau", "filiere", "filière", "formation", "2ap", "ensa maroc",
    "contact", "campus", "mghila", "beni mellal", "ensa bm",
    "iacs", "iaa", "g2er", "tdi", "coordinateur", "coordonnateur", "responsable",
    "admission", "programme", "credits", "duree", "debouche", "debouches",
    "competence", "competences", "stage", "stages", "pfe", "partenaire",
    "partenaires", "infrastructure", "cycle preparatoire", "cycle ingenieur",
    "espace etudiant", "attestation", "releve de notes", "documents administratifs",
    "bourse", "amo", "absence", "absences", "inscription pedagogique", "reclamation",
    "مدير", "إيميل", "ايميل", "بريد", "موقع", "رسمي", "جامعة", "رسالة", "تكوين", "شبكة",
    "الاسم الكامل", "تم إنشاء", "انشئت", "تابعة", "مرتبطة", "المدرسة الوطنية", "المؤسسة",
]

TIMETABLE_VERBS = [
    "voir", "afficher", "montre", "montrer", "donne", "donner", "consulter",
    "show", "display", "see", "view", "open", "give", "check",
]

TEMPORAL_MARKERS = [
    "aujourd", "demain", "hier", "maintenant", "currently", "today", "tomorrow",
    "this week", "semaine", "next", "prochain", "upcoming",
]

FULL_TIMETABLE_MARKERS = [
    "tout l'emploi du temps",
    "tout l emploi du temps",
    "emploi du temps complet",
    "emploi du temps entier",
    "planning complet",
    "toute la semaine",
    "semaine complete",
    "montre moi tout l'emploi du temps",
    "montre moi tout l emploi du temps",
    "affiche tout l'emploi du temps",
    "affiche tout l emploi du temps",
    "full timetable",
    "complete timetable",
    "full schedule",
    "weekly schedule",
    "entire timetable",
    "show full timetable",
    "show all classes",
]

DAY_INDEX_BY_TOKEN = {
    "lundi": 0,
    "mardi": 1,
    "mercredi": 2,
    "jeudi": 3,
    "vendredi": 4,
    "samedi": 5,
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
}

FOCUS_STOPWORDS = {
    "emploi", "temps", "planning", "edt", "cours", "module", "matiere", "matiere", "prof", "professeur",
    "enseignant", "avec", "pour", "dans", "classe", "filiere", "filiere", "horaire", "schedule", "timetable",
    "show", "full", "complete", "all", "today", "tomorrow", "hier", "demain", "aujourd", "semaine", "complet",
}

EDT_INTENT_TOKENS = {
    "emploi", "temps", "edt", "planning", "horaire", "cours", "module", "matiere",
    "prof", "professeur", "enseignant", "enseigne", "classe", "filiere", "semaine", "schedule", "timetable",
    "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "today", "tomorrow", "aujourd", "demain",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "morning", "afternoon",
    "teacher", "professor", "subject", "course", "classes",
}

GENERAL_TIMETABLE_TOKENS = {
    "emploi", "temps", "edt", "planning", "horaire", "semaine", "schedule", "timetable",
}


def _env_true(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


ENABLE_RAG_FALLBACK = _env_true("ENABLE_RAG_FALLBACK", "false")

_COMMON_QUERY_REWRITES = [
    (r"\bcooridnateur\b", "coordinateur"),
    (r"\bcoordianteur\b", "coordinateur"),
    (r"\bcoordonnateur\b", "coordinateur"),
    (r"\bresponsable\b", "coordinateur"),
    (r"\bsigni+fie\b", "signifie"),
    (r"\bsignife\b", "signifie"),
    (r"\bintellignece\b", "intelligence"),
    (r"\binteligence\b", "intelligence"),
    (r"\bintelligance\b", "intelligence"),
    (r"\bcyber\s+securite\b", "cybersecurite"),
    (r"\bagro\s+alimentaires\b", "agroalimentaires"),
    (r"\bagro\s+alimentaire\b", "agroalimentaire"),
    (r"\benergies?\s+renouvelable\b", "energies renouvelables"),
    (r"\btransformation\s+numerique\s+industrielle\b", "transformation digitale industrielle"),
    (r"\bdigitalisation\s+industrielle\b", "transformation digitale industrielle"),
    (r"\bindustrie\s+4[.\s]*0\b", "industrie 4 0"),
    (r"\bfiliers\b", "filiere"),
    (r"\bfiliers?\b", "filiere"),
    (r"\bifliere\b", "filiere"),
    (r"\bfiiere\b", "filiere"),
    (r"\bfileire\b", "filiere"),
    (r"\bquesl\b", "quel"),
    (r"\bformationde\b", "formation de"),
    (r"\bagoalimentaire\b", "agroalimentaire"),
    (r"\bpreparatoir\b", "preparatoire"),
    (r"\bpreparaoire\b", "preparatoire"),
    (r"\bprepa\b", "preparatoire"),
    (r"\bcombine\b", "combien"),
    (r"\banne\b", "annee"),
    (r"\bkoi\b", "quoi"),
    (r"\bfilier\b", "filiere"),
    (r"\bnsa\b", "ensa"),
    (r"\bmlal\b", "mellal"),
]


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFD", value.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[’']", " ", text)
    text = re.sub(r"[_\-/]+", " ", text)
    for pattern, replacement in _COMMON_QUERY_REWRITES:
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


TRACK_CODES = {"iacs", "tdi", "g2er", "iaa", "2ap"}
TRACK_CODE_ORDER = ["iacs", "tdi", "g2er", "iaa", "2ap"]

TRACK_ALIASES_BY_CODE = {
    "iacs": [
        "iacs",
        "iac",
        "intelligence artificielle",
        "cybersecurite",
        "cyber securite",
    ],
    "tdi": [
        "tdi",
        "transformation digitale",
        "transformation numerique",
        "industrie 4 0",
        "industrie 4.0",
    ],
    "g2er": [
        "g2er",
        "geer",
        "genie electrique",
        "energies renouvelables",
        "energie renouvelable",
    ],
    "iaa": [
        "iaa",
        "industrie agroalimentaire",
        "industries agroalimentaires",
        "agroalimentaire",
    ],
    "2ap": [
        "2ap",
        "cycle preparatoire",
        "classes preparatoires",
    ],
}


def _normalize_class_reference_text(value: str | None) -> str:
    text = _normalize_text(value)
    if not text:
        return ""

    text = re.sub(r"\b(?:semestre|semester|sem)\s*([1-6])\b", r"s\1", text)
    text = re.sub(r"\bs\s+([1-6])\b", r"s\1", text)
    text = re.sub(r"\by\s+([1-5])\b", r"y\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_semester_token(text: str | None) -> str | None:
    normalized = _normalize_class_reference_text(text)
    match = re.search(r"\bs([1-6])\b", normalized)
    return f"s{match.group(1)}" if match else None


def _extract_track_codes(text: str | None) -> list[str]:
    q = _normalize_text(text)
    if not q:
        return []

    codes = []
    for code in TRACK_CODE_ORDER:
        aliases = TRACK_ALIASES_BY_CODE.get(code, [code])
        if any(re.search(rf"\b{re.escape(alias)}\b", q) for alias in aliases):
            codes.append(code)
    return codes


def _extract_track_code(text: str | None) -> str | None:
    codes = _extract_track_codes(text)
    return codes[0] if codes else None


def _track_code_from_class_label(class_label: str | None) -> str | None:
    normalized = _normalize_text(class_label)
    if not normalized:
        return None

    for token in re.findall(r"[a-z0-9]+", normalized):
        if token in TRACK_CODES:
            return token.upper()
    return None


def _expand_profile_track_reference(question: str, class_label: str | None) -> str:
    track_code = _track_code_from_class_label(class_label)
    if not track_code:
        return question

    q_norm = _normalize_text(question)
    if not q_norm or track_code.lower() in q_norm:
        return question

    own_track_markers = [
        "ma filiere",
        "ma formation",
        "mon cycle",
        "ma classe",
        "my track",
        "my major",
        "my program",
        "my class",
    ]
    if any(marker in q_norm for marker in own_track_markers):
        return f"{question} (la filiere de l'etudiant connecte est {track_code})"

    return question


def _get_intent_smart(question: str, history: list[dict] | None = None) -> str:
    """
    Utilise un appel LLM ultra-rapide pour classer l'intention.
    Categories : GREETING, IDENTITY, EDT, FAQ.
    """
    from backend.services.groq_service import call_groq
    
    # Heuristique pour les salutations tres courtes
    q_norm = _normalize_text(question)
    if len(q_norm) < 15 and any(g in q_norm for g in ["hello", "hi", "bonjour", "salut", "salam", "hey", "yo"]):
        return "GREETING"
    if _is_edt_question(question):
        return "EDT"
    if _is_campus_info_question(question):
        return "FAQ"
    if os.getenv("ENABLE_INTENT_LLM", "false").strip().lower() != "true":
        return "FAQ"
    
    system = "Tu es un classificateur d'intention ultra-rapide. Reponds par un seul mot parmi : GREETING, IDENTITY, EDT, FAQ."
    prompt = (
        f"Question d'etudiant : '{question}'\n"
        "Categories :\n"
        "- GREETING: salutations, politesses.\n"
        "- IDENTITY: qui es-tu, que peux-tu faire, ton role.\n"
        "- EDT: emplois du temps, horaires, planning.\n"
        "- FAQ: questions administratives, bourses, inscriptions, localisation.\n"
        "INTENTION :"
    )
    
    intent = call_groq(prompt, system=system, timeout=5, max_tokens=10)
    intent = (intent or "FAQ").upper().strip().replace(".", "")
    if intent not in ["GREETING", "IDENTITY", "EDT", "FAQ"]:
        if _is_edt_question(question): return "EDT"
        return "FAQ"
    
    return intent


def _has_timetable_phrase(question: str) -> bool:
    q = _normalize_text(question)
    if not q:
        return False

    patterns = [
        r"\bemplo\w*\b\s+(?:du|de la|de l|de)\s+\btemp\w*\b",
        r"\bemploi\w*\b\s+\btemp\w*\b",
        r"\bedt\b",
        r"\btime\s*table\b",
        r"\btimetable\b",
        r"\bschedule\b",
    ]
    return any(re.search(pattern, q) for pattern in patterns)


def _mentions_track(question: str) -> bool:
    return bool(_extract_track_codes(question))


def _is_document_lookup_question(question: str) -> bool:
    q = _normalize_text(question)
    if not q:
        return False

    markers = [
        "que dit la page",
        "que dit l ensa bm a propos de",
        "que faut il savoir sur",
        "que precise la page",
        "explique la section",
        "quelles informations fournit",
        "quelle information donne l ensa bm sur",
        "ou trouver les informations sur",
    ]
    return any(marker in q for marker in markers)


def _has_day_or_live_time_marker(question: str) -> bool:
    q = _normalize_text(question)
    if not q:
        return False

    live_markers = [
        "lundi",
        "mardi",
        "mercredi",
        "jeudi",
        "vendredi",
        "samedi",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "aujourd",
        "demain",
        "hier",
        "semaine",
        "maintenant",
        "prochain",
        "next",
        "today",
        "tomorrow",
        "this week",
    ]
    if any(marker in q for marker in live_markers):
        return True
    return bool(re.search(r"\b([01]?\d|2[0-3])\s*(?:h|:)\s*([0-5]?\d)?\b", q))


def _contains_normalized_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text))


def _is_teacher_module_lookup_question(question: str) -> bool:
    q = _normalize_text(question)
    if not q:
        return False

    teacher_marker = bool(
        re.search(r"\b(?:pr|prof|professeur|enseignant|enseignante|teacher|professor)\b", q)
    )
    asks_module = any(marker in q for marker in ["module", "modules", "matiere", "matieres", "cours", "subject", "course"])
    asks_teaching = any(marker in q for marker in ["enseigne", "enseignes", "donne", "teaches", "teaching"])

    if teacher_marker and (asks_module or asks_teaching):
        return True
    if asks_module and asks_teaching and re.search(r"\b[A-Za-z]{4,}\b", question or ""):
        return True
    return False


def _is_program_catalog_question(question: str) -> bool:
    q = _normalize_text(question)
    if not q or _has_timetable_phrase(question):
        return False

    if _has_day_or_live_time_marker(question):
        return False

    teacher_lookup_markers = [
        "qui enseigne",
        "qui donne",
        "qui assure",
        "quel prof",
        "quels prof",
        "professeur de",
        "enseignant de",
    ]
    if any(marker in q for marker in teacher_lookup_markers):
        return False
    if _is_teacher_module_lookup_question(question):
        return False

    if re.search(r"\bstages?\b|\bpfe\b", q) and not re.search(r"\bstage\s*[12]\b", q):
        return False

    has_track = _mentions_track(q)
    has_semester = bool(re.search(r"\b(?:s\s*[1-6]|semestre\s*[1-6])\b", q))
    program_markers = [
        "programme",
        "formation",
        "module",
        "modules",
        "matiere",
        "matieres",
        "cours",
        "brochure",
        "enseigne",
        "enseignes",
        "contient",
        "comprend",
        "inclut",
        "comporte",
        "etudie",
        "etudies",
        "fait",
        "font",
        "trouve",
        "ou se trouve",
        "dans quel semestre",
        "en quel semestre",
        "quelle annee",
    ]
    module_names = [
        "blockchain",
        "devops",
        "devsecops",
        "haccp",
        "smart factory",
        "machine learning",
        "deep learning",
        "forensics",
        "cryptographie",
        "iot",
        "toxicologie",
        "systemes solaires",
        "genie logiciel",
    ]

    has_program_marker = any(_contains_normalized_phrase(q, marker) for marker in program_markers)
    has_module_name = any(marker in q for marker in module_names)
    asks_module_position = any(
        marker in q
        for marker in [
            "dans quel semestre",
            "en quel semestre",
            "quel semestre",
            "semestre",
            "quelle annee",
            "quand",
            "ou se trouve le module",
        ]
    )
    known_module_hit = False
    try:
        programs, aliases = _program_catalog_data()
        track = _extract_program_track(q, programs, aliases)
        known_module_hit = bool(track and _find_program_module(q, track, programs))
    except Exception:
        known_module_hit = False

    return has_track and (
        (has_semester and has_program_marker)
        or (has_module_name and (has_program_marker or asks_module_position))
        or (known_module_hit and (has_program_marker or asks_module_position))
        or ("programme" in q and any(marker in q for marker in ["formation", "filiere", "cycle"]))
    )


def _tokenize(question: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _normalize_text(question))


def _approx_match_token(token: str, candidate: str, ratio_threshold: float = 0.82) -> bool:
    if token == candidate:
        return True

    if len(token) >= 4 and len(candidate) >= 4:
        if token.startswith(candidate) or candidate.startswith(token):
            return True

    if len(token) < 4 or len(candidate) < 4:
        return False

    if abs(len(token) - len(candidate)) > 2:
        return False

    return SequenceMatcher(None, token, candidate).ratio() >= ratio_threshold


def _has_approx_token(tokens: list[str], lexicon: set[str], min_hits: int = 1) -> bool:
    if not tokens or not lexicon:
        return False

    hits = 0
    used = set()
    for token in tokens:
        for candidate in lexicon:
            if candidate in used:
                continue
            if _approx_match_token(token, candidate):
                used.add(candidate)
                hits += 1
                if hits >= min_hits:
                    return True
                break
    return False


def _has_edt_like_signals(question: str) -> bool:
    q = _normalize_text(question)
    if not q:
        return False

    if _is_document_lookup_question(question):
        return False

    if _is_program_catalog_question(question):
        return False

    if _has_timetable_phrase(question):
        return True

    if any(_normalize_text(marker) in q for marker in FULL_TIMETABLE_MARKERS):
        return True

    tokens = _tokenize(question)
    if _has_approx_token(tokens, EDT_INTENT_TOKENS, min_hits=2):
        return True

    asks_all = _has_approx_token(tokens, {"tout", "all", "entier", "complete", "complet", "full"}, min_hits=1)
    if asks_all and any(marker in q for marker in ["planning", "horaire", "emploi", "edt", "timetable", "schedule"]):
        return True

    if _mentions_track(q) and any(marker in q for marker in ["planning", "horaire", "calendrier"]):
        return True

    asks_to_show = _has_approx_token(tokens, set(TIMETABLE_VERBS), min_hits=1)
    has_schedule_signal = _has_approx_token(tokens, EDT_INTENT_TOKENS, min_hits=1)
    if asks_to_show and has_schedule_signal:
        return True

    has_semester = bool(re.search(r"\bs\s?\d{1,2}\b", q))
    has_track = bool(re.search(r"\b(iacs|tdi|g2er|iaa|2ap|classe|filiere)\b", q))
    if has_semester and has_track:
        return True

    if has_track and _has_day_or_live_time_marker(question):
        return True

    teacher_lookup_markers = [
        "qui enseigne",
        "qui donne",
        "qui assure",
        "quel prof",
        "quels prof",
        "qui sont les prof",
        "professeur de",
        "enseignant de",
    ]
    if has_track and (any(marker in q for marker in teacher_lookup_markers) or _is_teacher_module_lookup_question(question)):
        return True

    return False


def _tone_message(message: str, user_state: str | None) -> str:
    from backend.services.chatbot_service import apply_emotional_tone

    return apply_emotional_tone(message, user_state)


def _basic_conversational_answer(question: str, class_label: str | None = None, language: str = "fr") -> str | None:
    """Short deterministic answers for greetings and identity questions."""
    q = _normalize_text(question)
    tokens = _tokenize(question)
    if not q:
        return None

    greeting_tokens = {"bonjour", "salut", "salam", "hello", "hi", "hey", "bonsoir"}
    is_greeting = len(tokens) <= 3 and any(token in greeting_tokens for token in tokens)
    thanks_tokens = {"merci", "thanks", "thank"}
    is_thanks = len(tokens) <= 4 and any(token in thanks_tokens for token in tokens)
    is_identity = any(
        marker in q
        for marker in [
            "qui es tu",
            "qui etes vous",
            "tu es qui",
            "que peux tu faire",
            "c est quoi ton role",
            "what can you do",
            "who are you",
            "what are you",
        ]
    )

    if not is_greeting and not is_identity and not is_thanks:
        return None

    if is_thanks and not is_identity and not is_greeting:
        if language == "en":
            return "You're welcome. I can still help you check a timetable or an ENSA BM question."
        if language == "ar":
            return "على الرحب والسعة. يمكنني مساعدتك في التحقق من جدولك أو معلومات ENSA BM."
        return "Avec plaisir. Je reste la si tu veux verifier un emploi du temps ou une information ENSA."

    if language == "en":
        answer = (
            "Hello! I am the ENSA Beni Mellal AI assistant. "
            "I can help with administrative questions, FAQ information, and timetables."
        )
    elif language == "ar":
        answer = (
            "مرحبا! أنا المساعد الذكي لمدرسة ENSA بني ملال. "
            "يمكنني مساعدتك في الأسئلة الإدارية، معلومات FAQ، واستعمالات الزمن."
        )
    else:
        answer = (
            "Bonjour ! Je suis l'assistant IA de l'ENSA Beni Mellal. "
            "Je peux t'aider avec les questions administratives, les informations FAQ et les emplois du temps."
        )

    if class_label and language != "ar":
        answer += f" Classe actuelle : {class_label}."
    return answer


@lru_cache(maxsize=1)
def _program_catalog_data() -> tuple[dict, dict]:
    try:
        from backend.scripts.generate_ensa_bm_official_faq import TRACK_ALIASES, TRACK_SEMESTER_PROGRAMS

        return TRACK_SEMESTER_PROGRAMS, TRACK_ALIASES
    except Exception as exc:
        logger.debug(f"Program catalog unavailable: {exc}")
        return {}, {}


@lru_cache(maxsize=1)
def _official_track_facts_data() -> dict:
    try:
        from backend.scripts.generate_ensa_bm_official_faq import TRACK_FACTS

        return TRACK_FACTS
    except Exception as exc:
        logger.debug(f"Official track facts unavailable: {exc}")
        return {}


def _extract_program_track(q: str, programs: dict, aliases: dict) -> str | None:
    for code in programs:
        if re.search(rf"\b{re.escape(code.lower())}\b", q):
            return code

    candidates = []
    for code, alias_list in aliases.items():
        for alias in alias_list:
            normalized_alias = _normalize_text(alias)
            if normalized_alias:
                candidates.append((code, normalized_alias))

    for code, alias in sorted(candidates, key=lambda item: len(item[1]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", q):
            return code
    return None


def _extract_program_semester(q: str) -> str | None:
    match = re.search(r"\bs\s*([1-6])\b", q)
    if not match:
        match = re.search(r"\bsemestres?\s*([1-6])\b", q)
    return f"S{match.group(1)}" if match else None


def _format_program_semester_answer(track: str, semester: str, data: dict) -> str:
    title = data.get("title") or "programme"
    modules = "; ".join(data.get("modules") or [])
    answer = f"En {track} {semester} (semestre {semester[1:]} - {title}), les modules sont : {modules}."
    if data.get("note"):
        answer += f" {data['note']}"
    return answer


def _program_module_tokens(module: str) -> set[str]:
    stopwords = {
        "de",
        "des",
        "du",
        "et",
        "a",
        "en",
        "pour",
        "la",
        "le",
        "les",
        "aux",
        "applique",
        "appliquee",
        "applications",
    }
    return {token for token in _tokenize(module) if len(token) >= 3 and token not in stopwords}


def _find_program_module(question: str, track: str, programs: dict) -> tuple[str, str, dict] | None:
    q = _normalize_text(question)
    q_tokens = set(_tokenize(q))
    q_tokens.update(token[:-1] for token in list(q_tokens) if token.endswith("s") and len(token) > 4)
    best: tuple[float, str, str, dict] | None = None

    for semester, data in (programs.get(track) or {}).items():
        for module in data.get("modules") or []:
            module_norm = _normalize_text(module)
            module_tokens = _program_module_tokens(module)
            if not module_tokens:
                continue

            overlap = q_tokens & module_tokens
            distinctive_hit = any(token in overlap and len(token) >= 5 for token in module_tokens)
            phrase_hit = module_norm and module_norm in q
            score = len(overlap) / max(len(module_tokens), 1)
            if phrase_hit:
                score = 2.0
            elif distinctive_hit:
                score += 0.35

            if score >= 0.45 and (best is None or score > best[0]):
                best = (score, semester, module, data)

    if not best:
        return None
    _, semester, module, data = best
    return semester, module, data


def _program_catalog_answer(question: str) -> str | None:
    if not _is_program_catalog_question(question):
        return None

    programs, aliases = _program_catalog_data()
    if not programs:
        return None

    q = _normalize_text(question)
    track = _extract_program_track(q, programs, aliases)
    if not track:
        return None

    semester = _extract_program_semester(q)
    if semester and semester in programs.get(track, {}):
        return _format_program_semester_answer(track, semester, programs[track][semester])

    asks_module_position = any(
        marker in q
        for marker in [
            "dans quel semestre",
            "en quel semestre",
            "quel semestre",
            "semestre",
            "quelle annee",
            "quand",
            "se trouve",
            "cours sur",
            "fait",
            "etudie",
        ]
    )
    if asks_module_position:
        module_match = _find_program_module(question, track, programs)
        if module_match:
            matched_semester, module, data = module_match
            answer = (
                f"Le module {module} est enseigne en {track} {matched_semester} "
                f"(semestre {matched_semester[1:]}). "
            )
            answer += f"Dans ce semestre, le programme comprend aussi : {'; '.join(data.get('modules') or [])}."
            return answer

    overview = []
    for semester_key in sorted(programs.get(track, {}), key=lambda s: int(s[1:])):
        data = programs[track][semester_key]
        title = data.get("title") or "programme"
        overview.append(f"{semester_key} : {title}")
    if overview:
        return f"Le programme {track} est organise ainsi : " + "; ".join(overview) + "."
    return None


def _extract_official_track(q: str, facts: dict) -> str | None:
    candidates: list[tuple[str, str]] = []
    for code, data in facts.items():
        aliases = [
            code,
            data.get("short_name", ""),
            data.get("name", ""),
            data.get("keywords", ""),
        ]
        if code == "G2ER":
            aliases.extend(["geer", "genie electrique", "energies renouvelables"])
        elif code == "IAA":
            aliases.extend(["agroalimentaire", "industrie agroalimentaire", "industries agroalimentaires"])
        elif code == "IACS":
            aliases.extend(["iac", "intelligence artificielle", "cybersecurite", "ia cybersecurite", "ia et cybersecurite"])
        elif code == "TDI":
            aliases.extend(["transformation digitale", "transformation numerique", "industrie 4 0", "industrie 4.0"])
        elif code == "2AP":
            aliases.extend(["cycle preparatoire", "classes preparatoires", "prepa integree"])

        for alias in aliases:
            normalized_alias = _normalize_text(alias)
            if normalized_alias:
                candidates.append((code, normalized_alias))

    for code, alias in sorted(candidates, key=lambda item: len(item[1]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", q):
            return code
    return None


def _official_track_fact_answer(question: str, q: str, asks_email: bool, asks_contact: bool) -> str | None:
    if _has_day_or_live_time_marker(question):
        return None

    facts = _official_track_facts_data()
    if not facts:
        return None

    code = _extract_official_track(q, facts)
    if not code:
        return None

    data = facts.get(code) or {}
    name = data.get("name") or code
    coordinator = data.get("coordinator")
    email = data.get("email")

    asks_coordinator = any(marker in q for marker in ["coordinateur", "coordinator", "responsable", "chef de filiere", "chef", "pilote", "supervise", "dirige", "encadre", "encadrant", "encadrement", "lead", "head"])
    asks_definition = any(marker in q for marker in ["quoi", "signifie", "veut dire", "correspond", "definition", "c est quoi", "c koi", "concerne", "presente", "explique", "cest quoi", "what is", "what's", "what are", "about", "mainly about", "mean", "means", "overview"])
    asks_admission = any(marker in q for marker in ["rejoindre", "integrer", "admission", "acceder", "acces", "entrer", "bac2", "bac 2", "bac plus deux", "candidater"])
    asks_duration = any(marker in q for marker in ["duree", "dure", "combien de temps", "annee", "semestre"])
    asks_credits = "credit" in q
    asks_language = any(marker in q for marker in ["langue", "francais", "anglais", "arabe"])
    asks_mode = any(marker in q for marker in ["mode", "presentiel", "distance", "hybride"])
    asks_program = any(marker in q for marker in ["programme", "module", "modules", "matiere", "matieres", "cours", "enseigne", "etudie"])
    asks_skills = any(marker in q for marker in ["competence", "competences", "savoir faire", "apprendre", "acquerir"])
    asks_jobs = any(marker in q for marker in ["debouche", "debouches", "metier", "metiers", "job", "jobs", "poste", "carrieres", "travail"])
    asks_sectors = any(marker in q for marker in ["secteur", "secteurs", "recrute", "entreprise", "domaines d activite"])
    asks_stages = any(marker in q for marker in ["stage", "stages", "pfe", "soutenance", "memoire"])
    asks_infrastructure = any(marker in q for marker in ["infrastructure", "laboratoire", "laboratoires", "equipement", "equipements", "plateforme", "materiel"])
    asks_partners = any(marker in q for marker in ["partenaire", "partenaires", "partenariat", "partenariats", "cooperation", "double diplome", "double diplomation", "mobilite"])
    asks_club = any(marker in q for marker in ["club", "csia", "vie etudiante", "hackathon", "ctf"])

    if code == "IACS" and any(marker in q for marker in ["repartition", "répartition", "proportion", "pourcentage", "57", "43", "ia data", "ia/data", "data et cyber"]):
        return "La brochure IACS indique une repartition d'environ 57 % IA/Data Science et 43 % Cybersecurite."

    if asks_coordinator:
        if asks_email and email:
            return f"Le contact indique pour {code} est {email}."
        answer = f"Le coordinateur de la filiere {code} ({name}) est {coordinator}."
        if email:
            answer += f" Contact indique : {email}."
        return answer
    if asks_email and email:
        return f"Le contact indique pour {code} est {email}."
    if asks_contact:
        if coordinator and email:
            return f"Pour {code}, le coordinateur est {coordinator}. Contact indique : {email}."
        if email:
            return f"Le contact indique pour {code} est {email}."
    if asks_admission and data.get("admission"):
        return f"Admission {code} : {data['admission']}"
    if asks_duration:
        parts = [f"La filiere {code} ({name}) dure {data.get('duration')}"]
        if data.get("semesters"):
            parts.append(f"et comprend {data['semesters']}")
        return " ".join(parts).strip() + "."
    if asks_credits and data.get("credits"):
        return f"La page officielle indique pour {code} : {data['credits']}."
    if asks_language and data.get("language"):
        return f"La langue ou les langues indiquees pour {code} : {data['language']}."
    if asks_mode and data.get("mode"):
        return f"Le mode indique pour {code} : {data['mode']}."
    if asks_program and data.get("program"):
        return f"Programme {code} : {data['program']}"
    if asks_skills and data.get("skills"):
        return f"Competences visees en {code} : {data['skills']}"
    if asks_jobs and data.get("jobs"):
        return f"Debouches {code} : {data['jobs']}"
    if asks_sectors and data.get("sectors"):
        return f"Secteurs lies a {code} : {data['sectors']}."
    if asks_stages and data.get("stages"):
        stages = data["stages"]
        normalized_stages = _normalize_text(stages)
        if (
            "projet de fin d etudes" in normalized_stages
            or "projet de fin d'etudes" in normalized_stages
        ) and "pfe" not in normalized_stages:
            stages = f"{stages} (PFE)."
        return f"Stages en {code} : {stages}"
    if asks_infrastructure and data.get("infrastructure"):
        return f"Infrastructures {code} : {data['infrastructure']}."
    if asks_partners and data.get("partners"):
        return f"Partenaires lies a {code} : {data['partners']}."
    if asks_club and data.get("student_life"):
        return f"Vie etudiante {code} : {data['student_life']}"
    if asks_definition and data.get("summary"):
        return f"{code} signifie {name}. {data['summary']}"

    return None


def _official_student_service_answer(question: str, q: str) -> str | None:
    if not q:
        return None

    if any(marker in q for marker in ["coordinateur", "coordonnateur", "responsable", "contact", "email", "mail", "chef", "pilote", "supervise", "dirige"]):
        return None

    if (
        any(marker in q for marker in ["attestation", "attestion", "certificat", "document administratif", "documents administratifs", "releve de notes"])
        and any(marker in q for marker in ["recupere", "recuperer", "obtenir", "demander", "telecharger", "retirer", "ou"])
    ):
        return (
            "Pour recuperer une attestation d'inscription, un releve de notes officiel ou un document administratif, "
            "passe par l'ENT/Espace Etudiant si le service est disponible, sinon contacte le service de scolarite "
            "et suis les avis officiels de l'administration."
        )

    asks_results_lookup = (
        any(marker in q for marker in ["note", "notes", "resultat", "resultats", "resulta", "fin de semestre"])
        and any(marker in q for marker in ["consulter", "voir", "trouver", "ou", "resulta", "resultat", "note"])
    )
    if asks_results_lookup:
        return (
            "La consultation des notes et resultats de fin de semestre se fait via l'Espace Etudiant/ENT "
            "de l'ENSA Beni Mellal, ou selon les avis officiels publies par l'administration."
        )

    asks_attestation = (
        any(marker in q for marker in ["attestation", "attestion", "certificat", "document administratif", "documents administratifs", "releve de notes"])
        or (
            "inscription" in q
            and any(marker in q for marker in ["recupere", "recuperer", "obtenir", "demander", "telecharger", "retirer"])
        )
    )
    if asks_attestation:
        return (
            "Pour recuperer une attestation d'inscription ou un document administratif, passe par l'ENT/Espace Etudiant "
            "si le service est disponible, sinon contacte le service de scolarite et suis les avis officiels de l'administration."
        )

    asks_validation_threshold = (
        any(marker in q for marker in ["moyenne", "seuil", "note minimale", "note minimum", "validation", "valider"])
        and any(marker in q for marker in ["cycle ingenieur", "semestre", "module", "annee", "valider", "validation"])
    )
    if asks_validation_threshold:
        return (
            "Je n'ai pas de seuil officiel fiable dans la base pour la moyenne de validation. "
            "Pour cette question, il faut se referer au reglement des etudes ou demander confirmation au service de scolarite."
        )

    if "master" in q:
        return (
            "La base ne confirme pas une offre de master interne/propre a l'ENSA Beni Mellal. "
            "Elle mentionne surtout le cycle ingenieur et des partenariats/doubles diplomations pouvant inclure un master chez un partenaire. "
            "Pour une candidature master, consulte les avis officiels de l'ENSABM/USMS."
        )

    asks_infrastructure = any(
        marker in q
        for marker in [
            "laboratoire",
            "laboratoires",
            "aboratoire",
            "aboratoires",
            "infrastructure",
            "infrastructures",
            "equipement",
            "equipements",
            "plateforme",
            "plateformes",
        ]
    )
    if asks_infrastructure and not _mentions_track(q):
        return (
            "Oui. L'ENSA Beni Mellal dispose d'infrastructures pedagogiques et pratiques selon les filieres : "
            "salles de TP, salle informatique, ateliers industriels, equipements IAA comme HPLC/CPG, PCR et autoclave, "
            "plateformes G2ER pour photovoltaique/automatique/robotique, laboratoire IA industrielle en TDI, "
            "et environnements pratiques pour IA, data, reseaux et cybersecurite en IACS."
        )

    asks_canteen = any(
        marker in q
        for marker in [
            "resto",
            "resto u",
            "restaurant universitaire",
            "restaurant u",
            "cantine",
        ]
    )
    if asks_canteen:
        return (
            "Je n'ai aucune information officielle sur un restaurant universitaire a l'ENSA Beni Mellal. "
            "Consulte le site officiel ou le service de scolarite pour confirmation."
        )

    asks_boarding = any(
        marker in q
        for marker in [
            "internat",
            "dortoir",
            "residence",
            "résidence",
            "hebergement",
            "hébergement",
        ]
    )
    if asks_boarding:
        return (
            "Je n'ai aucune confirmation officielle sur un internat a l'ENSA Beni Mellal. "
            "Verifie auprès de la scolarite ou du site officiel pour obtenir une reponse fiable."
        )

    asks_salary = any(
        marker in q
        for marker in [
            "salaire",
            "revenu",
            "gain",
            "remuneration",
            "rémunération",
        ]
    )
    if asks_salary:
        return (
            "Je n'ai pas d'information fiable sur le salaire moyen des diplomes de l'ENSA BM. "
            "Les debouches et les revenus varient selon la filiere, l'experience et le contexte professionnel."
        )

    asks_passerelle_age = any(
        marker in q
        for marker in [
            "age maximum",
            "âge maximum",
            "limite d age",
            "limite d'âge",
            "age limite",
            "âge limite",
        ]
    ) and any(
        marker in q
        for marker in [
            "passerelle",
            "2ap",
            "cycle preparatoire",
            "concours",
        ]
    )
    if not asks_passerelle_age:
        asks_passerelle_age = "maximum" in q and "passerelle" in q
    if asks_passerelle_age:
        return (
            "Je n'ai pas de limite d'age officielle pour la passerelle. "
            "Consulte les avis officiels du concours ENSA ou contacte le service de scolarite pour obtenir une reponse precise."
        )

    asks_program_details = any(
        marker in q
        for marker in [
            "module",
            "modules",
            "cours",
            "programme",
            "semestre",
            "s1",
            "s2",
            "s3",
            "s4",
            "s5",
            "s6",
        ]
    )
    asks_definition = any(marker in q for marker in ["signifie", "veut dire", "definition", "c est quoi", "cest quoi"])
    asks_existence = (
        any(marker in q for marker in ["y a", "y'a", "ya", "existe", "dispose", "propose", "offre", "est ce que", "il y a"])
        or ("filiere" in q and any(marker in q for marker in ["intelligence artificielle", "energetique", "energie", "renouvelable"]))
    )

    if asks_existence and not asks_program_details and not asks_definition:
        if "intelligence artificielle" in q or re.search(r"\bia\b", q):
            return (
                "Oui. L'ENSA Beni Mellal propose la filiere IACS : Intelligence Artificielle et Cybersecurite. "
                "Elle forme des ingenieurs en IA, data science, reseaux, cloud et cybersecurite."
            )
        if any(marker in q for marker in ["energetique", "energie", "energies", "renouvelable", "renouvelables"]):
            return (
                "Oui. Le volet energie est couvert par la filiere G2ER : Genie Electrique et Energies Renouvelables. "
                "Elle porte sur les systemes electriques, les energies renouvelables et l'efficacite energetique."
            )

    return None


def _official_fast_fact_answer(question: str) -> str | None:
    q = _normalize_text(question)
    if not q:
        return None

    if _is_document_lookup_question(question):
        return None

    raw_question = question or ""
    if any(marker in raw_question for marker in ["مدير", "من هو المدير"]):
        return "المدير ديال ENSA Beni Mellal هو Pr. BELAID BOUILKHILANE."
    if any(marker in raw_question for marker in ["الموقع الرسمي", "موقع ENSA", "موقع المدرسة"]):
        return "الموقع الرسمي ديال ENSA Beni Mellal هو https://ensabm.usms.ac.ma/."

    student_service_answer = _official_student_service_answer(question, q)
    if student_service_answer:
        return student_service_answer

    program_answer = _program_catalog_answer(question)
    if program_answer:
        return program_answer

    tokens = set(_tokenize(q))
    asks_site = "site officiel" in q or bool(tokens.intersection({"site", "web", "portail", "website"}))
    asks_email = bool(tokens.intersection({"email", "mail", "courriel"}))
    asks_contact = any(token in tokens for token in ["contact", "contacter"])
    mentions_track_or_role = any(
        marker in q
        for marker in [
            "coordinateur",
            "responsable",
            "g2er",
            "iaa",
            "iacs",
            "tdi",
            "agroalimentaire",
            "intelligence artificielle",
            "transformation digitale",
            "genie electrique",
        ]
    )

    if asks_email and asks_site and not mentions_track_or_role:
        return "L'email officiel est ensabm.contact@usms.ma. Le site officiel est https://ensabm.usms.ac.ma/."
    if asks_email and not mentions_track_or_role:
        return "L'email de contact officiel est ensabm.contact@usms.ma."
    if asks_site and not mentions_track_or_role:
        return "Le site officiel de l'ENSA Beni Mellal est https://ensabm.usms.ac.ma/."
    if asks_contact and not mentions_track_or_role:
        return "Tu peux contacter l'ENSA Beni Mellal par email a ensabm.contact@usms.ma. Le site officiel est https://ensabm.usms.ac.ma/."

    if "directeur" in q or "director" in q or ("dirige" in q and any(marker in q for marker in ["ensa", "ensabm", "ecole", "beni mellal"])):
        return "Le directeur de l'ENSA Beni Mellal est Pr. BELAID BOUILKHILANE."

    if any(marker in q for marker in ["nom complet", "sigle ensa", "sigle ensa bm", "signifie ensa", "ensa bm veut dire", "ensa bm signifie", "ensabm veut dire", "ensabm ca veut dire", "ensabm signifie"]):
        return "ENSA BM designe l'Ecole Nationale des Sciences Appliquees de Beni Mellal."

    if any(marker in q for marker in ["c est quoi l ensa", "cest quoi l ensa", "qu est ce que l ensa", "presente ensa", "explique ensa"]):
        return (
            "L'ENSA Beni Mellal est une Ecole Nationale des Sciences Appliquees relevant de l'Universite Sultan Moulay Slimane. "
            "Elle forme des ingenieurs d'Etat via deux annees preparatoires puis trois annees de cycle ingenieur."
        )

    if ("mission" in tokens or "objectif" in tokens or any(marker in q for marker in ["role de l ensa", "a quoi sert ensa"])):
        return (
            "La mission de l'ENSA Beni Mellal est de former des ingenieurs d'Etat avec une base scientifique solide, "
            "des competences techniques et une ouverture vers l'innovation, la recherche et les besoins socio-economiques."
        )

    if any(marker in q for marker in ["cree", "creation", "ouverte", "ouvert", "date de creation"]):
        return "L'Ecole Nationale des Sciences Appliquees de Beni Mellal a ouvert ses portes en 2019."

    if "reseau ensa" in q or "ensa maroc" in q:
        return "Oui. L'ENSA Beni Mellal est membre du reseau des Ecoles Nationales des Sciences Appliquees du Maroc."

    asks_role_or_contact = asks_email or asks_contact or any(marker in q for marker in ["responsable", "coordinateur", "coordonnateur", "chef", "pilote", "supervise"])
    if (
        any(marker in q for marker in ["ou se situe", "where is", "adresse", "localisation", "situe", "campus"])
        and any(marker in q for marker in ["ensa", "ensabm", "bm", "beni mellal", "mghila", "ecole", "campus"])
        and not asks_role_or_contact
    ):
        return "L'ENSA Beni Mellal est situee sur le campus universitaire de M'ghila, a Beni Mellal."

    if any(marker in q for marker in ["double diplomation", "double diplome", "partenariat", "partenariats", "mobilite internationale"]):
        return (
            "Oui. L'ENSABM developpe des partenariats academiques pour la mobilite, la recherche et la double diplomation, "
            "notamment avec Polytech Angers et l'EILCO/Universite du Littoral Cote d'Opale."
        )

    asks_admission = any(marker in q for marker in ["rejoindre", "integrer", "admission", "acceder", "acces", "entrer"])
    mentions_preparatory = any(marker in q for marker in ["cycle preparatoire", "2ap", "classes preparatoires"])
    mentions_engineering_cycle = any(marker in q for marker in ["cycle ingenieur", "filiere ingenieur", "admission parallele"])
    asks_duration = (
        "duree" in q
        or "dure" in q
        or "combien de temps" in q
        or "semestre" in q
        or ("combien" in q and "annee" in q)
        or ("combien" in q and "anne" in q)
        or ("annee" in q and "cycle" in q)
    )
    if any(marker in q for marker in ["formation ingenieur", "formation ing"]) and asks_duration:
        return "La formation ingenieur ENSA dure 5 ans au total apres le bac."
    if any(marker in q for marker in ["cycle complet", "cursus complet", "parcours complet", "formation complete"]) and asks_duration:
        return "Le cursus complet ENSA dure generalement 5 ans : 2 ans de cycle preparatoire puis 3 ans de cycle ingenieur."
    if mentions_preparatory and any(marker in q for marker in ["combien", "duree", "annee", "semestre"]):
        return "Le cycle preparatoire 2AP a l'ENSA Beni Mellal dure 2 ans, soit 4 semestres, avant l'orientation vers une filiere ingenieur."
    if mentions_engineering_cycle and asks_duration:
        return (
            "Le cycle ingenieur a l'ENSA Beni Mellal dure 3 ans, soit six semestres. "
            "Le cursus complet ENSA se fait donc generalement en 5 ans : 2 ans de cycle preparatoire puis 3 ans de cycle ingenieur."
        )

    track_fact_answer = _official_track_fact_answer(question, q, asks_email, asks_contact)
    if track_fact_answer:
        return track_fact_answer

    if asks_admission and mentions_engineering_cycle:
        return (
            "Pour rejoindre le cycle ingenieur de l'ENSA Beni Mellal, le parcours normal passe par le cycle preparatoire "
            "ENSA puis l'orientation vers une filiere ingenieur. Une admission parallele peut aussi etre ouverte selon "
            "les avis officiels, le diplome, le dossier et les places disponibles."
        )
    if asks_admission and (mentions_preparatory or "ensa" in q or "beni mellal" in q):
        return (
            "Pour rejoindre l'ENSA Beni Mellal, l'acces se fait selon les avis officiels : concours national apres le bac "
            "pour le cycle preparatoire 2AP, puis orientation vers une filiere ingenieur; le cycle ingenieur peut aussi "
            "etre accessible par admission parallele selon les conditions annoncees."
        )

    if any(marker in q for marker in ["qui est", "role", "monsieur", "madame"]):
        people = {
            "gouskir": "Pr. Mohamed GOUSKIR est indique comme coordinateur de la filiere IACS (Intelligence Artificielle et Cybersecurite). Contact indique : m.gouskir@usms.ma.",
            "rokni": "M. Yahya ROKNI est indique comme coordinateur de la filiere IAA (Industries Agroalimentaires). Contact indique : agroalimentaire.ensa@gmail.com.",
            "oulcaid": "M. Mostapha OULCAID est indique comme coordinateur de la filiere G2ER (Genie Electrique et Energies Renouvelables). Contact indique : m.oulcaid@usms.ma.",
            "ouanan": "M. Hamid OUANAN est indique comme coordinateur de la filiere TDI (Transformation Digitale Industrielle). Contact indique : ham.ouanan@gmail.com.",
            "kaab": "M. Mohamed KAAB est indique comme coordinateur du cycle preparatoire 2AP a l'ENSA Beni Mellal.",
        }
        for name, answer in people.items():
            if name in q:
                return answer

    track_facts = {
        "g2er": {
            "name": "Genie Electrique et Energies Renouvelables",
            "definition": "La filiere forme des ingenieurs en genie electrique, production d'energie propre et efficacite energetique.",
            "coordinator": "Le coordinateur de la filiere G2ER (Genie Electrique et Energies Renouvelables) est M. Mostapha OULCAID. Contact indique : m.oulcaid@usms.ma.",
            "infrastructure": "Les infrastructures G2ER incluent des plateformes de TP photovoltaique, pompage solaire, automatique, instrumentation industrielle, regulation, automatismes et robotique, electronique de puissance, geothermie, solaire thermique et smart grid.",
            "aliases": [
                "g2er",
                "geer",
                "genie electrique",
                "energies renouvelables",
                "genie electrique et energies renouvelables",
                "genie electrique energies renouvelables",
            ],
        },
        "iaa": {
            "name": "Industries Agroalimentaires",
            "definition": "La filiere forme des ingenieurs capables de concevoir, developper et gerer des produits et procedes agroalimentaires.",
            "coordinator": "Le coordinateur de la filiere IAA (Industries Agroalimentaires) est M. Yahya ROKNI. Contact indique : agroalimentaire.ensa@gmail.com.",
            "infrastructure": "Les infrastructures IAA mentionnent notamment amphitheatre, salles de cours/TD, salles de TP, salle informatique, bibliotheque, ateliers industriels, fermenteurs, spectrophotometre UV/Visible, autoclave, HPLC/CPG, PCR, secheur et cabines d'analyse sensorielle.",
            "aliases": [
                "iaa",
                "industries agroalimentaires",
                "industrie agroalimentaire",
                "agroalimentaire",
                "industries agro alimentaires",
                "industrie agro alimentaire",
            ],
        },
        "iacs": {
            "name": "Intelligence Artificielle et Cybersecurite",
            "definition": "La filiere forme des ingenieurs capables de concevoir des systemes d'IA et de securiser les infrastructures numeriques.",
            "coordinator": "Le coordinateur de la filiere IACS (Intelligence Artificielle et Cybersecurite) est Pr. Mohamed GOUSKIR. Contact indique : m.gouskir@usms.ma.",
            "infrastructure": "La filiere IACS s'appuie sur une formation numerique orientee IA, data, reseaux, cybersecurite, cloud, DevSecOps et projets pratiques.",
            "aliases": [
                "iacs",
                "iac",
                "intelligence artificielle et cybersecurite",
                "intelligence artificielle cybersecurite",
                "intelligence artificielle",
                "cybersecurite",
                "cyber securite",
                "ia et cybersecurite",
                "ia cybersecurite",
            ],
        },
        "tdi": {
            "name": "Transformation Digitale Industrielle",
            "definition": "La filiere est axee sur l'industrie 4.0, l'automatisation, l'IoT, la robotique et les systemes de production intelligents.",
            "coordinator": "Le coordinateur de la filiere TDI (Transformation Digitale Industrielle) est M. Hamid OUANAN. Contact indique : ham.ouanan@gmail.com.",
            "infrastructure": "Les infrastructures TDI mentionnent station de calcul, salles TP, salle reseau/supervision industrielle, laboratoire IA industrielle, casques AR/VR, studio MOOC, tableaux interactifs, serveur cloud industriel prive et licences Microsoft.",
            "aliases": [
                "tdi",
                "transformation digitale industrielle",
                "transformation digitale",
                "transformation numerique industrielle",
                "digitalisation industrielle",
                "industrie 4.0",
                "industrie 4 0",
            ],
        },
    }
    asks_coordinator = any(marker in q for marker in ["coordinateur", "coordinator", "responsable", "chef", "pilote", "supervise", "dirige"])
    asks_definition = any(marker in q for marker in ["quoi", "signifie", "veut dire", "correspond", "definition", "c est quoi", "c koi", "concerne"])
    asks_infrastructure = any(marker in q for marker in ["infrastructure", "laboratoire", "equipement", "plateforme"])
    for code, facts in track_facts.items():
        mentions_track = code in q or any(alias in q for alias in facts["aliases"])
        if not mentions_track:
            continue
        if asks_coordinator:
            return facts["coordinator"]
        if asks_email and "Contact indique :" in facts["coordinator"]:
            return facts["coordinator"].split("Contact indique :", 1)[1].strip()
        if asks_contact and "Contact indique :" in facts["coordinator"]:
            return facts["coordinator"]
        if asks_infrastructure:
            return facts["infrastructure"]
        if asks_definition:
            return f"{code.upper()} signifie {facts['name']}. {facts['definition']}"

    if (
        ("intelligence artificielle" in q and ("cyber" in q or "cybersecurite" in q))
        or ("iacs" in q and any(marker in q for marker in ["signifie", "concerne", "correspond", "definition", "c est quoi"]))
    ) and not asks_coordinator:
        return (
            "La filiere concernee est IACS (Intelligence Artificielle et Cybersecurite) : "
            "elle forme des ingenieurs capables de concevoir des systemes d'IA et de securiser les infrastructures numeriques."
        )

    asks_tracks_list = any(marker in q for marker in ["quelles", "quels", "liste", "citer", "cite", "combien", "dispo", "disponible"])
    asks_program_details = any(
        marker in q
        for marker in [
            "module",
            "modules",
            "cours",
            "programme",
            "semestre",
            "s1",
            "s2",
            "s3",
            "s4",
            "s5",
            "s6",
            "blockchain",
        ]
    )
    if asks_tracks_list and not asks_program_details and any(marker in q for marker in ["filiere", "filieres", "filier", "formation", "specialite", "cycle ingenieur", "nsa", "ensa"]):
        return (
            "Les filieres du cycle ingenieur sont : G2ER (Genie Electrique et Energies Renouvelables), "
            "IAA (Industries Agroalimentaires), IACS (Intelligence Artificielle et Cybersecurite), "
            "TDI (Transformation Digitale Industrielle)."
        )

    if any(marker in q for marker in ["usms", "universite", "rattachee", "fait partie", "affiliee"]):
        return "L'ENSA Beni Mellal fait partie de l'Universite Sultan Moulay Slimane."

    return None


def _is_explicit_full_timetable_request(question: str) -> bool:
    q = _normalize_text(question)
    if any(_normalize_text(marker) in q for marker in FULL_TIMETABLE_MARKERS):
        return True

    tokens = _tokenize(question)
    asks_all = _has_approx_token(tokens, {"tout", "all", "entier", "complete", "complet", "full"}, min_hits=1)
    timetable_context = _has_edt_like_signals(question)
    return asks_all and timetable_context


def _is_general_timetable_request(question: str) -> bool:
    q = _normalize_text(question)
    general_markers = [
        "emploi du temps",
        "emploi de temps",
        "edt",
        "planning",
        "semaine",
        "horaire",
        "timetable",
        "schedule",
    ]
    if any(_normalize_text(marker) in q for marker in general_markers) or _has_timetable_phrase(question):
        return True

    tokens = _tokenize(question)
    return _has_approx_token(tokens, GENERAL_TIMETABLE_TOKENS, min_hits=2)


def _extract_day_indexes(question: str) -> set[int]:
    q = _normalize_text(question)
    days: set[int] = set()
    for token, day_idx in DAY_INDEX_BY_TOKEN.items():
        if token in q:
            days.add(day_idx)
    return days


def _extract_hour_filters(question: str) -> set[int]:
    q = _normalize_text(question)
    matches = re.findall(r"\b([01]?\d|2[0-3])\s*(?:h|:)\s*([0-5]?\d)?\b", q)
    hours: set[int] = set()
    for hour, _ in matches:
        try:
            hours.add(int(hour))
        except ValueError:
            continue
    return hours


def _extract_focus_terms(question: str) -> set[str]:
    q = _normalize_text(question)
    terms: set[str] = set()

    patterns = [
        r"(?:cours de|matiere|module|prof(?:esseur)?|enseignant)\s+([a-z0-9\-\s]{3,})",
        r"(?:avec|par)\s+([a-z0-9\-\s]{3,})",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, q):
            for token in match.split():
                tok = token.strip()
                if len(tok) >= 4 and tok not in FOCUS_STOPWORDS:
                    terms.add(tok)

    return terms


def _slot_hour(slot: dict, key: str) -> int | None:
    value = str(slot.get(key) or "")
    match = re.match(r"\s*([01]?\d|2[0-3])", value)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _slot_matches_focus_terms(slot: dict, terms: set[str]) -> bool:
    if not terms:
        return True
    haystack = _normalize_text(
        " ".join([
            str(slot.get("subject") or ""),
            str(slot.get("professor") or ""),
            str(slot.get("room") or ""),
            str(slot.get("type") or ""),
        ])
    )
    return any(term in haystack for term in terms)


def build_timetable_view_for_question(question: str, timetable: dict | None) -> dict | None:
    """
    Retourne la vue EDT a exposer dans les metadata:
    - full si demande explicite
    - subset si la question cible un jour/heure/module/prof
    - None si question EDT generale non explicite
    """
    if not timetable:
        return None

    if _is_explicit_full_timetable_request(question):
        return timetable

    slots = list(timetable.get("slots") or [])
    if not slots:
        return None

    day_filters = _extract_day_indexes(question)
    hour_filters = _extract_hour_filters(question)
    focus_terms = _extract_focus_terms(question)

    # Question precise => pas de visuel EDT.
    if day_filters or hour_filters or focus_terms:
        return None

    # Question globale/generale => afficher l'EDT complet.
    if _is_general_timetable_request(question):
        return timetable

    return None


def _extract_semester_from_label(label: str | None) -> str:
    normalized = _normalize_text(label)
    match = re.search(r"\bs(\d+)\b", normalized)
    return f"S{match.group(1)}" if match else ""


def _emploi_json_from_structured_timetable(tt_structured: dict | None) -> dict:
    if not tt_structured:
        return {}

    day_names = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]
    emploi_json = {day: [] for day in day_names}

    for slot in tt_structured.get("slots", []):
        day_idx = slot.get("day_of_week")
        if not isinstance(day_idx, int) or day_idx < 0 or day_idx >= len(day_names):
            continue
        emploi_json[day_names[day_idx]].append({
            "heure": f"{slot.get('start_time', '')} --> {slot.get('end_time', '')}",
            "contenu": slot.get("subject", ""),
            "professeur": slot.get("professor", ""),
            "salle": slot.get("room", ""),
            "seance": slot.get("type", "Cours"),
        })

    return emploi_json


# ─────────────────────────────────────────────────
# REGISTRE DES CLASSES
# ─────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _scan_available_classes() -> dict:
    """
    Lit les emplois du temps actifs en base et retourne :
    { "IACS Y1 S4": {"canonical_label": "IACS_Y1_S4", "semester": "S4", "academic_year": "2025-2026"}, ... }
    """
    from backend.services import db_service

    classes = {}
    for timetable in db_service.list_active_timetables():
        canonical_label = timetable["class_label"]
        raw_label = canonical_label.replace("_", " ")
        classes[raw_label] = {
            "canonical_label": canonical_label,
            "semester": timetable.get("semester"),
            "academic_year": timetable.get("academic_year"),
        }

    return classes


def get_available_classes(force_refresh: bool = False) -> dict:
    """
    Retourne les classes disponibles avec cache mémoire pour éviter
    un scan disque à chaque requête.
    """
    if force_refresh:
        _scan_available_classes.cache_clear()
    return _scan_available_classes()


def detect_class_in_question(question: str, available_classes: dict):
    """
    Détecte la classe mentionnée dans la question.
    """
    q = _normalize_class_reference_text(question)
    if not q:
        return None

    scored: list[tuple[int, str]] = []
    for label in available_classes:
        label_tokens = _label_tokens(label)
        aliases = _label_aliases(label)

        exact_alias = max((len(alias.split()) for alias in aliases if alias and alias in q), default=0)
        all_tokens_present = all(token in q.split() for token in label_tokens)
        matched_tokens = len([token for token in label_tokens if token in q.split()])

        score = 0
        if all_tokens_present:
            score = 100 + len(label_tokens)
        elif exact_alias:
            score = 70 + exact_alias
        elif matched_tokens:
            score = 20 + matched_tokens

        if score:
            scored.append((score, label))

    if not scored:
        return None

    scored.sort(key=lambda item: item[0], reverse=True)
    top_score = scored[0][0]
    top_labels = [label for score, label in scored if score == top_score]
    return top_labels[0] if len(top_labels) == 1 else None


def _label_tokens(value: str) -> list[str]:
    normalized = _normalize_class_reference_text(value)
    return [t for t in normalized.split() if t]


def _label_aliases(value: str) -> set[str]:
    tokens = _label_tokens(value)
    if not tokens:
        return set()

    aliases = {" ".join(tokens)}
    track = tokens[0]
    aliases.add(track)

    year_tokens = [t for t in tokens if re.fullmatch(r"y?\d+", t)]
    semester_tokens = [t for t in tokens if re.fullmatch(r"s\d+", t)]

    for year in year_tokens:
        aliases.add(f"{track} {year}")
        aliases.add(f"{track} {year.removeprefix('y')}")
        aliases.add(f"{track} {year.removeprefix('y')}a")
    for semester in semester_tokens:
        aliases.add(f"{track} {semester}")
    for year in year_tokens:
        for semester in semester_tokens:
            aliases.add(f"{track} {year} {semester}")
            aliases.add(f"{track} {year.removeprefix('y')} {semester}")
            aliases.add(f"{track} {year.removeprefix('y')}a {semester}")

    return {alias.strip() for alias in aliases if alias.strip()}


def resolve_class_label(input_label: str | None, available_classes: dict) -> tuple[str | None, list[str]]:
    """
    Resolve a user-provided class label against available classes.

    Returns:
      - (resolved_label, []) when resolved uniquely
      - (None, candidates) when ambiguous
      - (None, []) when no match
    """
    if not input_label:
        return None, []

    normalized_input = _normalize_class_reference_text(input_label)
    wanted_tokens = _label_tokens(input_label)
    if not wanted_tokens:
        return None, []

    canonical_by_label = {
        " ".join(_label_tokens(label)): label
        for label in available_classes
    }
    wanted_key = " ".join(wanted_tokens)
    if wanted_key in canonical_by_label:
        return canonical_by_label[wanted_key], []

    alias_hits = [label for label in available_classes if normalized_input in _label_aliases(label)]
    if len(alias_hits) == 1:
        return alias_hits[0], []
    if len(alias_hits) > 1:
        return None, alias_hits

    candidates = []
    for label in available_classes:
        label_tokens = _label_tokens(label)
        alias_token_sets = [set(alias.split()) for alias in _label_aliases(label)]
        if all(token in label_tokens for token in wanted_tokens) or any(
            all(token in alias_tokens for token in wanted_tokens) for alias_tokens in alias_token_sets
        ):
            candidates.append(label)

    if len(candidates) == 1:
        return candidates[0], []
    if len(candidates) > 1:
        return None, candidates

    wanted_track = next((token for token in wanted_tokens if token in TRACK_CODES), None)
    wanted_semester = next((token for token in wanted_tokens if re.fullmatch(r"s\d+", token)), None)
    if wanted_track and wanted_semester:
        semester_matches = []
        for label in available_classes:
            label_tokens = _label_tokens(label)
            if label_tokens and label_tokens[0] == wanted_track and wanted_semester in label_tokens:
                semester_matches.append(label)
        if len(semester_matches) == 1:
            return semester_matches[0], []
        if len(semester_matches) > 1:
            return None, semester_matches

    if wanted_track:
        track_matches = []
        for label in available_classes:
            label_tokens = _label_tokens(label)
            if label_tokens and label_tokens[0] == wanted_track:
                track_matches.append(label)
        if len(track_matches) == 1:
            return track_matches[0], []

    # Fallback: filiere-only match (first token) when unique.
    if len(wanted_tokens) == 1:
        prefix = wanted_tokens[0]
        prefix_matches = []
        for label in available_classes:
            label_tokens = _label_tokens(label)
            if label_tokens and label_tokens[0] == prefix:
                prefix_matches.append(label)
        if len(prefix_matches) == 1:
            return prefix_matches[0], []
        if len(prefix_matches) > 1:
            return None, prefix_matches

    return None, []


def _classes_for_track(track_code: str | None, available_classes: dict) -> list[str]:
    if not track_code or not available_classes:
        return []

    track = track_code.lower()
    matches = []
    for label in available_classes:
        label_tokens = _label_tokens(label)
        if label_tokens and label_tokens[0] == track:
            matches.append(label)
    return matches


def _history_awaits_timetable_class(history: list[dict] | None) -> bool:
    if not history:
        return False

    selection_markers = [
        "quelle est ta classe",
        "choisis une classe",
        "quel semestre",
        "quelle semestre",
        "plusieurs emplois du temps",
        "plusieurs classes",
        "besoin de connaitre ta filiere",
        "besoin de connaitre ta classe",
        "besoin de precision",
    ]

    for item in reversed(history[-6:]):
        content = str(item.get("content") or "")
        q = _normalize_text(content)
        if not q:
            continue
        if any(marker in q for marker in selection_markers):
            return True
        if _has_timetable_phrase(content) or any(marker in q for marker in ["planning", "horaire", "edt"]):
            return True
    return False


def _recent_timetable_track_from_history(history: list[dict] | None) -> str | None:
    if not _history_awaits_timetable_class(history):
        return None

    for item in reversed((history or [])[-8:]):
        track = _extract_track_code(str(item.get("content") or ""))
        if track:
            return track
    return None


def _history_has_recent_timetable_context(history: list[dict] | None) -> bool:
    if not history:
        return False

    for item in reversed((history or [])[-8:]):
        content = str(item.get("content") or "")
        q = _normalize_text(content)
        if not q:
            continue
        if _is_edt_question(content):
            return True
        if any(marker in q for marker in ["emploi du temps", "planning", "horaire", "seance", "cours du", "cours de"]):
            return True
        if re.search(r"\b\d{1,2}:\d{2}\b", q) and any(day in q for day in DAY_INDEX_BY_TOKEN):
            return True
    return False


def _extract_day_token(text: str | None) -> str | None:
    q = _normalize_text(text)
    if not q:
        return None
    for day in DAY_INDEX_BY_TOKEN:
        if re.search(rf"\b{re.escape(day)}\b", q):
            return day
    for relative in ["aujourd", "demain", "hier", "today", "tomorrow"]:
        if re.search(rf"\b{relative}\b", q):
            return relative
    return None


def _has_period_marker(text: str | None) -> bool:
    q = _normalize_text(text)
    return bool(q and any(marker in q for marker in ["matin", "morning", "apres midi", "apres-midi", "aprem", "afternoon"]))


def _recent_day_from_history(history: list[dict] | None) -> str | None:
    for item in reversed((history or [])[-8:]):
        day = _extract_day_token(str(item.get("content") or ""))
        if day:
            return day
    return None


def _recent_timetable_intent_from_history(history: list[dict] | None) -> str | None:
    for item in reversed((history or [])[-8:]):
        if item.get("role") != "user":
            continue
        q = _normalize_text(str(item.get("content") or ""))
        if not q:
            continue
        if any(marker in q for marker in ["qui enseigne", "qui donne", "qui assure", "quel prof", "quelle prof", "who teaches", "teacher"]):
            return "teacher_for_module"
        if _extract_day_token(q) or _has_period_marker(q):
            return "day_lookup"
        if _has_timetable_phrase(q) or any(marker in q for marker in ["planning", "horaire", "edt"]):
            return "timetable"
    return None


def _clean_followup_fragment(question: str) -> str:
    q = _normalize_class_reference_text(question)
    q = re.sub(r"^(?:et|and|also|aussi|sinon|puis)\b", " ", q)
    q = re.sub(r"\b(?:stp|svp|please|alors|donc)\b", " ", q)
    q = re.sub(r"[?!.]+", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q


def _looks_like_timetable_followup(question: str, class_label: str | None, history: list[dict] | None) -> bool:
    if not question:
        return False
    if _is_edt_question(question):
        return False
    if not (class_label or _history_has_recent_timetable_context(history)):
        return False

    q = _normalize_text(question)
    if not q:
        return False

    has_short_followup_prefix = bool(re.match(r"^(?:et|and|aussi|also|puis|sinon)\b", q))
    has_day_or_period = bool(_extract_day_token(q) or _has_period_marker(q))
    if has_day_or_period:
        return True

    recent_intent = _recent_timetable_intent_from_history(history)
    if recent_intent == "timetable" and has_short_followup_prefix and _extract_track_code(q):
        return True

    if recent_intent == "teacher_for_module":
        fragment = _clean_followup_fragment(question)
        tokens = [token for token in fragment.split() if len(token) > 2 and token not in TRACK_CODES and not re.fullmatch(r"s[1-6]", token)]
        return bool(tokens) and (has_short_followup_prefix or len(tokens) <= 4)

    return False


def _contextualize_timetable_followup_question(question: str, class_label: str | None, history: list[dict] | None) -> str:
    if not _looks_like_timetable_followup(question, class_label, history):
        return question

    intent = _recent_timetable_intent_from_history(history)
    fragment = _clean_followup_fragment(question)
    if not fragment:
        return question

    track = _extract_track_code(fragment)
    if intent == "timetable" and track:
        return f"planning {track.upper()}"

    if intent == "teacher_for_module" and not (_extract_day_token(fragment) or _has_period_marker(fragment)):
        return f"qui enseigne {fragment} ?"

    day = _extract_day_token(fragment)
    if _has_period_marker(fragment) and not day:
        recent_day = _recent_day_from_history(history)
        if recent_day:
            fragment = f"{recent_day} {fragment}"

    return f"quels cours {fragment} ?"


def _contextualize_faq_followup_question(question: str, history: list[dict] | None) -> str:
    if not question or not history:
        return question

    q = _normalize_text(question)
    if not q or not re.match(r"^(?:et|and|aussi|also|son|sa|ses|leur|his|her|their)\b", q):
        return question

    asks_contact = any(marker in q for marker in ["email", "mail", "e mail", "contact", "adresse mail", "courriel"])
    recent_text = " ".join(str(item.get("content") or "") for item in (history or [])[-6:])
    recent_norm = _normalize_text(recent_text)
    track = _extract_track_code(recent_text)

    if asks_contact and ("coordinateur" in recent_norm or "coordonnateur" in recent_norm or "coordinator" in recent_norm):
        if track:
            return f"email du coordinateur de la filiere {track.upper()}"
        return "email du coordinateur de la filiere"

    if asks_contact and ("directeur" in recent_norm or "director" in recent_norm or "belaid" in recent_norm or "bouilkhilane" in recent_norm):
        return "email du directeur de l'ENSA Beni Mellal"

    intent = _recent_faq_intent_from_history(history)
    subject = _followup_subject(question)
    if not intent or not subject:
        return question

    if intent == "coordinator":
        if asks_contact:
            return f"email du coordinateur de la filiere {subject}"
        return f"qui est le coordinateur de la filiere {subject}"
    if intent == "definition":
        return f"que signifie {subject}"
    if intent == "duration":
        return f"combien dure {subject}"
    if intent == "admission":
        return f"comment acceder a {subject}"
    if intent == "program":
        return f"quels sont les modules de {subject}"
    if intent == "jobs":
        return f"quels sont les debouches de {subject}"
    if intent == "infrastructure":
        return f"quelles infrastructures pour {subject}"
    if intent == "stages":
        return f"quels stages en {subject}"

    return question


def _recent_faq_intent_from_history(history: list[dict] | None) -> str | None:
    for item in reversed((history or [])[-8:]):
        if item.get("role") != "user":
            continue
        q = _normalize_text(str(item.get("content") or ""))
        if not q:
            continue
        if any(marker in q for marker in ["coordinateur", "coordonnateur", "coordinator", "responsable", "chef de filiere", "chef"]):
            return "coordinator"
        if any(marker in q for marker in ["signifie", "veut dire", "definition", "c est quoi", "cest quoi", "que signifie"]):
            return "definition"
        if any(marker in q for marker in ["duree", "dure", "combien de temps", "combien d annee", "combien d'annee"]):
            return "duration"
        if any(marker in q for marker in ["rejoindre", "integrer", "admission", "acceder", "acces", "entrer", "candidater"]):
            return "admission"
        if any(marker in q for marker in ["programme", "module", "modules", "matiere", "matieres", "cours", "etudie"]):
            return "program"
        if any(marker in q for marker in ["debouche", "debouches", "metier", "metiers", "job", "jobs", "carriere"]):
            return "jobs"
        if any(marker in q for marker in ["infrastructure", "laboratoire", "laboratoires", "equipement", "equipements"]):
            return "infrastructure"
        if any(marker in q for marker in ["stage", "stages", "pfe", "soutenance"]):
            return "stages"
    return None


def _followup_subject(question: str) -> str | None:
    track = _extract_track_code(question)
    if track:
        return track.upper()

    fragment = _clean_followup_fragment(question)
    fragment = re.sub(r"^(?:pour|sur|concernant|a propos de)\b", " ", fragment)
    fragment = re.sub(r"\s+", " ", fragment).strip()
    if not fragment or fragment in {"son", "sa", "ses", "leur"}:
        return None
    if len(fragment.split()) > 6:
        return None
    return fragment


def _is_short_class_reference(text: str | None) -> bool:
    normalized = _normalize_class_reference_text(text)
    if not normalized:
        return False

    tokens = normalized.split()
    allowed = TRACK_CODES | {"s1", "s2", "s3", "s4", "s5", "s6"}
    return len(tokens) <= 4 and all(
        token in allowed or re.fullmatch(r"(?:20\d{2}|20\d{2}20\d{2}|y?\d+)", token)
        for token in tokens
    )


def _resolve_contextual_class_followup(
    question: str,
    class_label: str | None,
    available_classes: dict,
    history: list[dict] | None = None,
) -> str | None:
    if not question or not available_classes:
        return None

    semester = _extract_semester_token(question)
    track = _extract_track_code(question)
    if track and semester:
        resolved, candidates = resolve_class_label(f"{track} {semester}", available_classes)
        if resolved:
            return resolved
        if len(candidates) == 1:
            return candidates[0]

    if not semester or not _is_short_class_reference(question):
        return None

    history_track = _recent_timetable_track_from_history(history)
    if history_track:
        resolved, candidates = resolve_class_label(f"{history_track} {semester}", available_classes)
        if resolved:
            return resolved
        if len(candidates) == 1:
            return candidates[0]

    profile_track = _track_code_from_class_label(class_label)
    if profile_track:
        resolved, candidates = resolve_class_label(f"{profile_track.lower()} {semester}", available_classes)
        if resolved:
            return resolved
        if len(candidates) == 1:
            return candidates[0]

    resolved, candidates = resolve_class_label(semester, available_classes)
    if resolved:
        return resolved
    if len(candidates) == 1:
        return candidates[0]
    return None


def _ambiguous_track_timetable_candidates(
    question: str,
    available_classes: dict,
    history: list[dict] | None = None,
) -> list[str]:
    if not question or not available_classes or _extract_semester_token(question):
        return []

    tracks = _extract_track_codes(question)
    if not tracks:
        return []

    if not (_is_edt_question(question) or _history_awaits_timetable_class(history)):
        return []

    for track in tracks:
        candidates = _classes_for_track(track, available_classes)
        if len(candidates) > 1:
            return candidates
    return []


def _semester_selection_text(candidates: list[str]) -> str:
    track = _extract_track_code(" ".join(candidates))
    subject = track.upper() if track else "cette filiere"
    return (
        f"J'ai trouve plusieurs emplois du temps pour {subject}. "
        "Quel semestre veux-tu consulter ?\n\n"
        + "\n".join(f"* {candidate}" for candidate in candidates)
    )


def _is_weak(response: str) -> bool:
    if not response or len(response.strip()) < 20:
        return True
    return any(m in response.lower() for m in WEAK_MARKERS)


# ─────────────────────────────────────────────────
# SEMANTIC ROUTING (Intent Detection)
# ─────────────────────────────────────────────────

INTENT_PROTOTYPES = {
    "GET_TIMETABLE": [
        "What is my schedule?", "show me the timetable", "when is my next class",
        "quel est mon emploi du temps", "planning de la semaine", "horaire des cours",
        "donne moi l'edt", "calendrier des cours", "ma classe",
        "جدول الحصص", "متى يبدأ الدرس", "برنامج الدراسية"
    ]
}

def is_timetable_intent_semantic(question: str, threshold: float = 0.75) -> bool:
    """
    Utilise les embeddings pour détecter si la question concerne l'emploi du temps.
    """
    from backend.services.rag_service import get_embeddings
    import numpy as np

    model = get_embeddings()
    normalized_question = _normalize_text(question)
    q_vec = model.encode([normalized_question or question])[0]
    
    # Simuler un check de similarité cosinus avec les prototypes
    # En production, on pourrait stocker ces vecteurs pour aller plus vite.
    for intent, samples in INTENT_PROTOTYPES.items():
        sample_vecs = model.encode([_normalize_text(sample) or sample for sample in samples])
        for s_vec in sample_vecs:
            denom = np.linalg.norm(q_vec) * np.linalg.norm(s_vec)
            if denom == 0:
                continue
            sim = np.dot(q_vec, s_vec) / denom
            if sim >= threshold:
                return True
    return False


def _is_edt_question(question: str) -> bool:
    q = _normalize_class_reference_text(question)
    if any(_normalize_text(marker) in q for marker in NON_EDT_MARKERS):
        return False

    if _has_timetable_phrase(question):
        return True

    if _is_program_catalog_question(question):
        return False

    if _has_edt_like_signals(question):
        return True

    # Guardrail: location/campus questions should not be routed to timetable flow.
    location_markers = [
        "ou se situe", "où se situe", "where is", "location", "adresse", "localisation",
        "وين", "اين", "أين", "فين", "العنوان",
    ]
    campus_markers = ["ensa", "ensabm", "bm", "beni mellal", "mghila", "بني", "مليل", "مغيلا"]
    if any(_normalize_text(marker) in q for marker in location_markers):
        has_explicit_edt = any(_normalize_text(marker) in q for marker in EDT_MARKERS)
        if not has_explicit_edt or any(_normalize_text(marker) in q for marker in campus_markers):
            return False

    # 1. Check direct patterns (Fast)
    direct_patterns = [
        "emploi du temps", "edt", "planning", "cours de", "cours du",
        "qui donne", "qui assure",
        "quel cours", "quel prof", "qui enseigne", "professeur de", "matiere de", "matière de",
        "calendrier des examens", "planning des examens",
        "timetable", "time table", "schedule", "class schedule", "my classes",
        "next class", "prochain cours", "mes cours", "cours aujourd", "cours demain",
    ]
    if any(_normalize_text(p) in q for p in direct_patterns):
        return True

    tokens = _tokenize(question)
    asks_to_show = _has_approx_token(tokens, set(TIMETABLE_VERBS), min_hits=1)
    has_schedule_signal = any(_normalize_text(marker) in q for marker in EDT_MARKERS) or any(marker in q for marker in TEMPORAL_MARKERS)
    if asks_to_show and has_schedule_signal:
        return True

    if any(day in q for day in ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]):
        if any(word in q for word in ["cours", "class", "classe", "module", "matiere", "subject", "prof"]):
            return True
        if any(marker in q for marker in ["on a", "on fait", "j ai", "jai", "notre", "quoi", "qu est ce qu on a", "what do i have"]):
            return True

    # 2. Semantic Fallback (Robust / Multilingual)
    try:
        return is_timetable_intent_semantic(question)
    except Exception as e:
        logger.error(f"Semantic routing error: {e}")
        return any(_normalize_text(marker) in q for marker in EDT_MARKERS)


def _resolve_class_only_turn(question: str, available: dict) -> str | None:
    """Detects when user sends only a class label as a follow-up answer."""
    if not question or not available:
        return None

    short_tokens = _tokenize(question)
    class_label_tokens = TRACK_CODES | {"s1", "s2", "s3", "s4", "s5", "s6"}
    if len(short_tokens) <= 3 and all(
        token in class_label_tokens or re.fullmatch(r"(?:20\d{2}|20\d{2}20\d{2}|y?\d+)", token)
        for token in short_tokens
    ):
        resolved, candidates = resolve_class_label(question, available)
        if resolved:
            return resolved
        if len(candidates) == 1:
            return candidates[0]

    if _is_edt_question(question) or _is_campus_info_question(question):
        return None

    resolved, candidates = resolve_class_label(question, available)
    if resolved:
        return resolved

    if len(candidates) == 1:
        return candidates[0]

    return None


def _is_lookup_guidance_question(question: str) -> bool:
    if _is_explicit_full_timetable_request(question):
        return False

    q = _normalize_text(question)
    tokens = set(_tokenize(q))
    asks_where = bool(tokens.intersection({"ou", "comment", "consulter", "trouver"})) or "espace etudiant" in q
    asks_schedule_or_exam = (
        any(x in q for x in ["emploi du temps", "edt", "calendrier", "examen", "partiel", "rattrapage", "planning", "horaire"])
        or bool(tokens.intersection({"planning", "horaire"}))
    )
    return asks_where and asks_schedule_or_exam


def _is_campus_info_question(question: str) -> bool:
    q = _normalize_text(question)
    if not q:
        return False

    # Prioritize timetable flow when the query carries EDT-like intent.
    if _has_edt_like_signals(question):
        return False

    if any(_normalize_text(marker) in q for marker in FAQ_MARKERS):
        return True

    arabic_cues = ["شكون", "شنو", "فين", "واش", "كاش", "شنو هو", "علاش", "شحال"]
    if any(cue in q for cue in arabic_cues):
        return True

    generic_school_markers = [
        "full name", "established", "founded", "created", "affiliated", "network",
        "الاسم الكامل", "متى تم", "تم انشاء", "انشئت", "تابعة", "مرتبطة",
        "المدرسة", "المؤسسة", "الجامعة",
    ]
    if any(_normalize_text(marker) in q for marker in generic_school_markers):
        return True

    return False


# ─────────────────────────────────────────────────
# ROUTER API — version stateless pour FastAPI
# ─────────────────────────────────────────────────

def _message_language(question: str, preferred_language: str = "fr") -> str:
    if re.search(r"[\u0600-\u06FF]", question or ""):
        return "ar"
    try:
        from backend.services.groq_service import _detect_question_language

        detected = _detect_question_language(question, language_hint=preferred_language)
        if detected in {"fr", "en", "ar"}:
            return detected
    except Exception as exc:
        logger.debug(f"Question language detection failed: {exc}")
    return preferred_language if preferred_language in {"fr", "en", "ar"} else "fr"


def _style_answer_for_question(
    answer: str,
    question: str,
    user_state: str | None = None,
    language: str | None = None,
) -> str:
    if not answer:
        return answer
    q = _normalize_text(question)
    if (
        any(marker in q for marker in ["traduis", "traduire", "translate"])
        and any(marker in q for marker in ["anglais", "english"])
    ):
        return answer
    if (
        any(marker in q for marker in ["redige", "ecris", "prepare", "draft", "write"])
        and any(marker in q for marker in ["email", "e mail", "mail"])
        and "convention" in q
        and "stage" in q
    ):
        return answer
    if (
        any(marker in q for marker in ["modifie", "reecris", "reformule", "change"])
        and any(marker in q for marker in ["email precedent", "e mail precedent", "message precedent", "l email precedent"])
        and any(marker in q for marker in ["agressif", "agressive", "familier", "non professionnel", "impoli", "insultant"])
    ):
        return answer
    try:
        from backend.services.groq_service import _finalize_answer_style

        return _finalize_answer_style(answer, question, user_state=user_state, language_hint=language)
    except Exception as exc:
        logger.debug(f"Answer language styling failed: {exc}")
        return answer


def _recent_assistant_answer(history: list[dict] | None) -> str:
    for item in reversed(history or []):
        if item.get("role") == "assistant":
            return str(item.get("content") or "")
    return ""


def _recent_history_text(history: list[dict] | None, limit: int = 8) -> str:
    return " ".join(str(item.get("content") or "") for item in (history or [])[-limit:])


def _track_list_answer() -> str:
    return (
        "Les quatre filieres d'ingenierie enseignees a l'ENSA Beni Mellal sont : "
        "G2ER (Genie Electrique et Energies Renouvelables), "
        "IAA (Industries Agroalimentaires), "
        "IACS (Intelligence Artificielle et Cybersecurite) et "
        "TDI (Transformation Digitale Industrielle)."
    )


def _iacs_security_modules_answer() -> str:
    return (
        "Pour IACS, les modules directement lies a la securite sont notamment : "
        "Cryptographie en S2; Cybersecurite et Cyberdefense, Gestion des Identites et Acces, "
        "et IoT et Edge Computing Security en S3; Administration Securisee et Forensics, "
        "DevOps / DevSecOps, et Ethique et Droit Numerique en S4."
    )


def _iacs_security_modules_summary() -> str:
    return (
        "En trois points :\n"
        "1. Cryptographie pose les bases de la protection des donnees, du chiffrement et de l'authentification.\n"
        "2. Forensics et administration securisee couvrent l'analyse d'incidents, les traces numeriques et la securisation des systemes.\n"
        "3. DevSecOps, cyberdefense, IAM et IoT security relient la securite aux infrastructures modernes, au cloud et aux pipelines logiciels."
    )


def _formal_internship_convention_email() -> str:
    return (
        "A : ensabm.contact@usms.ma\n"
        "Objet : Demande de convention de stage\n\n"
        "Madame, Monsieur,\n\n"
        "Je me permets de vous contacter afin de demander les informations et les demarches necessaires "
        "pour l'obtention d'une convention de stage.\n\n"
        "Je suis etudiant a l'ENSA Beni Mellal et je souhaite constituer mon dossier de stage dans les meilleurs delais. "
        "Pourriez-vous, s'il vous plait, m'indiquer les pieces a fournir, la procedure a suivre et le service concerne ?\n\n"
        "Je vous remercie par avance pour votre aide et reste disponible pour toute information complementaire.\n\n"
        "Cordialement,\n"
        "[Nom et prenom]\n"
        "[Filiere / semestre]\n"
        "[Telephone]"
    )


def _respectful_email_tone_refusal() -> str:
    return (
        "Je ne vais pas transformer un e-mail administratif en message agressif ou non professionnel. "
        "Voici une version plus directe, mais correcte :\n\n"
        "A : ensabm.contact@usms.ma\n"
        "Objet : Relance - demande de convention de stage\n\n"
        "Madame, Monsieur,\n\n"
        "Je reviens vers vous au sujet de ma demande de convention de stage. "
        "Cette demarche est importante pour finaliser mon dossier dans les delais, "
        "et je vous serais reconnaissant de bien vouloir m'indiquer la procedure a suivre ou l'etat d'avancement de ma demande.\n\n"
        "Cordialement,\n"
        "[Nom et prenom]"
    )


def _stage_pfe_duration_answer() -> str:
    return (
        "Pour IACS, le stage d'assistant ingenieur est prevu apres S4 et dure 8 semaines. "
        "Le PFE correspond au semestre S6 et dure 4 a 6 mois. "
        "La difference principale est donc que le stage S4 est intermediaire et plus court, "
        "tandis que le PFE est le projet final du cycle ingenieur, avec memoire/soutenance et une duree plus longue."
    )


def _iaa_tdi_iacs_jobs_comparison_answer() -> str:
    return (
        "IAA, TDI et IACS menent vers des familles de metiers differentes :\n"
        "- IAA vise surtout l'agroalimentaire : ingenieur qualite, production/procedes, R&D, laboratoire, audit et certification.\n"
        "- TDI vise la transformation digitale industrielle : automatisation, supervision, IIoT, cloud industriel, data industrielle et Industrie 4.0.\n"
        "- IACS vise le numerique avance : IA, data science, machine learning, cybersecurite, SOC, pentest, cloud, DevSecOps, forensics et RSSI.\n"
        "En bref, IAA est plus orientee industrie agroalimentaire/qualite, TDI industrie 4.0, et IACS IA + cybersecurite."
    )


def _multi_track_definition_answer(q: str) -> str | None:
    asks_definition = any(marker in q for marker in ["signifie", "veut dire", "acronyme", "acronymes", "definition", "quoi"])
    if not asks_definition:
        return None
    has_iaa = re.search(r"\biaa\b", q) is not None
    has_tdi = re.search(r"\btdi\b", q) is not None
    if has_iaa and has_tdi:
        return (
            "IAA signifie Industries Agroalimentaires. "
            "TDI signifie Transformation Digitale Industrielle."
        )
    return None


def _official_priority_answer(question: str, history: list[dict] | None = None) -> str | None:
    q = _normalize_text(question)
    if not q:
        return None

    recent_text = _normalize_text(_recent_history_text(history))

    if any(marker in q for marker in ["changer ma classe", "changer mon semestre", "changer de classe", "changer de semestre", "modifier ma classe", "modifier mon semestre", "mettre a jour ma classe", "mettre a jour mon semestre"]):
        return (
            "Pour changer ta classe ou ton semestre dans l'application, va dans Profil > Demande academique, "
            "choisis la nouvelle classe/semestre puis envoie la demande. L'administrateur doit la valider "
            "avant que le chatbot utilise ce nouveau contexte."
        )

    if (
        any(marker in q for marker in ["convention de stage", "document de stage", "documents de stage", "stage", "pfe"])
        and any(marker in q for marker in ["qui contacter", "qui dois je contacter", "contacter", "contacte", "deposer", "deposer", "procedure", "demarche"])
    ):
        return (
            "Pour une convention ou des documents de stage/PFE, contacte d'abord le coordinateur de ta filiere, "
            "ton encadrant ou le service administratif/scolarite concerne. Suis aussi les avis officiels de "
            "l'ENSA BM et les consignes de ta filiere."
        )

    if (
        any(marker in q for marker in ["ou consulter", "ou trouver", "comment consulter", "comment trouver", "where can i find"])
        and any(marker in q for marker in ["emploi du temps", "edt", "planning", "horaire", "timetable", "schedule"])
    ):
        return (
            "Tu peux consulter ton emploi du temps via l'Espace Etudiant/ENT de l'ENSA Beni Mellal "
            "et les annonces officielles publiees par l'ecole. Dans ce chatbot, tu peux aussi demander "
            "directement le planning d'une filiere et d'un semestre, par exemple : planning IACS S4."
        )

    if (
        any(marker in q for marker in ["modifie", "reecris", "reformule", "change"])
        and any(marker in q for marker in ["email precedent", "e mail precedent", "message precedent", "l email precedent"])
        and any(marker in q for marker in ["agressif", "agressive", "familier", "non professionnel", "impoli", "insultant"])
    ):
        return _respectful_email_tone_refusal()

    if (
        any(marker in q for marker in ["redige", "ecris", "prepare", "draft", "write"])
        and any(marker in q for marker in ["email", "e mail", "mail"])
        and "convention" in q
        and "stage" in q
    ):
        return _formal_internship_convention_email()

    if (
        any(marker in q for marker in ["traduis", "traduire", "translate"])
        and any(marker in q for marker in ["anglais", "english"])
        and any(marker in q for marker in ["description", "ce que tu viens", "vient de", "precedent", "precedente"])
    ):
        last_answer = _recent_assistant_answer(history)
        last_norm = _normalize_text(last_answer)
        if "mostapha" in last_norm and "oulcaid" in last_norm and "g2er" in last_norm:
            return (
                "Mr. Mostapha OULCAID is listed as the coordinator of the G2ER track "
                "(Electrical Engineering and Renewable Energies) at ENSA Beni Mellal. "
                "Contact: m.oulcaid@usms.ma."
            )
        if "gouskir" in last_norm and "iacs" in last_norm:
            return (
                "Pr. Mohamed GOUSKIR is listed as the coordinator of the IACS track "
                "(Artificial Intelligence and Cybersecurity) at ENSA Beni Mellal. "
                "Contact: m.gouskir@usms.ma."
            )
        if "rokni" in last_norm and "iaa" in last_norm:
            return (
                "Mr. Yahya ROKNI is listed as the coordinator of the IAA track "
                "(Food Industries) at ENSA Beni Mellal. Contact: agroalimentaire.ensa@gmail.com."
            )
        if "ouanan" in last_norm and "tdi" in last_norm:
            return (
                "Mr. Hamid OUANAN is listed as the coordinator of the TDI track "
                "(Industrial Digital Transformation) at ENSA Beni Mellal. Contact: ham.ouanan@gmail.com."
            )

    if (
        any(marker in q for marker in ["resume", "resumer", "synthese", "summarize"])
        and any(marker in q for marker in ["ces modules", "ces cours", "ces matieres", "these modules"])
        and ("cryptographie" in recent_text or "forensics" in recent_text or "devsecops" in recent_text)
    ):
        return _iacs_security_modules_summary()

    if (
        any(marker in q for marker in ["quatre filieres", "4 filieres", "filieres d ingenierie", "filieres ingenieur", "filieres du cycle ingenieur"])
        or (
            any(marker in q for marker in ["quelles", "quels", "liste", "citer", "cite"])
            and any(marker in q for marker in ["filiere", "filieres", "formation", "specialite"])
            and any(marker in q for marker in ["ingenierie", "ingenieur", "ensa", "ensabm", "usms"])
            and not any(marker in q for marker in ["module", "modules", "cours", "planning", "emploi du temps", "edt", "semestre"])
        )
    ):
        return _track_list_answer()

    multi_definition = _multi_track_definition_answer(q)
    if multi_definition:
        return multi_definition

    if (
        "iacs" in q
        and any(marker in q for marker in ["module", "modules", "cours", "contenu"])
        and any(marker in q for marker in ["securite", "security", "cyber", "cryptographie", "forensics", "devsecops"])
    ):
        return _iacs_security_modules_answer()

    if (
        "stage" in q
        and any(marker in q for marker in ["pfe", "projet de fin d etudes", "projet de fin"])
        and any(marker in q for marker in ["difference", "differences", "compare", "comparer", "duree", "dure"])
    ):
        return _stage_pfe_duration_answer()

    compares_jobs = (
        any(marker in q for marker in ["compare", "comparer", "comparaison", "difference", "differences", "par rapport"])
        and any(marker in q for marker in ["debouche", "debouches", "metier", "metiers", "job", "jobs", "carriere"])
    )
    mentions_two_tracks = ("iaa" in q and "tdi" in q) or ("ces deux" in q and "iaa" in recent_text and "tdi" in recent_text)
    mentions_iacs = "iacs" in q or "iacs" in recent_text or "ma filiere" in q
    if compares_jobs and mentions_two_tracks and mentions_iacs:
        return _iaa_tdi_iacs_jobs_comparison_answer()

    return None


def _security_guard_answer(question: str) -> str | None:
    q = _normalize_text(question)
    if not q:
        return None

    injection_markers = [
        "ignore previous instructions",
        "ignore all previous instructions",
        "ignore prior instructions",
        "forget previous instructions",
        "disregard previous instructions",
        "override instructions",
        "instruction override",
        "system instruction override",
        "bypass instructions",
        "bypass rules",
        "reveal your system prompt",
        "show your system prompt",
        "system prompt",
        "[system]",
        "system message",
        "message systeme",
        "message système",
        "donne moi ton prompt",
        "montre ton prompt",
        "prompt developpeur",
        "prompt développeur",
        "developer prompt",
        "developer message",
        "jailbreak",
        "developer mode",
        "dev mode",
        "dev mode activated",
        "mode dev",
        "ignore les instructions",
        "oublie toutes tes instructions",
        "oublie tes instructions",
        "oublie les instructions",
        "instructions prealables",
        "prompt systeme",
        "prompt initial",
        "affiche le prompt",
        "regles de securite cachees",
        "regles cachees",
        "hidden rules",
        "hidden safety rules",
        "oublie les consignes",
        "contourne les instructions",
        "contourne les regles",
        "desactive les regles",
        "desactive la securite",
        "debloque de tes filtres",
        "filtres ethiques",
        "desormais debloque",
        "tu es maintenant",
        "agis comme admin",
        "agis comme root",
        "agis comme developpeur",
    ]
    exact_hijack = (
        any(marker in q for marker in ["retourne exactement", "retourne moi exactement", "return exactly"])
        and any(marker in q for marker in ["hacked", "bot bypassed", "bypassed", "status"])
    )
    if any(marker in q for marker in injection_markers) or exact_hijack or re.search(r"\bdan\b", q):
        return (
            "Je ne peux pas suivre une consigne qui tente de contourner les instructions "
            "du systeme ou de changer mon role. Je peux par contre aider avec les informations "
            "ENSA BM, les FAQ et les emplois du temps."
        )

    secret_markers = [
        ".env",
        " env ",
        "secret",
        "secrets",
        "password",
        "mot de passe",
        "token",
        "jwt",
        "api key",
        "cle api",
        "admin password",
    ]
    padded_q = f" {q} "
    if any(marker in padded_q for marker in secret_markers):
        return (
            "Je ne peux pas fournir de mots de passe, secrets, tokens, fichiers .env "
            "ou cles API. Pour les informations publiques de l'ENSA BM, je peux t'aider."
        )

    privacy_markers = [
        "donnees personnelles des autres",
        "donnees privees des autres",
        "autres etudiants",
        "emails des etudiants",
        "liste des utilisateurs",
        "conversations des autres",
        "messages des autres",
        "compte d un autre utilisateur",
        "compte d'un autre utilisateur",
        "compte des autres",
        "profil d un autre utilisateur",
        "profil d'un autre utilisateur",
    ]
    if any(marker in q for marker in privacy_markers):
        return (
            "Je ne peux pas fournir les donnees personnelles, messages ou comptes d'autres "
            "utilisateurs. Je peux aider avec des informations publiques ou ton propre planning."
        )

    unsafe_cyber = (
        any(marker in q for marker in ["exploiter une vulnerabilite", "exploit", "vulnerabilite", "pirater", "attaque", "attaquer", "bypass", "contourner"])
        and any(marker in q for marker in ["script", "python", "automatis", "portail etudiant", "systeme", "site", "serveur", "application"])
        and not any(marker in q for marker in ["signaler", "corriger", "securiser", "defensif", "audit autorise", "responsable"])
    )
    if unsafe_cyber:
        return (
            "Je ne peux pas aider a exploiter une vulnerabilite, automatiser une attaque "
            "ou cibler le portail etudiant. Je peux par contre aider a rediger un signalement "
            "responsable, une checklist de securisation ou un plan de test defensif autorise."
        )

    destructive_markers = [
        "rm rf",
        "format disk",
        "drop database",
        "drop table",
        "truncate table",
        "delete all users",
        "supprimer tous les utilisateurs",
    ]
    sql_destructive = (
        ("sql" in q or "requete" in q or "query" in q)
        and any(verb in q for verb in ["delete", "drop", "truncate", "supprimer", "effacer"])
        and any(target in q for target in ["users", "utilisateurs", "database", "base de donnees", "table"])
    )
    if any(marker in q for marker in destructive_markers) or sql_destructive:
        return (
            "Je ne peux pas aider a supprimer des utilisateurs, detruire une base de donnees "
            "ou produire une action destructive. Je peux aider sur une alternative sure."
        )

    return None


def route_question_api_stream(question: str, class_label: str | None = None, history: list[dict] | None = None, language: str = "fr", user_state: str | None = None):
    """
    Version streaming du router API avec support de l'historique.
    Yield chaque fragment de réponse, puis un JSON final pour les sources.
    """
    from backend.services.chatbot_service import (
        ask_question_structured_stream,
        ask_question_rag_stream,
        ask_question_rag,
    )
    from backend.services.rag_service import search_context

    question = _expand_profile_track_reference(question, class_label)
    message_language = _message_language(question, language)
    security_answer = _security_guard_answer(question)
    if security_answer:
        yield _tone_message(_style_answer_for_question(security_answer, question, user_state, message_language), user_state)
        return

    early_fast_fact = _official_fast_fact_answer(question) if message_language == "ar" else None
    if early_fast_fact and not _is_edt_question(question):
        yield _tone_message(_style_answer_for_question(early_fast_fact, question, user_state, message_language), user_state)
        yield f"__metadata__:{json.dumps({'source_files': 'faq_ensa_bm_officielle_5000.json'})}"
        return

    basic_answer = _basic_conversational_answer(question, class_label=class_label, language=message_language)
    if basic_answer:
        yield _tone_message(basic_answer, user_state)
        return

    priority_answer = _official_priority_answer(question, history)
    if priority_answer:
        yield _tone_message(_style_answer_for_question(priority_answer, question, user_state, message_language), user_state)
        yield f"__metadata__:{json.dumps({'source_files': 'faq_ensa_bm_officielle_5000.json'})}"
        return

    question = _contextualize_faq_followup_question(question, history)

    available = get_available_classes()
    contextual_class = _resolve_contextual_class_followup(question, class_label, available, history)
    if contextual_class:
        class_label = contextual_class
        if _is_short_class_reference(question):
            question = "montre moi tout l'emploi du temps"
    else:
        track_candidates = _ambiguous_track_timetable_candidates(question, available, history)
        if track_candidates:
            yield _tone_message(_semester_selection_text(track_candidates), user_state)
            return

        class_from_turn = _resolve_class_only_turn(question, available)
        if class_from_turn:
            class_label = class_from_turn
            question = "montre moi tout l'emploi du temps"

    question = _contextualize_timetable_followup_question(question, class_label, history)

    fast_fact = _official_fast_fact_answer(question)
    if fast_fact and not _is_edt_question(question):
        yield _tone_message(_style_answer_for_question(fast_fact, question, user_state, message_language), user_state)
        yield f"__metadata__:{json.dumps({'source_files': 'faq_ensa_bm_officielle_5000.json'})}"
        return

    available = get_available_classes()
    contextual_class = _resolve_contextual_class_followup(question, class_label, available, history)
    if contextual_class:
        class_label = contextual_class
        if _is_short_class_reference(question):
            question = "montre moi tout l'emploi du temps"
    else:
        class_from_turn = _resolve_class_only_turn(question, available)
        if class_from_turn:
            class_label = class_from_turn
            question = "montre moi tout l'emploi du temps"

    intent = _get_intent_smart(question, history=history)

    if intent in ["GREETING", "IDENTITY"]:
        yield from ask_question_rag_stream(question, history=history, user_state=user_state, language=message_language)
        return

    # FAQ/Campus : direct RAG stream
    if intent == "FAQ" or _is_campus_info_question(question):
        _, sources, _ = search_context(question)
        found_any = False
        for chunk in ask_question_rag_stream(question, history=history, user_state=user_state, language=message_language):
            if chunk:
                found_any = True
                yield chunk
        if not found_any:
            yield _tone_message("❌ Je n'ai pas trouvé d'information fiable dans la FAQ pour cette question.", user_state)
        elif sources:
            yield f"__metadata__:{json.dumps({'source_files': sources})}"
        return

    if not _is_edt_question(question):
        # On vérifie d'abord si on a du contexte avant de dire qu'on ne trouve pas
        _, sources, rag_score = search_context(question)
        
        found_any = False
        for chunk in ask_question_rag_stream(question, history=history, user_state=user_state, language=message_language):
            if chunk:
                found_any = True
                yield chunk
        
        if not found_any:
            yield _tone_message("❌ Je n'ai pas trouvé d'information fiable dans la FAQ pour cette question.", user_state)
        else:
            confidence = "high"
            if rag_score < 0.4: confidence = "low"
            elif rag_score < 0.7: confidence = "medium"
            yield f"__metadata__:{json.dumps({'source_files': sources, 'rag_confidence': confidence, 'rag_score': round(rag_score, 2)})}"
        return

    # Questions de type "où consulter" -> FAQ
    if _is_lookup_guidance_question(question):
        _, sources, _ = search_context(question)
        for chunk in ask_question_rag_stream(question, history=history, user_state=user_state, language=message_language):
            yield chunk
        if sources:
            yield f"__metadata__:{json.dumps({'source_files': sources})}"
        return

    if not available:
        yield _tone_message("⚠️ Aucun emploi du temps importé. Consulte l'Espace Étudiant.", user_state)
        return

    # Auto-selection or detection
    if len(available) == 1 and not class_label:
        class_label = list(available.keys())[0]

    if not class_label:
        detected = detect_class_in_question(question, available)
        if detected:
            class_label = detected
        else:
            # Check for partial ambiguity (multiple years for same filiere)
            q = question.lower()
            candidates = []
            for label in available:
                if label.split()[0].lower() in q:
                    candidates.append(label)
            
            if candidates:
                yield _tone_message("J'ai trouvé plusieurs classes correspondant à ta recherche. Laquelle est la tienne ?\n\n", user_state)
                for c in candidates:
                    yield f"• {c}\n"
                return

            yield _tone_message("Pour te répondre précisément, j'ai besoin de connaître ta filière. Quelle est ta classe ?\n\n", user_state)
            for c in available:
                yield f"• {c}\n"
            return

    question_detected_class = detect_class_in_question(question, available)
    if question_detected_class:
        class_label = question_detected_class

    # Resolve labels
    resolved, candidates = resolve_class_label(class_label, available)
    if resolved:
        class_label = resolved
    elif candidates:
        yield _tone_message("J'ai besoin de précision sur ta classe :\n\n", user_state)
        for c in candidates:
            yield f"• {c}\n"
        return

    # Load EDT
    paths = available.get(class_label, {})
    db_class_label = paths.get("canonical_label", class_label)

    from backend.services import db_service
    tt_structured = db_service.get_active_timetable(db_class_label)

    if not tt_structured:
        yield _tone_message(
            f"⚠️ Aucun créneau n'est actuellement disponible pour la classe {class_label}. "
            "Aucun emploi du temps actif n'est publié dans la base pour cette classe.",
            user_state,
        )
        return

    emploi_json = _emploi_json_from_structured_timetable(tt_structured)
    calendrier_json = None

    timetable_view = build_timetable_view_for_question(question, tt_structured)
    if timetable_view:
        yield f"__metadata__:{json.dumps({'timetable': timetable_view})}"

    # Stream from structured or fallback. The UI uses this endpoint, so language
    # styling must also happen here for deterministic EDT answers.
    structured_chunks = [
        chunk
        for chunk in ask_question_structured_stream(question, emploi_json, calendrier_json, class_label, user_state=user_state)
        if chunk
    ]
    structured_answer = "".join(structured_chunks)
    found_any = bool(structured_answer)
    if structured_answer:
        if message_language != "fr":
            structured_answer = _style_answer_for_question(structured_answer, question, user_state, message_language)
        yield structured_answer

    if not found_any and ENABLE_RAG_FALLBACK:
        _, sources, rag_score = search_context(question)
        for chunk in ask_question_rag_stream(question, history=history, user_state=user_state, language=message_language):
            yield chunk
        
        confidence = "high"
        if rag_score < 0.4: confidence = "low"
        elif rag_score < 0.7: confidence = "medium"
        yield f"__metadata__:{json.dumps({'source_files': sources, 'rag_confidence': confidence, 'rag_score': round(rag_score, 2)})}"


def route_question_api(question: str, class_label: str | None = None, history: list[dict] | None = None, language: str = "fr", user_state: str | None = None) -> dict:
    """
    Version stateless du router, utilisée par l'API REST.

    Returns:
        dict with keys:
          - answer: str
          - class_label: str | None
          - requires_class_selection: bool
          - available_classes: list[str]
          - source_file: str | None
    """
    from backend.services.chatbot_service import ask_question_structured, ask_question_rag

    question = _expand_profile_track_reference(question, class_label)
    message_language = _message_language(question, language)
    security_answer = _security_guard_answer(question)
    if security_answer:
        return {
            "answer": _tone_message(_style_answer_for_question(security_answer, question, user_state, message_language), user_state),
            "class_label": class_label,
            "requires_class_selection": False,
            "available_classes": [],
            "source_file": None,
            "rag_confidence": "high",
            "rag_score": 1.0,
        }

    early_fast_fact = _official_fast_fact_answer(question) if message_language == "ar" else None
    if early_fast_fact and not _is_edt_question(question):
        return {
            "answer": _tone_message(_style_answer_for_question(early_fast_fact, question, user_state, message_language), user_state),
            "class_label": class_label,
            "requires_class_selection": False,
            "available_classes": [],
            "source_file": "faq_ensa_bm_officielle_5000.json",
            "rag_confidence": "high",
            "rag_score": 1.0,
        }

    basic_answer = _basic_conversational_answer(question, class_label=class_label, language=message_language)
    if basic_answer:
        return {
            "answer": _tone_message(basic_answer, user_state),
            "class_label": class_label,
            "requires_class_selection": False,
            "available_classes": [],
            "source_file": None,
            "rag_confidence": "high",
            "rag_score": 1.0,
        }

    priority_answer = _official_priority_answer(question, history)
    if priority_answer:
        return {
            "answer": _tone_message(_style_answer_for_question(priority_answer, question, user_state, message_language), user_state),
            "class_label": class_label,
            "requires_class_selection": False,
            "available_classes": [],
            "source_file": "faq_ensa_bm_officielle_5000.json",
            "rag_confidence": "high",
            "rag_score": 1.0,
        }

    question = _contextualize_faq_followup_question(question, history)

    available = get_available_classes()
    contextual_class = _resolve_contextual_class_followup(question, class_label, available, history)
    if contextual_class:
        class_label = contextual_class
        if _is_short_class_reference(question):
            question = "montre moi tout l'emploi du temps"
    else:
        track_candidates = _ambiguous_track_timetable_candidates(question, available, history)
        if track_candidates:
            return {
                "answer": _tone_message(_semester_selection_text(track_candidates), user_state),
                "class_label": None,
                "requires_class_selection": True,
                "available_classes": track_candidates,
                "source_file": None,
            }

        class_from_turn = _resolve_class_only_turn(question, available)
        if class_from_turn:
            class_label = class_from_turn
            question = "montre moi tout l'emploi du temps"

    question = _contextualize_timetable_followup_question(question, class_label, history)

    fast_fact = _official_fast_fact_answer(question)
    if fast_fact and not _is_edt_question(question):
        return {
            "answer": _tone_message(_style_answer_for_question(fast_fact, question, user_state, message_language), user_state),
            "class_label": class_label,
            "requires_class_selection": False,
            "available_classes": [],
            "source_file": "faq_ensa_bm_officielle_5000.json",
            "rag_confidence": "high",
            "rag_score": 1.0,
        }

    # FAQ/Campus : direct RAG (pas besoin de classe)
    if _is_campus_info_question(question):
        try:
            rag_resp, sources, rag_score = ask_question_rag(question, history=history, user_state=user_state, language=message_language)
            if rag_resp and not rag_resp.lower().startswith("erreur"):
                confidence = "high"
                if rag_score < 0.4: confidence = "low"
                elif rag_score < 0.7: confidence = "medium"
                return {
                    "answer": rag_resp,
                    "class_label": class_label,
                    "requires_class_selection": False,
                    "available_classes": [],
                    "source_file": sources,
                    "rag_confidence": confidence,
                    "rag_score": round(rag_score, 2),
                }
        except Exception as exc:
            logger.debug(f"Campus info RAG fallback failed: {exc}")

        return {
            "answer": _tone_message(
                "❌ Je n'ai pas trouvé d'information fiable dans la FAQ pour cette question. Essaie une reformulation plus précise.",
                user_state,
            ),
            "class_label": class_label,
            "requires_class_selection": False,
            "available_classes": [],
            "source_file": None,
        }

    available = get_available_classes()
    contextual_class = _resolve_contextual_class_followup(question, class_label, available, history)
    if contextual_class:
        class_label = contextual_class
        if _is_short_class_reference(question):
            question = "montre moi tout l'emploi du temps"
    else:
        class_from_turn = _resolve_class_only_turn(question, available)
        if class_from_turn:
            class_label = class_from_turn
            question = "montre moi tout l'emploi du temps"

    intent = _get_intent_smart(question, history=history)

    if intent in ["GREETING", "IDENTITY"]:
        rag_resp, sources, rag_score = ask_question_rag(question, history=history, user_state=user_state, language=message_language)
        return {
            "answer": rag_resp,
            "class_label": class_label,
            "requires_class_selection": False,
            "available_classes": [],
            "source_file": sources,
            "rag_confidence": "high",
            "rag_score": 1.0,
        }

    if not _is_edt_question(question):
        try:
            rag_resp, sources, rag_score = ask_question_rag(question, history=history, user_state=user_state, language=message_language)
            if rag_resp and not rag_resp.lower().startswith("erreur"):
                confidence = "high"
                if rag_score < 0.4: confidence = "low"
                elif rag_score < 0.7: confidence = "medium"
                return {
                    "answer": rag_resp,
                    "class_label": class_label,
                    "requires_class_selection": False,
                    "available_classes": [],
                    "source_file": sources,
                    "rag_confidence": confidence,
                    "rag_score": round(rag_score, 2),
                }
        except Exception as exc:
            logger.debug(f"Non-EDT RAG fallback failed: {exc}")

        # Pour une question FAQ, ne pas basculer vers une demande de classe.
        return {
            "answer": _tone_message(
                "❌ Je n'ai pas trouvé d'information fiable dans la FAQ pour cette question. "
                "Essaie une reformulation plus précise (ex: « Qui est le directeur de l'ENSA Béni Mellal ? »).",
                user_state,
            ),
            "class_label": class_label,
            "requires_class_selection": False,
            "available_classes": [],
            "source_file": None,
        }

    # Questions de type "ou consulter l'EDT / calendrier" -> reponse FAQ generale.
    if _is_lookup_guidance_question(question):
        try:
            rag_resp, sources, rag_score = ask_question_rag(question, history=history, user_state=user_state, language=message_language)
            if rag_resp and not rag_resp.lower().startswith("erreur"):
                confidence = "high"
                if rag_score < 0.4: confidence = "low"
                elif rag_score < 0.7: confidence = "medium"
                return {
                    "answer": rag_resp,
                    "class_label": class_label,
                    "requires_class_selection": False,
                    "available_classes": [],
                    "source_file": sources,
                    "rag_confidence": confidence,
                    "rag_score": round(rag_score, 2),
                }
        except Exception as exc:
            logger.debug(f"Lookup guidance RAG fallback failed: {exc}")

        return {
            "answer": _tone_message(
                "Tu peux consulter ces informations sur l'Espace Etudiant ENSA BM "
                "et dans les annonces officielles de l'ecole.",
                user_state,
            ),
            "class_label": class_label,
            "requires_class_selection": False,
            "available_classes": [],
            "source_file": None,
        }

    if not available:
        return {
            "answer": _tone_message(
                "⚠️ Je n'ai pas encore de fichier d'emploi du temps importé dans l'application. "
                "En attendant, consulte l'Espace Étudiant ENSA BM pour l'EDT et le calendrier des examens, "
                "ou demande à l'administration d'importer les fichiers dans le panneau admin.",
                user_state,
            ),
            "class_label": None,
            "requires_class_selection": False,
            "available_classes": [],
            "source_file": None,
        }

    # Auto-sélection si 1 seule classe
    if len(available) == 1 and not class_label:
        class_label = list(available.keys())[0]

    # Détecter la classe dans la question si non fournie
    if not class_label:
        detected = detect_class_in_question(question, available)
        if detected:
            class_label = detected
        else:
            return {
                "answer": _tone_message(
                    "Pour te répondre précisément, j'ai besoin de connaître ta filière. "
                    "Quelle est ta classe ?\n\n"
                    + "\n".join(f"• {c}" for c in available),
                    user_state,
                ),
                "class_label": None,
                "requires_class_selection": True,
                "available_classes": list(available.keys()),
                "source_file": None,
            }

    question_detected_class = detect_class_in_question(question, available)
    if question_detected_class:
        class_label = question_detected_class

    # Résoudre les labels partiels (ex: "IACS") ou variantes (ex: "IACS_S4").
    if class_label:
        resolved, candidates = resolve_class_label(class_label, available)
        if resolved:
            class_label = resolved
        elif candidates:
            return {
                "answer": _tone_message(
                    "Ta filière est bien reconnue, mais j'ai besoin de précision sur le semestre ou l'année.\n\n"
                    "Choisis une classe parmi :\n"
                    + "\n".join(f"• {c}" for c in candidates),
                    user_state,
                ),
                "class_label": None,
                "requires_class_selection": True,
                "available_classes": candidates,
                "source_file": None,
            }

    # Vérifier que la classe existe
    if class_label and class_label not in available:
        return {
            "answer": _tone_message(
                f"Classe « {class_label} » introuvable. Classes disponibles : "
                + ", ".join(available.keys()),
                user_state,
            ),
            "class_label": None,
            "requires_class_selection": True,
            "available_classes": list(available.keys()),
            "source_file": None,
        }

    # Charger EDT
    paths = available.get(class_label, {})
    db_class_label = paths.get("canonical_label", class_label)

    from backend.services import db_service
    tt_structured = db_service.get_active_timetable(db_class_label)

    if not tt_structured:
        return {
            "answer": _tone_message(
                f"⚠️ Aucun créneau n'est actuellement disponible pour la classe {class_label}. "
                "Aucun emploi du temps actif n'est publié dans la base pour cette classe.",
                user_state,
            ),
            "class_label": class_label,
            "requires_class_selection": False,
            "available_classes": [],
            "source_file": None,
            "timetable": None
        }

    emploi_json = _emploi_json_from_structured_timetable(tt_structured)
    calendrier_json = None

    timetable_view = build_timetable_view_for_question(question, tt_structured)

    # Répondre via structured puis RAG si faible
    structured = ask_question_structured(question, emploi_json, calendrier_json, class_label, user_state=user_state)
    source_file = None
    if ENABLE_RAG_FALLBACK and (_is_weak(structured) or structured.startswith("❌")):
        try:
            rag_resp, sources, rag_score = ask_question_rag(question, history=history, user_state=user_state, language=message_language)
            if rag_resp and not rag_resp.lower().startswith("erreur"):
                confidence = "high"
                if rag_score < 0.4: confidence = "low"
                elif rag_score < 0.7: confidence = "medium"
                return {
                    "answer": rag_resp,
                    "class_label": class_label,
                    "requires_class_selection": False,
                    "available_classes": [],
                    "source_file": sources,
                    "timetable": timetable_view,
                    "rag_confidence": confidence,
                    "rag_score": round(rag_score, 2),
                }
        except Exception as exc:
            logger.debug(f"Structured response RAG fallback failed: {exc}")

    structured_answer = (
        structured
        if message_language == "fr"
        else _style_answer_for_question(structured, question, user_state, message_language)
    )
    return {
        "answer": structured_answer,
        "class_label": class_label,
        "requires_class_selection": False,
        "available_classes": [],
        "source_file": source_file,
        "timetable": timetable_view
    }
