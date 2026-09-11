"""Unit tests for universal tool-call normalizer — any model format support."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.terminal_tool import extract_terminal_commands
from app.services.tool_normalizer import normalize_tool_calls
from app.services.web_search import extract_search_blocks


def test_simplified_terminal_string():
    """Model sends { "terminal": "Start-Process chrome" }"""
    reply = '{"terminal": "Start-Process chrome"}'
    result = normalize_tool_calls(reply)
    assert "<<<TERMINAL>>>" in result, f"Missing TERMINAL block: {result}"
    cmds = extract_terminal_commands(result)
    assert cmds == ["Start-Process chrome"], f"Bad cmds: {cmds} from {result}"
    print(f"✓ simplified terminal string:\n{result}\n")


def test_simplified_web_search_string():
    """Model sends { "web_search": "python tutorial" }"""
    reply = '{"web_search": "python tutorial"}'
    result = normalize_tool_calls(reply)
    assert "<<<WEB_SEARCH>>>" in result, f"Missing WEB_SEARCH block: {result}"
    searches = extract_search_blocks(result)
    assert searches and searches[0]["query"] == "python tutorial"
    print(f"✓ simplified web search:\n{reply}\n→\n{result}\n")


def test_simplified_read_file_nested():
    """Model sends { "read_file": {"path": "app/main.py"} }"""
    reply = '{"read_file": {"path": "app/main.py"}}'
    result = normalize_tool_calls(reply)
    assert "<<<READ_FILE>>>" in result, f"Missing READ_FILE block: {result}"
    print(f"✓ simplified read_file nested:\n{result}\n")


def test_simplified_git_status():
    """Model sends { "git_status": {} }"""
    reply = '{"git_status": {}}'
    result = normalize_tool_calls(reply)
    assert "<<<GIT_STATUS>>>" in result, f"Missing GIT_STATUS block: {result}"
    print(f"✓ simplified git_status:\n{result}\n")


def test_multiple_simplified_tools():
    """Model sends multiple tool calls."""
    reply = '{"terminal": "ls -la"}\n{"web_search": "test query"}'
    result = normalize_tool_calls(reply)
    assert "<<<TERMINAL>>>" in result, f"Missing TERMINAL: {result}"
    assert "<<<WEB_SEARCH>>>" in result, f"Missing WEB_SEARCH: {result}"
    print(f"✓ multiple simplified tools:\n{result}\n")


def test_text_blocks_passthrough():
    """Already has text blocks — no conversion needed."""
    reply = "Here is the result:\n\n<<<TERMINAL>>>\nls -la\n<<<END_TERMINAL>>>"
    result = normalize_tool_calls(reply)
    assert "<<<TERMINAL>>>" in result
    assert extract_terminal_commands(result) == ["ls -la"]
    print("✓ text blocks passthrough\n")


def test_openai_tool_calls_array():
    """OpenAI format tool_calls array."""
    reply = json.dumps(
        [{"name": "run_terminal", "arguments": {"command": "dir"}}],
        ensure_ascii=False,
    )
    result = normalize_tool_calls(reply)
    assert "<<<TERMINAL>>>" in result, f"Missing TERMINAL: {result}"
    assert extract_terminal_commands(result) == ["dir"]
    print(f"✓ OpenAI tool_calls array:\n{result}\n")


def test_action_search_replace_nemotron():
    """Nemotron 550 emits {action, path, old, new} instead of executing a tool."""
    reply = json.dumps(
        {
            "action": "search_replace",
            "path": r"C:\proj\file.py",
            "old": "from gateway.providers.base import ProviderRegistry",
            "new": "from gateway.providers.registry import ProviderRegistry",
        }
    )
    result = normalize_tool_calls(reply)
    assert "<<<SEARCH_REPLACE>>>" in result, f"Missing SEARCH_REPLACE: {result}"
    assert "C:\\proj\\file.py" in result or r"C:\proj\file.py" in result
    assert "old_string:" in result or "old:" in result
    assert "new_string:" in result or "new:" in result
    print(f"✓ action search_replace:\n{result}\n")


def test_action_search_replace_inside_tool_call_xml():
    reply = (
        '<tool_call>{"action": "search_replace", "path": "a.py", '
        '"old": "foo", "new": "bar"}</tool_call>'
    )
    result = normalize_tool_calls(reply)
    assert "<<<SEARCH_REPLACE>>>" in result, f"Missing SEARCH_REPLACE: {result}"
    print(f"✓ tool_call xml action search_replace:\n{result}\n")


def test_openai_function_format():
    """OpenAI single function call object."""
    reply = json.dumps(
        {
            "function": {
                "name": "web_search",
                "arguments": json.dumps({"query": "hello"}),
            }
        },
        ensure_ascii=False,
    )
    result = normalize_tool_calls(reply)
    assert "<<<WEB_SEARCH>>>" in result, f"Missing WEB_SEARCH: {result}"
    print(f"✓ OpenAI function format:\n{result}\n")


def test_plain_text_passthrough():
    """Plain text — no conversion."""
    reply = "Hello! How can I help you?"
    result = normalize_tool_calls(reply)
    assert result == reply, f"Should be unchanged: {result}"
    print("✓ plain text passthrough (unchanged)\n")


def test_empty_input():
    """Empty string."""
    result = normalize_tool_calls("")
    assert result == ""
    print("✓ empty input\n")

    result = normalize_tool_calls(None)
    assert result is None
    print("✓ None input\n")


def test_browser_nested():
    """Model sends { "browser": {"action": "screenshot", "url": "https://example.com"} }"""
    reply = json.dumps({"browser": {"action": "screenshot", "url": "https://example.com"}})
    result = normalize_tool_calls(reply)
    assert "<<<BROWSER>>>" in result, f"Missing BROWSER: {result}"
    print(f"✓ browser nested:\n{result}\n")


def test_image_gen_nested():
    """Model sends { "image_gen": {"size": "1024x1024", "prompt": "a cat"} }"""
    reply = json.dumps({"image_gen": {"size": "1024x1024", "prompt": "a cat"}})
    result = normalize_tool_calls(reply)
    assert "<<<IMAGE_GEN>>>" in result, f"Missing IMAGE_GEN: {result}"
    print(f"✓ image_gen nested:\n{result}\n")


def test_xml_tool_call_wrapper():
    """Qwen-style <tool_call>{\"terminal\": \"...\"}"""
    reply = '<tool_call>\n{"terminal": "Start-Process chrome"}'
    result = normalize_tool_calls(reply)
    assert extract_terminal_commands(result) == ["Start-Process chrome"], result
    print(f"✓ xml tool_call wrapper:\n{result}\n")


def test_hybrid_broken_terminal():
    """Hybrid: <tool_call>{\"TERMINAL\"}\\ncmd\\n<<<END_TERMINAL>>>"""
    reply = '<tool_call>\n{"TERMINAL"}\nStart-Process chrome\n<<<END_TERMINAL>>>'
    result = normalize_tool_calls(reply)
    assert extract_terminal_commands(result) == ["Start-Process chrome"], result
    print(f"✓ hybrid broken terminal:\n{result}\n")


def test_queries_array():
    """{\"queries\": [\"a\", \"b\"]} → WEB_SEARCH blocks"""
    reply = '<tool_call>\n{"queries": ["best sites 2026", "telegram channels"]}'
    result = normalize_tool_calls(reply)
    searches = extract_search_blocks(result)
    assert len(searches) >= 2, result
    print(f"✓ queries array:\n{result}\n")


def test_embedded_openai_name_args():
    """Prose + OpenAI-style object"""
    reply = (
        'Opening chrome.\n\n'
        '{"name": "run_terminal", "arguments": {"command": "Start-Process chrome"}}'
    )
    result = normalize_tool_calls(reply)
    assert extract_terminal_commands(result) == ["Start-Process chrome"], result
    print(f"✓ embedded openai name args:\n{result}\n")


def test_cmd_prefix_stripped():
    """Labeled terminal body still runs"""
    reply = "<<<TERMINAL>>>\ncmd: Get-Date\n<<<END_TERMINAL>>>"
    result = normalize_tool_calls(reply)
    assert extract_terminal_commands(result) == ["Get-Date"], result
    print(f"✓ cmd prefix stripped:\n{result}\n")


if __name__ == "__main__":
    test_simplified_terminal_string()
    test_simplified_web_search_string()
    test_simplified_read_file_nested()
    test_simplified_git_status()
    test_multiple_simplified_tools()
    test_text_blocks_passthrough()
    test_openai_tool_calls_array()
    test_action_search_replace_nemotron()
    test_action_search_replace_inside_tool_call_xml()
    test_openai_function_format()
    test_plain_text_passthrough()
    test_empty_input()
    test_browser_nested()
    test_image_gen_nested()
    test_xml_tool_call_wrapper()
    test_hybrid_broken_terminal()
    test_queries_array()
    test_embedded_openai_name_args()
    test_cmd_prefix_stripped()
    print("All tests passed!")
