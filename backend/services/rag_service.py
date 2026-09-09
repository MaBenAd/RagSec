"""
RAG service backed by local Qdrant storage for FAQ documents.
"""

import json
import os
import re
import math
import hashlib
import unicodedata
from functools import lru_cache
from difflib import SequenceMatcher
from datetime import UTC, datetime
from typing import Tuple
from dotenv import load_dotenv
from backend.services.logging_service import logger

load_dotenv()

# Absolute paths, robust regardless of current working directory.
_THIS_FILE = os.path.abspath(__file__)
_SERVICES_DIR = os.path.dirname(_THIS_FILE)  # backend/services/
_BACKEND_DIR = os.path.dirname(_SERVICES_DIR)  # backend/
FAQ_DIR = os.path.join(_BACKEND_DIR, "data", "faq")
QDRANT_URL = os.getenv("QDRANT_URL", "").strip()
VECTORSTORE_PATH = os.getenv(
    "VECTORSTORE_PATH",
    os.path.join(_BACKEND_DIR, "vectorstore_qdrant"),
)

COLLECTION_NAME = "faq_campus"
CACHE_COLLECTION_NAME = "semantic_cache"
_QDRANT_CLIENT = None
_EMBED_MODEL = None


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()

_TRACK_ALIASES = {
    "g2er": [
        "genie electrique et energies renouvelables",
        "genie electrique energies renouvelables",
        "energies renouvelables",
        "genie electrique",
    ],
    "iaa": [
        "industries agroalimentaires",
        "industrie agroalimentaire",
        "industries agro alimentaires",
        "industrie agro alimentaire",
        "agroalimentaire",
    ],
    "iacs": [
        "intelligence artificielle et cybersecurite",
        "intelligence artificielle cybersecurite",
        "intellignece artificielle et cybersecurite",
        "intellignece artificielle cybersecurite",
        "intelligence artificielle",
        "intellignece artificielle",
        "ia et cybersecurite",
        "ia cybersecurite",
        "cyber securite",
    ],
    "tdi": [
        "transformation digitale industrielle",
        "transformation digitale",
        "transformation numerique industrielle",
        "digitalisation industrielle",
        "industrie 4 0",
        "industrie 4.0",
    ],
}

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
    (r"\bbac\s*\+?\s*2\b", "bac2"),
    (r"\bbac\s+plus\s+deux\b", "bac2"),
]
_COMMON_QUERY_REWRITE_PATTERNS = [(re.compile(pattern), replacement) for pattern, replacement in _COMMON_QUERY_REWRITES]
_QUERY_REWRITE_MAX_CHARS = 280

_TOKEN_CANONICALS = {
    "courriel": "email",
    "mail": "email",
    "contacter": "contact",
    "responsable": "coordinateur",
    "coordonnateur": "coordinateur",
    "coordinator": "coordinateur",
    "integrer": "admission",
    "rejoindre": "admission",
    "acceder": "admission",
    "acces": "admission",
    "entrer": "admission",
    "concours": "admission",
    "orientation": "admission",
    "bac2": "admission",
    "candidater": "admission",
    "postuler": "admission",
    "procedure": "admission",
    "procedures": "admission",
    "modalite": "admission",
    "modalites": "admission",
    "edt": "planning",
    "horaire": "planning",
    "horaires": "planning",
    "timetable": "planning",
    "schedule": "planning",
    "dispo": "liste",
    "disponible": "liste",
    "disponibles": "liste",
    "liste": "liste",
    "resultat": "note",
    "resultats": "note",
    "releve": "document",
    "attestation": "document",
    "certificat": "document",
    "absence": "presence",
    "absences": "presence",
    "amo": "assurance",
    "minhaty": "bourse",
    "ebourse": "bourse",
    "contester": "reclamation",
    "contestation": "reclamation",
    "reclamer": "reclamation",
    "reclamation": "reclamation",
    "reclamations": "reclamation",
    "recours": "reclamation",
    "plainte": "reclamation",
    "plaintes": "reclamation",
    "programme": "module",
    "program": "module",
    "matiere": "module",
    "matieres": "module",
    "competence": "competence",
    "competences": "competence",
    "debouche": "debouche",
    "debouches": "debouche",
    "metier": "debouche",
    "metiers": "debouche",
    "carriere": "debouche",
    "job": "debouche",
    "jobs": "debouche",
    "stage": "stage",
    "stages": "stage",
    "pfe": "stage",
    "internship": "stage",
    "infrastructure": "infrastructure",
    "infrastructures": "infrastructure",
    "equipement": "infrastructure",
    "equipements": "infrastructure",
    "laboratoire": "infrastructure",
    "laboratoires": "infrastructure",
    "plateforme": "infrastructure",
    "plateformes": "infrastructure",
    "partenaire": "partenaire",
    "partenaires": "partenaire",
    "partenariat": "partenaire",
    "partenariats": "partenaire",
    "cooperation": "partenaire",
    "cooperations": "partenaire",
    "filiere": "filiere",
    "filieres": "filiere",
    "formation": "filiere",
    "formations": "filiere",
    "parcours": "filiere",
    "specialite": "filiere",
    "specialites": "filiere",
    "definition": "definition",
    "signifie": "definition",
    "signification": "definition",
    "correspond": "definition",
    "duree": "duree",
    "annee": "duree",
    "annees": "duree",
    "semestre": "semestre",
    "semestres": "semestre",
    "credit": "credit",
    "credits": "credit",
}

_CANONICAL_SINGULAR_EXCEPTIONS = {
    "cours",
    "temps",
    "iacs",
    "usms",
    "ens",
    "tdi",
    "iaa",
    "g2er",
    "2ap",
}

_FAQ_MATCH_STOPWORDS = {
    "a",
    "au",
    "aux",
    "avec",
    "ce",
    "ces",
    "cette",
    "comment",
    "dans",
    "de",
    "des",
    "du",
    "en",
    "est",
    "et",
    "faire",
    "fait",
    "la",
    "le",
    "les",
    "ma",
    "mes",
    "mon",
    "ou",
    "par",
    "pour",
    "que",
    "quel",
    "quelle",
    "quels",
    "quelles",
    "qui",
    "sur",
    "un",
    "une",
    "voir",
    "trouver",
    "donner",
    "donne",
    "avoir",
    "obtenir",
    "ensa",
    "ensabm",
    "bm",
    "beni",
    "mellal",
}

_FAQ_STRONG_DOMAIN_TOKENS = {
    "admission",
    "assurance",
    "bourse",
    "contact",
    "coordinateur",
    "credit",
    "debouche",
    "definition",
    "document",
    "duree",
    "email",
    "filiere",
    "infrastructure",
    "liste",
    "module",
    "note",
    "partenaire",
    "planning",
    "presence",
    "reclamation",
    "semestre",
    "stage",
}

_FAQ_PRIMARY_DOMAIN_TOKENS = _FAQ_STRONG_DOMAIN_TOKENS - {"filiere"}
_FAQ_TRACK_TOKENS = {"g2er", "iaa", "iacs", "tdi", "2ap"}
_FAQ_KEY_FACT_TOKENS = _FAQ_TRACK_TOKENS | {
    "gouskir",
    "rokni",
    "oulcaid",
    "ouanan",
    "kaab",
    "bouilkhalene",
    "bouilkhilane",
    "ensabm",
    "usms",
}
_GENERIC_FAQ_QUESTION_PREFIXES = (
    "pour un etudiant de l'ensa bm",
    "pour un etudiant de l ensa bm",
    "que dit la page",
    "que dit l'ensa bm a propos de",
    "que dit l ensa bm a propos de",
    "que faut-il savoir sur",
    "que faut il savoir sur",
    "que precise la page",
    "explique la section",
    "quelles informations fournit",
    "quelle information donne l'ensa bm sur",
    "quelle information donne l ensa bm sur",
)


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    normalized = normalized.lower()
    if len(normalized) <= _QUERY_REWRITE_MAX_CHARS:
        for pattern, replacement in _COMMON_QUERY_REWRITE_PATTERNS:
            normalized = pattern.sub(replacement, normalized)
    return normalized


def _canonicalize_token(token: str) -> str:
    token = token.lower()
    if token.endswith("email") and len(token) <= 10:
        return "email"
    if token in _TOKEN_CANONICALS:
        return _TOKEN_CANONICALS[token]
    if len(token) > 4 and token.endswith("s") and token not in _CANONICAL_SINGULAR_EXCEPTIONS:
        singular = token[:-1]
        return _TOKEN_CANONICALS.get(singular, singular)
    return token


def _tokenize(text: str) -> list[str]:
    raw_tokens = re.findall(r"[a-z0-9]{2,}", _normalize_text(text))
    return [_canonicalize_token(token) for token in raw_tokens]


def _contains_marker(text: str, marker: str) -> bool:
    normalized_text = _normalize_text(text)
    normalized_marker = _normalize_text(marker)
    if not normalized_marker:
        return False
    if re.search(r"[\u0600-\u06FF]", normalized_marker):
        return normalized_marker in normalized_text
    if " " in normalized_marker:
        return normalized_marker in normalized_text
    return bool(re.search(rf"\b{re.escape(normalized_marker)}\b", normalized_text))


