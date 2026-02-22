"""Core utility functions for Specta AI platform."""

import json
import re
from typing import Any


def extract_json_from_content(content: str) -> dict | None:
    """Extract JSON object from text content.

    Handles various formats:
    - Plain JSON starting with {
    - JSON wrapped in markdown code blocks
    - JSON with leading/trailing text
    - JSON mixed with XML/tool call tags

    Args:
        content: Text content that may contain JSON

    Returns:
        Parsed JSON dict or None if not found/invalid
    """
    if not content:
        return None

    content = content.strip()

    # Try to find JSON in markdown code blocks
    json_block_pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
    matches = re.findall(json_block_pattern, content, re.DOTALL)

    for match in matches:
        try:
            return json.loads(match.strip())
        except json.JSONDecodeError:
            continue

    # Try to find JSON object directly - look for balanced braces
    # This handles cases where JSON is embedded in other text
    def find_json_objects(text: str) -> list[str]:
        """Find all potential JSON objects in text."""
        results = []
        i = 0
        while i < len(text):
            if text[i] == '{':
                # Try to find matching closing brace
                brace_count = 1
                j = i + 1
                while j < len(text) and brace_count > 0:
                    if text[j] == '{':
                        brace_count += 1
                    elif text[j] == '}':
                        brace_count -= 1
                    j += 1
                if brace_count == 0:
                    results.append(text[i:j])
            i += 1
        return results

    # Try each potential JSON object (longest first)
    json_candidates = find_json_objects(content)
    json_candidates.sort(key=len, reverse=True)

    # Try each JSON candidate (longest first — most likely to be the complete output)
    for candidate in json_candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    # Try the whole content as last resort
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    return None


def load_prompt_template(prompt_name: str) -> str:
    """Load prompt template from file.

    Args:
        prompt_name: Name of the prompt file (without extension)

    Returns:
        Prompt template content
    """
    import os

    prompts_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "prompts"
    )

    # Try markdown first, then txt
    for ext in [".md", ".txt"]:
        prompt_path = os.path.join(prompts_dir, f"{prompt_name}{ext}")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()

    raise FileNotFoundError(f"Prompt template not found: {prompt_name}")


def render_prompt(template: str, variables: dict[str, Any]) -> str:
    """Render prompt template with variables.

    Simple template rendering using {{variable}} syntax.
    Supports conditional blocks with {% if variable %}...{% endif %}

    Args:
        template: Template string
        variables: Variables to substitute

    Returns:
        Rendered prompt
    """
    result = template

    # Handle conditional blocks
    # Pattern: {% if variable %}content{% endif %}
    conditional_pattern = r"{%\s*if\s+(\w+)\s*%}(.*?){%\s*endif\s*%}"

    def replace_conditional(match):
        var_name = match.group(1)
        content = match.group(2)

        if var_name in variables and variables[var_name]:
            # Recursively render the content
            return render_prompt(content, variables)
        else:
            return ""

    result = re.sub(conditional_pattern, replace_conditional, result, flags=re.DOTALL)

    # Handle variable substitution
    # Pattern: {{variable}}
    var_pattern = r"\{\{\s*(\w+)\s*\}\}"

    def replace_var(match):
        var_name = match.group(1)
        if var_name in variables:
            value = variables[var_name]
            if isinstance(value, list):
                return ", ".join(str(v) for v in value)
            return str(value)
        return match.group(0)  # Keep original if not found

    result = re.sub(var_pattern, replace_var, result)

    return result


def extract_domain(url: str) -> str:
    """Extract domain from URL, stripping 'www.' prefix.

    Shared by nodes_a5.py (citation matching) and analytics_service.py.

    Examples:
        'https://www.nike.com/foo' -> 'nike.com'
        'nike.com' -> 'nike.com'
        '' -> ''
    """
    if not url:
        return ""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url if url.startswith("http") else f"https://{url}")
        domain = parsed.netloc or parsed.path.split("/")[0]
        return domain.lower().replace("www.", "")
    except Exception:
        return ""
