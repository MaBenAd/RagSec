from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pdfplumber

ROOT_DIR = Path(__file__).resolve().parents[2]
TMP_DIR = ROOT_DIR / "tmp" / "rag_benchmark"
RESULTS_DIR = TMP_DIR / "results"
TRANSLATIONS_DIR = TMP_DIR / "translations"
DEFAULT_VECTORSTORE = TMP_DIR / "vectorstore"

os.environ.setdefault("ENABLE_CACHE", "false")
os.environ.setdefault("QDRANT_URL", "")
os.environ.setdefault("VECTORSTORE_PATH", str(DEFAULT_VECTORSTORE))

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from backend.services.groq_service import (  # noqa: E402
    _contains_arabic,
    _detect_question_language,
    _looks_english,
    _looks_french,
    call_groq,
)
from backend.services.rag_service import rebuild_vectorstore  # noqa: E402
from backend.services.router_service import route_question_api  # noqa: E402

FAQ_PATTERN = re.compile(r"Q\s*:\s*(.+?)\s*A\s*:\s*(.+?)(?=Q\s*:|$)", re.DOTALL)
DOC_PREFIX_PATTERN = re.compile(
    r"^\s*(?:le site|la page d'accueil|the website|the homepage|oui[\.,]?|yes[\.,]?)\b",
    re.IGNORECASE,
)
TOKEN_PATTERN = re.compile(r"[a-z0-9]{3,}")
IMPORTANT_ENTITY_PATTERN = re.compile(
    r"https?://\S+|[\w.+-]+@[\w.-]+\.\w+|\b(?:19|20)\d{2}\b|\b(?:2ap|g2er|iaa|iacs|tdi|usms|ensa|ensabm)\b",
    re.IGNORECASE,
)
STOPWORDS = {
    "avec",
    "dans",
    "pour",
    "sans",
    "that",
    "the",
    "this",
    "what",
    "which",
    "who",
    "where",
    "when",
    "comment",
    "combien",
    "quelle",
    "quelles",
    "quels",
    "quel",
    "ainsi",
    "alors",
    "dans",
    "elle",
    "elles",
    "est",
    "font",
    "leur",
    "leurs",
    "mais",
    "meme",
    "nous",
    "pour",
    "sont",
    "tous",
    "toutes",
    "une",
    "des",
    "les",
    "aux",
    "que",
    "qui",
    "sur",
    "and",
    "are",
    "from",
    "have",
    "into",
    "its",
    "with",
}
FRENCH_OMISSION_STOPWORDS = {
    "a", "à", "au", "aux", "de", "des", "du", "d", "l", "le", "la", "les",
    "est", "elle", "il", "ils", "elles", "et", "en", "un", "une", "que",
    "qui", "quels", "quelles", "quel", "quelle", "quand", "ou", "où",
    "se", "s", "t", "te", "tu", "vous", "nous", "je", "moi", "mon", "ma",
}


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    normalized = normalized.lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", normalize_text(value)).strip()


def tokenize(value: str) -> set[str]:
    return {
        token
        for token in TOKEN_PATTERN.findall(normalize_key(value))
        if token not in STOPWORDS
    }


def extract_pairs() -> list[dict[str, Any]]:
    faq_dir = ROOT_DIR / "backend" / "data" / "faq"
    rows: list[dict[str, Any]] = []
    for pdf_path in sorted(faq_dir.glob("*.pdf")):
        full_text = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                full_text.append(page.extract_text() or "")

        joined = "\n".join(full_text)
        for index, (question, answer) in enumerate(FAQ_PATTERN.findall(joined), start=1):
            clean_question = " ".join(question.split())
            clean_answer = " ".join(answer.split())
            rows.append(
                {
                    "id": f"{pdf_path.stem}:{index}",
                    "source_pdf": pdf_path.name,
                    "question_fr": clean_question,
                    "expected_answer_fr": clean_answer,
                    "normalized_question": normalize_key(clean_question),
                }
            )
    return rows


def dedupe_pairs(rows: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    if mode == "none":
        return rows

    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row["normalized_question"]
        deduped.setdefault(key, row)
    return list(deduped.values())


def chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[start : start + size] for start in range(0, len(items), size)]


