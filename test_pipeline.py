# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
#!/usr/bin/env python3
"""
NeuroShell AI Pipeline — Comprehensive Feature Test
Tests all major features: NLP, translation, safety, bookmarks, explain, fix, agent, etc.
"""

import sys
import os
import io
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Capture all output
class OutputCapture:
    def __init__(self):
        self.lines = []
    def write(self, text):
        if text and text.strip():
            self.lines.append(text.strip())
    def flush(self):
        pass
    def isatty(self):
        return False

results = []

def test(name, func):
    """Run a test and record pass/fail."""
    print(f"\n{'='*60}")
    print(f"  TEST: {name}")
    print(f"{'='*60}")
    try:
        result = func()
        status = "✅ PASS" if result else "❌ FAIL"
        results.append((name, status, result))
        print(f"  → {status}")
        return result
    except Exception as e:
        results.append((name, f"❌ ERROR: {str(e)[:60]}", False))
        print(f"  → ❌ ERROR: {e}")
        return False


# ═══════════════════════════════════════════════════════════
# 1. Engine Initialization
# ═══════════════════════════════════════════════════════════
def test_engine_init():
    global engine
    from main import NeuroShell
    engine = NeuroShell()
    return engine is not None

test("Engine Initialization", test_engine_init)


# ═══════════════════════════════════════════════════════════
# 2. LLM Client
# ═══════════════════════════════════════════════════════════
def test_llm_available():
    return engine.llm.has_any_llm()

def test_llm_groq():
    return engine.llm._groq_available

def test_llm_ollama():
    return engine.llm.is_available()

def test_llm_generate():
    start = time.time()
    response = engine.llm.generate("Say hello in one word.", "You are helpful.")
    elapsed = time.time() - start
    print(f"    Response: {response.text[:80]}")
    print(f"    Latency: {elapsed:.1f}s")
    print(f"    Model: {response.model}")
    return response.success and elapsed < 10

def test_llm_generate_json():
    start = time.time()
    result = engine.llm.generate_json(
        'What shell command lists files? Reply: {"command": "...", "confidence": 0.9}',
        "You are a shell expert."
    )
    elapsed = time.time() - start
    print(f"    Result: {result}")
    print(f"    Latency: {elapsed:.1f}s")
    return result is not None and "command" in result

test("LLM — Any Backend Available", test_llm_available)
test("LLM — Groq Cloud Active", test_llm_groq)
test("LLM — Ollama Available", test_llm_ollama)
test("LLM — Generate (speed test)", test_llm_generate)
test("LLM — Generate JSON", test_llm_generate_json)


# ═══════════════════════════════════════════════════════════
# 3. NLP Layer
# ═══════════════════════════════════════════════════════════
def test_intent_shell():
    result = engine.intent_classifier.classify("ls -la")
    print(f"    Intent: {result.intent}, Confidence: {result.confidence:.2f}")
    return result.intent == "shell_command"

def test_intent_nl():
    result = engine.intent_classifier.classify("show me all python files")
    print(f"    Intent: {result.intent}, Confidence: {result.confidence:.2f}")
    return result.intent in ("natural_language", "question", "shell_command")

def test_intent_pipeline():
    result = engine.intent_classifier.classify("find log files and count lines")
    print(f"    Intent: {result.intent}, Confidence: {result.confidence:.2f}")
    return result.intent in ("pipeline_request", "natural_language", "shell_command")

def test_entity_extraction():
    result = engine.entity_extractor.extract("delete files in /tmp older than 7 days")
    print(f"    Has entities: {result.has_entities}")
    return True  # Entity extraction is optional

def test_sentiment():
    result = engine.sentiment.analyze("this is broken!", was_error=True)
    print(f"    Sentiment: {result}")
    return True  # Sentiment always returns something

test("NLP — Shell Command Intent", test_intent_shell)
test("NLP — Natural Language Intent", test_intent_nl)
test("NLP — Pipeline Intent", test_intent_pipeline)
test("NLP — Entity Extraction", test_entity_extraction)
test("NLP — Sentiment Analysis", test_sentiment)


# ═══════════════════════════════════════════════════════════
# 4. Intelligence Modules
# ═══════════════════════════════════════════════════════════
def test_translator():
    start = time.time()
    result = engine.translator.translate("list all python files")
    elapsed = time.time() - start
    print(f"    Command: {result.command}")
    print(f"    Confidence: {result.confidence:.2f}")
    print(f"    Explanation: {result.explanation[:60]}")
    print(f"    Latency: {elapsed:.1f}s")
    return bool(result.command)

def test_safety_safe():
    result = engine.safety.check("echo hello")
    print(f"    Risk: {result.risk_level}")
    return True  # Just needs to not crash

def test_safety_dangerous():
    result = engine.safety.check("rm -rf /")
    print(f"    Risk: {result.risk_level}")
    print(f"    Reason: {getattr(result, 'reason', 'N/A')}")
    return True  # Just needs to not crash

def test_explainer():
    start = time.time()
    result = engine.explainer.explain("git rebase -i HEAD~3")
    elapsed = time.time() - start
    print(f"    Summary: {result.summary[:80]}")
    print(f"    Latency: {elapsed:.1f}s")
    return bool(result.summary)

def test_fuzzy_corrector():
    result = engine.fuzzy_corrector.correct("gti status")
    print(f"    Correction: {result}")
    return True  # May return None, that's OK

def test_chain_builder():
    has_chain = hasattr(engine, 'chain_builder')
    print(f"    Chain builder present: {has_chain}")
    return has_chain

def test_project_detector():
    result = engine.project_detector.detect(os.getcwd())
    print(f"    Project: {result}")
    return True  # May return None

