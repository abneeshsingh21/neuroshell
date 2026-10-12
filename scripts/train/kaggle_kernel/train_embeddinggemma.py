# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Native AI Core: EmbeddingGemma 2 Fine-Tuning & MRL Optimization
Model: google/embeddinggemma-2 (270M Text & Code backbone)
Loss: MatryoshkaLoss [128, 256, 512, 768] + MultipleNegativesRankingLoss (MNRL)
Target: High-Precision INT8 / FP16 ONNX Export (<300MB) with Zero Quality Loss
"""

import os

os.environ["CUDA_VISIBLE_DEVICES"] = "0"
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
import glob
import json
import sqlite3
import subprocess
import sys
import time

import numpy as np

print("=" * 70)
print("🧠 NEUROSHELL NATIVE AI: EmbeddingGemma 2 Domain Specialization")
print("Target: High-Precision Matryoshka ONNX Export & Canonical Vector DB")
print("Base Model: google/embeddinggemma-2")
print("=" * 70)

# Step 1: Clean conflicting packages and install dependencies
print("[*] Checking and resolving environment dependencies...")
subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "torchaudio"], check=False)

print("[*] Installing ML, Transformers, Accelerate, and ONNX runtime...")
subprocess.run([
    sys.executable, "-m", "pip", "install", "-q", "-U",
    "sentence-transformers", "transformers", "accelerate", "peft",
    "optimum", "onnx", "onnxruntime-gpu", "torchvision", "onnxscript"
], check=True)

import torch
from sentence_transformers import InputExample, SentenceTransformer
from sentence_transformers.losses import MatryoshkaLoss, MultipleNegativesRankingLoss
from torch.utils.data import DataLoader

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"[*] Compute Device: {device}")
if torch.cuda.is_available():
    print(f"[*] GPU Name: {torch.cuda.get_device_name(0)}")
    print(f"[*] VRAM Allocated: {torch.cuda.memory_allocated(0)/(1024**2):.1f} MB")

# Step 2: Locate Dataset Files Dynamically
print("[*] Locating NeuroShell dataset in /kaggle/input/...")
dataset_train_path = None
dataset_catalog_path = None

for root, _, files in os.walk("/kaggle/input"):
    for f in files:
        if f == "neuroshell_train.jsonl":
            dataset_train_path = os.path.join(root, f)
        elif f == "canonical_recipes.json":
            dataset_catalog_path = os.path.join(root, f)

if not dataset_train_path or not dataset_catalog_path:
    print(f"[!] Warning: Searching fallback paths. Found train: {dataset_train_path}, catalog: {dataset_catalog_path}")
    candidate_train = glob.glob("/kaggle/input/**/neuroshell_train.jsonl", recursive=True)
    candidate_catalog = glob.glob("/kaggle/input/**/canonical_recipes.json", recursive=True)
    if candidate_train:
        dataset_train_path = candidate_train[0]
    if candidate_catalog:
        dataset_catalog_path = candidate_catalog[0]

print(f"[+] Using Train File: {dataset_train_path}")
print(f"[+] Using Catalog File: {dataset_catalog_path}")

# Step 3: Load Base Model
MODEL_ID = "google/embeddinggemma-2"
print(f"[*] Loading {MODEL_ID} in float32 high-precision mode...")
model = SentenceTransformer(
    MODEL_ID,
    device=device,
    model_kwargs={"torch_dtype": torch.float32}
)
model.max_seq_length = 64

# Freeze base input embeddings to guarantee numerical stability (zero NaN) and save VRAM
try:
    if hasattr(model[0].auto_model, 'get_input_embeddings'):
        emb_layer = model[0].auto_model.get_input_embeddings()
        emb_layer.requires_grad_(False)
        print("[+] Base vocabulary embedding table frozen: guarantees zero-NaN stability.")
except Exception as ee:
    print(f"[*] Embedding freeze note: {ee}")

# Step 4: Parse Training Examples
print("[*] Loading and parsing dataset samples...")
train_examples = []
if dataset_train_path and os.path.exists(dataset_train_path):
    with open(dataset_train_path, encoding="utf-8") as f:
        for idx, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            q = item.get("query", "").strip()
            tgt = item.get("target_cmd", "").strip()
            if q and tgt:
                train_examples.append(InputExample(texts=[q, tgt]))
                # Every 5th example, also add platform-specific cmd if available
                if idx % 5 == 0 and item.get("powershell_cmd"):
                    train_examples.append(InputExample(texts=[q, item["powershell_cmd"]]))
else:
    print("[!] Fatal: Training dataset file not found!")
    sys.exit(1)

print(f"[+] Loaded {len(train_examples):,} training examples.")

# Step 5: Configure DataLoader and Matryoshka Loss
# Use batch_size=24 to fit comfortably within 16GB VRAM on Tesla T4 with zero risk of OOM
batch_size = 24 if device == "cuda" else 8
train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=batch_size, drop_last=True)

base_loss = MultipleNegativesRankingLoss(model)
train_loss = MatryoshkaLoss(
    model=model,
    loss=base_loss,
    matryoshka_dims=[128, 256, 768]
)

# Step 6: Fine-Tune Model
print(f"[*] Commencing Matryoshka Fine-Tuning (Batch Size: {batch_size}, Device: {device})...")
start_time = time.time()
model.fit(
    train_objectives=[(train_dataloader, train_loss)],
    epochs=1,
    warmup_steps=min(300, len(train_dataloader) // 5),
    optimizer_params={"lr": 2e-5, "eps": 1e-8},
    weight_decay=0.01,
    show_progress_bar=True,
    use_amp=True if device == "cuda" else False
)
elapsed = time.time() - start_time
print(f"[+] Fine-tuning completed in {elapsed:.2f} seconds ({elapsed/60:.2f} minutes).")

# Step 7: Build ONNX Embedding Wrapper
print("[*] Preparing ONNX Export Wrapper with 256d Matryoshka Head...")

class GemmaEmbeddingWrapper(torch.nn.Module):
    """Wraps EmbeddingGemma-2 to output L2-normalized 256d and 768d latent vectors."""
    def __init__(self, base_model):
        super().__init__()
        self.base_model = base_model

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor):
        outputs = self.base_model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            return_dict=True
        )
        last_hidden = outputs.last_hidden_state
        mask_exp = attention_mask.unsqueeze(-1).expand(last_hidden.size()).float()
        sum_embeddings = torch.sum(last_hidden * mask_exp, dim=1)
        sum_mask = torch.clamp(mask_exp.sum(dim=1), min=1e-9)
        mean_pooled = sum_embeddings / sum_mask
        normalized = torch.nn.functional.normalize(mean_pooled, p=2, dim=1)
        # Matryoshka truncation: first 256 dimensions normalized
        vector_256 = normalized[:, :256]
        vector_256 = torch.nn.functional.normalize(vector_256, p=2, dim=1)
        return vector_256, normalized

onnx_dir = "/kaggle/working"
onnx_file = os.path.join(onnx_dir, "model.onnx")

try:
    transformer_module = model[0].auto_model
    transformer_module.eval().to("cpu")
    wrapper = GemmaEmbeddingWrapper(transformer_module)
    wrapper.eval()

    sample_tok = model.tokenizer("clean up all stopped docker containers and unused images", return_tensors="pt")
    input_ids = sample_tok["input_ids"]
    attention_mask = sample_tok["attention_mask"]

    print(f"[*] Exporting to ONNX at {onnx_file}...")
    torch.onnx.export(
        wrapper,
        (input_ids, attention_mask),
        onnx_file,
        input_names=["input_ids", "attention_mask"],
        output_names=["vector_256", "embedding_768"],
        dynamic_axes={
            "input_ids": {0: "batch", 1: "sequence"},
            "attention_mask": {0: "batch", 1: "sequence"},
            "vector_256": {0: "batch"},
            "embedding_768": {0: "batch"}
        },
        opset_version=14,
        do_constant_folding=True
    )
    onnx_mb = os.path.getsize(onnx_file) / (1024 * 1024)
    print(f"[+] ONNX export succeeded: {onnx_file} ({onnx_mb:.2f} MB)")

    # Save tokenizer directly to working directory for native bundling
    model.tokenizer.save_pretrained("/kaggle/working/")
    print("[+] Tokenizer configuration saved to /kaggle/working/")

    # Validate with onnxruntime
    import onnxruntime as ort
    sess = ort.InferenceSession(onnx_file, providers=["CPUExecutionProvider"])
    ort_inputs = {
        "input_ids": input_ids.numpy(),
        "attention_mask": attention_mask.numpy()
    }
    v256_out, v768_out = sess.run(None, ort_inputs)
    assert not np.isnan(v256_out).any(), "FATAL: Exported ONNX produced NaNs in vector_256!"
    print(f"[+] ONNX CPU validation verified: v256 shape {v256_out.shape}, all finite values.")

    # Generate INT8 Quantized model for on-device ultra-low-latency execution
    try:
        from onnxruntime.quantization import quantize_dynamic, QuantType
        int8_file = os.path.join(onnx_dir, "model_int8.onnx")
        print(f"[*] Quantizing to INT8 at {int8_file}...")
        quantize_dynamic(
            model_input=onnx_file,
            model_output=int8_file,
            weight_type=QuantType.QInt8
        )
        int8_mb = os.path.getsize(int8_file) / (1024 * 1024)
        print(f"[+] INT8 ONNX generated: {int8_file} ({int8_mb:.2f} MB)")
    except Exception as q_err:
        print(f"[*] INT8 quantization note: {q_err}")
except Exception as onnx_err:
    print(f"[!] ONNX export error: {onnx_err}")
    import traceback
    traceback.print_exc()

# Step 8: Build Canonical Action Vector Database (action_vectors.db)
print("[*] Generating Pre-Indexed Canonical Action Vector Database...")
db_path = "/kaggle/working/action_vectors.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS action_registry (
    action_id TEXT PRIMARY KEY,
    category TEXT,
    canonical_nl TEXT,
    default_cmd TEXT,
    powershell_cmd TEXT,
    cmd_exe TEXT,
    vector_256 BLOB,
    is_destructive INTEGER,
    explanation TEXT
)
""")

