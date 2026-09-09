"""
Chatbot Service — deux modes de réponse :

  ask_question_structured(question, emploi_json, calendrier_json)
    → Répond aux questions emploi du temps à partir des JSON parsés.
    → Pas de LLM, réponse déterministe.

  ask_question_rag(question)
    → Répond aux questions FAQ via RAG (Qdrant + Groq).
"""

import re
import unicodedata
import secrets
import os
import json
from datetime import datetime, timedelta
from typing import Tuple, List, Optional
from backend.services.logging_service import logger

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

try:
    import dateparser
except Exception:
    dateparser = None

JOURS_MAP = {
    "lundi":    "Lundi",
    "mardi":    "Mardi",
    "mercredi": "Mercredi",
    "jeudi":    "Jeudi",
    "vendredi": "Vendredi",
    "samedi":   "Samedi",
    "monday":   "Lundi",
    "tuesday":  "Mardi",
    "wednesday": "Mercredi",
    "thursday": "Jeudi",
    "friday":   "Vendredi",
    "saturday": "Samedi",
}

SUPPORTIVE_PREFIXES = {
    "fr": {
        "stressed": "Je comprends que la situation puisse te stresser. Respire un instant, je vais t'aider calmement.",
        "anxious": "Je comprends ton inquiétude. On va regarder ça simplement, étape par étape.",
        "frustrated": "Je vois que c'est agaçant. Je vais te répondre clairement pour aller à l'essentiel.",
        "urgent": "Je vais aller droit au but pour t'aider rapidement.",
        "sad": "Je suis désolé que tu traverses ça. Je vais t'aider du mieux possible.",
    },
    "en": {
        "stressed": "I understand this can feel stressful. Take a breath, and I will guide you calmly.",
        "anxious": "I understand your concern. Let us go through it clearly, step by step.",
        "frustrated": "I can see this is frustrating. I will keep it clear and to the point.",
        "urgent": "I will get straight to the point to help you quickly.",
        "sad": "I am sorry you are going through this. I will do my best to help you.",
    },
    "ar": {
        "stressed": "أتفهم أن هذا قد يسبب لك التوتر. خذ نفسا عميقا وسأساعدك بهدوء.",
        "anxious": "أتفهم قلقك. سنمشي خطوة بخطوة بشكل واضح.",
        "frustrated": "أتفهم أنك منزعج. سأجيبك بشكل واضح ومباشر.",
        "urgent": "سأدخل مباشرة في النقطة لمساعدتك بسرعة.",
        "sad": "أنا آسف لأنك تمر بهذا. سأساعدك قدر الإمكان.",
    },
}

_EMOTION_LABELS = ("urgent", "stressed", "anxious", "frustrated", "sad")

_EMOTION_MARKERS = {
    "urgent": [
        ("urgent", 1.25), ("vite", 1.0), ("rapidement", 1.0), ("asap", 1.0),
        ("quickly", 0.9), ("immediately", 1.0), ("svp", 0.6),
        ("ضروري", 1.3), ("حالاً", 1.0), ("سريع", 0.9),
    ],
    "stressed": [
        ("stress", 1.2), ("stresse", 1.1), ("angoiss", 1.0), ("pression", 1.0),
        ("overwhelmed", 1.1), ("under pressure", 1.0), ("panic", 1.1),
        ("متوتر", 1.2), ("ضغط", 1.0), ("مضغوط", 1.0),
    ],
    "anxious": [
        ("inquiet", 1.1), ("peur", 1.0), ("j ai peur", 1.1), ("anxious", 1.2),
        ("worried", 1.1), ("afraid", 1.1), ("nervous", 0.9),
        ("قلق", 1.2), ("خايف", 1.1), ("خائف", 1.1),
    ],
    "frustrated": [
        ("marre", 1.1), ("enerve", 1.1), ("frustr", 1.2), ("agace", 1.0),
        ("bloque", 0.9), ("annoyed", 1.0), ("frustrated", 1.2), ("stuck", 0.9),
        ("منزعج", 1.1), ("معصب", 1.1), ("مقهور", 1.0),
    ],
    "sad": [
        ("triste", 1.1), ("decourag", 1.1), ("epuis", 1.0), ("fatigue", 0.9),
        ("i am tired", 0.8), ("sad", 1.1), ("down", 0.9), ("hopeless", 1.2),
        ("حزين", 1.2), ("تعبان", 0.9), ("محبط", 1.1),
    ],
}

_NEGATION_MARKERS = [
    "pas", "ne", "non", "not", "no", "never", "sans",
    "ما", "مش", "مو", "ليس", "لا",
]

_INTENSIFIERS = [
    "tres", "grave", "beaucoup", "vraiment", "extremement",
    "very", "really", "so", "extremely", "super",
    "جدا", "بزاف", "كثير", "قوي",
]

_DOWNPLAYERS = [
    "un peu", "plutot", "maybe", "a bit", "slightly", "kind of",
    "شوية", "قليل", "نوعا ما",
]


def detect_user_state(
    question: str,
    history: list[dict] | None = None,
    language: str | None = None,
) -> str | None:
    """Expose un état émotionnel détecté à partir de la question et du contexte."""
    return detect_user_state_details(question, history=history, language=language).get("label")


def detect_user_state_details(
    question: str,
    history: list[dict] | None = None,
    language: str | None = None,
) -> dict:
    """
    Détection hybride multi-langue: règles pondérées + historique,
    avec raffinement sémantique optionnel via Groq si l'incertitude est élevée.
    """
    label, confidence, detected_language, reasons = _detect_user_state_hybrid(
        question,
        history=history,
        language=language,
    )

    return {
        "label": label,
        "confidence": confidence,
        "language": detected_language,
        "reasons": reasons,
    }


def apply_emotional_tone(answer: str, user_state: str | None) -> str:
    """Expose l'ajout d'une tonalité empathique à une réponse."""
    return _apply_emotional_tone(answer, user_state)


# ─────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────

def normalize(text: str) -> str:
    """
    Normalise un texte pour la comparaison :
    minuscules + suppression des accents.
    Ex: "MÉCANIQUES DES FLUIDES" → "mecaniques des fluides"
    """
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text