def _has_contact_cue(text: str) -> bool:
    normalized = _normalize_text(text)
    tokens = set(_tokenize(text))
    if "email" in tokens or "contact" in tokens:
        return True
    return any(
        marker in normalized
        for marker in [
            "site officiel",
            "portail officiel",
            "site web",
            "official website",
            "mوقع",
            "موقع",
            "بريد",
            "إيميل",
            "ايميل",
        ]
    )


def _has_email_cue(text: str) -> bool:
    return "email" in set(_tokenize(text)) or "@" in (text or "")


def _has_website_cue(text: str) -> bool:
    normalized = _normalize_text(text)
    return any(
        marker in normalized
        for marker in [
            "site officiel",
            "portail officiel",
            "site web",
            "official website",
            "official portal",
            "http://",
            "https://",
            "الموقع الرسمي",
        ]
    )


def _has_director_cue(text: str) -> bool:
    normalized = _normalize_text(text)
    return any(
        _contains_marker(normalized, marker)
        for marker in [
            "directeur",
            "director",
            "coordinateur",
            "coordinator",
            "مدير",
            "شكون",
            "من هو",
            "من هي",
        ]
    )


def _extract_track_code(text: str) -> str:
    t = _normalize_text(text or "")
    match = re.search(r"\b(iacs|tdi|g2er|iaa|2ap)\b", t)
    if match:
        return match.group(1)
    compact = re.sub(r"[^a-z0-9]+", " ", t).strip()
    for code, aliases in _TRACK_ALIASES.items():
        for alias in aliases:
            if alias in compact:
                return code
    return ""


def _source_quality_weight(source: str | None) -> float:
    s = (source or "").lower()
    if "officielle_5000" in s or "official" in s:
        return 0.12
    if "rag_enrichie" in s:
        return 0.07
    if "scrape_rag_complete" in s:
        return 0.05
    if "faq_usms" in s:
        return -0.05
    return 0.0


def _noisy_text_penalty(text: str) -> float:
    if not text:
        return 0.0
    noisy_markers = ["�", "´", "`", "Ã", "\ufffd"]
    hits = sum(text.count(marker) for marker in noisy_markers)
    if hits <= 0:
        return 0.0
    return min(0.18, 0.02 * hits)


def _intent_type(text: str) -> str:
    t = _normalize_text(text)
    if any(_contains_marker(t, k) for k in [
        "ou consulter",
        "ou voir",
        "comment consulter",
        "comment voir",
        "ou demander",
        "comment demander",
        "espace etudiant",
        "notes",
        "resultats",
        "absences",
        "documents administratifs",
        "attestation",
        "emploi du temps",
        "edt",
        "bourse",
        "amo",
        "inscription pedagogique",
        "login",
        "compte etudiant",
        "convention de stage",
    ]):
        return "other"
    if _has_contact_cue(t):
        return "contact"
    if any(_contains_marker(t, k) for k in ["qui est", "who is", "coordinateur", "coordinator", "مدير", "شكون", "من هو", "من هي"]):
        return "who"
    if any(_contains_marker(t, k) for k in ["signifie", "meaning", "veut dire", "stands for", "definition", "c est quoi", "c quoi"]):
        return "definition"
    if any(_contains_marker(t, k) for k in [
        "quels", "quelles", "liste", "filiere", "filiere", "available", "program",
        "شحال", "كم", "مسارات", "تخصصات", "فيلير", "filiere",
    ]):
        return "list"
    if any(_contains_marker(t, k) for k in ["ou", "where", "scolarite", "adresse", "location", "وين", "اين", "أين", "فين"]):
        return "where"
    return "other"


def _augment_query_for_retrieval(question: str) -> str:
    q = question or ""
    translated_q = ""
    try:
        from backend.services.groq_service import _detect_question_language, _translate_question_to_french

        if _detect_question_language(q) != "fr":
            translated_q = _translate_question_to_french(q)
    except Exception:
        translated_q = ""

    seed_query = q if not translated_q or _normalize_text(translated_q) == _normalize_text(q) else f"{q} {translated_q}"
    t = _normalize_text(seed_query)
    extras: list[str] = []

    has_location_cue = any(_contains_marker(t, k) for k in [
        "ou", "où", "where", "location", "adresse", "localisation",
        "وين", "اين", "أين", "فين",
    ])
    mentions_campus = any(k in t for k in ["ensa", "bm", "beni mellal", "mghila", "بني", "مليل", "مغيلا"])
    has_who_cue = _has_director_cue(t)
    has_contact_cue = _has_contact_cue(t)
    has_email_cue = _has_email_cue(t)
    has_website_cue = _has_website_cue(t)
    has_list_cue = any(_contains_marker(t, k) for k in ["combien", "how many", "quelles", "quels", "liste", "tracks", "filiere", "filiere", "شحال", "كم", "مسارات", "تخصصات", "فيلير"])
    target_track = _extract_track_code(seed_query)
    asks_admission = any(_contains_marker(t, k) for k in ["rejoindre", "integrer", "admission", "acceder", "acces", "entrer"])
    mentions_preparatory = any(_contains_marker(t, k) for k in ["cycle preparatoire", "2ap", "classes preparatoires"])
    mentions_engineering_cycle = any(_contains_marker(t, k) for k in ["cycle ingenieur", "filiere ingenieur", "admission parallele"])

    if has_location_cue and mentions_campus:
        extras.extend([
            "where is ensa beni mellal",
            "ou se situe ensa beni mellal",
            "adresse campus mghila beni mellal",
        ])

    if has_who_cue and mentions_campus:
        extras.extend([
            "who is the director of ensa bm",
            "directeur ensa bm",
            "pr belaid bouilkhilane",
        ])

    if has_list_cue and mentions_campus:
        extras.extend([
            "how many engineering tracks ensa bm",
            "combien de filieres ingenieur ensa bm",
            "g2er iaa iacs tdi",
        ])
        if any(marker in t for marker in ["nom", "definition", "signifie", "veut dire", "c est quoi", "c'est quoi"]):
            extras.extend([
                "que signifie g2er",
                "que signifie iaa",
                "que signifie iacs",
                "que signifie tdi",
            ])

    if asks_admission and (mentions_campus or mentions_engineering_cycle or mentions_preparatory):
        extras.extend([
            "admission ensa beni mellal",
            "integrer cycle preparatoire 2ap",
            "integrer cycle ingenieur admission parallele",
            "concours national ensa",
        ])

    if mentions_preparatory and any(_contains_marker(t, k) for k in ["combien", "duree", "annee", "semestre"]):
        extras.extend([
            "cycle preparatoire 2AP dure deux ans",
            "cycle preparatoire quatre semestres",
        ])

    if has_contact_cue and mentions_campus:
        extras.extend([
            "contact ensa bm",
            "site officiel ensa bm",
            "email ensabm.contact@usms.ma",
        ])
        if has_email_cue:
            extras.append("adresse email ensa bm")
        if has_website_cue:
            extras.append("https://ensabm.usms.ac.ma/")
        if has_who_cue:
            extras.extend([
                "email directeur ensa bm",
                "b.bouikhalene@usms.ma",
            ])

    if target_track:
        extras.append(target_track)

    if any(_contains_marker(t, k) for k in ["وين", "اين", "أين", "فين"]):
        extras.extend(["location", "where", "adresse"])

    if not extras:
        return seed_query

    # Keep deterministic order while deduplicating.
    unique_extras = list(dict.fromkeys(extras))
    return f"{seed_query} {' '.join(unique_extras)}"


def _fuzzy_token_overlap(left: list[str], right: list[str]) -> float:
    if not left or not right:
        return 0.0

    right_set = set(right)
    exact = sum(1 for tok in left if tok in right_set)
    if exact == len(left):
        return 1.0
    if len(right_set) > 80:
        return exact / max(len(left), 1)

    fuzzy = 0
    unmatched = [tok for tok in left if tok not in right_set]
    for tok in unmatched:
        candidates = (
            cand
            for cand in right_set
            if cand[:1] == tok[:1] and abs(len(cand) - len(tok)) <= 2
        )
        if any(SequenceMatcher(None, tok, cand).ratio() >= 0.84 for cand in candidates):
            fuzzy += 1

    return (exact + 0.6 * fuzzy) / max(len(left), 1)


def _faq_match_tokens(text: str) -> list[str]:
    tokens = []
    for token in _tokenize(text):
        if len(token) < 3 or token in _FAQ_MATCH_STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def _text_similarity(left: str, right: str) -> float:
    left_key = _faq_question_key(left)
    right_key = _faq_question_key(right)
    if not left_key or not right_key:
        return 0.0
    return SequenceMatcher(None, left_key, right_key).ratio()


def _faq_pair_mentions_conflicting_track(pair_blob: str, target_track: str) -> bool:
    if not target_track:
        return False

    mentioned = {code for code in ["g2er", "iaa", "iacs", "tdi", "2ap"] if code in pair_blob}
    if not mentioned or target_track in mentioned:
        return False

    return True


def _is_generic_scraped_faq_question(question: str) -> bool:
    normalized = _normalize_text(question)
    if normalized.startswith(_GENERIC_FAQ_QUESTION_PREFIXES):
        return True
    if any(marker in normalized for marker in _GENERIC_FAQ_QUESTION_PREFIXES):
        return True
    return any(
        marker in normalized
        for marker in [
            " que dit la page ",
            " explique la section ",
            " que dit l'ensa bm a propos de ",
            " que dit l ensa bm a propos de ",
        ]
    )


