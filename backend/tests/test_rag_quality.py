from backend.services import db_service, groq_service, rag_service, chatbot_service, router_service


def test_de_documentize_answer_removes_source_style_intro():
    raw = "Le site de formation initiale indique Pr. GOUSKIR MOHAMED."
    cleaned = groq_service._de_documentize_answer(raw)
    assert cleaned == "Pr. GOUSKIR MOHAMED."


def test_de_documentize_answer_removes_explique_intro():
    raw = "Le site explique que l'ecole a pour mission de former des ingenieurs."
    cleaned = groq_service._de_documentize_answer(raw)
    assert cleaned == "l'ecole a pour mission de former des ingenieurs."


def test_cacheable_answer_rejects_generic_yes_prefix():
    assert groq_service.is_cacheable_faq_answer("Oui. Le site officiel indique cela.") is False
    assert groq_service.is_cacheable_faq_answer("Les filieres disponibles sont IACS, TDI, G2ER et IAA.") is True


def test_semantic_cache_match_rejects_intent_mismatch():
    assert rag_service._is_semantic_cache_match(
        "quelles sont les filieres disponibles",
        "ou est la scolarite",
        cached_intent="where",
    ) is False


def test_semantic_cache_match_accepts_typo_variant_same_intent():
    assert rag_service._is_semantic_cache_match(
        "quels sont les filieres disponibles a l ensa beni melall",
        "quelles sont les filieres disponibles a l ensa beni mellal",
        cached_intent="list",
    ) is True


def test_low_quality_answer_text_detection():
    assert rag_service._is_low_quality_answer_text("Oui. La page d'accueil cite une ceremonie.") is True
    assert rag_service._is_low_quality_answer_text("Les filieres sont IACS, TDI, G2ER et IAA.") is False


def test_direct_faq_answer_rejects_generic_page_link():
    answer, source, score = rag_service._find_direct_faq_answer("C'est où le campus de l'ENSA BM ?")
    assert answer is None
    assert source is None
    assert score == 0.0


def test_intent_type_detects_arabic_where_query():
    assert rag_service._intent_type("وين كاينة ENSA BM؟") == "where"


def test_intent_type_detects_arabic_who_query():
    assert rag_service._intent_type("شكون هو المدير ديال ENSA BM؟") == "who"


def test_intent_type_detects_arabic_list_query():
    assert rag_service._intent_type("شحال من فيلير عند ENSA BM؟") == "list"


def test_intent_type_detects_contact_query_with_missing_apostrophe():
    question = "Quel est lemail du directeur mentionne sur le site ?"
    assert rag_service._intent_type(question) == "contact"
    assert groq_service._intent_type(question) == "contact"


def test_intent_type_does_not_treat_admin_lookup_as_location():
    question = "ou consulter mes notes ?"
    assert rag_service._intent_type(question) == "other"
    assert groq_service._intent_type(question) == "other"


def test_extract_track_code_from_question():
    assert rag_service._extract_track_code("qui est le coordinateur de la filiere iacs") == "iacs"
    assert rag_service._extract_track_code("quelles sont les filieres de cycle ingenieur") == ""


def test_extract_track_code_supports_full_track_name_alias():
    question = "qui est le coordinateur de la filiere intelligence artificielle et cybersecurite"
    assert rag_service._extract_track_code(question) == "iacs"
    assert groq_service._extract_track_code_or_alias(question) == "iacs"


def test_source_quality_weight_prefers_enriched_pdfs():
    assert rag_service._source_quality_weight("faq_ensa_bm_rag_enrichie.pdf") > 0
    assert rag_service._source_quality_weight("faq_ensa_bm_scrape_rag_complete.pdf") > 0
    assert rag_service._source_quality_weight("faq_usms.pdf") < 0


def test_augment_query_for_retrieval_adds_location_hints_for_arabic():
    augmented = rag_service._augment_query_for_retrieval("وين كاينة ENSA BM؟")
    normalized = rag_service._normalize_text(augmented)
    assert "where" in normalized
    assert "mghila" in normalized or "beni mellal" in normalized


