"""
Text Processing Tools - String manipulation and text analysis.

This module provides various text processing and manipulation tools.
"""

from app import mcp
from typing import Annotated, Literal
from pydantic import Field
import re


@mcp.tool(
    description="Convert text to uppercase, lowercase, or title case",
    tags={"text", "formatting"}
)
def change_case(
    text: Annotated[str, Field(description="Text to transform")],
    case: Annotated[Literal["upper", "lower", "title"], Field(
        description="Target case format"
    )]
) -> str:
    """Change the case of the provided text."""
    if case == "upper":
        return text.upper()
    elif case == "lower":
        return text.lower()
    elif case == "title":
        return text.title()
    return text


@mcp.tool(
    description="Count words, characters, and lines in text",
    tags={"text", "analysis"}
)
def count_text(
    text: Annotated[str, Field(description="Text to analyze")]
) -> dict:
    """Analyze text and return various counts."""
    lines = text.split('\n')
    words = text.split()
    
    return {
        "characters": len(text),
        "characters_no_spaces": len(text.replace(" ", "")),
        "words": len(words),
        "lines": len(lines),
        "sentences": len(re.split(r'[.!?]+', text))
    }


@mcp.tool(
    description="Replace text using regex patterns",
    tags={"text", "regex"}
)
def regex_replace(
    text: Annotated[str, Field(description="Text to process")],
    pattern: Annotated[str, Field(description="Regex pattern to match")],
    replacement: Annotated[str, Field(description="Replacement string")],
    case_sensitive: Annotated[bool, Field(description="Case sensitive matching")] = True
) -> dict:
    """Replace text using regular expressions."""
    flags = 0 if case_sensitive else re.IGNORECASE
    
    try:
        result = re.sub(pattern, replacement, text, flags=flags)
        matches = len(re.findall(pattern, text, flags=flags))
        
        return {
            "original": text,
            "result": result,
            "pattern": pattern,
            "replacement": replacement,
            "matches_found": matches
        }
    except re.error as e:
        raise ValueError(f"Invalid regex pattern: {str(e)}")


@mcp.tool(
    description="Extract all URLs from text",
    tags={"text", "extraction"}
)
def extract_urls(
    text: Annotated[str, Field(description="Text to extract URLs from")]
) -> dict:
    """Extract all URLs from the provided text."""
    url_pattern = r'https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&/=]*)'
    
    urls = re.findall(url_pattern, text)
    
    return {
        "count": len(urls),
        "urls": urls
    }


@mcp.tool(
    description="Reverse text (characters or words)",
    tags={"text", "transformation"}
)
def reverse_text(
    text: Annotated[str, Field(description="Text to reverse")],
    mode: Annotated[Literal["characters", "words"], Field(
        description="Reverse by characters or words"
    )] = "characters"
) -> str:
    """Reverse text by characters or words."""
    if mode == "characters":
        return text[::-1]
    elif mode == "words":
        words = text.split()
        return " ".join(reversed(words))
    return text


@mcp.tool(
    description="Remove extra whitespace from text",
    tags={"text", "cleaning"}
)
def clean_whitespace(
    text: Annotated[str, Field(description="Text to clean")],
    mode: Annotated[Literal["all", "leading", "trailing", "extra"], Field(
        description="Type of whitespace cleaning to perform"
    )] = "extra"
) -> str:
    """Clean whitespace from text in various ways."""
    if mode == "all":
        return text.replace(" ", "").replace("\n", "").replace("\t", "")
    elif mode == "leading":
        return text.lstrip()
    elif mode == "trailing":
        return text.rstrip()
    elif mode == "extra":
        # Replace multiple spaces with single space
        return re.sub(r'\s+', ' ', text).strip()
    return text