def _faq_pair_match_score(
    question: str,
    pair: dict,
    q_tokens: list[str],
    q_intent: str,
    target_track: str,
    target_semester: str,
) -> float:
    pair_question = pair.get("question", "")
    answer = pair.get("answer", "")
    pair_blob = pair.get("blob") or _normalize_text(f"{pair_question} {answer}")
    is_generic_scraped_question = _is_generic_scraped_faq_question(pair_question)

    if _faq_pair_mentions_conflicting_track(pair_blob, target_track):
        return 0.0

    if target_semester:
        pair_semester = _extract_semester(pair_blob)
        if pair_semester and pair_semester != target_semester:
            return 0.0
    elif target_track and "module" in q_tokens:
        pair_question_norm = _normalize_text(pair_question)
        if _extract_semester(pair_question_norm):
            return 0.0

    asks_coordinator = _asks_coordinator(question)
    if asks_coordinator and "coordinateur" not in pair_blob and "coordinator" not in pair_blob:
        return 0.0

    asks_definition = _asks_track_definition(question)
    if asks_definition and target_track and "coordinateur" in pair_blob:
        return 0.0

    if "pfe" in _normalize_text(question):
        if "pfe" not in pair_blob and "projet de fin d'etudes" not in pair_blob and "projet de fin d etudes" not in pair_blob:
            return 0.0

    if q_intent == "contact":
        has_contact = (
            "@" in answer
            or any(term in pair_blob for term in ["email", "contact", "courriel", "site officiel", "portail officiel"])
        )
        if not has_contact:
            return 0.0

    if q_intent == "who" and not any(
        term in pair_blob
        for term in ["coordinateur", "coordinator", "directeur", "director", "pr.", "monsieur", "m."]
    ):
        return 0.0

    if q_intent == "where" and any(marker in _normalize_text(question) for marker in ["ou se situe", "where is", "adresse", "localisation"]):
        if not any(term in pair_blob for term in ["campus", "mghila", "adresse", "se situe", "localisation"]):
            return 0.0

    if q_intent == "list" and not target_track and "filiere" in q_tokens:
        mentioned_tracks = {code for code in _FAQ_TRACK_TOKENS if code in pair_blob}
        if len(mentioned_tracks) == 1 and any(
            marker in pair_blob
            for marker in ["signifie", "veut dire", "definition", "coordinateur", "responsable"]
        ):
            return 0.0

    if "infrastructure" in q_tokens:
        pair_question_norm = _normalize_text(pair_question)
        explicit_infra_question = any(
            term in pair_question_norm
            for term in ["infrastructure", "laboratoire", "equipement", "plateforme"]
        )
        looks_like_programme_answer = any(term in pair_blob for term in ["semestre", "module", "modules", "pfe"])
        looks_like_module_lookup = any(
            term in pair_question_norm
            for term in [
                "etudie",
                "quand",
                "dans quel semestre",
                "en quel semestre",
                "que contient le semestre",
                "cours suit",
                "modules sont enseignes",
                "est ce que",
                "fait",
                "ou se trouve le module",
                "dans le programme",
                "trouve t on",
                "annee ou semestre",
            ]
        )
        if looks_like_programme_answer and (not explicit_infra_question or looks_like_module_lookup):
            return 0.0

    pair_question_tokens = list(pair.get("question_tokens") or _faq_match_tokens(pair_question))
    answer_tokens = list(pair.get("answer_tokens") or _faq_match_tokens(answer))
    pair_all_tokens = pair_question_tokens + answer_tokens
    if not pair_all_tokens:
        return 0.0
    q_token_set = set(q_tokens)
    pair_question_token_set = set(pair_question_tokens)
    answer_token_set = set(answer_tokens)
    primary_q_tokens = q_token_set & _FAQ_PRIMARY_DOMAIN_TOKENS
    primary_in_question = primary_q_tokens & pair_question_token_set
    primary_in_answer = primary_q_tokens & answer_token_set
    if primary_q_tokens and not (primary_in_question or primary_in_answer):
        return 0.0

    question_overlap = _fuzzy_token_overlap(q_tokens, pair_question_tokens)
    answer_overlap = _fuzzy_token_overlap(q_tokens, answer_tokens)
    full_overlap = _fuzzy_token_overlap(q_tokens, pair_all_tokens)
    if max(question_overlap, answer_overlap, full_overlap) < 0.18:
        return 0.0

    reverse_question_overlap = _fuzzy_token_overlap(pair_question_tokens, q_tokens)
    q_key = _faq_question_key(question)
    pair_question_key = pair.get("question_key") or _faq_question_key(pair_question)
    if is_generic_scraped_question or len(pair_question_key) > 180:
        text_similarity = 0.0
    else:
        text_similarity = SequenceMatcher(None, q_key, pair_question_key).ratio() if q_key and pair_question_key else 0.0

    score = max(
        0.56 * question_overlap + 0.14 * reverse_question_overlap + 0.16 * answer_overlap + 0.14 * text_similarity,
        0.70 * full_overlap + 0.18 * question_overlap + 0.12 * text_similarity,
    )

    pair_intent = _intent_type(pair_question)
    if q_intent == pair_intent:
        score += 0.06
    elif q_intent != "other" and pair_intent != "other":
        score -= 0.08

    if target_track and target_track in pair_blob:
        score += 0.12
    if target_semester and target_semester == _extract_semester(pair_blob):
        score += 0.08
    if primary_q_tokens:
        if primary_in_question:
            score += 0.16 + min(0.08, 0.03 * len(primary_in_question))
        elif primary_in_answer:
            score -= 0.08
    elif any(token in _FAQ_STRONG_DOMAIN_TOKENS for token in q_tokens):
        score += 0.04

    if is_generic_scraped_question:
        score -= 0.20
        if primary_q_tokens and not primary_in_question:
            score -= 0.14

    missing_track = target_track and target_track not in pair_blob
    if missing_track and target_track in q_token_set:
        score -= 0.18

    return max(score, 0.0)


def _direct_match_threshold(q_tokens: list[str], target_track: str, target_semester: str) -> float:
    if not q_tokens:
        return 1.0
    has_strong_token = any(token in _FAQ_STRONG_DOMAIN_TOKENS for token in q_tokens)
    if len(q_tokens) <= 2:
        return 0.45 if has_strong_token or target_track else 0.56
    if len(q_tokens) <= 4:
        return 0.52 if has_strong_token or target_track or target_semester else 0.60
    return 0.58 if has_strong_token or target_track or target_semester else 0.64


def _is_low_quality_answer_text(answer: str) -> bool:
    if not answer:
        return True

    cleaned = answer.strip().lower()
    generic_starts = [
        "oui.", "oui,", "yes.", "yes,", "the website", "le site", "la page d'accueil",
    ]
    if any(cleaned.startswith(start) for start in generic_starts) and len(cleaned) < 220:
        return True

    if cleaned.startswith("les informations sur") and "page officielle" in cleaned and len(cleaned) < 220:
        return True
    if cleaned.startswith("les informations sur") and len(cleaned) < 180:
        return True

    return False


def _direct_answer_is_relevant(question: str, answer: str) -> bool:
    if not question or not answer:
        return False

    q_norm = _normalize_text(question)
    a_norm = _normalize_text(answer)

    if any(marker in q_norm for marker in ["resto", "restaurant universitaire", "restaurant u", "cantine"]):
        return any(term in a_norm for term in ["resto", "cantine", "restaurant", "alimentaire"])

    if any(marker in q_norm for marker in ["internat", "dortoir", "residence", "résidence", "hebergement", "hébergement"]):
        return any(term in a_norm for term in ["internat", "hebergement", "résidence", "dortoir"])

    if any(marker in q_norm for marker in ["site officiel", "site", "web", "portail", "inscription", "inscris", "inscrire", "concours"]):
        return any(term in a_norm for term in ["site officiel", "http", "https", "email", "contact", "portail"])

    if any(marker in q_norm for marker in ["ou se situe", "où se situe", "campus", "adresse", "localisation", "situe", "située", "situé"]):
        return any(term in a_norm for term in ["mghila", "beni mellal", "campus", "adresse", "localisation", "situé"])

    if any(marker in q_norm for marker in ["salaire", "revenu", "gain", "remuneration", "rémunération"]):
        return any(term in a_norm for term in ["salaire", "revenu", "dirhams", "euro", "ans", "année"])

    if any(marker in q_norm for marker in ["age maximum", "âge maximum", "limite d age", "limite d'âge", "age limite", "âge limite"]):
        return any(term in a_norm for term in ["age", "ans", "limite"])

    return True


def _is_semantic_cache_match(question: str, cached_question: str, cached_intent: str | None = None) -> bool:
    if not cached_question:
        return False

    q_tokens = _tokenize(question)
    c_tokens = _tokenize(cached_question)
    overlap = _fuzzy_token_overlap(q_tokens, c_tokens)
    if overlap < 0.55:
        return False

    current_intent = _intent_type(question)
    if cached_intent and cached_intent != current_intent and current_intent != "other":
        return False

    return True


# ... existing methods ...