def apply_typo(word: str) -> str:
    if len(word) < 6 or not re.search(r"[A-Za-zÀ-ÿ]", word):
        return word
    if "'" in word or "’" in word:
        return word.replace("’", "").replace("'", "")
    return word[:2] + word[3:4] + word[2:3] + word[4:]


def mutate_french_question(question: str, variant: str) -> str:
    if variant == "original":
        return question

    stripped = question.strip().rstrip("?").strip()
    if variant == "rephrase":
        replacements = [
            (r"^Quel est", "C'est quoi"),
            (r"^Quelle est", "C'est quoi"),
            (r"^Quels sont", "C'est quoi"),
            (r"^Quelles sont", "Cite-moi"),
            (r"^Combien de", "Il y a combien de"),
            (r"^À quelle université", "Elle dépend de quelle université"),
            (r"^A quelle université", "Elle dépend de quelle université"),
            (r"^Où se situe", "Où se trouve"),
            (r"^Ou se situe", "Où se trouve"),
            (r"^Qui est", "C'est qui"),
            (r"^Que signifie ([A-Za-z0-9-]+)", r"\1 ça veut dire quoi"),
            (r"^Quand ", "En quelle année "),
        ]
        out = stripped
        for pattern, replacement in replacements:
            candidate = re.sub(pattern, replacement, out, count=1, flags=re.IGNORECASE)
            if candidate != out:
                return candidate + " ?"
        return f"Peux-tu me dire {stripped[:1].lower()}{stripped[1:]} ?"

    if variant == "omission":
        normalized = unicodedata.normalize("NFKD", stripped)
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        normalized = normalized.replace("’", " ").replace("'", " ")
        tokens = [token for token in re.findall(r"[A-Za-z0-9]+", normalized.lower()) if token not in FRENCH_OMISSION_STOPWORDS]
        compact = " ".join(tokens[:10]).strip()
        return compact or stripped

    if variant == "typo":
        words = stripped.split()
        mutated = []
        typo_used = False
        for word in words:
            bare = re.sub(r"[^\wÀ-ÿ-]", "", word)
            if not typo_used and len(bare) >= 6 and bare.upper() not in {"ENSA", "BM", "USMS", "IACS", "TDI", "IAA", "G2ER", "2AP"}:
                mutated_word = apply_typo(word)
                mutated.append(mutated_word)
                typo_used = True
            else:
                mutated.append(word)
        out = " ".join(mutated)
        out = unicodedata.normalize("NFKD", out)
        out = "".join(ch for ch in out if unicodedata.category(ch) != "Mn")
        return out + " ?"

    return question


def load_translation_cache(language: str) -> dict[str, str]:
    path = TRANSLATIONS_DIR / f"{language}.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_translation_cache(language: str, payload: dict[str, str]) -> None:
    TRANSLATIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = TRANSLATIONS_DIR / f"{language}.json"
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def translate_batch(rows: list[dict[str, Any]], language: str) -> dict[str, str]:
    if language == "en":
        language_name = "English"
    elif language == "ar":
        language_name = "Arabic"
    else:
        return {row["id"]: row["question_fr"] for row in rows}

    source = [{"id": row["id"], "question": row["question_fr"]} for row in rows]
    system = (
        "You translate FAQ questions for benchmark inputs. "
        "Return strict JSON only. Keep meaning unchanged. "
        "Preserve product names, URLs, acronyms, and emails. "
        "Never replace ENSA BM, ENSABM, Beni Mellal, USMS, or Mghila with another school or city."
    )
    prompt = (
        f"Translate each question into natural {language_name}.\n"
        "Return a JSON array where each item has exactly these keys: id, question.\n"
        "Do not add explanations.\n\n"
        f"{json.dumps(source, ensure_ascii=False)}"
    )
    raw = call_groq(prompt, system=system, timeout=90, max_tokens=3500)
    if not raw:
        raise RuntimeError(f"Empty translation response for language={language}")

    match = re.search(r"\[.*\]", raw, flags=re.DOTALL)
    payload = json.loads(match.group(0) if match else raw)
    translated = {}
    for item in payload:
        item_id = str(item.get("id", "")).strip()
        question = str(item.get("question", "")).strip()
        if item_id and question:
            translated[item_id] = question

    missing = [row["id"] for row in rows if row["id"] not in translated]
    if missing:
        raise RuntimeError(f"Missing translated questions for {language}: {missing[:5]}")

    return translated


