import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from multi_agent_video.shared_capabilities import SharedCapabilitiesService


def test_read_documents_masks_sensitive_data() -> None:
    svc = SharedCapabilitiesService()
    result = svc.read_documents(
        [
            {
                "doc_id": "d1",
                "title": "invoice",
                "text": "Contact me at a@b.com and card 1234 5678 9999 0000",
            }
        ]
    )

    assert result.docs
    masked_text = result.docs[0]["text"]
    assert "[email_redacted]" in masked_text
    assert "[card_like_redacted]" in masked_text
    assert result.redaction_counts.get("email", 0) == 1


def test_rank_context_returns_top_match() -> None:
    svc = SharedCapabilitiesService()
    ranked = svc.rank_context(
        query="rainy cyberpunk city",
        docs=[
            {"doc_id": "a", "title": "a", "text": "office budget table"},
            {"doc_id": "b", "title": "b", "text": "cyberpunk rainy city neon reflections"},
        ],
        top_k=1,
    )

    assert len(ranked.contexts) == 1
    assert ranked.contexts[0]["doc_id"] == "b"


def test_build_markdown_report_has_sections() -> None:
    svc = SharedCapabilitiesService()
    result = svc.build_markdown_report(
        title="Integration Report",
        sections=[
            {"heading": "Summary", "body": "ok"},
            {"heading": "Actions", "body": "next"},
        ],
    )

    assert "# Integration Report" in result.markdown
    assert "## Summary" in result.markdown
    assert "## Actions" in result.markdown