def test_augment_query_for_retrieval_adds_who_hints_for_arabic():
    augmented = rag_service._augment_query_for_retrieval("شكون هو المدير ديال ENSA BM؟")
    normalized = rag_service._normalize_text(augmented)
    assert "director" in normalized or "directeur" in normalized or "pr belaid bouilkhilane" in normalized


def test_augment_query_for_retrieval_adds_contact_hints_for_email_typo():
    augmented = rag_service._augment_query_for_retrieval("Quel est lemail du directeur mentionne sur le site officiel de l ENSA BM ?")
    normalized = rag_service._normalize_text(augmented)
    assert "email directeur ensa bm" in normalized
    assert "b.bouikhalene@usms.ma" in normalized


def test_force_arabic_style_keeps_arabic_answers():
    assert groq_service._force_arabic_style("المدير هو Pr. BELAID BOUILKHILANE", "شكون هو المدير ديال ENSA BM؟") == "المدير هو Pr. BELAID BOUILKHILANE"


def test_force_arabic_style_translates_non_arabic_answers(monkeypatch):
    monkeypatch.setattr(groq_service, "call_groq", lambda *args, **kwargs: "المدير هو Pr. BELAID BOUILKHILANE")
    result = groq_service._force_arabic_style("Le directeur est Pr. BELAID BOUILKHILANE.", "شكون هو المدير ديال ENSA BM؟")
    assert "المدير" in result


def test_force_english_style_translates_french_answer(monkeypatch):
    monkeypatch.setattr(groq_service, "call_groq", lambda *args, **kwargs: "The director is Pr. BELAID BOUILKHILANE.")
    result = groq_service._force_english_style("Le directeur est Pr. BELAID BOUILKHILANE.", "Who is the director of ENSA BM?")
    assert "director" in result.lower()


def test_rag_school_fact_returns_question_language(monkeypatch):
    monkeypatch.setattr(groq_service, "call_groq", lambda *args, **kwargs: "")
    context = (
        "Question : Qui est le directeur de l'ENSA BM ?\n"
        "Reponse : Le directeur de l'ENSA Beni Mellal est Pr. BELAID BOUILKHILANE."
    )

    result = groq_service.answer_faq_with_groq("Who is the director of ENSA BM?", context)

    assert "The director is Pr. BELAID BOUILKHILANE" in result
    assert "Le directeur" not in result


def test_force_english_style_uses_local_fallback_when_model_is_unavailable(monkeypatch):
    monkeypatch.setattr(groq_service, "call_groq", lambda *args, **kwargs: "")
    result = groq_service._force_english_style(
        "Le portail officiel est https://ensabm.usms.ac.ma/.",
        "What is the official website of ENSA BM?",
    )
    assert "official website" in result.lower()
    assert "https://ensabm.usms.ac.ma/" in result


def test_force_french_style_translates_english_answer(monkeypatch):
    monkeypatch.setattr(groq_service, "call_groq", lambda *args, **kwargs: "Le directeur est Pr. BELAID BOUILKHILANE.")
    result = groq_service._force_french_style("The director is Pr. BELAID BOUILKHILANE.", "Qui est le directeur de l'ENSA BM ?")
    assert "directeur" in result.lower()


def test_force_arabic_style_uses_local_fallback_when_model_is_unavailable(monkeypatch):
    monkeypatch.setattr(groq_service, "call_groq", lambda *args, **kwargs: "")
    result = groq_service._force_arabic_style(
        "Le portail officiel est https://ensabm.usms.ac.ma/.",
        "ما هو الموقع الرسمي ل ENSA BM؟",
    )
    assert "الموقع الرسمي" in result
    assert "https://ensabm.usms.ac.ma/" in result


def test_translate_question_to_french_has_local_multilingual_fallback(monkeypatch):
    monkeypatch.setattr(groq_service, "call_groq", lambda *args, **kwargs: "")
    groq_service._translate_question_to_french.cache_clear()
    assert "quand" in groq_service._translate_question_to_french("When was ENSA BM established?").lower()
    groq_service._translate_question_to_french.cache_clear()
    assert "site officiel" in groq_service._translate_question_to_french("ما هو الموقع الرسمي ل ENSA BM؟").lower()


