# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Benchmark and verification script for fine-tuned EmbeddingGemma 2 ONNX model
and pre-indexed action vector database.
"""

import time
import sqlite3
from pathlib import Path
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

def benchmark():
    models_dir = Path(__file__).resolve().parent.parent.parent / "models" / "native_ai"
    tokenizer_path = models_dir / "tokenizer.json"
    model_path = models_dir / "model_int8.onnx"
    db_path = models_dir / "action_vectors.db"

    print("==================================================================")
    print("🧠 NeuroShell Native AI Inference & Vector Search Benchmark")
    print("==================================================================")
    print(f"[*] Loading Tokenizer: {tokenizer_path.name}")
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    tokenizer.enable_truncation(max_length=64)
    tokenizer.enable_padding(length=64)

    print(f"[*] Initializing ONNXRuntime Session: {model_path.name}")
    sess_opts = ort.SessionOptions()
    sess_opts.intra_op_num_threads = 4
    session = ort.InferenceSession(str(model_path), sess_opts)

    inputs = [i.name for i in session.get_inputs()]
    outputs = [o.name for o in session.get_outputs()]
    print(f"[+] Model Inputs:  {inputs}")
    print(f"[+] Model Outputs: {outputs}")

    print(f"[*] Loading Action Vectors DB: {db_path.name}")
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute("SELECT action_id, category, canonical_nl, default_cmd, vector_256 FROM action_registry")
    rows = c.fetchall()
    actions = [(r[0], r[1], r[2], r[3], np.frombuffer(r[4], dtype=np.float32)) for r in rows]
    print(f"[+] Loaded {len(actions)} canonical action vectors (dim={len(actions[0][4])}).")

    test_cases = [
        # Standard Developer Edition
        ("undo last commit keeping changes", "GIT"),
        ("compile modern c++ project with release flags", "POLYGLOT_DEV"),
        ("docker remove all stopped containers", "DOCKER"),
        ("show git reflog history", "GIT"),
        ("list top memory consuming processes", "PROCESS"),
        
        # Cyber Security Edition
        ("run stealth syn port scan without ping probe", "RECON_SCANNING"),
        ("find suid binaries for privilege escalation", "PRIVESC"),
        ("fuzz hidden directories and files on target web server", "WEB_SECURITY"),
        ("crack wpa2 handshake with rockyou wordlist", "CRACKING"),
        ("generate base64 encoded powershell reverse shell", "ORCHESTRATION"),
        ("execute automated reconnaissance scan on target host", "RECON_SCANNING"),
    ]

    print("\n" + "=" * 66)
    print("🚀 RUNNING REAL-TIME INFERENCE & RETRIEVAL")
    print("=" * 66)

    total_latency_ms = 0.0
    correct_category_matches = 0

    for query, expected_cat in test_cases:
        t0 = time.perf_counter()
        
        # Tokenize
        encoded = tokenizer.encode(query)
        input_ids = np.array([encoded.ids], dtype=np.int64)
        attention_mask = np.array([encoded.attention_mask], dtype=np.int64)

        # Infer embedding
        feed = {"input_ids": input_ids, "attention_mask": attention_mask}
        onnx_outs = session.run(None, feed)
        
        # MRL 256 slice & L2 normalize
        raw_vec = onnx_outs[0][0, :256]
        norm = np.linalg.norm(raw_vec)
        query_vec = raw_vec / (norm + 1e-9)

        # Vector search (Dot product / Cosine Similarity against unit vectors)
        scored = []
        for act_id, cat, cnl, cmd, vec in actions:
            score = float(np.dot(query_vec, vec))
            scored.append((score, act_id, cat, cnl, cmd))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        dt_ms = (time.perf_counter() - t0) * 1000
        total_latency_ms += dt_ms

        top_score, top_id, top_cat, top_cnl, top_cmd = scored[0]
        runner_up = scored[1]

        match_status = "✅ MATCH" if top_cat == expected_cat else "⚠️ MISMATCH"
        if top_cat == expected_cat:
            correct_category_matches += 1

        print(f"\nQuery: \"{query}\" (Expected: [{expected_cat}]) [{match_status}]")
        print(f"  Latency:    {dt_ms:.2f} ms")
        print(f"  Top Match:  {top_id} (Category: {top_cat}, Similarity: {top_score:.4f})")
        print(f"  Command:    {top_cmd}")
        print(f"  Runner-up:  {runner_up[1]} (Category: {runner_up[2]}, Similarity: {runner_up[0]:.4f})")

    avg_latency = total_latency_ms / len(test_cases)
    accuracy = (correct_category_matches / len(test_cases)) * 100.0

    print("\n" + "=" * 66)
    print("📊 BENCHMARK SUMMARY")
    print("=" * 66)
    print(f"Total Test Queries:      {len(test_cases)}")
    print(f"Category Match Accuracy: {accuracy:.1f}% ({correct_category_matches}/{len(test_cases)})")
    print(f"Average Search Latency:  {avg_latency:.2f} ms per query")
    print(f"Target Threshold:        < 50.0 ms per query (Ultra-fast Native Terminal parity)")
    print("==================================================================")

if __name__ == "__main__":
    benchmark()
