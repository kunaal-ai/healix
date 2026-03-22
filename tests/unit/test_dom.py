
import pytest
from healix.engine import Healix
from unittest.mock import patch, MagicMock

class TestHealixDOM:
    @pytest.fixture
    def healix_instance(self):
        with patch("healix.engine.Healix._check_ollama"), \
             patch("healix.engine.Healix._ensure_dirs"), \
             patch("healix.engine.Healix._load_cache", return_value={}):
            return Healix()

    def test_get_clean_dom_removes_scripts_and_styles(self, healix_instance):
        html = """
        <html>
            <head>
                <script>console.log('remove');</script>
                <style>.remove { color: red; }</style>
            </head>
            <body>
                <div id="keep">Content</div>
            </body>
        </html>
        """
        clean = healix_instance.get_clean_dom(html)
        assert "script" not in clean
        assert "style" not in clean
        assert 'id="keep"' in clean
        assert "Content" in clean

    def test_get_clean_dom_preserves_interactive_attributes(self, healix_instance):
        html = """
        <button id="btn" class="primary" data-testid="submit-btn" onclick="alert()">Submit</button>
        """
        clean = healix_instance.get_clean_dom(html)
        assert 'id="btn"' in clean
        assert 'class="primary"' in clean
        assert 'data-testid="submit-btn"' in clean
        assert 'onclick' not in clean  # unsafe attribute removed

    def test_get_clean_dom_truncates_long_content(self, healix_instance):
        # Generate huge HTML
        html = "<div>" + ("<p>content</p>" * 1000) + "</div>"
        clean = healix_instance.get_clean_dom(html)
        assert len(clean) <= 15000

    def test_get_clean_dom_formats_text_elements(self, healix_instance):
        html = """
        <div>
            <h1>Title</h1>
            <p>Paragraph text</p>
            <span>Inline text</span>
        </div>
        """
        clean = healix_instance.get_clean_dom(html)
        assert "<h1>Title</h1>" in clean
        assert "<p>Paragraph text</p>" in clean
        assert "<span>Inline text</span>" in clean

    def test_get_clean_dom_handles_inputs(self, healix_instance):
        html = '<input type="text" placeholder="Enter name" name="username" value="test">'
        clean = healix_instance.get_clean_dom(html)
        assert '<input' in clean
        assert 'type="text"' in clean
        assert 'placeholder="Enter name"' in clean
        assert 'name="username"' in clean
        assert 'value="test"' in clean