def test_build_tracks_list_answer_from_context():
    context = (
        "Informations pertinentes:\n"
        "- Question : Quelles sont les quatre filieres ingenieur de l'ENSA BM ?\\n"
        "Reponse : G2ER, IAA, IACS et TDI.\n"
    )
    answer = groq_service._build_tracks_list_answer_from_context(
        "quelles sont les filieres ingenieur de l ensa bm",
        context,
    )
    assert "G2ER" in answer and "IAA" in answer and "IACS" in answer and "TDI" in answer


def test_answer_faq_handles_typo_global_tracks_without_generic_generation(monkeypatch):
    context = (
        "Informations pertinentes:\n"
        "- Question : Quelles sont les quatre filieres ingenieur de l'ENSA BM ?\\n"
        "Reponse : G2ER, IAA, IACS et TDI.\n"
    )
    monkeypatch.setattr(groq_service, "call_groq", lambda *args, **kwargs: "Reponse generique")

    answer = groq_service.answer_faq_with_groq(
        "quels sonts les filiers a l'ensa beni melall",
        context,
    )

    assert answer.startswith("Les filieres du cycle ingenieur sont")
    assert "G2ER" in answer and "IAA" in answer and "IACS" in answer and "TDI" in answer


def test_build_tracks_list_answer_can_expand_names_and_definitions():
    context = (
        "Informations pertinentes:\n"
        "- Question : Quelles sont les quatre filieres ingenieur de l'ENSA BM ?\\n"
        "Reponse : G2ER, IAA, IACS et TDI.\n"
    )
    answer = groq_service._build_tracks_list_answer_from_context(
        "quelles sont les filieres d ingenieur a l ensa beni mellal donne le nom et la definition des filieres",
        context,
    )
    assert "Intelligence Artificielle et Cybersecurite" in answer
    assert "Transformation Digitale Industrielle" in answer


def test_requested_track_details_answer_for_multiple_codes():
    context = (
        "Informations pertinentes:\n"
        "- Question : Quelles sont les quatre filieres ingenieur de l'ENSA BM ?\n"
        "Reponse : G2ER, IAA, IACS et TDI.\n"
    )
    answer = groq_service._best_context_answer(
        "donne les noms complets des filieres iacs tdi g2er iaa",
        context,
    )
    assert "Intelligence Artificielle et Cybersecurite" in answer
    assert "Transformation Digitale Industrielle" in answer
    assert "Genie Electrique et Energies Renouvelables" in answer
    assert "Industries Agroalimentaires" in answer


def test_best_context_answer_for_specific_track_coordinator():
    context = (
        "Informations pertinentes:\n"
        "- Question : Un coordinateur est-il mentionne pour les 2AP ?\n"
        "Reponse : Oui. Pr. KAAB MOHAMED est coordinateur du cycle preparatoire.\n"
        "- Question : Quel est le coordinateur indique pour la filiere IACS ?\n"
        "Reponse : Le coordinateur affiche est Mohamed Gouskir.\n"
    )
    answer = groq_service._best_context_answer("qui est le coordinateur de la filiere iacs", context)
    assert "gouskir" in answer.lower()


def test_best_context_answer_prefers_director_email_over_identity_for_typo_variant():
    context = (
        "Informations pertinentes:\n"
        "- Question : Quel est l'email du directeur mentionne sur le site ?\n"
        "Reponse : Le mot du directeur affiche l'adresse b.bouikhalene@usms.ma.\n"
        "- Question : Qui est le directeur mentionne sur le site renove ?\n"
        "Reponse : Le portail met en avant le Pr. Belaid Bouilkhilane comme directeur.\n"
        "- Question : Quel est l'email de contact officiel de l'ecole ?\n"
        "Reponse : L'adresse de contact affichee sur le site est ensabm.contact@usms.ma.\n"
    )
    answer = groq_service._best_context_answer("Quel est lemail du directeur mentionne sur le site ?", context)
    assert "b.bouikhalene@usms.ma" in answer.lower()