def _detect_language(question: str, language_hint: str | None = None) -> str:
    if language_hint in {"fr", "en", "ar"}:
        return language_hint

    text = (question or "").strip()
    if not text:
        return "fr"

    if re.search(r"[\u0600-\u06FF]", text):
        return "ar"

    q = normalize(text)
    english_cues = [
        " the ", " what ", " when ", " where ", " how ", " please ", " can you ",
        " show me ", " help me ", " i am ", " i m ", " my ", " schedule ",
    ]
    if any(cue in f" {q} " for cue in english_cues):
        return "en"

    # Lightweight lexical fallback for short EN sentences.
    en_stopwords = {
        "i", "you", "we", "they", "he", "she", "it", "is", "are", "am", "was", "were",
        "here", "your", "my", "for", "with", "from", "this", "that", "tomorrow", "today",
        "please", "help", "schedule", "timetable",
    }
    words = re.findall(r"[a-z]+", q)
    en_hits = sum(1 for w in words if w in en_stopwords)
    if en_hits >= 2:
        return "en"

    return "fr"


def _score_single_text(question: str) -> Tuple[dict[str, float], list[str]]:
    q = normalize(question)
    scores = {label: 0.0 for label in _EMOTION_LABELS}
    reasons: list[str] = []

    def _is_marker_negated(marker_pos: int, marker_text: str) -> bool:
        # Negation should be close to and primarily before the marker.
        # This avoids false negation on clauses like "منزعج جدا وما فاهمش".
        before = q[max(0, marker_pos - 32):marker_pos]
        after = q[marker_pos + len(marker_text): min(len(q), marker_pos + len(marker_text) + 16)]
        before_tokens = before.split()
        after_tokens = after.split()

        if any(tok in _NEGATION_MARKERS for tok in before_tokens[-3:]):
            return True

        # Support post-position negation patterns like "stresse pas".
        if after_tokens and after_tokens[0] in _NEGATION_MARKERS:
            return True

        return False

    for label, markers in _EMOTION_MARKERS.items():
        for marker, weight in markers:
            pos = q.find(marker)
            if pos < 0:
                continue

            local = q[max(0, pos - 28): min(len(q), pos + len(marker) + 28)]
            contribution = weight

            if _is_marker_negated(pos, marker):
                contribution *= -0.8
                reasons.append(f"negated:{label}:{marker}")

            if any(intense in local for intense in _INTENSIFIERS):
                contribution *= 1.35
                reasons.append(f"intense:{label}:{marker}")

            if any(down in local for down in _DOWNPLAYERS):
                contribution *= 0.7
                reasons.append(f"downplay:{label}:{marker}")

            scores[label] += contribution
            reasons.append(f"hit:{label}:{marker}")

    # Punctuation/emphasis signals.
    if "!!!" in question or question.count("!") >= 3:
        scores["urgent"] += 0.25
        scores["frustrated"] += 0.2
        reasons.append("punctuation:exclamation")

    if question.count("?") >= 3:
        scores["anxious"] += 0.2
        reasons.append("punctuation:questions")

    return scores, reasons


def _blend_with_history(scores: dict[str, float], history: list[dict] | None) -> Tuple[dict[str, float], list[str]]:
    if not history:
        return scores, []

    reasons: list[str] = []
    user_messages = [m.get("content", "") for m in history if m.get("role") == "user" and m.get("content")]
    if not user_messages:
        return scores, reasons

    recent = user_messages[-4:]
    for idx, msg in enumerate(reversed(recent), start=1):
        hist_scores, _ = _score_single_text(msg)
        decay = 0.6 ** idx
        for label in _EMOTION_LABELS:
            scores[label] += hist_scores[label] * 0.45 * decay
    reasons.append("context:history_blend")
    return scores, reasons


def _choose_label(scores: dict[str, float]) -> Tuple[str | None, float]:
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_label, top_score = ordered[0]
    second_score = ordered[1][1] if len(ordered) > 1 else 0.0

    if top_score < 0.4:
        return None, 0.25

    margin = max(0.0, top_score - second_score)
    confidence = min(0.98, max(0.35, (top_score / (top_score + abs(second_score) + 0.8))))
    if margin < 0.2:
        confidence *= 0.8

    return top_label, round(confidence, 2)


def _detect_user_state_hybrid(
    question: str,
    history: list[dict] | None = None,
    language: str | None = None,
) -> Tuple[str | None, float, str, list[str]]:
    detected_language = _detect_language(question, language_hint=language)

    scores, reasons = _score_single_text(question)
    scores, history_reasons = _blend_with_history(scores, history)
    reasons.extend(history_reasons)

    label, confidence = _choose_label(scores)

    # Optional semantic refinement only when explicitly enabled. For the demo,
    # neutral campus/FAQ questions must not spend tokens or wait on Groq.
    if label is None and confidence < 0.72 and os.getenv("ENABLE_EMOTION_LLM", "false").lower() == "true":
        try:
            from backend.services.groq_service import classify_user_emotion

            llm_result = classify_user_emotion(
                question,
                history=history,
                language_hint=detected_language,
            )
            if llm_result:
                llm_label = llm_result.get("label")
                llm_conf = float(llm_result.get("confidence", 0.0) or 0.0)
                if llm_label in set(_EMOTION_LABELS) and llm_conf >= 0.6:
                    label = llm_label
                    confidence = round(llm_conf, 2)
                    reasons.append("model:groq_refine")
        except Exception as e:
            logger.debug(f"Emotion refinement skipped: {e}")

    return label, confidence, detected_language, reasons


# Les appels LLM sont centralisés dans groq_service.py


def _detect_jour(question: str):
    q = question.lower()
    for fr, canonical in JOURS_MAP.items():
        if fr in q:
            return canonical
    return None


def _day_from_weekday_idx(idx: int) -> str:
    days = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    return days[idx]


def _app_timezone_name() -> str:
    tz_name = (os.getenv("APP_TIMEZONE") or "Africa/Casablanca").strip()
    return tz_name or "Africa/Casablanca"


def _now_for_timetable() -> datetime:
    """Retourne l'heure courante dans le fuseau applicatif (Maroc par defaut)."""
    tz_name = _app_timezone_name()
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(tz_name))
        except Exception as exc:
            logger.debug(f"Invalid timezone '{tz_name}', using local fallback: {exc}")
    return datetime.now().astimezone()


