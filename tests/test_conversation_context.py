from app.config import get_settings
from app.services.chat_memory import ChatMemoryStore
from app.services.conversation_context import (
    augment_question_for_dataset,
    build_pdf_search_query,
    should_skip_dataset_lookup,
)


def test_augment_without_history_returns_plain_question(client) -> None:
    s = get_settings()
    ctx = augment_question_for_dataset("conv-no-hist-xyz", "Combien de lignes ?", s)
    assert ctx.llm_question == "Combien de lignes ?"
    assert ctx.pdf_search_question == "Combien de lignes ?"
    assert ctx.skip_dataset_lookup is False


def test_augment_includes_prior_turns_for_follow_up(client) -> None:
    s = get_settings()
    cid = "conv-coh-test-1"
    mem = ChatMemoryStore()
    mem.append_turn(cid, "Résume le stock par catégorie", "Réponse synthétique de test.")
    ctx = augment_question_for_dataset(cid, "Et le total global ?", s)
    assert "Et le total global ?" in ctx.pdf_search_question
    assert "Résume le stock" in ctx.llm_question
    assert "Question actuelle" in ctx.llm_question
    assert "Et le total global ?" in ctx.llm_question
    assert "Résume le stock" in ctx.pdf_search_question
    assert "U:" in ctx.llm_question or "A:" in ctx.llm_question
    assert "Entrée dans le fil" in ctx.llm_question


def test_build_pdf_search_merges_prior_user_messages() -> None:
    hist = [
        ("user", "Chapitre 2 stress hydrique"),
        ("assistant", "Voici un résumé."),
        ("user", "Et la définition du potentiel ?"),
        ("assistant", "Le potentiel hydrique mesure…"),
    ]
    q = "La B"
    merged = build_pdf_search_query(hist, q)
    assert "La B" in merged
    assert "potentiel" in merged.lower()


def test_skip_merci_without_router(client) -> None:
    s = get_settings()
    hist = [
        ("user", "Explique la section 2"),
        ("assistant", "Voici l'explication détaillée."),
    ]
    assert should_skip_dataset_lookup(hist, "Merci", s) is True


def test_router_off_short_reply_after_question_no_skip(client) -> None:
    """Routeur désactivé en tests : pas de CHAT implicite hors accusés."""
    s = get_settings()
    assert s.dataset_tool_router_enabled is False
    hist = [
        ("user", "Révisons le QCM page 3"),
        ("assistant", "Question 1 : quel est l'effet de X ?"),
    ]
    assert should_skip_dataset_lookup(hist, "Réponse B", s) is False


def test_skip_requires_last_turn_assistant(client) -> None:
    s = get_settings()
    hist = [("user", "Bonjour")]
    assert should_skip_dataset_lookup(hist, "suite", s) is False