def test_best_context_answer_supports_track_full_name_for_coordinator():
    context = (
        "Informations pertinentes:\n"
        "- Question : Un coordinateur est-il mentionne pour les 2AP ?\n"
        "Reponse : Oui. Pr. KAAB MOHAMED est coordinateur du cycle preparatoire.\n"
        "- Question : Quel est le coordinateur indique pour la filiere IACS ?\n"
        "Reponse : Le coordinateur affiche est Pr. GOUSKIR MOHAMED.\n"
    )
    answer = groq_service._best_context_answer(
        "qui est le coordinateur de la filiere intelligence artificielle et cybersecurite",
        context,
    )
    assert "gouskir" in answer.lower()


def test_router_fast_facts_handle_demo_typos_and_admission_questions():
    checks = [
        ("qui est le cooridnateur de la filiere iaa", "rokni"),
        ("qui est est le coordinateur de la filiere intellignece artificielle et cybersecurite", "gouskir"),
        ("quie signife iacs", "intelligence artificielle"),
        ("qui signiifie iaa", "industries agroalimentaires"),
        ("c koi les filier dispo a nsa beni mlal", "g2er"),
        ("tdi ca veut dire quoi", "transformation digitale"),
        ("comment rejoindre le cycle ingenieur de l'ensa beni mellal", "admission parallele"),
        ("combine d'anne fait on en cycle preparatoir a l'ensa beni mellal", "2 ans"),
        ("combien d'anne fait on en cycle ingenieur", "3 ans"),
        ('duree de l"annee de cycle ingenieur a l\'ensa beni mellal', "3 ans"),
    ]

    for question, expected in checks:
        answer = router_service._official_fast_fact_answer(question)
        assert answer
        assert expected in answer.lower()


def test_router_fast_facts_cover_jury_style_campus_questions():
    checks = [
        ("ensabm ca veut dire quoi", "ecole nationale des sciences appliquees"),
        ("c est quoi l ensa beni mellal", "ingenieurs d'etat"),
        ("mission de ensa bm", "former des ingenieurs"),
        ("qui dirige ensa bm", "belaid bouilkhilane"),
        ("cycle ingenieur dure combien", "3 ans"),
        ("cycle complet ensa dure combien", "5 ans"),
        ("double diplomation ensa bm", "polytech angers"),
        ("partenariats double diplome", "eilco"),
    ]

    for question, expected in checks:
        answer = router_service._official_fast_fact_answer(question)
        assert answer
        assert expected in answer.lower()


def test_router_fast_facts_cover_track_details_without_rag_drift():
    checks = [
        ("email responsable iacs", "m.gouskir@usms.ma"),
        ("iacs dure combien", "6 semestres"),
        ("quels stages en iacs", "pfe"),
        ("debouches iacs", "data scientist"),
        ("competences iacs", "cybermenaces"),
        ("langue enseignement iacs", "francais"),
        ("mode formation iacs", "presentiel"),
        ("credits iacs", "180 credits"),
        ("partenaires iacs", "polytech"),
        ("club iacs", "csia"),
        ("infrastructures tdi", "cloud industriel"),
        ("debouches industrie agro alimentaire", "ingenieur qualite"),
        ("stages genie electrique renouvelable", "pfe"),
    ]

    for question, expected in checks:
        answer = router_service._official_fast_fact_answer(question)
        assert answer
        assert expected in answer.lower()


def test_fast_facts_do_not_steal_live_timetable_questions():
    assert router_service._official_fast_fact_answer("la filiere iacs a quelle cours demain") is None
    assert router_service._official_fast_fact_answer("tdi a quel cours lundi") is None