def _ensure_cache_collection(client, vector_size: int):
    from qdrant_client.http import models

    try:
        existing = {c.name for c in client.get_collections().collections}
    except Exception:
        existing = set()

    if CACHE_COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=CACHE_COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE,
            ),
        )


def get_semantic_cache(question: str, threshold: float = 0.95) -> Tuple[str | None, str | None]:
    """
    Recherche une question sémantiquement similaire dans le cache.
    Retourne (answer, source) si trouvée, sinon (None, None).
    """
    try:
        model = get_embeddings()
        query_embedding = model.encode([question])[0]
        client = _get_qdrant_client()
        _ensure_cache_collection(client, len(query_embedding))
    except Exception as e:
        logger.error(f"Semantic cache initialization error: {e}")
        return None, None

    try:
        query_res = client.query_points(
            collection_name=CACHE_COLLECTION_NAME,
            query=query_embedding,
            limit=1,
            with_payload=True,
        )
        hits = getattr(query_res, "points", [])
        if hits and hits[0].score >= threshold:
            payload = hits[0].payload
            answer = payload.get("answer")
            cached_question = payload.get("question", "")
            cached_intent = payload.get("intent")

            if not _is_semantic_cache_match(question, cached_question, cached_intent):
                return None, None
            if _is_low_quality_answer_text(answer or ""):
                return None, None

            # Increment hit count for analytics
            client.set_payload(
                collection_name=CACHE_COLLECTION_NAME,
                payload={"hit_count": payload.get("hit_count", 0) + 1, "last_asked": _utc_now_iso()},
                points=[hits[0].id]
            )
            return answer, payload.get("source")
    except Exception as e:
        logger.error(f"Semantic cache retrieval error: {e}")
    
    return None, None


def set_semantic_cache(question: str, answer: str, source: str | None = None):
    """
    Stocke une nouvelle réponse dans le cache sémantique.
    """
    if not question or not answer:
        return
    if _is_low_quality_answer_text(answer):
        return

    try:
        model = get_embeddings()
        query_embedding = model.encode([question])[0]
        client = _get_qdrant_client()
        _ensure_cache_collection(client, len(query_embedding))
    except Exception as e:
        logger.error(f"Semantic cache initialization error: {e}")
        return

    # Use a deterministic 64-bit digest for stable point IDs.
    point_id = int.from_bytes(
        hashlib.blake2b(question.lower().strip().encode("utf-8"), digest_size=8).digest(),
        "big",
        signed=False,
    )

    try:
        from qdrant_client.http import models
        client.upsert(
            collection_name=CACHE_COLLECTION_NAME,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=query_embedding,
                    payload={
                        "question": question,
                        "normalized_question": _normalize_text(question),
                        "intent": _intent_type(question),
                        "answer": answer,
                        "source": source,
                        "hit_count": 1,
                        "last_asked": _utc_now_iso(),
                        "created_at": _utc_now_iso()
                    }
                )
            ]
        )
    except Exception as e:
        logger.error(f"Semantic cache storage error: {e}")


def get_most_asked_questions(limit: int = 10) -> list:
    """
    Retourne les questions les plus fréquemment posées via le cache sémantique.
    """
    client = _get_qdrant_client()
    try:
        # Use scroll to get points sorted by hit_count if we were using a real DB, 
        # but Qdrant scroll doesn't support sorting by payload yet without filters.
        # We'll retrieve all (or a large batch) and sort locally.
        res = client.scroll(
            collection_name=CACHE_COLLECTION_NAME,
            limit=100,
            with_payload=True,
            with_vectors=False
        )
        points = res[0]
        sorted_points = sorted(points, key=lambda x: x.payload.get("hit_count", 0), reverse=True)
        return [
            {
                "question": p.payload.get("question"),
                "answer": p.payload.get("answer"),
                "hit_count": p.payload.get("hit_count"),
                "last_asked": p.payload.get("last_asked")
            }
            for p in sorted_points[:limit]
        ]
    except Exception as e:
        logger.error(f"Error retrieving most asked questions: {e}")
        return []


class _FastEmbeddings:
    """
    Semantic embeddings using fastembed (CPU-optimized transformers).
    Provides actual meaning-based retrieval instead of just keyword matching.
    """

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        from fastembed import TextEmbedding
        self._model = TextEmbedding(model_name=model_name)

    def get_sentence_embedding_dimension(self) -> int:
        # bge-small-en-v1.5 is 384, all-MiniLM-L6-v2 is 384.
        return 384

    def encode(self, texts: list[str]) -> list[list[float]]:
        if isinstance(texts, str):
            texts = [texts]
        # fastembed.embed returns a generator of numpy arrays
        return [list(vec) for vec in self._model.embed(texts)]


class _HashEmbeddings:
    """Deterministic local fallback embeddings when fastembed is unavailable."""

    def __init__(self, dim: int = 384):
        self._dim = dim

    def get_sentence_embedding_dimension(self) -> int:
        return self._dim

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"[a-z0-9]{2,}", (text or "").lower())

    def _token_index(self, token: str) -> int:
        digest = hashlib.blake2s(token.encode("utf-8"), digest_size=4).digest()
        return int.from_bytes(digest, "big", signed=False) % self._dim

    def encode(self, texts: list[str]) -> list[list[float]]:
        if isinstance(texts, str):
            texts = [texts]

        vectors = []
        for text in texts:
            vec = [0.0] * self._dim
            for token in self._tokenize(text):
                vec[self._token_index(token)] += 1.0

            norm = math.sqrt(sum(v * v for v in vec))
            if norm > 0:
                vec = [v / norm for v in vec]
            vectors.append(vec)

        return vectors


def get_embeddings():
    global _EMBED_MODEL
    if _EMBED_MODEL is not None:
        return _EMBED_MODEL

    embedding_backend = os.getenv("RAG_EMBEDDING_BACKEND", "fast").strip().lower()
    if embedding_backend in {"hash", "local", "demo"}:
        logger.info("RAG embeddings backend: hash")
        _EMBED_MODEL = _HashEmbeddings(dim=384)
        return _EMBED_MODEL

    try:
        # Preferred semantic model when available.
        _EMBED_MODEL = _FastEmbeddings(model_name="BAAI/bge-small-en-v1.5")
    except Exception as e:
        logger.warning(f"RAG embeddings fallback enabled (fastembed unavailable): {e}")
        _EMBED_MODEL = _HashEmbeddings(dim=384)

    return _EMBED_MODEL


def _get_qdrant_client():
    global _QDRANT_CLIENT
    if _QDRANT_CLIENT is not None:
        return _QDRANT_CLIENT
    from qdrant_client import QdrantClient

    if QDRANT_URL:
        _QDRANT_CLIENT = QdrantClient(url=QDRANT_URL)
    else:
        os.makedirs(VECTORSTORE_PATH, exist_ok=True)
        _QDRANT_CLIENT = QdrantClient(path=VECTORSTORE_PATH)
    return _QDRANT_CLIENT


def _reset_qdrant_client():
    global _QDRANT_CLIENT
    if _QDRANT_CLIENT is not None:
        try:
            _QDRANT_CLIENT.close()
        except Exception as exc:
            logger.debug(f"Qdrant client close failed during reset: {exc}")
    _QDRANT_CLIENT = None


def _collection_count(client) -> int:
    try:
        return int(client.count(collection_name=COLLECTION_NAME, exact=True).count)
    except Exception:
        return 0


def _looks_like_dimension_mismatch(error: Exception) -> bool:
    message = str(error).lower()
    return any(
        marker in message
        for marker in ("not aligned", "shapes", "dimension", "vector", "dim 1")
    )


def _ensure_collection(client, vector_size: int):
    from qdrant_client.http import models

    try:
        existing = {c.name for c in client.get_collections().collections}
    except Exception:
        existing = set()

    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE,
            ),
        )


def _doc(text: str, metadata: dict) -> dict:
    return {"page_content": text, "metadata": metadata}


# ----------------------------- LOADERS -----------------------------
def _split_text_chunks(text: str, min_len: int = 30) -> list:
    """
    Smarter text splitter that respects paragraph boundaries and
    prevents cutting in the middle of a sentence if possible.
    """
    # 1. Split by double newlines (paragraphs)
    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > min_len]
    
    final_chunks = []
    current_chunk = ""
    
    for p in paragraphs:
        # If adding this paragraph exceeds target size (approx 600 chars),
        # save the current chunk and start a new one.
        if len(current_chunk) + len(p) > 600 and current_chunk:
            final_chunks.append(current_chunk.strip())
            current_chunk = p
        else:
            current_chunk += "\n\n" + p if current_chunk else p
            
    if current_chunk:
        final_chunks.append(current_chunk.strip())
        
    return [c for c in final_chunks if len(c) > min_len]


def _load_pdf(path: str, max_pages: int | None = None, max_chars: int | None = None) -> list:
    import pdfplumber
    import re

    chunks = []
    full_text = ""

    with pdfplumber.open(path) as pdf:
        pages = pdf.pages[:max_pages] if max_pages else pdf.pages
        for page in pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
                if max_chars and len(full_text) >= max_chars:
                    full_text = full_text[:max_chars]
                    break

    if not full_text:
        return chunks

    qa_pattern = re.compile(r"Q\s*:\s*(.+?)\s*A\s*:\s*(.+?)(?=Q\s*:|$)", re.DOTALL)
    matches = qa_pattern.findall(full_text)

    source = os.path.basename(path)
    if matches:
        for question, reponse in matches:
            q = " ".join(question.split())
            r = " ".join(reponse.split())
            if len(q) > 5 and len(r) > 5:
                chunks.append(_doc(f"Question : {q}\nReponse : {r}", {"source": source, "type": "pdf_faq"}))
    else:
        for para in _split_text_chunks(full_text):
            chunks.append(_doc(para, {"source": source, "type": "pdf_faq"}))

    return chunks


