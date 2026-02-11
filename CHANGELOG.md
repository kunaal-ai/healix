# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.3] - 2026-02-11

### Changed
- Replaced Mermaid diagram with text flowchart for better PyPI compatibility
- Updated README architecture section to match actual project structure
- Removed Docker section from README (Docker support temporarily removed)
- Updated Quick Start example to use a real testing URL (`the-internet.herokuapp.com`)

### Fixed
- Fixed internal import in integration tests to use public API (`from healix import smart_click`)
- Added `Changelog` URL to PyPI metadata
- Removed `data/` and `docker/` directories from version control
- Updated `.gitignore` to verify exclusion of build artifacts and data directories
- Friendly error messages when Playwright browsers are not installed
- Custom exception classes: `HealixError`, `OllamaConnectionError`, `BrowserNotInstalledError`
- Lazy initialization — importing `healix` no longer crashes if Ollama is down
- Unit test suite covering DOM cleaning, caching, proposal logging, and error handling
- GitHub Actions CI workflow
- PyPI badges, prerequisites, and known limitations in README

### Changed
- Cache directory moved from relative `healix_data/` to `~/.healix/` for reliability
- README cleaned up: removed emojis, added professional sections

### Fixed
- License placeholder in README replaced with actual MIT reference

## [0.1.1] - 2026-02-11

### Fixed
- License display on PyPI showing "[Add your license here]"
- Updated README license section

## [0.1.0] - 2026-02-11

### Added
- Initial release
- AI-powered self-healing for broken Playwright selectors
- Browser-aware cache keys (separate fixes per browser engine)
- Improved AI prompt to prevent hallucinated selectors
- Plan B retry loop with failure feedback to AI
- DOM scrubbing and minification for token efficiency
- Persistent cache in JSON format
- Code proposal logging for review
- CLI entry point: `healix <test_file.py>`
- Multi-browser support (Chromium, Firefox)