def test_router_fast_facts_accept_abbreviations_and_full_track_names():
    checks = [
        ("qui est le coordinateur de g2er", "oulcaid"),
        ("qui est le coordinateur de genie electrique et energies renouvelables", "oulcaid"),
        ("que signifie genie electrique energies renouvelables", "g2er"),
        ("qui est le coordinateur de iaa", "rokni"),
        ("qui est le coordinateur de industries agroalimentaires", "rokni"),
        ("qui est le coordinateur de industrie agro alimentaire", "rokni"),
        ("que signifie industries agro-alimentaires", "iaa"),
        ("qui est le coordinateur de iacs", "gouskir"),
        ("qui est le coordinateur de intelligence artificielle et cyber securite", "gouskir"),
        ("que signifie intelligence artificielle et cybersecurite", "iacs"),
        ("qui est le coordinateur de tdi", "ouanan"),
        ("qui est le coordinateur de transformation digitale industrielle", "ouanan"),
        ("qui est le coordinateur de transformation numerique industrielle", "ouanan"),
        ("que signifie digitalisation industrielle", "tdi"),
    ]

    for question, expected in checks:
        answer = router_service._official_fast_fact_answer(question)
        assert answer
        assert expected in answer.lower()


def test_router_fast_facts_answer_program_catalog_questions():
    checks = [
        ("quels sont les modules que les filieres iacs font en semestre 4", "devsecops"),
        ("c'est dans quels semestres la fileire iacs font le cours sur blockchain", "semestre 5"),
        ("Quesl est le programme de la formationde la fiiere iacs", "s5"),
        ("que font la filiere industrie agoalimentaire lors du Semestre 5", "toxicologie"),
        ("iacs fait devsecops quand", "semestre 4"),
    ]

    for question, expected in checks:
        answer = router_service._official_fast_fact_answer(question)
        assert answer
        assert expected in answer.lower()


def test_split_compound_faq_question_splits_two_faq_requests():
    parts = chatbot_service._split_compound_faq_question(
        "qui est le coordinateur de la filiere iacs ? et que signifie iacs"
    )
    assert len(parts) == 2
    assert "coordinateur" in parts[0].lower()
    assert "signifie" in parts[1].lower()


def test_global_tracks_question_detects_cites_typo_style():
    assert groq_service._is_global_engineering_tracks_question("cites les filiere de cycle ingenieurs a l'ensa beni mellaal")


def test_best_context_answer_ignores_cycle_preparatoire_for_iacs_coordinator():
    context = (
        "Informations pertinentes:\n"
        "- Question : Un coordinateur est-il mentionne pour les 2AP ?\n"
        "Reponse : Oui. Pr. KAAB MOHAMED est coordinateur du cycle preparatoire. 4. Filiere IACS\n"
        "- Question : Quel est le coordinateur indique pour la filiere IACS ?\n"
        "Reponse : Le site de formation initiale indique Pr. GOUSKIR MOHAMED.\n"
    )
    answer = groq_service._best_context_answer("qui est le coordinateur de la filiere iacs", context)
    assert "gouskir" in answer.lower()


def test_official_rag_contains_key_track_coordinators():
    rag_service._extract_faq_pairs_cached.cache_clear()
    rag_service._faq_question_index_cached.cache_clear()

    checks = [
        ("qui est le coordinateur de la filiere iaa", "Yahya ROKNI"),
        ("qui est le coordinateur de la filiere iacs", "GOUSKIR"),
        ("qui est le coordinateur de la filiere tdi", "OUANAN"),
        ("qui est le coordinateur de la filiere g2er", "OULCAID"),
        ("qui est monsieur gouskir", "IACS"),
    ]

    for question, expected in checks:
        context, _, _ = rag_service.search_context(question)
        assert context is not None
        assert expected.lower() in context.lower()


def test_official_rag_contains_track_details_and_admin_faq():
    rag_service._extract_faq_pairs_cached.cache_clear()
    rag_service._faq_question_index_cached.cache_clear()
    rag_service._faq_token_index_cached.cache_clear()

    checks = [
        ("quel est le programme de la filiere iaa", "HACCP"),
        ("quels stages sont prevus en iacs", "PFE"),
        ("quels sont les debouches de tdi", "transformation digitale"),
        ("quel est le programme de 2ap", "programmation en langage C"),
        ("comment demander une attestation de scolarite", "ENT"),
        ("ou consulter mes notes", "Espace Etudiant"),
        ("ou consulter emploi du temps", "portail EDT"),
        ("comment suivre ma bourse", "E-Bourse"),
        ("comment rejoindre le cycle ingenieur de l'ensa beni mellal", "admission parallele"),
        ("combine d'anne fait on en cycle preparatoir a l'ensa beni mellal", "2 ans"),
    ]

    for question, expected in checks:
        context, _, _ = rag_service.search_context(question)
        assert context is not None
        assert expected.lower() in context.lower()


