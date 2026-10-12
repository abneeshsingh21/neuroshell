"""
NeuroShell Kaggle CLI Training Orchestrator.
Manages the end-to-end cloud GPU fine-tuning lifecycle for EmbeddingGemma 2 (270M):
1. Verifies Kaggle CLI authentication credentials.
2. Generates the 7-category multi-domain dataset (Polyglot Dev, SysAdmin, Recon, Web, PrivEsc, Passwords, Orchestration).
3. Pushes updated dataset version to Kaggle via `kaggle datasets version`.
4. Dispatches GPU training kernel via `kaggle kernels push`.
5. Monitors training progress and pulls trained INT8 ONNX & vector database to models/native_ai/.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = REPO_ROOT / "data" / "kaggle_dataset"
KERNEL_DIR = REPO_ROOT / "scripts" / "train" / "kaggle_kernel"
MODELS_DIR = REPO_ROOT / "models" / "native_ai"

DATASET_REF = "abneeshsingh/neuroshell-command-corpus"
KERNEL_REF = "abneeshsingh/neuroshell-embeddinggemma-train"


class KaggleTrainer:
    """Automates model training operations using Kaggle CLI."""

    @staticmethod
    def get_kaggle_bin() -> str:
        """Locate kaggle executable on system or in venv."""
        bin_path = shutil.which("kaggle") or shutil.which("kaggle.exe")
        if bin_path:
            return bin_path
        # Check standard python script paths on Windows
        candidate = Path(sys.prefix) / "Scripts" / "kaggle.exe"
        if candidate.exists():
            return str(candidate)
        return "kaggle"

    @classmethod
    def check_auth(cls) -> tuple[bool, str]:
        """Verify that Kaggle CLI is authenticated."""
        k_bin = cls.get_kaggle_bin()
        try:
            cp = subprocess.run([k_bin, "config", "view"], capture_output=True, text=True, timeout=10)
            if "username:" in cp.stdout:
                user = ""
                for line in cp.stdout.splitlines():
                    if "username:" in line:
                        user = line.split(":", 1)[1].strip()
                return True, f"Authenticated as Kaggle user: {user}"
            return False, cp.stderr or "No Kaggle credentials found."
        except Exception as e:
            return False, str(e)

    @classmethod
    def generate_corpus(cls, samples: int = 50000) -> bool:
        """Run dataset synthesis across all 7 categories."""
        gen_script = REPO_ROOT / "scripts" / "train" / "generate_dataset.py"
        print(f"[*] Generating {samples:,} multi-domain dataset samples across 7 categories...")
        cp = subprocess.run([
            sys.executable, str(gen_script), "--samples", str(samples)
        ], capture_output=True, text=True)

        if cp.returncode == 0:
            print(cp.stdout)
            return True
        print(f"❌ Dataset generation failed: {cp.stderr}")
        return False

    @classmethod
    def push_dataset(cls, message: str = "Update 7-category Cyber and Dev corpus") -> bool:
        """Push dataset directory to Kaggle."""
        k_bin = cls.get_kaggle_bin()
        if not DATASET_DIR.exists():
            print(f"❌ Dataset directory does not exist: {DATASET_DIR}")
            return False

        print(f"[*] Uploading dataset version to Kaggle ({DATASET_REF})...")
        cp = subprocess.run([
            k_bin, "datasets", "version",
            "-p", str(DATASET_DIR),
            "-m", message,
            "--dir-mode", "zip"
        ], capture_output=True, text=True)

        print(cp.stdout)
        if cp.stderr:
            print(cp.stderr)
        return cp.returncode == 0

    @classmethod
    def push_kernel(cls) -> bool:
        """Push and trigger training kernel on Kaggle GPU."""
        k_bin = cls.get_kaggle_bin()
        if not KERNEL_DIR.exists():
            print(f"❌ Kernel directory does not exist: {KERNEL_DIR}")
            return False

        print(f"[*] Dispatching GPU training kernel to Kaggle ({KERNEL_REF})...")
        cp = subprocess.run([
            k_bin, "kernels", "push",
            "-p", str(KERNEL_DIR)
        ], capture_output=True, text=True)

        print(cp.stdout)
        if cp.stderr:
            print(cp.stderr)
        return cp.returncode == 0

    @classmethod
    def get_status(cls) -> str:
        """Fetch current status of Kaggle training kernel."""
        k_bin = cls.get_kaggle_bin()
        try:
            cp = subprocess.run([
                k_bin, "kernels", "status", KERNEL_REF
            ], capture_output=True, text=True, timeout=15)
            out = cp.stdout.strip()
            if "KernelWorkerStatus.COMPLETE" in out or "complete" in out.lower():
                return "COMPLETE"
            elif "KernelWorkerStatus.RUNNING" in out or "running" in out.lower():
                return "RUNNING"
            elif "KernelWorkerStatus.QUEUED" in out or "queued" in out.lower():
                return "QUEUED"
            elif "KernelWorkerStatus.ERROR" in out or "error" in out.lower():
                return "ERROR"
            return out or "UNKNOWN"
        except Exception as e:
            return f"Error querying status: {e}"

    @classmethod
    def pull_model(cls) -> bool:
        """Download trained model artifacts from Kaggle into models/native_ai/."""
        k_bin = cls.get_kaggle_bin()
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        print(f"[*] Downloading trained ONNX model artifacts to {MODELS_DIR}...")
        cp = subprocess.run([
            k_bin, "kernels", "output", KERNEL_REF,
            "-p", str(MODELS_DIR)
        ], capture_output=True, text=True)

        print(cp.stdout)
        if cp.stderr:
            print(cp.stderr)

        print("\n📦 Available Local Models & Embeddings:")
        for f in MODELS_DIR.glob("*"):
            sz = f.stat().st_size / 1024
            print(f"  • {f.name:<25} ({sz:.1f} KB)")
        return cp.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="NeuroShell Kaggle Training Orchestrator")
    parser.add_argument("action", choices=["auth", "generate", "push-data", "push-kernel", "status", "pull", "full-pipeline"],
                        help="Action to perform")
    parser.add_argument("--samples", type=int, default=50000, help="Number of dataset samples (default: 50000)")
    parser.add_argument("--message", type=str, default="Update 7-category Cyber and Dev corpus", help="Dataset version note")
    parser.add_argument("--watch", action="store_true", help="Watch kernel status until completion")

    args = parser.parse_args()

    print("=" * 65)
    print("🧠 NeuroShell Kaggle CLI Model Training Orchestrator")
    print("=" * 65)

    ok, msg = KaggleTrainer.check_auth()
    if not ok:
        print(f"❌ Kaggle CLI Authentication Error: {msg}")
        sys.exit(1)
    print(f"✔ {msg}\n")

    if args.action == "auth":
        return

    if args.action == "generate":
        KaggleTrainer.generate_corpus(samples=args.samples)

    elif args.action == "push-data":
        KaggleTrainer.push_dataset(message=args.message)

    elif args.action == "push-kernel":
        KaggleTrainer.push_kernel()

    elif args.action == "status":
        st = KaggleTrainer.get_status()
        print(f"📊 Current Kernel Status: {st}")

    elif args.action == "pull":
        KaggleTrainer.pull_model()

    elif args.action == "full-pipeline":
        print("[1/4] Generating 7-category dataset...")
        if not KaggleTrainer.generate_corpus(samples=args.samples):
            sys.exit(1)

        print("\n[2/4] Uploading dataset version to Kaggle...")
        if not KaggleTrainer.push_dataset(message=args.message):
            sys.exit(1)

        print("\n[3/4] Launching GPU training kernel on Kaggle...")
        if not KaggleTrainer.push_kernel():
            sys.exit(1)

        if args.watch:
            print("\n[4/4] Watching training kernel...")
            while True:
                st = KaggleTrainer.get_status()
                print(f"  • Status: {st} at {time.strftime('%H:%M:%S')}")
                if st == "COMPLETE":
                    print("\n🎉 Training completed! Downloading artifacts...")
                    KaggleTrainer.pull_model()
                    break
                elif st in ("ERROR", "CANCELLED"):
                    print(f"\n❌ Kernel ended with status {st}.")
                    break
                time.sleep(30)
        else:
            print("\n✔ Training launched successfully on Kaggle GPU!")
            print("  Check status anytime with: python scripts/train/kaggle_trainer.py status")
            print("  Download trained model with: python scripts/train/kaggle_trainer.py pull")


if __name__ == "__main__":
    main()
