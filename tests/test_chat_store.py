from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.chat_store import ChatStore


class ChatStoreTests(unittest.TestCase):
    def test_chat_is_saved_loaded_and_cleared_per_knowledge_package(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "a").mkdir()
            (root / "b").mkdir()

            def resolve(knowledge_id: str) -> Path:
                if knowledge_id not in {"a", "b"}:
                    raise FileNotFoundError(knowledge_id)
                return root / knowledge_id

            store = ChatStore(resolve)
            store.append("a", [{"role": "user", "content": "A 的问题"}])
            store.append("b", [{"role": "user", "content": "B 的问题"}])
            self.assertEqual(store.load("a")["messages"][0]["content"], "A 的问题")
            self.assertEqual(store.load("b")["messages"][0]["content"], "B 的问题")
            store.clear("a")
            self.assertEqual(store.load("a")["messages"], [])
            self.assertEqual(len(store.load("b")["messages"]), 1)

    def test_credentials_are_not_added_to_chat_payload(self) -> None:
        with TemporaryDirectory() as temporary:
            package = Path(temporary)
            store = ChatStore(lambda _: package)
            stored = store.append("demo", [{"role": "assistant", "content": "回答", "api_key": "secret"}])
            self.assertNotIn("api_key", stored["messages"][0])


if __name__ == "__main__":
    unittest.main()