def ensure_questions(rows: list[dict[str, Any]], language: str, batch_size: int = 20) -> dict[str, str]:
    if language == "fr":
        return {row["id"]: row["question_fr"] for row in rows}

    cache = load_translation_cache(language)
    missing_rows = [row for row in rows if row["id"] not in cache]
    if not missing_rows:
        return {row["id"]: cache[row["id"]] for row in rows}

    for batch in chunked(missing_rows, batch_size):
        translated = translate_batch(batch, language)
        cache.update(translated)
        save_translation_cache(language, cache)

    return {row["id"]: cache[row["id"]] for row in rows}


def important_entities(value: str) -> set[str]:
    return {match.group(0).lower() for match in IMPORTANT_ENTITY_PATTERN.finditer(value or "")}


def token_overlap_score(expected: str, answer: str) -> float:
    left = tokenize(expected)
    right = tokenize(answer)
    if not left or not right:
        return 0.0
    return len(left & right) / max(len(left), 1)


def language_ok(question: str, answer: str) -> bool:
    question_language = _detect_question_language(question)
    if question_language == "ar":
        return _contains_arabic(answer)
    if question_language == "en":
        return _looks_english(answer) and not _contains_arabic(answer)
    return _looks_french(answer) or not _looks_english(answer)


def detect_intent(question: str) -> str:
    normalized = normalize_text(question)
    if any(marker in normalized for marker in ["website", "site officiel", "portal", "email", "contact", "mail", "mوقع", "موقع", "بريد"]):
        return "contact"
    if any(marker in normalized for marker in ["when", "quand", "mty", "متى", "created", "established", "fond", "تم انشاء", "تم إنشاء"]):
        return "when"
    if any(marker in normalized for marker in ["where", "ou se situe", "adresse", "location", "located", "اين", "أين", "فين", "العنوان"]):
        return "where"
    if any(marker in normalized for marker in ["who", "qui est", "directeur", "director", "coordinator", "شكون", "من هو", "مدير", "منسق"]):
        return "who"
    if any(marker in normalized for marker in ["track", "filiere", "filière", "program", "which are", "what are", "quelles sont", "مسارات", "تخصصات"]):
        return "list"
    return "other"


def intent_ok(question: str, answer: str) -> bool:
    normalized_answer = normalize_text(answer)
    intent = detect_intent(question)

    if intent == "when":
        return bool(re.search(r"\b(?:19|20)\d{2}\b", answer))
    if intent == "where":
        location_markers = ["beni mellal", "mghila", "campus", "adresse", "address", "maroc", "المغرب", "بني", "مغيلا"]
        return any(marker in normalized_answer for marker in location_markers)
    if intent == "who":
        return bool(re.search(r"\b(?:pr|prof|dr)\.?\b", normalized_answer)) or bool(re.search(r"[A-Z][a-z]+\s+[A-Z][a-z]+", answer))
    if intent == "contact":
        return ("http://" in answer) or ("https://" in answer) or ("@" in answer)
    if intent == "list":
        codes = ["g2er", "iaa", "iacs", "tdi", "2ap"]
        return sum(1 for code in codes if code in normalized_answer) >= 2
    return True