def _resolve_target_day(question: str):
    """
    Résout le jour cible pour les questions d'emploi du temps.
    Priorité:
    1) Jour explicite (lundi, mardi, ...)
    2) Date relative/naturelle (aujourd'hui, hier, demain, ...)
    Retourne (jour_canonique | None).
    """
    explicit = _detect_jour(question)
    if explicit:
        return explicit

    qn = normalize(question)
    now_local = _now_for_timetable()

    # Regles deterministes pour les expressions relatives les plus courantes.
    if any(k in qn for k in ["aujourd'hui", "aujourdhui", "actuellement", "maintenant", "en ce moment", "today"]):
        return _day_from_weekday_idx(now_local.weekday())
    if "avant-hier" in qn or "avant hier" in qn or "day before yesterday" in qn:
        return _day_from_weekday_idx((now_local - timedelta(days=2)).weekday())
    if "hier" in qn or "yesterday" in qn:
        return _day_from_weekday_idx((now_local - timedelta(days=1)).weekday())
    if "apres-demain" in qn or "apres demain" in qn or "day after tomorrow" in qn:
        return _day_from_weekday_idx((now_local + timedelta(days=2)).weekday())
    if "demain" in qn or "tomorrow" in qn:
        return _day_from_weekday_idx((now_local + timedelta(days=1)).weekday())

    if dateparser is None:
        return None

    temporal_cues = [
        "aujourd", "actuellement", "maintenant", "en ce moment",
        "hier", "avant-hier", "avant hier", "demain", "apres-demain", "apres demain",
        "today", "yesterday", "tomorrow", "day after tomorrow", "day before yesterday",
        "prochain", "dernier", "next", "last",
    ]
    if not any(cue in qn for cue in temporal_cues):
        return None

    try:
        parsed = dateparser.parse(
            question,
            languages=["fr", "en"],
            settings={
                "RELATIVE_BASE": now_local,
                "PREFER_DATES_FROM": "current_period",
                "TIMEZONE": _app_timezone_name(),
                "TO_TIMEZONE": _app_timezone_name(),
                "RETURN_AS_TIMEZONE_AWARE": True,
            },
        )
        if parsed:
            return _day_from_weekday_idx(parsed.weekday())
    except Exception:
        return None

    return None


def _resolved_day_label(question: str, jour: str) -> str:
    """Retourne un libelle naturel du jour cible (Demain, Aujourd'hui, etc.)."""
    qn = normalize(question)
    if "demain" in qn or "tomorrow" in qn:
        return f"Demain ({jour})"
    if "aujourd" in qn or "today" in qn:
        return f"Aujourd'hui ({jour})"
    if "hier" in qn or "yesterday" in qn:
        return f"Hier ({jour})"
    return f"Cours du {jour}"


def _detect_smalltalk(question: str):
    q = question.lower()
    greetings = ["salut", "bonjour", "cc", "coucou", "hey", "hello"]
    thanks = ["merci", "thanks", "thx", "merci beaucoup"]
    howare = ["ça va", "ca va", "comment ça va", "comment vas-tu", "how are you"]

    for g in greetings:
        if g in q:
            return ("greeting", secrets.choice(["Salut!", "Bonjour!", "Coucou!"]))
    for t in thanks:
        if t in q:
            return ("thanks", secrets.choice(["Avec plaisir!", "De rien !", "Je t'en prie."]))
    for h in howare:
        if h in q:
            return ("howare", secrets.choice(["Ça va bien, merci 🙂", "Très bien, et toi ?", "Tout va bien ici — comment puis-je t'aider ?"]))
    return None


def _detect_user_state(question: str) -> str | None:
    """Détecte un état émotionnel simple à partir du message utilisateur."""
    label, _, _, _ = _detect_user_state_hybrid(question, history=None, language=None)
    return label


def _apply_emotional_tone(answer: str, user_state: str | None) -> str:
    if not answer or not user_state:
        return answer

    lang = _detect_language(answer)
    by_lang = SUPPORTIVE_PREFIXES.get(lang) or SUPPORTIVE_PREFIXES["fr"]
    prefix = by_lang.get(user_state)
    if not prefix:
        return answer

    if answer.startswith(prefix):
        return answer

    return f"{prefix}\n\n{answer}"


def _detect_keywords(question: str, keywords: list) -> bool:
    q = normalize(question)
    return any(normalize(kw) in q for kw in keywords)


def _tokenize_normalized(question: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalize(question))


def _has_timetable_phrase(question: str) -> bool:
    qn = normalize(question)
    patterns = [
        r"\bemplo\w*\b\s+(?:du|de la|de l|de)\s+\btemp\w*\b",
        r"\bemploi\w*\b\s+\btemp\w*\b",
        r"\bedt\b",
        r"\btime\s*table\b",
        r"\btimetable\b",
        r"\bschedule\b",
    ]
    return any(re.search(pattern, qn) for pattern in patterns)


def _looks_like_program_catalog_request(question: str) -> bool:
    qn = normalize(question)
    if not qn or _has_timetable_phrase(question):
        return False

    teacher_lookup_markers = [
        "qui enseigne", "quel prof", "quels prof", "professeur de", "enseignant de",
    ]
    if any(marker in qn for marker in teacher_lookup_markers):
        return False

    if re.search(r"\bstages?\b|\bpfe\b", qn) and not re.search(r"\bstage\s*[12]\b", qn):
        return False

    live_markers = [
        "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi",
        "aujourd", "demain", "hier", "semaine", "maintenant", "prochain",
        "today", "tomorrow", "this week",
    ]
    if any(marker in qn for marker in live_markers):
        return False
    if re.search(r"\b([01]?\d|2[0-3])\s*(?:h|:)\s*([0-5]?\d)?\b", qn):
        return False

    track_aliases = [
        "iacs", "intelligence artificielle", "cybersecurite", "cyber securite",
        "tdi", "transformation digitale", "transformation numerique", "industrie 4.0", "industrie 4 0",
        "g2er", "genie electrique", "energies renouvelables",
        "iaa", "industrie agroalimentaire", "industries agroalimentaires", "agroalimentaire",
        "2ap", "cycle preparatoire",
    ]
    has_track = any(re.search(rf"\b{re.escape(alias)}\b", qn) for alias in track_aliases)
    has_semester = bool(re.search(r"\b(?:s\s*[1-6]|semestre\s*[1-6])\b", qn))
    has_program_cue = any(
        re.search(rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])", qn)
        for marker in [
            "programme", "formation", "module", "modules", "matiere", "matieres",
            "cours", "brochure", "enseigne", "enseignes", "etudie", "fait",
            "font", "dans quel semestre", "en quel semestre", "quel semestre",
            "quelle annee", "quand",
        ]
    )
    has_module_name = any(
        marker in qn
        for marker in [
            "blockchain", "devops", "devsecops", "haccp", "smart factory",
            "machine learning", "deep learning", "forensics", "cryptographie",
            "iot", "toxicologie", "systemes solaires", "genie logiciel",
        ]
    )
    has_module_lookup_cue = any(
        marker in qn
        for marker in [
            "cours", "module", "matiere", "enseigne", "etudie", "fait",
            "dans quel semestre", "en quel semestre", "quel semestre",
            "quelle annee", "quand", "se trouve", "est ce que",
        ]
    )
    return has_track and (
        (has_semester and has_program_cue)
        or (has_module_name and has_program_cue)
        or (has_program_cue and has_module_lookup_cue)
    )


