# Healix

**Healix** is an intelligent web automation agent that self-heals broken selectors and adapts to dynamic web pages using AI-powered DOM analysis.

## The Problem

Web automation is fragile. Selectors break when:
- Developers change class names
- DOM structure shifts
- Content loads dynamically
- A/B tests alter page layouts

## The Solution

Healix uses an **agentic loop** to automatically detect and fix selector failures:

1. **Observe** — Analyze the current page state and DOM
2. **Reason** — Use AI to determine the correct selector/action
3. **Act** — Execute the corrected action
4. **Verify** — Confirm the action succeeded
5. **Learn** — Cache successful fixes for future use

### Operational Workflow

```mermaid
flowchart TD
    subgraph Execution["Test Execution Layer"]
        Start(["Test Failure Detected"])
        RetryCache(["Re-run with Cache"])
        RetryAI(["Re-run with AI Fix"])
    end

    subgraph Persistence["Persistence Layer"]
        CheckCache{"Check Cache"}
        ApplyCache["Apply Cached Selector"]
        UpdateCache[("Update Cache")]
    end

    subgraph Intelligence["AI Intelligence Layer"]
        CleanDOM["DOM Scrubbing & Minification"]
        AskOllama["Query Ollama (qwen2.5-coder)"]
        Analyze["Confidence Scoring"]
    end

    subgraph Feedback["Reporting Layer"]
        Success(["Healing Successful"])
        Manual(["Manual Review Required"])
        Proposal[("Log Code Proposal")]
    end

    %% Flow Logic
    Start --> CheckCache
    
    CheckCache -- "Hit" --> ApplyCache
    ApplyCache --> RetryCache
    
    CheckCache -- "Miss" --> CleanDOM
    
    RetryCache -- "Success" --> Success
    RetryCache -- "Fail" --> CleanDOM
    
    CleanDOM --> AskOllama
    AskOllama --> Analyze
    
    Analyze -- "High Confidence" --> RetryAI
    Analyze -- "Low Confidence" --> Manual
    
    RetryAI -- "Success" --> UpdateCache
    UpdateCache --> Success
    
    RetryAI -- "Fail" --> Manual
    
    Success --> Proposal
    Manual --> Proposal
    Proposal --> End(["Action Complete"])

    %% Premium Styling
    classDef startEnd fill:#f8fafc,stroke:#64748b,stroke-width:2px,color:#1e293b
    classDef intelligence fill:#eff6ff,stroke:#3b82f6,stroke-width:2px,color:#1e3a8a
    classDef persistence fill:#ecfdf5,stroke:#10b981,stroke-width:2px,color:#064e3b
    classDef execution fill:#fff7ed,stroke:#f59e0b,stroke-width:2px,color:#7c2d12
    classDef feedback fill:#faf5ff,stroke:#a855f7,stroke-width:2px,color:#581c87
    classDef decision fill:#ffffff,stroke:#334155,stroke-width:2px,stroke-dasharray: 5 5

    class Start,End startEnd
    class CleanDOM,AskOllama,Analyze intelligence
    class CheckCache,ApplyCache,UpdateCache persistence
    class RetryCache,RetryAI execution
    class Success,Manual,Proposal,GenerateFeedback feedback
    class CheckCache,Analyze decision
```

## Architecture

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

## Installation

```bash
pip install healix-ai
```

Or install from source:

```bash
git clone https://github.com/kunaal-ai/healix.git
cd healix
pip install -e .
```

Make sure to install Playwright browsers:

```bash
playwright install chromium
```

## Quick Start

```python
import asyncio
from playwright.async_api import async_playwright
from healix import smart_click

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

## How It Works

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

## Configuration

Healix uses Ollama for local AI inference:

```python
from healix import Healix

# Default model: qwen2.5-coder:7b
healix = Healix(model="your-preferred-model")
```

Make sure Ollama is running:
```bash
ollama serve
```

## Testing

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=src/healix --cov-report=html

# Run integration tests (requires browser)
pytest tests/integration/
```

## Docker Support

```bash
# Build the container
docker build -t healix .

# Run tests in container
docker run healix
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

This project is licensed under the [MIT License](LICENSE).

## Roadmap

- [ ] Support for more AI models (OpenAI, Anthropic)
- [ ] Visual regression testing
- [ ] Multi-browser support expansion
- [ ] Performance optimization for large-scale testing
- [ ] Plugin system for custom healing strategies