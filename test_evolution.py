# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
from unittest.mock import MagicMock


def run_tests():
    print("Testing MagicDocs...")
    try:
        from intelligence.services.magic_docs import MagicDocs
        llm_mock = MagicMock()
        llm_mock.generate.return_value = "Mocked Doc"
        docs = MagicDocs(llm_mock)
        assert docs.get_context_content() is not None
        print("MagicDocs initialized cleanly!")
    except Exception as e:
        print(f"MagicDocs failed: {e}")

    print("Testing SessionMemory...")
    try:
        from intelligence.memory.session_memory import SessionMemory
        mem = SessionMemory(max_turns=2)
        mem.add_turn("user", "Hello")
        mem.add_turn("assistant", "Hi")
        mem.add_turn("user", "Testing limit")
        assert len(mem.get_context()) == 2
        print("SessionMemory limits and handles correctly!")
    except Exception as e:
        print(f"SessionMemory failed: {e}")

    print("Testing AutoDream...")
    try:
        from intelligence.memory.auto_dream import AutoDreamDaemon
        dream = AutoDreamDaemon(mem, llm_mock)
        print("AutoDream initialized cleanly!")
    except Exception as e:
        print(f"AutoDream failed: {e}")

    print("Testing Coordinator...")
    try:
        from intelligence.coordinator import Coordinator
        coord = Coordinator(llm_mock, MagicMock())
        print("Coordinator initialized cleanly!")
    except Exception as e:
        print(f"Coordinator failed: {e}")

if __name__ == "__main__":
    run_tests()