def _looks_like_timetable_request(question: str) -> bool:
    if _has_timetable_phrase(question):
        return True

    if _looks_like_program_catalog_request(question):
        return False

    qn = normalize(question)
    tokens = _tokenize_normalized(question)
    if not tokens:
        return False

    stems = [
        "emplo", "temp", "edt", "plan", "horair", "sched", "timet", "cours", "class", "fili",
        "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "aujourd", "demain", "hier", "semaine",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "morning", "afternoon",
    ]
    stem_hits = sum(1 for tok in tokens if any(tok.startswith(stem) for stem in stems))
    if stem_hits >= 2:
        return True

    has_semester = bool(re.search(r"\bs\s?\d{1,2}\b", qn))
    has_track = bool(re.search(r"\b(iacs|tdi|g2er|iaa|2ap|classe|filiere)\b", qn))
    return has_semester and has_track


def _render_full_timetable_text(emploi_json: dict, concise: bool = False) -> str:
    sections = ["## 📅 Emploi du temps"]
    if concise:
        sections.append("**Lecture rapide :** heures, modules, professeurs et salles sont déjà mis en avant.")
    else:
        sections.extend([
            "> Les heures, les modules, les professeurs et les salles sont mis en évidence pour une lecture rapide.",
            "",
        ])
    active_days = 0
    total_sessions = 0
    for jour_name in ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]:
        modules = emploi_json.get(jour_name, [])
        seen, unique = set(), []
        for m in modules:
            key = (m.get("heure", ""), m.get("contenu", ""))
            if key not in seen:
                seen.add(key)
                unique.append(m)
        if unique:
            active_days += 1
            total_sessions += len(unique)
            sections.append(f"### {jour_name}")
            sections.append(_format_seances(unique))
            sections.append("")

    if total_sessions == 0:
        return "Je n'ai trouvé aucun créneau publié pour cette classe. Vérifie que l'emploi du temps a bien été importé ou activé."

    summary = f"**Résumé :** {total_sessions} séance(s) sur {active_days} jour(s)."
    return "\n".join([sections[0], summary, *sections[1:]]).strip()


def _format_seances(modules: list, concise: bool = False) -> str:
    if not modules:
        return "Aucun cours. 🎉"
    lines = []
    for m in modules:
        seance = m.get("seance", "")
        prof   = m.get("professeur", "")
        heure  = m.get("heure", "")
        contenu = m.get("contenu", "")
        salle = m.get("salle", "")
        line = f"• **{heure}** — **{contenu}**"
        if prof:
            professor = _format_professor_name(prof)
            line += f" · {professor}" if concise else f" — {professor}"
        if salle:
            line += f" · Salle {salle}" if concise else f" — Salle {salle}"
        if seance:
            line += f" · _{seance}_" if concise else f" — _{seance}_"
        lines.append(line)
    return "\n".join(lines)


def _format_professor_name(professor: str) -> str:
    value = str(professor or "").strip()
    if not value:
        return ""
    if re.match(r"(?i)^(?:pr|prof|professeur|dr|doctor|enseignant)\.?\b", value):
        return value
    return f"Prof. {value}"


def _slot_start_minutes(module: dict) -> int | None:
    heure = str(module.get("heure", ""))
    match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", heure)
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def _time_of_day_label(question: str) -> str | None:
    qn = normalize(question)
    if any(marker in qn for marker in ["matin", "morning"]):
        return "matin"
    if any(marker in qn for marker in ["apres midi", "apres-midi", "aprem", "afternoon"]):
        return "apres-midi"
    return None


def _filter_modules_by_time_of_day(modules: list, question: str) -> tuple[list, str | None]:
    period = _time_of_day_label(question)
    if not period:
        return modules, None

    filtered = []
    for module in modules:
        start = _slot_start_minutes(module)
        if start is None:
            continue
        if period == "matin" and start < 13 * 60:
            filtered.append(module)
        elif period == "apres-midi" and start >= 13 * 60:
            filtered.append(module)
    return filtered, period


def _search_prof(query: str, emploi_json: dict) -> str:
    """Cherche un prof dans tout l'emploi du temps (insensible aux accents/casse)."""
    q = normalize(query)
    results = []
    seen = set()
    for jour, modules in emploi_json.items():
        for m in modules:
            prof    = m.get("professeur", "")
            contenu = m.get("contenu", "")
            key = (jour, m.get("heure", ""), contenu)
            if key in seen:
                continue
            if q in normalize(prof):
                seen.add(key)
                results.append(
                    f"• **{jour}** {m.get('heure', '')} — {contenu}"
                    + (f" ({prof})" if prof else "")
                )
    if results:
        return "Résultats trouvés :\n" + "\n".join(results)
    return ""


def _search_teacher_for_module(query: str, emploi_json: dict) -> str:
    q = normalize(query)
    q = re.sub(r"\b(?:semestre|semester|sem)\s*([1-6])\b", r"s\1", q)
    q = re.sub(r"\bs\s+([1-6])\b", r"s\1", q)
    q = re.sub(r"\b(?:pour|de|du|en|dans)\s+(?:iacs|tdi|g2er|iaa|2ap)(?:\s+s\d+)?\b", " ", q)
    q = re.sub(r"\b(?:qui|enseigne|prof|professeur|enseignant|donne|cours|module|matiere)\b", " ", q)
    q = re.sub(r"\b(?:iacs|tdi|g2er|iaa|2ap|s[1-6])\b", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    if len(q) < 3:
        return ""
    query_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", q)
        if len(token) >= 2 and token not in {"de", "du", "des", "la", "le", "les", "et", "en", "a", "l"}
    }

    results = []
    seen = set()
    for jour, modules in emploi_json.items():
        for module in modules:
            contenu = module.get("contenu", "")
            prof = module.get("professeur", "")
            if not prof:
                continue
            normalized_content = normalize(contenu)
            content_tokens = {
                token
                for token in re.findall(r"[a-z0-9]+", normalized_content)
                if len(token) >= 2 and token not in {"de", "du", "des", "la", "le", "les", "et", "en", "a", "l"}
            }
            token_match = bool(query_tokens) and (
                query_tokens.issubset(content_tokens)
                or len(query_tokens & content_tokens) >= min(3, len(query_tokens))
            )
            if q in normalized_content or normalized_content in q or token_match:
                key = (jour, module.get("heure", ""), contenu, prof)
                if key in seen:
                    continue
                seen.add(key)
                results.append(
                    f"* **{jour}** {module.get('heure', '')} - {contenu} ({prof})"
                )
    if results:
        return "Enseignant trouve :\n" + "\n".join(results)
    return ""