def analyze_answer(question: str, expected_answer: str, answer: str) -> dict[str, Any]:
    answer = answer or ""
    overlap = round(token_overlap_score(expected_answer, answer), 3)
    expected_entities = important_entities(expected_answer)
    matched_entities = sorted(entity for entity in expected_entities if entity in answer.lower())
    entity_coverage = round(len(matched_entities) / max(len(expected_entities), 1), 3) if expected_entities else None
    starts_document_like = bool(DOC_PREFIX_PATTERN.search(answer))
    empty_or_fallback = (not answer.strip()) or answer.strip().startswith("❌") or "pas d'information fiable" in normalize_text(answer)

    failure_reasons = []
    if empty_or_fallback:
        failure_reasons.append("empty_or_fallback")
    if starts_document_like:
        failure_reasons.append("document_style")
    if not language_ok(question, answer):
        failure_reasons.append("wrong_language")
    if not intent_ok(question, answer):
        failure_reasons.append("intent_miss")
    if expected_entities and entity_coverage is not None and entity_coverage < 0.5:
        failure_reasons.append("entity_miss")
    if _detect_question_language(question) == "fr" and overlap < 0.2:
        failure_reasons.append("low_overlap")

    return {
        "token_overlap": overlap,
        "expected_entities": sorted(expected_entities),
        "matched_entities": matched_entities,
        "entity_coverage": entity_coverage,
        "starts_document_like": starts_document_like,
        "empty_or_fallback": empty_or_fallback,
        "language_ok": language_ok(question, answer),
        "intent_ok": intent_ok(question, answer),
        "failure_reasons": failure_reasons,
        "passed": not failure_reasons,
    }


def run_single_case(row: dict[str, Any], question: str, language: str) -> dict[str, Any]:
    started = time.perf_counter()
    result = route_question_api(question)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    answer = result.get("answer", "")
    analysis = analyze_answer(question, row["expected_answer_fr"], answer)

    return {
        "id": row["id"],
        "language": language,
        "source_pdf": row["source_pdf"],
        "question_fr": row["question_fr"],
        "question_used": question,
        "expected_answer_fr": row["expected_answer_fr"],
        "answer": answer,
        "source_file": result.get("source_file"),
        "elapsed_ms": elapsed_ms,
        "analysis": analysis,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for item in results if item["analysis"]["passed"])
    failed = total - passed
    by_reason: dict[str, int] = {}
    for item in results:
        for reason in item["analysis"]["failure_reasons"]:
            by_reason[reason] = by_reason.get(reason, 0) + 1

    sorted_failures = sorted(
        (item for item in results if not item["analysis"]["passed"]),
        key=lambda item: (len(item["analysis"]["failure_reasons"]), -item["analysis"]["token_overlap"]),
        reverse=True,
    )

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round((passed / total), 3) if total else 0.0,
        "failure_reasons": by_reason,
        "sample_failures": sorted_failures[:15],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark RAG answers against FAQ PDFs.")
    parser.add_argument("--language", choices=["fr", "en", "ar"], default="fr")
    parser.add_argument("--variant", choices=["original", "rephrase", "omission", "typo"], default="original")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--dedupe", choices=["none", "normalized"], default="normalized")
    parser.add_argument("--output", type=str, default="")
    parser.add_argument("--skip-rebuild", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    TRANSLATIONS_DIR.mkdir(parents=True, exist_ok=True)

    if not args.skip_rebuild:
        rebuild_vectorstore()

    rows = dedupe_pairs(extract_pairs(), args.dedupe)
    selected = rows[args.offset : args.offset + args.limit] if args.limit > 0 else rows[args.offset :]
    translated_questions = ensure_questions(selected, args.language)
    if args.language == "fr":
        translated_questions = {
            row["id"]: mutate_french_question(translated_questions[row["id"]], args.variant)
            for row in selected
        }

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(args.workers, 1)) as executor:
        future_map = {
            executor.submit(run_single_case, row, translated_questions[row["id"]], args.language): row["id"]
            for row in selected
        }
        for future in as_completed(future_map):
            results.append(future.result())

    results.sort(key=lambda item: item["id"])
    summary = summarize(results)
    payload = {
        "language": args.language,
        "offset": args.offset,
        "limit": args.limit,
        "variant": args.variant,
        "dedupe": args.dedupe,
        "vectorstore_path": os.environ.get("VECTORSTORE_PATH"),
        "summary": summary,
        "results": results,
    }

    output_path = Path(args.output) if args.output else RESULTS_DIR / f"benchmark_{args.language}_{args.variant}_{args.offset}_{args.limit}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    print(json.dumps({"output": str(output_path), "summary": summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