def test_official_rag_reformulations_keep_the_right_category():
    rag_service._extract_faq_pairs_cached.cache_clear()
    rag_service._faq_question_index_cached.cache_clear()
    rag_service._faq_token_index_cached.cache_clear()

    checks = [
        ("c koi les filier dispo a nsa beni mlal", "G2ER"),
        ("contester resultat examen", "reclamation"),
        ("les jobs apres intelligence artificielle cyber securite", "data scientist"),
        ("laboratoires industrie agro alimentaire", "HPLC"),
        ("equipements genie electrique renouvelable", "photovoltaique"),
        ("pfe en intelligence artificielle cyber securite", "PFE"),
        ("cooperation et partenaires tdi", "Polytech"),
        ("modules intelligence artificielle cyber securite", "machine learning"),
        ("acceder formation ingenieur apres bac plus deux", "admission"),
    ]

    for question, expected in checks:
        context, _, score = rag_service._find_direct_faq_context(question)
        assert score > 0
        assert context is not None
        assert expected.lower() in context.lower()


def test_official_rag_contains_semester_programme_reformulations():
    rag_service._extract_faq_pairs_cached.cache_clear()
    rag_service._faq_question_index_cached.cache_clear()
    rag_service._faq_token_index_cached.cache_clear()

    checks = [
        ("quels sont les modules que les filieres iacs font en semestre 4", "DevOps"),
        ("Quesl est le programme de la formationde la fiiere iacs", "machine learning"),
        ("c'est dans quels semestres la fileire iacs font le cours sur blockchain", "semestre 5"),
        ("que font la filiere industrie agoalimentaire lors du Semestre 5", "Toxicologie"),
        ("quels cours fait tdi en s5", "Smart Factory"),
        ("dans quel semestre g2er fait systemes solaires", "S4"),
        ("en iaa le module haccp est dans quel semestre", "S3"),
        ("iacs fait devsecops quand", "S4"),
    ]

    for question, expected in checks:
        context, _, score = rag_service._find_direct_faq_context(question)
        assert score > 0
        assert context is not None
        assert expected.lower() in context.lower()


def test_exact_faq_context_prefers_requested_semester_modules(monkeypatch):
    docs = [
        {
            "page_content": "Question : Quels modules sont enseignés en semestre 1 (S1) du TDI ? Reponse : Modules S1 TDI.",
            "metadata": {"source": "test.pdf"},
        },
        {
            "page_content": "Question : Quels modules sont enseignés en semestre 4 (S4) du TDI ? Reponse : Modules S4 TDI.",
            "metadata": {"source": "test.pdf"},
        },
    ]
    monkeypatch.setattr(rag_service, "_collect_documents", lambda: docs)
    rag_service._extract_faq_pairs_cached.cache_clear()
    context, source = rag_service.find_exact_faq_context("Quels modules sont enseignés en semestre 4 S4 du TDI ?")
    assert "Modules S4 TDI" in context
    assert "Modules S1 TDI" not in context
    assert source == "test.pdf"


def test_exact_faq_context_prefers_track_definition_over_coordinator(monkeypatch):
    docs = [
        {
            "page_content": "Question : Qui est le coordinateur de la filiere TDI ? Reponse : Le coordinateur TDI est Pr. OUANAN HAMID.",
            "metadata": {"source": "test.pdf"},
        },
        {
            "page_content": "Question : C'est quoi la filiere TDI ? Reponse : TDI signifie Transformation Digitale Industrielle.",
            "metadata": {"source": "test.pdf"},
        },
    ]
    monkeypatch.setattr(rag_service, "_collect_documents", lambda: docs)
    rag_service._extract_faq_pairs_cached.cache_clear()
    context, _ = rag_service.find_exact_faq_context("C’est quoi la filière TDI ?")
    assert "Transformation Digitale Industrielle" in context
    assert "OUANAN" not in context


