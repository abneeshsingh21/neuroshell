# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Utility script to monitor and pull trained EmbeddingGemma 2 checkpoints
from Kaggle GPU into neuroshell/models/native_ai/.
"""

import subprocess
import sys
import time
from pathlib import Path

KERNEL_REF = "abneeshsingh/neuroshell-embeddinggemma-train"
MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models" / "native_ai"


def check_status() -> str:
    res = subprocess.run(["kaggle", "kernels", "status", KERNEL_REF], capture_output=True, text=True)
    out = res.stdout.strip()
    if "KernelWorkerStatus.COMPLETE" in out:
        return "COMPLETE"
    elif "KernelWorkerStatus.RUNNING" in out:
        return "RUNNING"
    elif "KernelWorkerStatus.QUEUED" in out:
        return "QUEUED"
    elif "KernelWorkerStatus.ERROR" in out:
        return "ERROR"
    return out


def pull_output():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[*] Downloading trained model artifacts into {MODELS_DIR}...")
    res = subprocess.run([
        "kaggle", "kernels", "output", KERNEL_REF,
        "-p", str(MODELS_DIR)
    ], capture_output=True, text=True)

    print(res.stdout)
    if res.stderr:
        print(res.stderr)

    print("\n📦 Downloaded Artifacts:")
    for f in MODELS_DIR.glob("*"):
        size_kb = f.stat().st_size / 1024
        print(f"  -> {f.name} ({size_kb:.1f} KB)")


def main():
    status = check_status()
    print(f"[*] Current Kaggle Kernel Status: {status}", flush=True)

    if len(sys.argv) > 1 and sys.argv[1] == "--watch":
        print("[*] Watching kernel until completion...", flush=True)
        while status in ("QUEUED", "RUNNING"):
            time.sleep(30)
            status = check_status()
            print(f"[*] Status: {status} at {time.strftime('%H:%M:%S')}", flush=True)

    if status == "COMPLETE":
        pull_output()
        print("\n✅ Native AI Model Checkpoint Successfully Retrieved!", flush=True)
    elif status == "ERROR":
        print("\n❌ Kernel encountered an error during execution. Run 'kaggle kernels output' to inspect logs.", flush=True)
    else:
        print(f"\n[*] Kernel is still {status}. Run with --watch to wait for completion.", flush=True)


if __name__ == "__main__":
    main()
