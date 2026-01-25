# Healix

**Healix** is an intelligent web automation agent that self-heals broken selectors and adapts to dynamic web pages using AI-powered DOM analysis.

## 🎯 The Problem

Web automation is fragile. Selectors break when:
- Developers change class names
- DOM structure shifts
- Content loads dynamically
- A/B tests alter page layouts

## 🚀 The Solution

Healix uses an **agentic loop** to automatically detect and fix selector failures:

1. **Observe** - Analyze the current page state and DOM
2. **Reason** - Use AI to determine the correct selector/action
3. **Act** - Execute the corrected action
4. **Verify** - Confirm the action succeeded
5. **Learn** - Cache successful fixes for future use

## 🏗️ Architecture

```
healix/
├── .github/                   # CI/CD workflows
│   └── workflows/
│       └── main.yml           # Automated test runs
├── src/                       # Source code for the library
│   └── healix/
│       ├── __init__.py        # Makes it a package
│       ├── engine.py          # The core Healix class
│       └── utilities/         # Helper functions
│           ├── __init__.py
│           └── dom_scrubber.py # BeautifulSoup logic
├── tests/                     # Test suites to verify Healix
│   ├── integration/
│   │   └── test_login.py      # Demo test case
│   └── unit/
│       └── test_engine.py     # Testing the AI logic/cleaner
├── data/                      # Local data storage
│   └── healix_cache.json      # Persistent cache for fixes
├── docker/                    # Containerized environments
│   └── Dockerfile
├── .gitignore                 # Ignore __pycache__ and local config
├── requirements.txt           # Dependencies
└── README.md                  # This file
```

## 🛠️ Installation

```bash
# Clone the repository
git clone <repository-url>
cd healix

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

## 🚦 Quick Start

```python
import asyncio
from playwright.async_api import async_playwright
from healix.engine import smart_click

async def test_healix_agent():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        await page.goto("https://example.com")
        
        # Healix will automatically fix broken selectors
        await smart_click(page, "#broken-selector")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_healix_agent())
```

## 🧠 How It Works

### DOM Cleaning & Privacy
- Strips scripts, styles, and heavy elements to save tokens
- Masks PII (Personally Identifiable Information) for privacy
- Focuses on actionable elements (buttons, links, inputs)

### AI-Powered Reasoning
- Uses local LLM (Ollama) for selector analysis
- Considers both technical errors and visible page state
- Returns confidence scores and explanations

### Persistent Learning
- Caches successful fixes in `healix_cache.json`
- Gets faster over time as it learns common patterns
- Maintains context across test runs

## 🔧 Configuration

Healix uses Ollama for local AI inference:

```python
from healix.engine import Healix

# Default model: qwen2.5-coder:7b
healix = Healix(model="your-preferred-model")
```

Make sure Ollama is running:
```bash
ollama serve
```

## 🧪 Testing

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=src/healix --cov-report=html

# Run integration tests (requires browser)
pytest tests/integration/
```

## 🐳 Docker Support

```bash
# Build the container
docker build -t healix .

# Run tests in container
docker run healix
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## 📄 License

[Add your license here]

## 🔮 Roadmap

- [ ] Support for more AI models (OpenAI, Anthropic)
- [ ] Visual regression testing
- [ ] Multi-browser support expansion
- [ ] Performance optimization for large-scale testing
- [ ] Plugin system for custom healing strategies