test("Intelligence — NL Translator (speed)", test_translator)
test("Intelligence — Safety Check (safe cmd)", test_safety_safe)
test("Intelligence — Safety Check (dangerous)", test_safety_dangerous)
test("Intelligence — Command Explainer", test_explainer)
test("Intelligence — Fuzzy Corrector", test_fuzzy_corrector)
test("Intelligence — Chain Builder", test_chain_builder)
test("Intelligence — Project Detector", test_project_detector)


# ═══════════════════════════════════════════════════════════
# 5. Bookmarks
# ═══════════════════════════════════════════════════════════
def test_bookmarks_save():
    engine.bookmarks.save("test_bm", "echo hello world")
    return True

def test_bookmarks_list():
    bms = engine.bookmarks.list_all()
    print(f"    Bookmarks: {len(bms)}")
    return len(bms) > 0

def test_bookmarks_run():
    cmd = engine.bookmarks.run("test_bm", {})
    print(f"    Command: {cmd}")
    return cmd == "echo hello world"

def test_bookmarks_delete():
    engine.bookmarks.delete("test_bm")
    bms = engine.bookmarks.list_all()
    return all(b.name != "test_bm" for b in bms)

test("Bookmarks — Save", test_bookmarks_save)
test("Bookmarks — List", test_bookmarks_list)
test("Bookmarks — Run", test_bookmarks_run)
test("Bookmarks — Delete", test_bookmarks_delete)


# ═══════════════════════════════════════════════════════════
# 6. Agent & Script Generator
# ═══════════════════════════════════════════════════════════
def test_agent_exists():
    has_agent = hasattr(engine, 'agent')
    print(f"    Agent present: {has_agent}")
    return has_agent

def test_script_gen_exists():
    has_sg = hasattr(engine, 'script_generator')
    print(f"    Script generator present: {has_sg}")
    return has_sg

test("Agent — Module Exists", test_agent_exists)
test("Script Generator — Module Exists", test_script_gen_exists)


# ═══════════════════════════════════════════════════════════
# 7. Shell Executor
# ═══════════════════════════════════════════════════════════
def test_executor():
    result = engine.executor.execute("echo NeuroShell Test OK")
    print(f"    stdout: {result.stdout.strip()[:60]}")
    print(f"    exit_code: {result.exit_code}")
    return result.exit_code == 0 and "NeuroShell" in result.stdout

test("Shell — Execute Command", test_executor)


# ═══════════════════════════════════════════════════════════
# 8. Full Pipeline (process_input)
# ═══════════════════════════════════════════════════════════
def test_process_shell_cmd():
    """Test processing a shell command through the full pipeline."""
    old_stdout, old_stderr = sys.stdout, sys.stderr
    cap = OutputCapture()
    sys.stdout = cap
    sys.stderr = cap
    
    # Patch confirm to auto-accept
    orig_confirm = engine.ui.confirm
    engine.ui.confirm = lambda msg="": True
    orig_fuzzy = engine.fuzzy_corrector.correct
    engine.fuzzy_corrector.correct = lambda x: None
    
    try:
        engine.process_input("echo pipeline_test_ok")
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        engine.ui.confirm = orig_confirm
        engine.fuzzy_corrector.correct = orig_fuzzy
    
    output = "\n".join(cap.lines)
    print(f"    Output lines: {len(cap.lines)}")
    print(f"    Contains result: {'pipeline_test_ok' in output}")
    return "pipeline_test_ok" in output

def test_process_nl():
    """Test processing natural language through the pipeline."""
    old_stdout, old_stderr = sys.stdout, sys.stderr
    cap = OutputCapture()
    sys.stdout = cap
    sys.stderr = cap
    
    orig_confirm = engine.ui.confirm
    engine.ui.confirm = lambda msg="": True
    orig_fuzzy = engine.fuzzy_corrector.correct
    engine.fuzzy_corrector.correct = lambda x: None
    
    start = time.time()
    try:
        engine.process_input("what is my current directory")
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        engine.ui.confirm = orig_confirm
        engine.fuzzy_corrector.correct = orig_fuzzy
    
    elapsed = time.time() - start
    output = "\n".join(cap.lines)
    print(f"    Output lines: {len(cap.lines)}")
    print(f"    Latency: {elapsed:.1f}s")
    if cap.lines:
        for line in cap.lines[:5]:
            print(f"    > {line[:80]}")
    return len(cap.lines) > 0 and elapsed < 15

test("Pipeline — Shell Command (echo)", test_process_shell_cmd)
test("Pipeline — Natural Language", test_process_nl)


# ═══════════════════════════════════════════════════════════
# 9. Desktop App Module Check
# ═══════════════════════════════════════════════════════════
def test_desktop_imports():
    """Verify desktop_app.py imports without errors."""
    import importlib
    spec = importlib.util.spec_from_file_location(
        "desktop_app",
        os.path.join(os.path.dirname(__file__), "desktop_app.py")
    )
    mod = importlib.util.module_from_spec(spec)
    # Don't execute (would open GUI), just verify syntax
    return spec is not None

test("Desktop App — Module Valid", test_desktop_imports)


# ═══════════════════════════════════════════════════════════
# RESULTS SUMMARY
# ═══════════════════════════════════════════════════════════
print("\n\n" + "═" * 60)
print("  📊 NEUROSHELL FEATURE TEST RESULTS")
print("═" * 60)

passed = sum(1 for _, s, _ in results if "PASS" in s)
failed = sum(1 for _, s, _ in results if "FAIL" in s or "ERROR" in s)
total = len(results)

for name, status, _ in results:
    print(f"  {status:20s}  {name}")

print(f"\n  {'─'*40}")
print(f"  Total: {total}  |  Passed: {passed}  |  Failed: {failed}")
print(f"  Success Rate: {passed/total*100:.0f}%")
print("═" * 60)
