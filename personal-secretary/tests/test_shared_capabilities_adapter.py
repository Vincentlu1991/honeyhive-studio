from __future__ import annotations

import unittest

from personal_secretary.shared_capabilities_adapter import SecretarySharedCapabilitiesAdapter


class _FakeHermes:
    def run_prompt(self, prompt: str, **kwargs) -> str:
        return "ok"


class SharedCapabilitiesAdapterTest(unittest.TestCase):
    def test_read_documents_masks_email(self) -> None:
        adapter = SecretarySharedCapabilitiesAdapter(_FakeHermes())
        result = adapter.read_documents(
            [
                {
                    "doc_id": "1",
                    "title": "doc",
                    "text": "reach me at a@b.com",
                }
            ]
        )

        self.assertEqual(result.redaction_counts.get("email"), 1)
        self.assertIn("[email_redacted]", result.docs[0]["text"])

    def test_rank_context_selects_relevant_doc(self) -> None:
        adapter = SecretarySharedCapabilitiesAdapter(_FakeHermes())
        ranked = adapter.rank_context(
            query="rainy neon",
            docs=[
                {"doc_id": "a", "title": "a", "text": "budget report"},
                {"doc_id": "b", "title": "b", "text": "rainy neon cyber city"},
            ],
            top_k=1,
        )

        self.assertEqual(len(ranked.contexts), 1)
        self.assertEqual(ranked.contexts[0]["doc_id"], "b")


if __name__ == "__main__":
    unittest.main()
