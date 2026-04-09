"""
Calculator Tools - Mathematical operations and calculations.

This module provides basic and advanced mathematical operations as MCP tools.
"""

from app import mcp
from typing import Annotated
from pydantic import Field


@mcp.tool(
    description="Add two numbers together",
    tags={"math", "calculator"}
)
def add(
    a: Annotated[float, Field(description="First number")],
    b: Annotated[float, Field(description="Second number")]
) -> float:
    """Add two numbers and return the result."""
    return a + b


@mcp.tool(
    description="Subtract second number from first number",
    tags={"math", "calculator"}
)
def subtract(
    a: Annotated[float, Field(description="Number to subtract from")],
    b: Annotated[float, Field(description="Number to subtract")]
) -> float:
    """Subtract b from a and return the result."""
    return a - b


@mcp.tool(
    description="Multiply two numbers together",
    tags={"math", "calculator"}
)
def multiply(
    a: Annotated[float, Field(description="First number")],
    b: Annotated[float, Field(description="Second number")]
) -> float:
    """Multiply two numbers and return the result."""
    return a * b


@mcp.tool(
    description="Divide first number by second number",
    tags={"math", "calculator"}
)
def divide(
    a: Annotated[float, Field(description="Numerator")],
    b: Annotated[float, Field(description="Denominator (must not be zero)")]
) -> float:
    """Divide a by b and return the result."""
    if b == 0:
        raise ValueError("Division by zero is not allowed")
    return a / b


@mcp.tool(
    name="calculate_power",
    description="Calculate a number raised to a power",
    tags={"math", "calculator", "advanced"}
)
def power(
    base: Annotated[float, Field(description="Base number")],
    exponent: Annotated[float, Field(description="Exponent")]
) -> float:
    """Calculate base raised to the power of exponent."""
    return base ** exponent


@mcp.tool(
    description="Calculate the square root of a number",
    tags={"math", "calculator", "advanced"}
)
def square_root(
    number: Annotated[float, Field(description="Number to find square root of", ge=0)]
) -> float:
    """Calculate the square root of a non-negative number."""
    import math
    return math.sqrt(number)


@mcp.tool(
    description="Calculate percentage of a number",
    tags={"math", "calculator"}
)
def percentage(
    value: Annotated[float, Field(description="The value to calculate percentage of")],
    percent: Annotated[float, Field(description="The percentage (e.g., 25 for 25%)")]
) -> float:
    """Calculate what percent% of value equals."""
    return (percent / 100) * value
