# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Streams trained model artifacts directly from Kaggle CDN to models/native_ai/
with chunked streaming to handle large files (1GB+ ONNX) without socket timeouts.
"""

from pathlib import Path

import requests
from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.kernels.types.kernels_api_service import ApiListKernelSessionOutputRequest

MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models" / "native_ai"


def stream_download():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    api = KaggleApi()
    api.authenticate()

    with api.build_kaggle_client() as kaggle:
        req = ApiListKernelSessionOutputRequest()
        req.user_name = "abneeshsingh"
        req.kernel_slug = "neuroshell-embeddinggemma-train"
        resp = kaggle.kernels.kernels_api_client.list_kernel_session_output(req)

    print(f"[*] Found {len(resp.files)} output artifacts on Kaggle:")
    for f in resp.files:
        target_path = MODELS_DIR / f.file_name
        print(f"[*] Streaming {f.file_name} -> {target_path} ...", flush=True)

        # Stream download with 1MB chunk size
        with requests.get(f.url, stream=True, timeout=300) as r:
            r.raise_for_status()
            total_bytes = 0
            with open(target_path, "wb") as out:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        out.write(chunk)
                        total_bytes += len(chunk)
            print(f"  ✓ Downloaded {f.file_name}: {total_bytes / (1024*1024):.2f} MB", flush=True)

    print("\n✅ All artifacts successfully streamed to models/native_ai/!", flush=True)


if __name__ == "__main__":
    stream_download()