def _is_teacher_for_module_lookup(question: str) -> bool:
    q = normalize(question)
    if not q:
        return False

    if _is_professor_list_request(question):
        return False

    if any(marker in q for marker in ["qui enseigne", "qui donne", "qui assure", "who teaches", "who gives"]):
        return True
    if any(marker in q for marker in ["quel prof", "quels prof", "quelle prof", "enseignant de", "professeur de"]):
        return True
    if "teacher" in q and any(marker in q for marker in ["for", "of", "module", "course", "subject"]):
        return True
    return False


def _clean_professor_lookup_name(name: str) -> str:
    cleaned = normalize(name or "")
    cleaned = re.sub(r"\b(?:le|la|les|un|une|du|de|des|d|mr|mme|m)\b", " ", cleaned)
    cleaned = re.split(
        r"\b(?:enseigne|enseignes|donne|module|modules|matiere|matieres|cours|quel|quelle|quels|quelles|"
        r"en|dans|pour|iacs|tdi|g2er|iaa|2ap|semestre|s\s*[1-6])\b",
        cleaned,
        maxsplit=1,
    )[0]
    cleaned = re.sub(r"[^a-z0-9\s\-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _extract_professor_lookup_name(question: str) -> str:
    q = normalize(question)
    if not q:
        return ""

    patterns = [
        r"\b(?:pr|prof|professeur|enseignant|enseignante|teacher|professor)\.?\s+([a-z0-9\s\-]+)",
        r"\b([a-z0-9][a-z0-9\s\-]{1,60})\s+(?:enseigne|donne)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, q)
        if not match:
            continue
        name = _clean_professor_lookup_name(match.group(1))
        tokens = [token for token in name.split() if len(token) > 1]
        if tokens:
            return " ".join(tokens[:4])
    return ""


def _search_modules_for_professor(name: str, emploi_json: dict) -> str:
    q = _clean_professor_lookup_name(name)
    tokens = [token for token in q.split() if len(token) > 1]
    if not tokens:
        return ""

    results = []
    seen = set()
    for jour, modules in emploi_json.items():
        for module in modules:
            prof = module.get("professeur", "")
            prof_norm = normalize(prof)
            if not prof_norm:
                continue
            if not (q in prof_norm or all(token in prof_norm for token in tokens)):
                continue
            key = (jour, module.get("heure", ""), module.get("contenu", ""), prof)
            if key in seen:
                continue
            seen.add(key)
            room = module.get("salle", "")
            room_suffix = f" - Salle {room}" if room else ""
            results.append(
                f"* **{jour}** {module.get('heure', '')} - {module.get('contenu', '')} ({prof}){room_suffix}"
            )

    if results:
        return "Modules trouves pour ce professeur :\n" + "\n".join(results)
    return ""


def _is_professor_list_request(question: str) -> bool:
    q = normalize(question)
    return any(
        marker in q
        for marker in [
            "liste des prof",
            "liste les prof",
            "tous les prof",
            "toutes les prof",
            "quels sont les prof",
            "quelles sont les prof",
            "professeurs dans l emploi",
            "enseignants dans l emploi",
            "professeurs apparaissent",
            "profs apparaissent",
            "professeurs presents",
            "enseignants presents",
            "quels professeurs apparaissent",
            "quels enseignants apparaissent",
            "professeurs du planning",
            "enseignants du planning",
        ]
    )


def _search_module(query: str, emploi_json: dict) -> str:
    """Cherche un module dans tout l'emploi du temps (insensible aux accents/casse)."""
    q = normalize(query)
    results = []
    seen = set()
    for jour, modules in emploi_json.items():
        for m in modules:
            contenu = m.get("contenu", "")
            prof    = m.get("professeur", "")
            key = (jour, m.get("heure", ""), contenu)
            if key in seen:
                continue
            if q in normalize(contenu):
                seen.add(key)
                results.append(
                    f"• **{jour}** {m.get('heure', '')} — {contenu}"
                    + (f" ({prof})" if prof else "")
                )
    if results:
        return "Résultats trouvés :\n" + "\n".join(results)
    return ""


# ─────────────────────────────────────────────────
# MODE 1 : STRUCTURED
# ─────────────────────────────────────────────────

def _pick_intro(kind: str, class_label: str | None = None) -> str:
    """Retourne une phrase d'accroche légère selon le type de réponse."""
    baselines = {
        "day": [
            "Parfait, voici ton planning :",
            "D'accord, allons droit au but :",
            "Pour ta classe{} :".format(f" ({class_label})" if class_label else ""),
        ],
        "list": [
            "Je te partage les informations utiles :",
            "Voici les détails :",
            "Très bien, voilà l'essentiel :",
        ],
        "info_empty": [
            "Je n'ai pas trouvé d'emploi du temps pour cette classe.",
            "Aucun EDT importé pour le moment pour cette filière.",
            "Rien n'a encore été chargé pour cette classe—tu peux importer un PDF si nécessaire.",
        ]
    }
    return secrets.choice(baselines.get(kind, ["Voici :"]))


def _reformat_with_groq_stream(raw_answer: str, question: str, class_label: str | None = None, user_state: str | None = None):
    """
    Reformule une réponse brute en streaming via Groq.
    """
    if not raw_answer or raw_answer.startswith("❌"):
        yield raw_answer
        return
    
    try:
        from backend.services.groq_service import reformat_with_groq_stream
        yield from reformat_with_groq_stream(raw_answer, question, class_label, user_state=user_state)
    except Exception:
        yield raw_answer


def ask_question_structured_stream(
    question: str,
    emploi_json: dict,
    calendrier_json: dict = None,
    class_label: str | None = None,
    user_state: str | None = None,
):
    """
    Version streaming de ask_question_structured.
    """
    raw_answer = _ask_question_structured_raw(question, emploi_json, calendrier_json, class_label, user_state=user_state)
    if os.getenv("ENABLE_EDT_LLM", "false").lower() != "true":
        yield raw_answer
        return
    yield from _reformat_with_groq_stream(raw_answer, question, class_label, user_state=user_state)


def ask_question_structured(
    question: str,
    emploi_json: dict,
    calendrier_json: dict = None,
    class_label: str | None = None,
    user_state: str | None = None,
) -> str:
    """
    Extrait info du JSON emploi du temps, puis reformule via Groq
    pour une réponse naturelle et conversationnelle.
    """
    from backend.services.cache_service import get_cached_response, set_cached_response
    
    # Cache key includes class and state so the tone/context stays consistent.
    cache_query = f"v6:{class_label or 'no_class'}:{user_state or 'neutral'}:{question}"
    cached = get_cached_response("edt", cache_query)
    if cached:
        return cached

    raw_answer = _ask_question_structured_raw(question, emploi_json, calendrier_json, class_label, user_state=user_state)

    if os.getenv("ENABLE_EDT_LLM", "false").lower() != "true":
        if raw_answer:
            set_cached_response("edt", cache_query, raw_answer)
        return raw_answer

    # Si la réponse est bonne (pas d'erreur), reformuler avec Groq
    if raw_answer and not raw_answer.startswith("❌"):
        from backend.services.groq_service import reformat_with_groq
        ans = reformat_with_groq(raw_answer, question, class_label, user_state=user_state)
        set_cached_response("edt", cache_query, ans)
        return ans
    
    return raw_answer


def _ask_question_structured_raw(
    question: str,
    emploi_json: dict,
    calendrier_json: dict = None,
    class_label: str | None = None,
    user_state: str | None = None,
) -> str:
    """Extrait l'info du JSON sans reformulation LLM (brut)."""
    q = question.lower()
    qn = normalize(question)
    if user_state is None:
        user_state = _detect_user_state(question)

    # Small-talk handling (greetings, thanks, how-are-you)
    small = _detect_smalltalk(question)
    if small:
        t, reply = small
        if t == "greeting":
            if class_label:
                return _apply_emotional_tone(
                    f"{reply} Je vois que tu es en **{class_label}**. Veux-tu que je consulte ton emploi du temps ou que je réponde à une question ?",
                    user_state,
                )
            return _apply_emotional_tone(
                f"{reply} Je suis le chatbot de l'ENSAM Béni Mellal — je peux t'aider avec les emplois du temps. Tu es en quelle classe ?",
                user_state,
            )
        if t == "thanks":
            return _apply_emotional_tone(reply, user_state)
        if t == "howare":
            return _apply_emotional_tone(reply, user_state)

    # ── 1. Jour cible (explicite ou relatif) ──
    jour = _resolve_target_day(question)
    if jour:
        modules = emploi_json.get(jour, [])
        # Dédoublonner (même module même heure)
        seen, unique = set(), []
        for m in modules:
            key = (m.get("heure", ""), m.get("contenu", ""))
            if key not in seen:
                seen.add(key)
                unique.append(m)
        unique, period = _filter_modules_by_time_of_day(unique, question)
        if not unique:
            return _apply_emotional_tone(
                f"Aucun cours n'est prévu le {jour}. Si tu veux, je peux aussi te montrer un autre jour ou l'emploi du temps complet.",
                user_state,
            )
        intro = f"Pour la filiere {class_label}," if class_label else _pick_intro("day", class_label)
        period_suffix = f" {period}" if period else ""
        header = f"**{_resolved_day_label(question, jour)}{period_suffix} :**\n"
        summary = f"**{len(unique)} séance(s)**"
        if period:
            summary += f" · **{period}**"
        return _apply_emotional_tone(f"{intro}\n\n{summary}\n\n{header}{_format_seances(unique)}", user_state)

    # ── 2. Professeur ──
    if _detect_keywords(q, ["prof", "professeur", "enseignant", "qui enseigne", "qui donne", "teacher", "professor", "who teaches", "who gives"]) or _extract_professor_lookup_name(question):
        if _is_professor_list_request(question):
            profs = sorted({
                m.get("professeur")
                for modules in emploi_json.values()
                for m in modules
                if m.get("professeur")
            })
            if profs:
                return _apply_emotional_tone(
                    f"{_pick_intro('list', class_label)}\n\n**Professeurs dans l'emploi du temps :**\n" + "\n".join(f"- {p}" for p in profs),
                    user_state,
                )

        if _is_teacher_for_module_lookup(question):
            teacher_result = _search_teacher_for_module(question, emploi_json)
            if teacher_result:
                return _apply_emotional_tone(f"{_pick_intro('list', class_label)}\n\n{teacher_result}", user_state)
            return _apply_emotional_tone(
                f"Je n'ai pas trouve d'enseignant correspondant dans l'emploi du temps de {class_label or 'cette classe'}. "
                "Verifie le nom du module ou precise la filiere/semestre.",
                user_state,
            )

        professor_name = _extract_professor_lookup_name(question)
        if professor_name:
            result = _search_modules_for_professor(professor_name, emploi_json)
            if result:
                return _apply_emotional_tone(f"{_pick_intro('list', class_label)}\n\n{result}", user_state)
            return _apply_emotional_tone(
                f"Je n'ai pas trouve ce professeur dans l'emploi du temps de {class_label or 'cette classe'}. "
                "Verifie l'orthographe ou precise la filiere/semestre.",
                user_state,
            )

        teacher_result = _search_teacher_for_module(question, emploi_json)
        if teacher_result:
            return _apply_emotional_tone(f"{_pick_intro('list', class_label)}\n\n{teacher_result}", user_state)

        # Extraire le nom après le mot-clé
        match = re.search(
            r'(?:prof(?:esseur)?|enseignant|enseigne|donne)\s+([a-zA-ZÀ-ÿ0-9\s\-]+)',
            q
        )
        if match:
            name = match.group(1).strip()
            result = _search_prof(name, emploi_json)
            if result:
                return _apply_emotional_tone(f"{_pick_intro('list', class_label)}\n\n{result}", user_state)
        # Pas de nom → lister tous les profs
        profs = sorted({
            m.get("professeur")
            for modules in emploi_json.values()
            for m in modules
            if m.get("professeur")
        })
        if profs:
            return _apply_emotional_tone(
                f"{_pick_intro('list', class_label)}\n\n**Professeurs dans l'emploi du temps :**\n" + "\n".join(f"• {p}" for p in profs),
                user_state,
            )

    # ── 3. Module / matière ──
    if _detect_keywords(q, ["module", "cours de", "matière", "quand", "quel jour", "course", "subject", "when is", "which day"]):
        # Extraire ce qui suit le mot-clé
        match = re.search(
            r'(?:module|cours de|mati[eè]re|quand est|quel jour)\s+([a-zA-ZÀ-ÿ0-9\s\-]+)',
            q
        )
        if match:
            name = match.group(1).strip()
            result = _search_module(name, emploi_json)
            if result:
                return _apply_emotional_tone(f"{_pick_intro('list', class_label)}\n\n{result}", user_state)
        # Pas de nom → lister tous les modules
        modules = sorted({
            m.get("contenu")
            for modules in emploi_json.values()
            for m in modules
            if m.get("contenu")
        })
        if modules:
            return _apply_emotional_tone(
                f"{_pick_intro('list', class_label)}\n\n**Modules dans l'emploi du temps :**\n" + "\n".join(f"• {m}" for m in modules),
                user_state,
            )

    # ── 4. Calendrier examens ──
    if _detect_keywords(q, ["examen", "exam", "contrôle", "rattrapage", "calendrier", "partiel"]):
        if calendrier_json:
            results = []
            for item in calendrier_json.get("examens", []):
                results.append(
                    f"• **{item.get('module', '')}** — {item.get('date', '')} "
                    f"à {item.get('heure', '')} — Salle : {item.get('salle', 'TBD')}"
                )
            if results:
                return _apply_emotional_tone(f"{_pick_intro('list', class_label)}\n\n**Calendrier des examens :**\n" + "\n".join(results), user_state)
        return _apply_emotional_tone("⚠️ Aucun calendrier d'examens disponible pour le moment.", user_state)

    # ── 5. Vue globale ──
    if _detect_keywords(q, [
        "emploi du temps",
        "emploi de temps",
        "emploi temps",
        "edt",
        "planning",
        "semaine",
        "tout",
        "complet",
        "horaire",
        "schedule",
        "timetable",
    ]) or _looks_like_timetable_request(question):
        return _apply_emotional_tone(_render_full_timetable_text(emploi_json), user_state)

    # ── Recherche libre dans tout l'EDT ──
    # Si la question contient un mot long, on tente une recherche dans les modules
    mots_significatifs = [m for m in qn.split() if len(m) > 4]
    for mot in mots_significatifs:
        result = _search_module(mot, emploi_json)
        if result:
            return _apply_emotional_tone(f"{_pick_intro('list', class_label)}\n\n{result}", user_state)
        result = _search_prof(mot, emploi_json)
        if result:
            return _apply_emotional_tone(f"{_pick_intro('list', class_label)}\n\n{result}", user_state)

    # Dernier filet de securite: eviter une reponse ❌ pour une question qui ressemble clairement a l'EDT.
    if _looks_like_timetable_request(question):
        return _apply_emotional_tone(_render_full_timetable_text(emploi_json), user_state)

    return _apply_emotional_tone(
        "Je n'ai pas encore trouvé une réponse fiable pour cette question. Essaie de préciser la classe, le jour ou le module, ou écris simplement 'emploi du temps'.",
        user_state,
    )


# ─────────────────────────────────────────────────
# MODE 2 : RAG FAQ
# ─────────────────────────────────────────────────

_FAQ_SUBQUESTION_START = re.compile(
    r"\b(?:qui est|que signifie|quel(?:le)?s?\s+(?:est|sont)|combien|ou se situe|où se situe|comment|a quelle|à quelle|c[' ]?est quoi)\b",
    flags=re.IGNORECASE,
)


def _split_compound_faq_question(question: str) -> list[str]:
    raw = (question or "").strip()
    if not raw:
        return []

    parts: list[str] = []
    for chunk in re.split(r"\?\s*", raw):
        chunk = chunk.strip(" .;,\n\t")
        if chunk:
            parts.append(chunk)

    if len(parts) > 1:
        normalized = []
        for part in parts:
            normalized.append(part if part.endswith("?") else f"{part} ?")
        return normalized[:3]

    connector_split = re.split(
        r"\s+(?:et|puis|ensuite)\s+(?=(?:qui est|que signifie|quel(?:le)?s?\s+(?:est|sont)|combien|ou se situe|où se situe|comment|a quelle|à quelle|c[' ]?est quoi))",
        raw,
        flags=re.IGNORECASE,
    )
    connector_split = [part.strip(" .;,\n\t") for part in connector_split if part.strip(" .;,\n\t")]
    if len(connector_split) > 1 and all(_FAQ_SUBQUESTION_START.search(part) for part in connector_split):
        return [part if part.endswith("?") else f"{part} ?" for part in connector_split[:3]]

    return [raw]


def _join_compound_faq_answers(answers: list[str]) -> str:
    cleaned = [answer.strip() for answer in answers if answer and answer.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    return " ".join(cleaned)


def _style_direct_answer(answer: str, question: str, user_state: str | None = None, language: str = "fr") -> str:
    if not answer:
        return answer
    try:
        from backend.services.groq_service import _finalize_answer_style

        return _finalize_answer_style(answer, question, user_state=user_state, language_hint=language)
    except Exception as exc:
        logger.debug(f"Direct answer styling failed: {exc}")
        return answer


def ask_question_rag_stream(question: str, history: list[dict] | None = None, user_state: str | None = None, language: str = "fr"):
    """
    RAG-based response using GroqCloud with streaming.
    Yields chunks of text, and finally a special marker for metadata if needed.
    """
    # --- Gestion des salutations simples (Direct Answer sans RAG) ---
    clean_q = (question or "").lower().strip().replace("?", "").replace("!", "")
    greetings = {"hello", "hi", "hey", "salut", "bonjour", "bonsoir", "coucou", "yo", "morning"}
    if clean_q in greetings:
        if language == "en":
            yield "Hello! I am your AI Assistant Agent at ENSA Béni Mellal. How can I help you with your studies or schedule today?"
        elif language == "ar":
            yield "مرحباً! أنا مساعدك الذكي في المدرسة الوطنية للعلوم التطبيقية ببني ملال. كيف يمكنني مساعدتك في دراستك أو جدولك اليوم؟"
        else:
            yield "Bonjour ! Je suis ton assistant intelligent (AI Assistant Agent) de l'ENSA Béni Mellal. Comment puis-je t'aider pour tes études ou ton emploi du temps aujourd'hui ?"
        return

    try:
        from backend.services.rag_service import search_context
    except Exception as e:
        logger.error(f"RAG import error: {e}")
        yield ""
        return

    try:
        from backend.services.router_service import _official_fast_fact_answer
        fast_answer = _official_fast_fact_answer(question)
        if fast_answer:
            yield fast_answer
            yield f"__metadata__:{json.dumps({'source_files': None, 'rag_confidence': 'high', 'rag_score': 1.0})}"
            return
    except Exception:
        pass

    subquestions = _split_compound_faq_question(question)
    if len(subquestions) > 1:
        answer, _, _ = ask_question_rag(question, history=history, user_state=user_state, language=language)
        if answer:
            yield answer
        else:
            yield ""
        return

    try:
        from backend.services.rag_service import _find_direct_faq_answer
    except Exception:
        _find_direct_faq_answer = None

    if _find_direct_faq_answer:
        direct_answer, direct_sources, direct_score = _find_direct_faq_answer(question)
        if direct_answer:
            direct_answer = _style_direct_answer(direct_answer, question, user_state=user_state, language=language)
            yield direct_answer
            yield f"__metadata__:{json.dumps({'source_files': direct_sources, 'rag_confidence': 'high', 'rag_score': round(direct_score, 2)})}"
            return

    context, sources, rag_score = search_context(question)
    if rag_score < 0.35:
        yield ""
        return

    lowered = (context or "").lower()
    if (not context) or ("aucune information" in lowered) or ("erreur lors de la recherche" in lowered):
        yield ""
        return

    try:
        from backend.services.groq_service import answer_faq_with_groq_stream
        # We can't easily yield sources in the middle of a text stream 
        # without a protocol. For now, we'll just yield the text.
        # The caller (router) will handle the sources.
        yield from answer_faq_with_groq_stream(question, context, history=history, user_state=user_state, language_hint=language)
        
        # Meta yield at the end
        confidence = "high"
        if rag_score < 0.4: confidence = "low"
        elif rag_score < 0.7: confidence = "medium"
        
        yield f"__metadata__:{json.dumps({'source_files': sources, 'rag_confidence': confidence, 'rag_score': round(rag_score, 2)})}"
    except Exception as e:
        logger.error(f"⚠️  Erreur RAG avec GroqCloud (stream) : {e}")
        yield ""


def ask_question_rag(question: str, history: list[dict] | None = None, user_state: str | None = None, language: str = "fr") -> Tuple[str, str | None, float]:
    """
    RAG-based response using GroqCloud.
    Returns (answer, source_files, score).
    """
    from backend.services.cache_service import get_cached_response, set_cached_response
    import json
    
    # History impacts context, so it should be part of the cache key if present.
    # For now, we only cache when history is empty for simplicity.
    cache_query = f"v5:{language or 'fr'}:{user_state or 'neutral'}:{question}"
    if not history:
        cached = get_cached_response("rag", cache_query)
        if cached:
            try:
                data = json.loads(cached)
                return data["ans"], data["sources"], data.get("score", 0.0)
            except:
                return cached, None, 0.0

    try:
        from backend.services.rag_service import search_context
    except Exception as e:
        logger.error(f"RAG import error: {e}")
        return "", None, 0.0

    try:
        from backend.services.router_service import _official_fast_fact_answer
        fast_answer = _official_fast_fact_answer(question)
        if fast_answer:
            return fast_answer, None, 1.0
    except Exception:
        pass

    subquestions = _split_compound_faq_question(question)
    if len(subquestions) > 1:
        try:
            from backend.services.groq_service import answer_faq_with_groq, is_cacheable_faq_answer
        except Exception as e:
            logger.error(f"⚠️  Erreur RAG avec GroqCloud : {e}")
            return "", None, 0.0

        sub_answers = []
        collected_sources = []
        max_rag_score = 0.0
        for subquestion in subquestions:
            context, sources, rag_score = search_context(subquestion)
            max_rag_score = max(max_rag_score, rag_score)
            lowered = (context or "").lower()
            if (not context) or ("aucune information" in lowered) or ("erreur lors de la recherche" in lowered):
                continue
            answer = answer_faq_with_groq(subquestion, context, history=history, user_state=user_state, language_hint=language)
            if answer:
                sub_answers.append(answer)
            if sources:
                collected_sources.append(sources)

        joined_answer = _join_compound_faq_answers(sub_answers)
        joined_sources = ", ".join(dict.fromkeys(collected_sources)) if collected_sources else None
        if joined_answer:
            if not history and is_cacheable_faq_answer(joined_answer):
                set_cached_response("rag", cache_query, json.dumps({"ans": joined_answer, "sources": joined_sources, "score": max_rag_score}))
            return joined_answer, joined_sources, max_rag_score
        return "", None, 0.0

    try:
        from backend.services.rag_service import _find_direct_faq_answer
    except Exception:
        _find_direct_faq_answer = None

    if _find_direct_faq_answer:
        direct_answer, direct_sources, direct_score = _find_direct_faq_answer(question)
        if direct_answer:
            styled_answer = _style_direct_answer(direct_answer, question, user_state=user_state, language=language)
            if not history:
                try:
                    from backend.services.groq_service import is_cacheable_faq_answer
                    if is_cacheable_faq_answer(styled_answer):
                        set_cached_response("rag", cache_query, json.dumps({"ans": styled_answer, "sources": direct_sources, "score": direct_score}))
                except Exception:
                    pass
            return styled_answer, direct_sources, direct_score

    context, sources, rag_score = search_context(question)
    if rag_score < 0.35:
        return "", None, 0.0

    lowered = (context or "").lower()
    if (not context) or ("aucune information" in lowered) or ("erreur lors de la recherche" in lowered):
        return "", None, 0.0

    try:
        from backend.services.groq_service import answer_faq_with_groq, is_cacheable_faq_answer
        ans = answer_faq_with_groq(question, context, history=history, user_state=user_state, language_hint=language)
        
        if not history and is_cacheable_faq_answer(ans):
            set_cached_response("rag", cache_query, json.dumps({"ans": ans, "sources": sources, "score": rag_score}))
            
        return ans, sources, rag_score
    except Exception as e:
        logger.error(f"⚠️  Erreur RAG avec GroqCloud : {e}")
        return "", None, 0.0