def _load_faq_json(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        items = json.load(f)

    docs = []
    for item in items:
        q = item.get("question", "")
        r = item.get("reponse", item.get("réponse", item.get("answer", item.get("rÃ©ponse", ""))))
        cat = item.get("categorie", item.get("catégorie", item.get("catÃ©gorie", "general")))
        source_url = item.get("source_url")
        source_title = item.get("source_title")
        tags = item.get("tags") or []
        page_content = f"Question : {q}\nReponse : {r}"
        docs.append(
            _doc(
                page_content,
                {
                    "source": os.path.basename(path),
                    "source_url": source_url,
                    "source_title": source_title,
                    "categorie": cat,
                    "tags": tags,
                    "type": "faq_json",
                },
            )
        )
    return docs


def _load_text(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        text = f.read()

    return [_doc(c.strip(), {"source": os.path.basename(path), "type": "texte"}) for c in text.split("\n\n") if len(c.strip()) > 30]


def _collect_documents(include_pdfs: bool = False) -> list:
    logger.info(f"[_collect_documents] Starting")
    docs = []
    if not os.path.exists(FAQ_DIR):
        os.makedirs(FAQ_DIR, exist_ok=True)
        logger.info(f"[_collect_documents] FAQ_DIR created, returning empty")
        return docs

    # Live request paths keep include_pdfs=False because PDF extraction
    # can be slow. Explicit rebuilds can include PDFs once, outside chat flow.
    files = [f for f in sorted(os.listdir(FAQ_DIR)) if not f.startswith(".")]
    logger.info(f"[_collect_documents] Found {len(files)} FAQ entries")
    if not files:
        logger.info(f"[_collect_documents] No files, returning empty")
        return docs

    json_stems = {os.path.splitext(f)[0] for f in files if f.endswith(".json")}
    for filename in files:
        logger.info(f"[_collect_documents] Loading {filename}...")
        filepath = os.path.join(FAQ_DIR, filename)
        if not os.path.isfile(filepath):
            continue
        try:
            if filename.endswith(".pdf"):
                if not include_pdfs:
                    continue
                if os.path.splitext(filename)[0] in json_stems:
                    logger.info(f"[_collect_documents] Skipping PDF with JSON twin: {filename}")
                    continue
                loaded = _load_pdf(filepath)
            elif filename.endswith(".json"):
                logger.info(f"[_collect_documents] Loading JSON...")
                loaded = _load_faq_json(filepath)
            elif filename.endswith((".txt", ".md")):
                logger.info(f"[_collect_documents] Loading text...")
                loaded = _load_text(filepath)
            else:
                continue
            logger.info(f"[_collect_documents] Loaded {len(loaded)} documents from {filename}")
            docs.extend(loaded)
        except Exception as e:
            logger.error(f"FAQ load error for {filename}: {e}")

    logger.info(f"[_collect_documents] Done, returning {len(docs)} documents total")
    return docs


def _is_active_faq_source(source: str | None) -> bool:
    if not source:
        return True
    name = os.path.basename(str(source))
    if not name:
        return True
    lowered = name.lower()
    if "_old" in lowered or "archive" in lowered or "ancienne" in lowered:
        return False
    if lowered.endswith((".json", ".pdf", ".txt", ".md")):
        return os.path.isfile(os.path.join(FAQ_DIR, name))
    return True


def _faq_files_signature() -> tuple:
    if not os.path.exists(FAQ_DIR):
        return (id(_collect_documents),)
    rows = []
    for filename in sorted(os.listdir(FAQ_DIR)):
        if filename.startswith("."):
            continue
        path = os.path.join(FAQ_DIR, filename)
        if os.path.isfile(path):
            try:
                stat = os.stat(path)
                rows.append((filename, stat.st_size, int(stat.st_mtime)))
            except OSError:
                continue
    return (id(_collect_documents), tuple(rows))


@lru_cache(maxsize=8)
def _extract_faq_pairs_cached(signature: tuple) -> tuple[dict, ...]:
    pairs = []
    for doc in _collect_documents():
        text = re.sub(r"\s+", " ", doc.get("page_content") or "").strip()
        metadata = doc.get("metadata") or {}
        match = re.search(
            r"Question\s*:\s*(.*?)\s*(?:Reponse|Réponse)\s*:\s*(.*)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            continue
        question = match.group(1).strip()
        answer = match.group(2).strip()
        if question and answer:
            pairs.append(
                {
                    "question": question,
                    "answer": answer,
                    "source": metadata.get("source"),
                    "blob": _normalize_text(f"{question} {answer}"),
                    "question_tokens": tuple(_faq_match_tokens(question)),
                    "answer_tokens": tuple(_faq_match_tokens(answer)),
                    "question_key": _faq_question_key(question),
                }
            )
    return tuple(pairs)


def _extract_faq_pairs() -> list[dict]:
    return list(_extract_faq_pairs_cached(_faq_files_signature()))


def _faq_question_key(text: str) -> str:
    return re.sub(r"\s+", " ", _normalize_text(text or "")).strip()


@lru_cache(maxsize=8)
def _faq_question_index_cached(signature: tuple) -> dict:
    index = {}
    for pair in _extract_faq_pairs_cached(signature):
        key = _faq_question_key(pair.get("question", ""))
        if key and key not in index:
            index[key] = pair
    return index


def _faq_question_index() -> dict:
    return _faq_question_index_cached(_faq_files_signature())


@lru_cache(maxsize=8)
def _faq_token_index_cached(signature: tuple) -> dict[str, tuple[dict, ...]]:
    buckets: dict[str, list[dict]] = {}
    for pair in _extract_faq_pairs_cached(signature):
        question_tokens = set(pair.get("question_tokens") or ())
        answer_tokens = set(pair.get("answer_tokens") or ())
        tokens = set(question_tokens)
        tokens.update(
            token
            for token in answer_tokens
            if token in _FAQ_PRIMARY_DOMAIN_TOKENS or token in _FAQ_KEY_FACT_TOKENS
        )
        for token in tokens:
            if token in _FAQ_MATCH_STOPWORDS:
                continue
            buckets.setdefault(token, []).append(pair)
    return {token: tuple(items) for token, items in buckets.items()}


def _candidate_faq_pairs_for_tokens(q_tokens: list[str]) -> list[dict]:
    index = _faq_token_index_cached(_faq_files_signature())
    if not q_tokens:
        return []

    primary_q_tokens = set(q_tokens) & _FAQ_PRIMARY_DOMAIN_TOKENS
    counts: dict[int, tuple[int, int, int, dict]] = {}
    for token in q_tokens:
        for pair in index.get(token, ()):
            key = id(pair)
            count, primary_count, question_count, _ = counts.get(key, (0, 0, 0, pair))
            question_tokens = set(pair.get("question_tokens") or ())
            counts[key] = (
                count + 1,
                primary_count + int(token in primary_q_tokens),
                question_count + int(token in question_tokens),
                pair,
            )

    if not counts:
        return _extract_faq_pairs()

    ranked = sorted(
        counts.values(),
        key=lambda item: (item[1], item[2], item[0]),
        reverse=True,
    )
    return [pair for _, _, _, pair in ranked[:180]]


def _extract_semester(text: str) -> str:
    normalized = _normalize_text(text or "")
    match = re.search(r"\bs\s*([1-9])\b", normalized)
    if not match:
        match = re.search(r"\bsemestre\s*([1-9])\b", normalized)
    return f"s{match.group(1)}" if match else ""


@lru_cache(maxsize=1)
def _program_catalog_data() -> tuple[dict, dict]:
    try:
        from backend.scripts.generate_ensa_bm_official_faq import TRACK_ALIASES, TRACK_SEMESTER_PROGRAMS

        return TRACK_SEMESTER_PROGRAMS, TRACK_ALIASES
    except Exception as exc:
        logger.debug(f"Program catalog unavailable in RAG service: {exc}")
        return {}, {}


def _program_track_from_query(question: str) -> str:
    q = _normalize_text(question or "")
    programs, aliases = _program_catalog_data()
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
    return ""


def _program_overview_context(question: str) -> tuple[str | None, str | None, float]:
    q_norm = _normalize_text(question or "")
    if any(
        marker in q_norm
        for marker in [
            "dans quel semestre",
            "en quel semestre",
            "quel semestre",
            "quand",
            "cours sur",
            "fait",
            "etudie",
        ]
    ):
        return None, None, 0.0

    q_tokens = set(_faq_match_tokens(question or ""))
    if not q_tokens.intersection({"module", "semestre"}):
        return None, None, 0.0
    if _extract_semester(question):
        return None, None, 0.0

    programs, _ = _program_catalog_data()
    track = _program_track_from_query(question)
    if not track or track not in programs:
        return None, None, 0.0

    parts = []
    for semester in sorted(programs[track], key=lambda value: int(value[1:])):
        data = programs[track][semester]
        title = data.get("title") or "programme"
        modules = "; ".join((data.get("modules") or [])[:3])
        parts.append(f"{semester} : {title} ({modules})")
    answer = f"Le programme {track} est organise par semestre : " + "; ".join(parts) + "."
    context = f"Informations pertinentes :\n- Question : Quel est le programme de la filiere {track} ?\nReponse : {answer}\n"
    return context, "faq_ensa_bm_officielle_5000.json", 0.97


def _asks_modules_by_semester(question: str) -> bool:
    q = _normalize_text(question)
    return bool(_extract_semester(q)) and any(
        marker in q
        for marker in ["module", "modules", "matiere", "matieres", "enseignes", "brochure"]
    )


def _asks_track_definition(question: str) -> bool:
    q = _normalize_text(question)
    return bool(_extract_track_code(q)) and any(
        marker in q
        for marker in ["c est quoi", "c'est quoi", "c’est quoi", "c quoi", "definition", "définition", "signifie", "veut dire", "exactement"]
    ) or bool(_extract_track_code(q) and re.search(r"\bc['’]?\s*est\s+quoi\b|\bc\s+quoi\b", q))


def _asks_coordinator(question: str) -> bool:
    q = _normalize_text(question)
    return "coordinateur" in q or "coordinator" in q


def _format_exact_faq_context(pair: dict) -> tuple[str, str | None]:
    context = f"Informations pertinentes :\n- Question : {pair['question']}\nReponse : {pair['answer']}\n"
    return context, pair.get("source")


def _needs_strict_faq_context(question: str) -> bool:
    q_norm = _normalize_text(question or "")
    if not q_norm:
        return False
    if _asks_modules_by_semester(q_norm) or _asks_track_definition(q_norm):
        return True
    if _asks_coordinator(q_norm) and _extract_track_code(q_norm):
        return True
    if "diplome" in q_norm:
        return True
    return bool(
        ("qu est ce que" in q_norm or re.search(r"\bqu['â€™]?\s*est[\s-]*ce\s+que\b", q_norm))
        and ("ensa" in q_norm or "ecole" in q_norm)
    )


def _find_direct_faq_context(question: str, min_score: float = 0.72) -> Tuple[str | None, str | None, float]:
    """
    Direct lookup against structured FAQ questions before vector search.

    The generated official FAQ contains many student-like formulations. When
    a user question matches one of them closely, this avoids a less precise
    neighboring vector chunk.
    """
    question_key = _faq_question_key(question)
    indexed = _faq_question_index()
    exact_pair = indexed.get(question_key)
    if exact_pair:
        context, source = _format_exact_faq_context(exact_pair)
        return context, source, 1.0

    if _needs_strict_faq_context(question):
        strict_context, strict_source = find_exact_faq_context(question)
        if strict_context:
            return strict_context, strict_source, 0.96

    program_context, program_source, program_score = _program_overview_context(question)
    if program_context:
        return program_context, program_source, program_score

    q_tokens = _faq_match_tokens(question or "")
    if not q_tokens:
        return None, None, 0.0

    best_pair = None
    best_score = 0.0
    q_intent = _intent_type(question)
    target_track = _extract_track_code(question)
    target_semester = _extract_semester(question)
    for pair in _candidate_faq_pairs_for_tokens(q_tokens):
        score = _faq_pair_match_score(
            question,
            pair,
            q_tokens,
            q_intent,
            target_track,
            target_semester,
        )
        if score > best_score:
            best_score = score
            best_pair = pair

    threshold = min(min_score, _direct_match_threshold(q_tokens, target_track, target_semester))
    if best_pair and best_score >= threshold:
        context, source = _format_exact_faq_context(best_pair)
        return context, source, best_score
    return None, None, best_score


def _find_direct_faq_answer(question: str, min_score: float = 0.72) -> Tuple[str | None, str | None, float]:
    """
    Return an exact FAQ answer when the question matches a FAQ entry closely enough.
    """
    context, source, score = _find_direct_faq_context(question, min_score=min_score)
    if not context:
        return None, None, 0.0

    for line in context.splitlines():
        match = re.search(r"(?:reponse|réponse)\s*:\s*(.+)", line, flags=re.IGNORECASE)
        if match:
            answer = match.group(1).strip()
            if answer:
                if _is_low_quality_answer_text(answer) or not _direct_answer_is_relevant(question, answer):
                    return None, None, 0.0
                return answer, source, score

    match = re.search(r"(?:reponse|réponse)\s*:\s*(.+)", context, flags=re.IGNORECASE | re.DOTALL)
    if match:
        answer = match.group(1).strip().splitlines()[0].strip()
        if answer:
            if _is_low_quality_answer_text(answer) or not _direct_answer_is_relevant(question, answer):
                return None, None, 0.0
            return answer, source, score

    return None, None, 0.0


def find_exact_faq_context(question: str) -> Tuple[str | None, str | None]:
    """
    Deterministic FAQ lookup for high-risk ambiguous questions.

    Vector search can confuse close questions such as S1 vs S4 modules or
    "coordinateur" vs "definition de filiere". This scanner only returns a
    context when strict discriminators match.
    """
    logger.info(f"[find_exact_faq_context] Starting")
    q_norm = _normalize_text(question or "")
    if not q_norm:
        logger.info(f"[find_exact_faq_context] Empty question, returning None")
        return None, None

    logger.info(f"[find_exact_faq_context] Calling _extract_faq_pairs...")
    pairs = _extract_faq_pairs()
    logger.info(f"[find_exact_faq_context] Got {len(pairs)} FAQ pairs")
    if not pairs:
        return None, None

    target_track = _extract_track_code(q_norm)
    target_semester = _extract_semester(q_norm)

    if _asks_modules_by_semester(q_norm):
        candidates = []
        for pair in pairs:
            blob = pair["blob"]
            if "module" not in blob and "modules" not in blob:
                continue
            if target_semester and _extract_semester(blob) != target_semester:
                continue
            if target_track and target_track not in blob:
                continue
            if not target_track and "2ap" in q_norm and "2ap" not in blob:
                continue
            score = 0
            if "brochure" in q_norm and "brochure" in blob:
                score += 3
            if target_track and target_track in blob:
                score += 3
            if target_semester and target_semester == _extract_semester(blob):
                score += 4
            if "modules list" in blob or "modules sont" in blob:
                score += 1
            candidates.append((score, pair))
        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            return _format_exact_faq_context(candidates[0][1])

    if _asks_track_definition(q_norm) and target_track:
        candidates = []
        for pair in pairs:
            blob = pair["blob"]
            if target_track not in blob:
                continue
            if "coordinateur" in blob or "coordinator" in blob:
                continue
            if not any(marker in blob for marker in ["signifie", "definition", "définition", "c est quoi", "filiere"]):
                continue
            score = 3
            if "signifie" in blob:
                score += 3
            if "forme des ingenieurs" in blob or "est axee" in blob or "est axée" in blob:
                score += 2
            candidates.append((score, pair))
        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            return _format_exact_faq_context(candidates[0][1])

    if _asks_coordinator(q_norm) and target_track:
        candidates = []
        for pair in pairs:
            blob = pair["blob"]
            if target_track not in blob or "coordinateur" not in blob:
                continue
            if "domaine scientifique" in blob or "associe au coordinateur" in blob:
                continue
            score = 3
            if "pr." in pair["answer"].lower() or "pr " in pair["answer"].lower():
                score += 3
            if target_track != "2ap" and "cycle preparatoire" in blob:
                score -= 4
            candidates.append((score, pair))
        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            return _format_exact_faq_context(candidates[0][1])

    if "diplome" in q_norm or "diplôme" in q_norm:
        for pair in pairs:
            blob = pair["blob"]
            if "quel diplome" in blob or "quel diplôme" in blob:
                if not target_track and "filiere" not in blob:
                    return _format_exact_faq_context(pair)

    if (
        "qu est ce que" in q_norm
        or re.search(r"\bqu['’]?\s*est[\s-]*ce\s+que\b", q_norm)
    ) and ("ensa" in q_norm or "ecole" in q_norm):
        for pair in pairs:
            blob = pair["blob"]
            if (
                "qu est ce que" in blob
                or re.search(r"\bqu['’]?\s*est[\s-]*ce\s+que\b", blob)
            ) and ("etablissement public" in blob or "universite sultan" in blob):
                return _format_exact_faq_context(pair)

    return None, None


def _documents_for_vectorstore(documents: list[dict]) -> list[dict]:
    """
    Keep Qdrant compact when a FAQ file contains many wording variants.

    Direct FAQ lookup still uses all Q/A pairs. The vector index only needs
    representative unique answers, otherwise local embedding becomes too slow
    and semantically redundant.
    """
    max_docs = int(os.getenv("RAG_VECTOR_MAX_DOCS", "1800"))
    if len(documents) <= max_docs:
        return documents

    selected: list[dict] = []
    seen_answers: set[str] = set()
    for doc in documents:
        text = doc.get("page_content") or ""
        answer_match = re.search(r"(?:Reponse|Réponse)\s*:\s*(.*)", text, flags=re.IGNORECASE | re.DOTALL)
        answer = answer_match.group(1) if answer_match else text
        key = _normalize_text(answer[:700])
        if not key or key in seen_answers:
            continue
        seen_answers.add(key)
        selected.append(doc)
        if len(selected) >= max_docs:
            break

    return selected or documents[:max_docs]


# -------------------------- VECTORSTORE --------------------------
def build_vectorstore() -> Tuple[object, str]:
    documents = _documents_for_vectorstore(_collect_documents(include_pdfs=True))
    model = get_embeddings()
    vector_size = int(model.get_sentence_embedding_dimension())

    client = _get_qdrant_client()
    try:
        client.delete_collection(collection_name=COLLECTION_NAME)
    except Exception as exc:
        logger.debug(f"Collection delete skipped before rebuild: {exc}")

    _ensure_collection(client, vector_size)

    if documents:
        from qdrant_client.http import models

        texts = [d["page_content"] for d in documents]
        embeddings = model.encode(texts)
        payloads = [{"text": texts[i], "metadata": documents[i]["metadata"]} for i in range(len(texts))]
        points = [
            models.PointStruct(id=i + 1, vector=embeddings[i], payload=payloads[i])
            for i in range(len(texts))
        ]
        client.upsert(collection_name=COLLECTION_NAME, points=points)

    return client, COLLECTION_NAME


def get_collection() -> Tuple[object, str]:
    client = _get_qdrant_client()
    model = get_embeddings()
    vector_size = int(model.get_sentence_embedding_dimension())
    _ensure_collection(client, vector_size)
    return client, COLLECTION_NAME


def rebuild_vectorstore() -> Tuple[object, str]:
    _reset_qdrant_client()
    _extract_faq_pairs_cached.cache_clear()
    _faq_question_index_cached.cache_clear()
    _faq_token_index_cached.cache_clear()
    return build_vectorstore()


def warm_faq_cache() -> dict:
    """
    Preload structured FAQ indexes once at startup so the first chat request
    does not pay the JSON parsing and token indexing cost.
    """
    signature = _faq_files_signature()
    pairs = _extract_faq_pairs_cached(signature)
    questions = _faq_question_index_cached(signature)
    tokens = _faq_token_index_cached(signature)
    return {
        "pairs": len(pairs),
        "questions": len(questions),
        "token_buckets": len(tokens),
    }


def get_faq_status() -> dict:
    status = {
        "faq_dir": FAQ_DIR,
        "faq_dir_exists": os.path.exists(FAQ_DIR),
        "files": [],
        "total_chunks": 0,
    }
    if status["faq_dir_exists"]:
        for f in sorted(os.listdir(FAQ_DIR)):
            if not f.startswith("."):
                fpath = os.path.join(FAQ_DIR, f)
                if not os.path.isfile(fpath):
                    continue
                status["files"].append({"name": f, "size_kb": os.path.getsize(fpath) // 1024})

    try:
        client, _ = get_collection()
        status["total_chunks"] = _collection_count(client)
    except Exception as exc:
        logger.debug(f"Unable to compute FAQ chunk count: {exc}")
    return status


# ---------------------------- SEARCH ----------------------------
def _search_context_once(question: str, k: int = 5) -> Tuple[str, str | None, float]:
    retrieval_query = _augment_query_for_retrieval(question)

    # Avoid triggering a full vectorstore rebuild during a live request.
    # Use existing local qdrant client but if the collection is empty, fall
    # back to lexical search to remain responsive.
    client = _get_qdrant_client()
    try:
        count = _collection_count(client)
    except Exception:
        count = 0

    if count == 0:
        logger.info("_search_context_once: vectorstore empty or unavailable — using lexical fallback")
        return _search_context_lexical(question, k)

    model = get_embeddings()
    query_embedding = model.encode([retrieval_query])[0]

    query_res = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_embedding,
        limit=min(max(k * 12, 24), count),
        with_payload=True,
    )

    hits = getattr(query_res, "points", None)
    if hits is None and isinstance(query_res, dict):
        hits = query_res.get("points", [])

    if not hits:
        return "Aucune information trouvée dans la base de connaissances.", None, 0.0

    candidates = []
    sources = set()
    # ... rest of the code logic to populate candidates ...
    q_tokens = _faq_match_tokens(retrieval_query)
    q_intent = _intent_type(retrieval_query)
    q_norm = _normalize_text(retrieval_query)
    target_track = _extract_track_code(retrieval_query)
    asks_coordinator = any(x in q_norm for x in ["coordinateur", "coordinator", "منسق"])
    asks_global_tracks = q_intent == "list" and not target_track and any(x in q_norm for x in ["filiere", "filieres", "tracks", "cycle ingenieur", "cycle ingénieur", "مسارات", "تخصصات", "فيلير"])
    asks_email = _has_email_cue(retrieval_query)
    asks_website = _has_website_cue(retrieval_query)
    mentions_director = _has_director_cue(retrieval_query)
    strict_terms: list[str] = []
    mentions_campus = any(x in q_norm for x in ["ensa", "bm", "beni mellal", "mghila"])
    location_strict = False
    if asks_coordinator and target_track:
        strict_terms = ["coordinateur", "coordinator", target_track]
    elif q_intent == "who" and any(x in q_norm for x in ["directeur", "director", "مدير", "شكون", "who is", "qui est"]):
        strict_terms = ["directeur", "director", "مدير", "belaid", "bouilkhilane", "pr."]
    elif q_intent == "where" and any(x in q_norm for x in ["وين", "اين", "أين", "فين", "where is", "ou se situe", "où se situe"]) and mentions_campus:
        strict_terms = ["campus", "mghila", "beni mellal", "adresse", "localisation", "se situe"]
        location_strict = True
    elif q_intent == "where" and any(x in q_norm for x in ["email", "contact", "site officiel", "ensabm.contact@usms.ma", "ensabm.usms.ac.ma"]):
        strict_terms = ["email", "contact", "site officiel", "ensabm.contact@usms.ma", "ensabm.usms.ac.ma"]
    elif q_intent == "contact":
        strict_terms = [
            "email",
            "contact",
            "courriel",
            "site officiel",
            "portail officiel",
            "ensabm.contact@usms.ma",
            "ensabm.usms.ac.ma",
            "b.bouikhalene@usms.ma",
        ]
    for hit in hits:
        score = float(getattr(hit, "score", 0.0) or 0.0)
        payload = getattr(hit, "payload", None) or {}
        text = payload.get("text", "")
        metadata = payload.get("metadata") or {}
        source = payload.get("source", "") or metadata.get("source", "")
        if source and not _is_active_faq_source(source):
            continue
        if text:
            t_tokens = _faq_match_tokens(text)
            lexical = _fuzzy_token_overlap(q_tokens, t_tokens)
            final_score = 0.65 * score + 0.35 * lexical

            t_norm = _normalize_text(text)
            has_contact_info = (
                any(
                    term in t_norm
                    for term in [
                        "email",
                        "contact",
                        "courriel",
                        "site officiel",
                        "portail officiel",
                        "ensabm.contact@usms.ma",
                        "ensabm.usms.ac.ma",
                        "b.bouikhalene@usms.ma",
                    ]
                )
                or "@" in text
                or "http://" in t_norm
                or "https://" in t_norm
            )
            has_director_info = any(
                term in t_norm
                for term in ["directeur", "director", "coordinateur", "coordinator", "pr.", "belaid", "bouilkhilane"]
            )
            if asks_coordinator and target_track:
                if target_track not in t_norm:
                    continue
                if target_track != "2ap" and "cycle preparatoire" in t_norm:
                    continue
            if strict_terms and not any(term in t_norm for term in strict_terms):
                continue
            if location_strict and any(term in t_norm for term in ["contact", "email", "site officiel", "ensabm.contact@usms.ma"]):
                continue
            if q_intent == "contact":
                if not has_contact_info:
                    continue
                if asks_email and "@" not in text and not any(term in t_norm for term in ["email", "contact", "courriel"]):
                    continue
                if asks_website and "http://" not in t_norm and "https://" not in t_norm and not any(term in t_norm for term in ["site officiel", "portail officiel"]):
                    continue
                if mentions_director and not has_director_info:
                    continue
            if q_intent == "list" and any(x in t_norm for x in ["filiere", "iacs", "tdi", "g2er", "iaa"]):
                final_score += 0.1
            if asks_global_tracks:
                track_hits = sum(1 for code in ["g2er", "iaa", "iacs", "tdi"] if code in t_norm)
                if track_hits >= 3:
                    final_score += 0.22
                elif track_hits >= 2:
                    final_score += 0.12
                if "quatre" in t_norm or "4 filiere" in t_norm or "4 fili" in t_norm:
                    final_score += 0.1
            if q_intent == "who" and any(x in t_norm for x in ["coordinateur", "coordinator", "pr.", "directeur", "director", "مدير"]):
                final_score += 0.1
            if q_intent == "who" and any(x in t_norm for x in ["belaid", "bouilkhilane"]):
                final_score += 0.12
            if q_intent == "contact" and has_contact_info:
                final_score += 0.14
            if q_intent == "contact" and asks_email and "@" in text:
                final_score += 0.22
            if q_intent == "contact" and asks_website and ("http://" in t_norm or "https://" in t_norm):
                final_score += 0.22
            if q_intent == "contact" and mentions_director and has_director_info:
                final_score += 0.12
            if q_intent == "where" and any(x in t_norm for x in ["email", "contact", "site officiel", "ensabm.usms.ac.ma", "ensabm.contact@usms.ma"]):
                final_score += 0.08
            if q_intent == "where" and any(x in t_norm for x in ["beni mellal", "mghila", "campus", "se situe", "adresse"]):
                final_score += 0.12
            final_score += _source_quality_weight(source)
            final_score -= _noisy_text_penalty(text)

            candidates.append((final_score, text, source))

    if not candidates:
        return "Aucune information trouvée dans la base de connaissances.", None, 0.0

    candidates.sort(key=lambda item: item[0], reverse=True)
    max_score = candidates[0][0]

    docs = []
    seen = set()
    for _, text, source in candidates:
        key = _normalize_text(text[:160])
        if key in seen:
            continue
        seen.add(key)
        docs.append(text)
        if source:
            sources.add(source)
        if len(docs) >= k:
            break

    context = "Informations pertinentes :\n"
    for doc in docs:
        # Keep enough content for list-style answers (modules, procedures).
        snippet = doc.strip()
        if len(snippet) > 1200:
            snippet = snippet[:1200].rsplit(" ", 1)[0].strip() + " ..."
        context += f"- {snippet}\n"
    
    source_str = ", ".join(sorted(list(sources))) if sources else None
    return context, source_str, max_score


def _tokenize_match(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]{2,}", (text or "").lower())


def _search_context_lexical(question: str, k: int = 5) -> Tuple[str, str | None, float]:
    """
    Fallback search used when Qdrant local storage is locked/unavailable.
    Uses token overlap on raw FAQ documents to keep the chatbot responsive.
    """
    documents = _collect_documents()
    if not documents:
        return "Aucune information trouvée dans la base de connaissances.", None, 0.0

    retrieval_query = _augment_query_for_retrieval(question)
    q_tokens = _faq_match_tokens(retrieval_query)
    if not q_tokens:
        return "Aucune information trouvée dans la base de connaissances.", None, 0.0

    scored = []
    # ... rest of the code logic to populate scored ...
    q_intent = _intent_type(retrieval_query)
    q_norm = _normalize_text(retrieval_query)
    target_track = _extract_track_code(retrieval_query)
    asks_coordinator = any(x in q_norm for x in ["coordinateur", "coordinator", "منسق"])
    asks_global_tracks = q_intent == "list" and not target_track and any(x in q_norm for x in ["filiere", "filieres", "tracks", "cycle ingenieur", "cycle ingénieur", "مسارات", "تخصصات", "فيلير"])
    asks_email = _has_email_cue(retrieval_query)
    asks_website = _has_website_cue(retrieval_query)
    mentions_director = _has_director_cue(retrieval_query)
    strict_terms: list[str] = []
    mentions_campus = any(x in q_norm for x in ["ensa", "bm", "beni mellal", "mghila"])
    location_strict = False
    if asks_coordinator and target_track:
        strict_terms = ["coordinateur", "coordinator", target_track]
    elif q_intent == "who" and any(x in q_norm for x in ["directeur", "director", "مدير", "شكون", "who is", "qui est"]):
        strict_terms = ["directeur", "director", "مدير", "belaid", "bouilkhilane", "pr."]
    elif q_intent == "where" and any(x in q_norm for x in ["وين", "اين", "أين", "فين", "where is", "ou se situe", "où se situe"]) and any(x in q_norm for x in ["ensa", "bm", "beni mellal", "mghila"]):
        strict_terms = ["campus", "mghila", "beni mellal", "adresse", "localisation", "se situe"]
        location_strict = True
    elif q_intent == "where" and any(x in q_norm for x in ["email", "contact", "site officiel", "ensabm.contact@usms.ma", "ensabm.usms.ac.ma"]):
        strict_terms = ["email", "contact", "site officiel", "ensabm.contact@usms.ma", "ensabm.usms.ac.ma"]
    elif q_intent == "contact":
        strict_terms = [
            "email",
            "contact",
            "courriel",
            "site officiel",
            "portail officiel",
            "ensabm.contact@usms.ma",
            "ensabm.usms.ac.ma",
            "b.bouikhalene@usms.ma",
        ]
    for doc in documents:
        text = doc.get("page_content", "")
        d_tokens = _faq_match_tokens(text)
        if not d_tokens:
            continue
        overlap = _fuzzy_token_overlap(q_tokens, d_tokens)
        if overlap <= 0.2:
            continue

        score = overlap
        t_norm = _normalize_text(text)
        has_contact_info = (
            any(
                term in t_norm
                for term in [
                    "email",
                    "contact",
                    "courriel",
                    "site officiel",
                    "portail officiel",
                    "ensabm.contact@usms.ma",
                    "ensabm.usms.ac.ma",
                    "b.bouikhalene@usms.ma",
                ]
            )
            or "@" in text
            or "http://" in t_norm
            or "https://" in t_norm
        )
        has_director_info = any(
            term in t_norm
            for term in ["directeur", "director", "coordinateur", "coordinator", "pr.", "belaid", "bouilkhilane"]
        )
        if asks_coordinator and target_track:
            if target_track not in t_norm:
                continue
            if target_track != "2ap" and "cycle preparatoire" in t_norm:
                continue
        if strict_terms and not any(term in t_norm for term in strict_terms):
            continue
        if location_strict and any(term in t_norm for term in ["contact", "email", "site officiel", "ensabm.contact@usms.ma"]):
            continue
        if q_intent == "contact":
            if not has_contact_info:
                continue
            if asks_email and "@" not in text and not any(term in t_norm for term in ["email", "contact", "courriel"]):
                continue
            if asks_website and "http://" not in t_norm and "https://" not in t_norm and not any(term in t_norm for term in ["site officiel", "portail officiel"]):
                continue
            if mentions_director and not has_director_info:
                continue
        if q_intent == "list" and any(x in t_norm for x in ["filiere", "iacs", "tdi", "g2er", "iaa"]):
            score += 0.1
        if asks_global_tracks:
            track_hits = sum(1 for code in ["g2er", "iaa", "iacs", "tdi"] if code in t_norm)
            if track_hits >= 3:
                score += 0.22
            elif track_hits >= 2:
                score += 0.12
            if "quatre" in t_norm or "4 filiere" in t_norm or "4 fili" in t_norm:
                score += 0.1
        if q_intent == "who" and any(x in t_norm for x in ["coordinateur", "coordinator", "pr.", "directeur", "director", "مدير"]):
            score += 0.1
        if q_intent == "who" and any(x in t_norm for x in ["belaid", "bouilkhilane"]):
            score += 0.12
        if q_intent == "contact" and has_contact_info:
            score += 0.14
        if q_intent == "contact" and asks_email and "@" in text:
            score += 0.22
        if q_intent == "contact" and asks_website and ("http://" in t_norm or "https://" in t_norm):
            score += 0.22
        if q_intent == "contact" and mentions_director and has_director_info:
            score += 0.12
        if q_intent == "where" and any(x in t_norm for x in ["email", "contact", "site officiel", "ensabm.usms.ac.ma", "ensabm.contact@usms.ma"]):
            score += 0.08
        if q_intent == "where" and any(x in t_norm for x in ["beni mellal", "mghila", "campus", "se situe", "adresse"]):
            score += 0.12
        score += _source_quality_weight(doc.get("metadata", {}).get("source"))
        score -= _noisy_text_penalty(text)

        scored.append((score, text, doc.get("metadata", {})))

    if not scored:
        return "Aucune information trouvée dans la base de connaissances.", None, 0.0

    scored.sort(key=lambda x: x[0], reverse=True)
    max_score = scored[0][0]
    top = scored[: max(1, k)]

    context = "Informations pertinentes :\n"
    sources = set()
    for _, text, metadata in top:
        snippet = text.strip()
        if len(snippet) > 1200:
            snippet = snippet[:1200].rsplit(" ", 1)[0].strip() + " ..."
        context += f"- {snippet}\n"
        source = metadata.get("source")
        if source:
            sources.add(source)

    source_str = ", ".join(sorted(list(sources))) if sources else None
    return context, source_str, max_score


def search_context(question: str, k: int = 5) -> Tuple[str, str | None, float]:
    logger.info(f"[search_context] Starting for: {question[:50]}")

    logger.info(f"[search_context] Calling _find_direct_faq_answer...")
    direct_answer, direct_source, direct_score = _find_direct_faq_answer(question)
    if direct_answer:
        direct_context, _, _ = _find_direct_faq_context(question)
        logger.info(f"[search_context] Found direct match, returning")
        return direct_context, direct_source, direct_score

    logger.info(f"[search_context] Trying vectorstore search...")
    try:
        logger.info(f"[search_context] Calling _search_context_once...")
        result = _search_context_once(question, k)
        logger.info(f"[search_context] Vectorstore search succeeded")
        return result
    except Exception as e:
        logger.error(f"[search_context] Exception caught: {type(e).__name__}: {str(e)[:100]}")
        if _looks_like_dimension_mismatch(e):
            logger.warning(f"RAG search detected incompatible vectorstore, using lexical fallback: {e}")
        else:
            logger.error(f"RAG search error: {e}")
        logger.warning("RAG fallback: switching to lexical search mode.")
        return _search_context_lexical(question, k)

