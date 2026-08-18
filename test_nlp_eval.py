# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
import json
import sys
import traceback
from pathlib import Path

try:
    sys.path.insert(0, r'c:\Users\lenovo\Desktop\LLM model train\neuroshell')
    from config import load_config
    from core.context import ContextManager
    from core.history import HistoryStore
    from intelligence.translator import Translator
    from llm.client import LLMClient

    print("Loading config...")
    config = load_config()

    print("Initializing LLM client...")
    llm = LLMClient(config)
    context = ContextManager(config)
    history = HistoryStore(Path('test_history.db'))

    print("Initializing Translator...")
    translator = Translator(llm, context, history)

    test_cases = [
        'list all files in this directory',
        'show saved wifi passwords',
        'open youtube',
        'how much free space is on my c drive',
        'kill the chrome process',
        'what is my ip address',
        'show active network ports',
        'restart my computer',
        'commit my changes with message fixed bugs',
        'show RAM usage',
        'create a new folder called testing_folder',
        'show startup apps',
        'clear the console',
        'check screen resolution'
    ]

    results = []
    print("Running tests...")
    for case in test_cases:
        print(f"Translating: {case}")
        res = translator.translate(case)
        results.append({
            'input': case,
            'command': res.command,
            'confidence': res.confidence,
            'explanation': res.explanation
        })

    with open("nlp_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("Results written to nlp_results.json")

except Exception as e:
    with open("nlp_results_error.txt", "w", encoding="utf-8") as f:
        f.write(traceback.format_exc())
    print("Error occurred", e)