def test_exact_faq_context_ignores_coordinateur_domain_question(monkeypatch):
    docs = [
        {
            "page_content": "Question : Quel domaine scientifique est associé au coordinateur IAA ? Reponse : La page IAA relie le coordinateur à la microbiologie.",
            "metadata": {"source": "test.pdf"},
        },
        {
            "page_content": "Question : Quel coordinateur est indiqué pour la filière IAA ? Reponse : La page Formation initiale indique Pr. ROKNI YAHYA.",
            "metadata": {"source": "test.pdf"},
        },
    ]
    monkeypatch.setattr(rag_service, "_collect_documents", lambda: docs)
    rag_service._extract_faq_pairs_cached.cache_clear()
    context, _ = rag_service.find_exact_faq_context("Qui est le coordinateur de la filière IAA ?")
    assert "ROKNI YAHYA" in context
    assert "microbiologie" not in context


def test_router_end_to_end_covers_faq_rag_and_timetable_variants(monkeypatch):
    monkeypatch.setattr(
        router_service,
        "get_available_classes",
        lambda force_refresh=False: {
            "IACS 2025-2026 S4": {
                "canonical_label": "IACS_2025-2026_S4",
                "semester": "S4",
                "academic_year": "2025-2026",
            }
        },
    )
    monkeypatch.setattr(
        db_service,
        "get_active_timetable",
        lambda _class_label: {
            "id": 1,
            "class_label": "IACS_2025-2026_S4",
            "academic_year": "2025-2026",
            "semester": "S4",
            "is_active": True,
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "slots": [
                {
                    "id": 1,
                    "timetable_id": 1,
                    "day_of_week": 0,
                    "start_time": "08:30",
                    "end_time": "10:00",
                    "subject": "Analyse numerique",
                    "professor": "Pr. Test",
                    "room": "A12",
                    "type": "Cours",
                },
                {
                    "id": 2,
                    "timetable_id": 1,
                    "day_of_week": 1,
                    "start_time": "10:15",
                    "end_time": "12:00",
                    "subject": "Physique appliquee",
                    "professor": "Pr. Autre",
                    "room": "B03",
                    "type": "TD",
                },
            ],
        },
    )

    captured_rag_questions: list[str] = []

    def fake_fast_fact(question: str):
        if "directeur" in question.lower():
            return "Le directeur est Pr. BELAID BOUILKHILANE."
        return None

    def fake_rag(question, **_kwargs):
        captured_rag_questions.append(question)
        return (
            "L'ENSA Béni Mellal est une école publique rattachée à l'USMS.",
            ["faq_ensa_bm_officielle_5000.json"],
            0.93,
        )

    monkeypatch.setattr(router_service, "_official_fast_fact_answer", fake_fast_fact)
    monkeypatch.setattr(chatbot_service, "ask_question_rag", fake_rag)

    faq_answer = router_service.route_question_api("Qui est le directeur de l'ENSA BM ?")
    assert "BELAID BOUILKHILANE" in faq_answer["answer"]
    assert faq_answer["source_file"] == "faq_ensa_bm_officielle_5000.json"

    rag_answer = router_service.route_question_api("Où se situe l'ENSA BM et comment rejoindre l'école ?")
    assert "école publique" in rag_answer["answer"]
    assert captured_rag_questions

    timetable_full = router_service.route_question_api("montre moi tout l'emploi du temps", class_label="IACS_2025-2026_S4")
    assert "## 📅 Emploi du temps" in timetable_full["answer"]
    assert "Analyse numerique" in timetable_full["answer"]
    assert "Physique appliquee" in timetable_full["answer"]

    timetable_day = router_service.route_question_api("qu'est-ce qu'on a mardi matin ?", class_label="IACS_2025-2026_S4")
    assert "Physique appliquee" in timetable_day["answer"]
    assert "Analyse numerique" not in timetable_day["answer"]

    timetable_variant = router_service.route_question_api("la filiere iacs a quel cours lundi", class_label="IACS_2025-2026_S4")
    assert "Analyse numerique" in timetable_variant["answer"]
