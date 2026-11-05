import unittest
from unittest.mock import patch

from local_rag import (
    LocalModelError,
    LocalRAGAssistant,
    OllamaSettings,
    RetrievalDocument,
    build_retrieval_corpus,
)


class LocalRAGTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = OllamaSettings(
            base_url="http://127.0.0.1:11434",
            chat_model="local-chat",
            embedding_model="local-embed",
            timeout_seconds=10,
        )
        self.documents = [
            RetrievalDocument("SHIPMENT DLV-2401", "Delayed shipment from Bengaluru."),
            RetrievalDocument("POLICY delay", "Delay claims require seven days."),
        ]

    @patch("local_rag._request_ollama")
    def test_answers_from_retrieved_context_and_returns_source_ids(
        self, request_ollama
    ) -> None:
        request_ollama.side_effect = [
            {"embeddings": [[1, 0], [0, 1]]},
            {"embeddings": [[0, 1]]},
            {"message": {"content": "The policy requires seven days. [POLICY delay]"}},
        ]
        assistant = LocalRAGAssistant(self.documents, self.settings)

        result = assistant.answer("What does the delay policy require?")

        self.assertIn("seven days", result["answer"])
        self.assertEqual(result["sources"][0]["source_id"], "POLICY delay")
        chat_payload = request_ollama.call_args_list[2].args[2]
        system_message = chat_payload["messages"][0]["content"]
        self.assertIn("[POLICY delay]", system_message)
        retrieved_context = system_message.split("Retrieved context:\n", 1)[1]
        self.assertLess(
            retrieved_context.index("[POLICY delay]"),
            retrieved_context.index("[SHIPMENT DLV-2401]"),
        )
        self.assertEqual(request_ollama.call_args_list[0].args[1], "/api/embed")
        self.assertEqual(request_ollama.call_args_list[2].args[1], "/api/chat")

    @patch("local_rag._request_ollama")
    def test_exact_shipment_id_ranks_that_shipment_first(
        self, request_ollama
    ) -> None:
        request_ollama.side_effect = [
            {"embeddings": [[0, 1], [1, 0]]},
            {"embeddings": [[1, 0]]},
        ]
        assistant = LocalRAGAssistant(self.documents, self.settings)

        matches = assistant.retrieve("Where is DLV-2401?")

        self.assertEqual(matches[0]["source_id"], "SHIPMENT DLV-2401")
        self.assertEqual(matches[0]["score"], 1.0)

    @patch("local_rag._request_ollama")
    def test_document_embeddings_are_cached_for_follow_up_questions(
        self, request_ollama
    ) -> None:
        request_ollama.side_effect = [
            {"embeddings": [[1, 0], [0, 1]]},
            {"embeddings": [[1, 0]]},
            {"embeddings": [[0, 1]]},
        ]
        assistant = LocalRAGAssistant(self.documents, self.settings)

        assistant.retrieve("Question one")
        assistant.retrieve("Question two")

        embedding_requests = [
            call for call in request_ollama.call_args_list
            if call.args[1] == "/api/embed"
        ]
        self.assertEqual(len(embedding_requests), 3)
        self.assertEqual(len(embedding_requests[0].args[2]["input"]), 2)

    def test_remote_model_hosts_are_rejected(self) -> None:
        remote_settings = OllamaSettings(
            base_url="https://models.example.com",
            chat_model="local-chat",
            embedding_model="local-embed",
        )

        with self.assertRaisesRegex(LocalModelError, "loopback URL"):
            LocalRAGAssistant(self.documents, remote_settings)

    def test_corpus_contains_shipment_tracking_and_policy_rules(self) -> None:
        corpus = build_retrieval_corpus(
            [{
                "shipment_id": "DLV-7000",
                "status": "In transit",
                "claim_type": "delay",
                "origin": "Pune",
                "destination": "Mumbai",
                "documents": {"invoice": True, "tracking_history": False},
                "tracking_events": ["2026-10-01: Picked up in Pune"],
            }],
            [{
                "claim_type": "delay",
                "title": "Transit delay claim",
                "required_documents": ["invoice", "tracking_history"],
                "minimum_delay_days": 7,
                "summary": "Delay claims need at least seven days.",
            }],
        )

        self.assertEqual(
            [document.source_id for document in corpus],
            ["SHIPMENT DLV-7000", "POLICY delay"],
        )
        self.assertIn("Picked up in Pune", corpus[0].text)
        self.assertIn("Minimum Delay Days: 7", corpus[1].text)


if __name__ == "__main__":
    unittest.main()
