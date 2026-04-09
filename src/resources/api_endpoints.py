"""
API Endpoints - External API access as resources.

This module provides access to external APIs through MCP resources.
"""

from app import mcp
from typing import Annotated, Optional
from pydantic import Field
import json


@mcp.resource(
    uri="api://weather/{city}{?units}",
    name="Weather Data by City",
    description="Get weather information for a specific city",
    mime_type="application/json",
    tags={"api", "weather", "template"}
)
async def get_weather(
    city: str,
    units: str = "metric"
) -> dict:
    """
    Get weather data for a city.
    
    This is a mock implementation. In production, this would call
    a real weather API like OpenWeatherMap.
    """
    # Mock weather data
    mock_data = {
        "london": {"temp": 15, "condition": "Cloudy", "humidity": 70},
        "paris": {"temp": 18, "condition": "Sunny", "humidity": 55},
        "tokyo": {"temp": 22, "condition": "Clear", "humidity": 60},
        "newyork": {"temp": 12, "condition": "Rainy", "humidity": 80},
    }
    
    city_key = city.lower().replace(" ", "")
    weather = mock_data.get(city_key, {
        "temp": 20,
        "condition": "Unknown",
        "humidity": 50
    })
    
    return {
        "city": city.title(),
        "temperature": weather["temp"],
        "temperature_unit": "celsius" if units == "metric" else "fahrenheit",
        "condition": weather["condition"],
        "humidity": weather["humidity"],
        "last_updated": "2025-11-19T10:00:00Z",
        "note": "This is mock data for demonstration"
    }


@mcp.resource(
    uri="api://exchange/{from_currency}/{to_currency}",
    name="Currency Exchange Rate",
    description="Get exchange rate between two currencies",
    mime_type="application/json",
    tags={"api", "currency", "template"}
)
def get_exchange_rate(
    from_currency: str,
    to_currency: str
) -> dict:
    """
    Get exchange rate between currencies.
    
    Mock implementation - would call a real API in production.
    """
    # Mock exchange rates (to USD)
    rates = {
        "USD": 1.0,
        "EUR": 0.85,
        "GBP": 0.73,
        "JPY": 110.0,
        "CAD": 1.25,
        "AUD": 1.35
    }
    
    from_curr = from_currency.upper()
    to_curr = to_currency.upper()
    
    if from_curr not in rates or to_curr not in rates:
        return {
            "error": "Currency not supported",
            "supported_currencies": list(rates.keys())
        }
    
    # Calculate rate
    rate = rates[to_curr] / rates[from_curr]
    
    return {
        "from": from_curr,
        "to": to_curr,
        "rate": round(rate, 4),
        "timestamp": "2025-11-19T10:00:00Z",
        "note": "This is mock data for demonstration"
    }


@mcp.resource(
    uri="api://quote/{category}",
    name="Random Quote by Category",
    description="Get a random inspirational quote",
    mime_type="application/json",
    tags={"api", "quotes", "template"}
)
def get_random_quote(category: str = "general") -> dict:
    """
    Get a random quote by category.
    
    Mock implementation with sample quotes.
    """
    quotes = {
        "motivation": [
            {
                "text": "The only way to do great work is to love what you do.",
                "author": "Steve Jobs"
            },
            {
                "text": "Believe you can and you're halfway there.",
                "author": "Theodore Roosevelt"
            }
        ],
        "technology": [
            {
                "text": "Technology is best when it brings people together.",
                "author": "Matt Mullenweg"
            },
            {
                "text": "The advance of technology is based on making it fit in so that you don't really even notice it.",
                "author": "Bill Gates"
            }
        ],
        "general": [
            {
                "text": "Be yourself; everyone else is already taken.",
                "author": "Oscar Wilde"
            },
            {
                "text": "The future belongs to those who believe in the beauty of their dreams.",
                "author": "Eleanor Roosevelt"
            }
        ]
    }
    
    category_quotes = quotes.get(category.lower(), quotes["general"])
    quote = category_quotes[0]  # In real implementation, would be random
    
    return {
        "category": category,
        "quote": quote["text"],
        "author": quote["author"],
        "note": "This is mock data for demonstration"
    }
