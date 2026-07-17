# Self-hosted Holo inference for Ghostpanel — OpenAI-compatible vLLM server.
#
# Serves Hcompany/Holo-3.1-35B-A3B (Apache-2.0) on a single NVIDIA H100 in FP8,
# exposing the OpenAI-compatible API at /v1. This is a drop-in replacement for
# the hosted H-Company Holo endpoint: it emits coordinates on the SAME 0-1000
# normalized grid, so Ghostpanel's LiveHoloClient/SelfHostedHoloClient work
# against it unchanged. See ../../docs/SELF_HOSTING.md.
#
# Build:  docker build -t ghostpanel-holo-vllm deploy/vllm
# Run:    docker run --gpus all -p 8000:8000 \
#           -e HF_TOKEN=hf_xxx \
#           -v ~/.cache/huggingface:/root/.cache/huggingface \
#           ghostpanel-holo-vllm

# Pin a concrete vLLM release for reproducibility. The official image already
# bundles CUDA + PyTorch + vLLM's OpenAI server entrypoint.
FROM vllm/vllm-openai:v0.6.6

# ---- Model + serving configuration (override at `docker run` with -e) --------
# The Holo weights vLLM will download from the Hugging Face Hub on first boot.
ENV MODEL_ID=Hcompany/Holo-3.1-35B-A3B
# FP8 fits the 35B-total / 3B-active (A3B, MoE) model comfortably on one H100
# (80GB) with room for KV cache. Use "bitsandbytes"/GGUF paths for smaller GPUs.
ENV QUANTIZATION=fp8
# Vision model: allow up to 5 images per request (matches the hosted Holo cap).
ENV MAX_MODEL_LEN=65536
ENV GPU_MEMORY_UTILIZATION=0.92
ENV SERVED_MODEL_NAME=Hcompany/Holo-3.1-35B-A3B
ENV PORT=8000

EXPOSE 8000

# The base image's entrypoint is `python -m vllm.entrypoints.openai.api_server`.
# We override CMD to pass our serving flags. --served-model-name keeps the model
# id stable regardless of the on-disk path, so HAI_MODEL in the app matches.
ENTRYPOINT []
CMD ["sh", "-c", "python3 -m vllm.entrypoints.openai.api_server \
  --model ${MODEL_ID} \
  --served-model-name ${SERVED_MODEL_NAME} \
  --quantization ${QUANTIZATION} \
  --max-model-len ${MAX_MODEL_LEN} \
  --gpu-memory-utilization ${GPU_MEMORY_UTILIZATION} \
  --limit-mm-per-prompt image=5 \
  --trust-remote-code \
  --host 0.0.0.0 \
  --port ${PORT}"]
