# Your Own AI — Self‑Hosted, No API Key (Ollama)

**Goal:** run Juriscite's AI on **your own open‑weight model, locally, with no paid API key.**
Juriscite is provider‑agnostic, so it talks to a local model exactly like any OpenAI‑compatible endpoint.

> Honest note: this is **not** "training a neural network from scratch" (that needs many GPUs, months,
> millions, and a labelled dataset — and an AI‑generated legal dataset would *cause* hallucinations).
> Instead you run a **pre‑trained open model you fully control**, and Juriscite **grounds it on your
> verified corpus via RAG** so every answer is cited. Same outcome (knows your law), honest + safe + free.

## Your machine (detected 2026‑06‑26)
- RAM **13.9 GB**, GPU **NVIDIA GTX 1650 (~4 GB VRAM)** → comfortably runs a 3B model; runs a 7–8B
  quantized model (partly on GPU, rest on CPU/RAM) a bit slower.

## Recommended models (pick one)
| Model | Pull | Best for |
|---|---|---|
| **Llama 3.1 8B** (Q4) | `ollama pull llama3.1:8b` | Best quality on your box (a touch slower) |
| **Qwen2.5 7B Instruct** | `ollama pull qwen2.5:7b-instruct` | Strong instruction-following for drafting |
| **Llama 3.2 3B** | `ollama pull llama3.2:3b` | Fastest; lighter answers |

## Setup (3 steps)
1. **Install Ollama** (free, trusted): `winget install Ollama.Ollama`  — or download from https://ollama.com
2. **Pull a model** (one‑time ~2–5 GB download): e.g. `ollama pull qwen2.5:7b-instruct`
   (Ollama then serves an OpenAI‑compatible API at `http://localhost:11434/v1` — no key.)
3. **Point Juriscite at it** — in the server's `.env`:
   ```
   AI_API_KEY=ollama                       # any non-empty string; Ollama ignores it
   AI_BASE_URL=http://localhost:11434/v1
   AI_MODEL=qwen2.5:7b-instruct
   ```
   Restart the server. The AI Assistant now runs **entirely on your local model** — no external call,
   no key — and stays grounded + cited via your 19‑act corpus and live case law.

## Production (EC2)
The small EC2 box (≈1 GB RAM) can't run a useful local model. Options: (a) keep the local model on a
machine with RAM/GPU and point the app at it over a private network/tunnel, or (b) run Ollama on a larger
instance. Until then, the app degrades gracefully (shows cited provisions + judgments in chat).

## Reality check (speed/quality)
A local 7–8B model on a GTX 1650 answers in a few seconds (slower than cloud), at good‑but‑not‑GPT‑4
quality — the fair trade for **full independence and zero keys/cost**. RAG keeps it accurate + cited.
If you later want a *real* fine‑tune, that's a separate funded project (GPUs + advocate‑labelled data +
G8 review) and still sits behind RAG.
