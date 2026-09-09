from backend.services import chatbot_service


def test_detects_stressed_in_french_sentence():
    details = chatbot_service.detect_user_state_details("Je suis tres stresse par les examens")
    assert details["label"] == "stressed"
    assert details["confidence"] >= 0.6


def test_detects_anxious_in_english_sentence():
    details = chatbot_service.detect_user_state_details("I am really worried about tomorrow")
    assert details["label"] == "anxious"


def test_detects_frustrated_in_arabic_sentence():
    details = chatbot_service.detect_user_state_details("أنا منزعج جدا وما فاهمش")
    assert details["label"] == "frustrated"


def test_negation_reduces_false_positive():
    details = chatbot_service.detect_user_state_details("Je ne suis pas stresse, tout va bien")
    assert not (details["label"] == "stressed" and details["confidence"] >= 0.8)


def test_history_can_lift_signal_when_current_is_ambiguous():
    history = [
        {"role": "user", "content": "Je suis tres stresse par mon semestre"},
        {"role": "assistant", "content": "Je suis la pour aider."},
        {"role": "user", "content": "franchement c'est dur"},
    ]
    details = chatbot_service.detect_user_state_details("Aide-moi", history=history, language="fr")
    assert details["label"] in {"stressed", "anxious", "frustrated"}


def test_emotional_tone_prefix_matches_english_answer_language():
    answer = "Here is your timetable for tomorrow."
    toned = chatbot_service.apply_emotional_tone(answer, "urgent")
    assert toned.startswith("I will get straight to the point")


def test_emotional_tone_prefix_matches_arabic_answer_language():
    answer = "هذا هو جدولك ليوم غد"
    toned = chatbot_service.apply_emotional_tone(answer, "anxious")
    assert toned.startswith("أتفهم قلقك")
