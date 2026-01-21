# AI Quality Engine: Milestone 1 Setup

This project demonstrates **Local Self-Healing Tests** with **Enterprise-Grade Privacy**. It uses a local LLM to fix broken CSS selectors without exposing sensitive data.

## 1. Prerequisites
Ensure you have [Ollama](https://ollama.com) installed and running on your machine.

## 2. Environment Setup
Run these commands in your terminal to install dependencies and the local AI model.

```bash
# 1. Install Python dependencies
pip install playwright beautifulsoup4 requests

# 2. Install Playwright browser binaries
playwright install chromium

# 3. Pull the local AI model (Requires Ollama running)
ollama pull qwen2.5-coder:7b
```

## 3. Run the Demo
Execute the script to see the self-healing logic in action.

```bash
python milestone_1.py
```

## 4. What to Observe
The script simulates a broken test case where an element's ID has changed. 

### The "Enterprise Security" Proof
Watch the terminal output for **"Initiating Local Secure Healing"**. Behind the scenes:
1. **DOM Scrubbing:** The script uses `BeautifulSoup` to strip all `<script>` and `<style>` tags.
2. **PII Masking:** It replaces all text in non-structural elements with `[SENSITIVE_DATA_MASKED]`.
3. **Local Inference:** The structural "skeleton" of the page is sent to your **local** Ollama instance. No data ever leaves your machine.
4. **Healing:** The AI identifies the correct selector (`#username`) based on context and continues the test.
