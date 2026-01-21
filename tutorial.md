# Healix Framework: AI-Powered Test Self-Healing

Healix is a reusable framework designed to make automated tests resilient to UI changes using local AI.

## 🚀 Milestone 1: Local Secure Healing
Demonstrates autonomous healing with **Enterprise-Grade Privacy**.
- **DOM Scrubbing:** Strips noise (scripts, styles) to minimize token usage.
- **PII Masking:** Replaces sensitive text with `[MASKED]` before local inference.

**Run Milestone 1:**
```bash
python milestone_1.py
```

## 🧠 Milestone 2: Reusable Framework & Caching
Transforms the script into a reusable engine with persistence.
- **Persistence:** Successful fixes are stored in `healix_cache.json`.
- **Performance:** Subsequent failures for the same element are healed instantly from the cache, bypassing the LLM.
- **Framework Ready:** The `Healix` class is separated into `healix.py` for easy integration.

**Run Milestone 2:**
```bash
python milestone_2.py
```

---

## 🛠️ Setup Instructions

### 1. Prerequisites
Install [Ollama](https://ollama.com) and ensure it is running.

### 2. Installation
```bash
# Install dependencies
pip install playwright beautifulsoup4 requests

# Install browser binaries
playwright install chromium

# Pull the AI model
ollama pull qwen2.5-coder:7b
```

## 🔍 What to Observe in Milestone 2
When you run `milestone_2.py`, observe the terminal:
1. **Run 1:** You'll see the AI being invoked to find a fix (takes a few seconds).
2. **Run 2:** You'll see **"Retrieved from Local Healing Cache"**. This happens nearly instantly because the fix was persisted to `healix_cache.json`.
3. **Persistence:** Check your project folder for `healix_cache.json` after the run to see the stored selector mapping.
