"""
FaceFlow AI — TMDB Service
Fetches rich celebrity data from The Movie Database.
"""

from __future__ import annotations

from typing import Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/person"


async def search_tmdb_person(name: str) -> Optional[dict]:
    """
    Search TMDB for a person by name. Returns the best match data or None.
    Returned dict includes: name, original_name, known_for_department, profile_path, popularity, known_for.
    """
    if not settings.tmdb_configured:
        return None

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                TMDB_SEARCH_URL,
                params={
                    "query": name,
                    "api_key": settings.tmdb_api_key,
                    "include_adult": "false",
                },
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            
            if not results:
                return None
                
            # Usually the first result is the most popular/relevant
            person = results[0]
            
            # Format known_for (list of movies/tv shows)
            known_for_titles = []
            for item in person.get("known_for", []):
                title = item.get("title") or item.get("name")
                if title:
                    known_for_titles.append(title)
            
            profile_path = person.get("profile_path")
            
            res = {
                "name": person.get("name"),
                "department": person.get("known_for_department"),
                "popularity": person.get("popularity"),
                "known_for": ", ".join(known_for_titles) if known_for_titles else None,
                "image_url": f"https://image.tmdb.org/t/p/w500{profile_path}" if profile_path else None
            }
            logger.info("TMDB match for %s: %s", name, res)
            return res
            
    except Exception as e:
        logger.warning("TMDB fetch failed for '%s': %s", name, e)
        return None
