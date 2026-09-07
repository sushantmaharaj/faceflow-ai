"""
FaceFlow AI — Gemini Vision Service
Sends the uploaded face image + search context to Gemini Flash.
Asks it to identify the person and return all public-domain details.
Free tier: 1,500 requests/day, 15 RPM.
"""

from __future__ import annotations

import base64
import json
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:generateContent"
)

IDENTIFY_PROMPT = """You are an AI assistant with access to public-domain knowledge.

I am providing you a face image and some web search context about who this person might be.

Web search context (titles from reverse image search):
{context}

TASK:
1. Look at the face in the image carefully.
2. Based on the image AND the context, identify the person if you recognize them.
3. Return a JSON object with these fields (use null for fields you don't know):

{{
  "identified": true or false,
  "name": "Full name",
  "description": "One-line role/title (e.g. 'Indian actor and film producer')",
  "birth_date": "DD Month YYYY or null",
  "birth_place": "City, Country or null",
  "nationality": "e.g. Indian or null",
  "occupation": "Comma-separated list e.g. 'Actor, Film producer' or null",
  "known_for": "2-3 most famous works or achievements or null",
  "active_years": "e.g. '1988–present' or null",
  "extract": "2-3 sentence public biography paragraph",
  "confidence": "high / medium / low"
}}

IMPORTANT:
- Only provide information that is publicly available and well-known.
- If you cannot confidently identify the person, set identified to false and leave other fields null.
- Do NOT guess. Only respond with a JSON object, no extra text.
"""


async def identify_with_gemini(
    image_bytes: bytes,
    candidate_titles: list[str],
) -> Optional[dict]:
    """
    Send face image + search context to Gemini Flash.
    Returns parsed JSON dict or None on failure.
    """
    if not settings.gemini_configured:
        logger.info("Gemini not configured — skipping")
        return None

    # Build context from titles (top 5)
    context = "\n".join(f"- {t}" for t in candidate_titles[:5] if t)
    prompt  = IDENTIFY_PROMPT.format(context=context or "No context available")

    # Encode image as base64
    b64 = base64.b64encode(image_bytes).decode()
    # Detect mime type (default jpeg)
    mime = "image/jpeg"
    if image_bytes[:4] == b"\x89PNG":
        mime = "image/png"
    elif image_bytes[:4] == b"RIFF":
        mime = "image/webp"

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime, "data": b64}},
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 512,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                GEMINI_URL,
                params={"key": settings.gemini_api_key},
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        # Extract text response
        text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        ).strip()

        logger.info("Gemini raw response: %s", text[:300])

        # Parse JSON — strip markdown code fences if present
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]

        result = json.loads(text)
        logger.info("Gemini identified: %s (confidence: %s)",
                    result.get("name"), result.get("confidence"))
        return result

    except json.JSONDecodeError as e:
        logger.warning("Gemini returned non-JSON: %s | error: %s", text[:200], e)
        return None
    except httpx.HTTPStatusError as e:
        logger.warning("Gemini HTTP error %s: %s", e.response.status_code, e.response.text[:200])
        return None
    except Exception as e:
        logger.warning("Gemini call failed: %s", e)
        return None