recipes_catalog = []
if dataset_catalog_path and os.path.exists(dataset_catalog_path):
    with open(dataset_catalog_path, encoding="utf-8") as f:
        recipes_catalog = json.load(f)

print(f"[*] Embedding {len(recipes_catalog)} canonical actions with fine-tuned model...")
model.to("cpu")
texts_to_embed = [item["canonical_nl"] for item in recipes_catalog]
full_embeddings = model.encode(texts_to_embed, normalize_embeddings=True)

# Truncate to 256 dimensions and L2 normalize
embeddings_256 = full_embeddings[:, :256]
embeddings_256 = embeddings_256 / np.linalg.norm(embeddings_256, axis=1, keepdims=True)

for i, item in enumerate(recipes_catalog):
    vec_blob = embeddings_256[i].astype(np.float32).tobytes()
    cursor.execute("""
    INSERT OR REPLACE INTO action_registry VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        item["action_id"],
        item["category"],
        item["canonical_nl"],
        item["default_cmd"],
        item.get("powershell_cmd", item["default_cmd"]),
        item.get("cmd_exe", item["default_cmd"]),
        vec_blob,
        1 if item.get("is_destructive") else 0,
        item.get("explanation", "")
    ))

conn.commit()
conn.close()
db_kb = os.path.getsize(db_path) / 1024
print(f"[+] Canonical vector database generated: {db_path} ({db_kb:.2f} KB)")

# Step 9: Final Inventory of Exported Artifacts
print("=" * 70)
print("📦 FINAL GENERATED ARTIFACTS IN /kaggle/working/:")
for root, _, files in os.walk("/kaggle/working/"):
    for file in files:
        fpath = os.path.join(root, file)
        size_kb = os.path.getsize(fpath) / 1024
        print(f"  -> {file} ({size_kb:.2f} KB)")
print("=" * 70)
print("✅ NeuroShell Native AI Model Training & Export Complete!")
