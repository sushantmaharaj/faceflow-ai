"""
FaceFlow AI — Person Identification Service
Orchestrates Gemini Vision (Primary) + Wikidata, Wikipedia, TMDB (Enrichment).

Pipeline:
  1. Determine name: Call Gemini Vision with image + titles. If fails, use regex extraction.
  2. Fetch Enrichment: If name found, fetch Wikipedia, Wikidata, and TMDB concurrently.
  3. Merge: Combine all sources into a single rich PersonProfile.
"""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from typing import Optional

import httpx

from app.core.logging import get_logger
from app.models.schemas import CandidateRecord, PersonProfile, SearchResult
from app.services.gemini_service import identify_with_gemini
from app.services.tmdb_service import search_tmdb_person

logger = get_logger(__name__)

WIKI_SUMMARY_URL  = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKI_SEARCH_URL   = "https://en.wikipedia.org/w/api.php"
WIKIDATA_ENTITY   = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"

P_DOB         = "P569"   # date of birth
P_CITIZENSHIP = "P27"    # country of citizenship
P_OCCUPATION  = "P106"   # occupation

# ── Pattern matching (fallback if Gemini unavailable/fails) ──────
_BEFORE_DASH_RE = re.compile(r"^([A-Z][a-z]+(?:\s+[A-Za-z]\.?\s*)*[A-Z][a-z]+)\s*[-–—|]")
_CONTEXT_RE = re.compile(
    r"(?:bollywood|hollywood|telugu|tamil|hindi|actor|actress|star|singer|"
    r"politician|president|minister|cricketer|footballer|rapper|musician|"
    r"comedian|celebrity|model|director|producer|businessman)\s+"
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
    re.IGNORECASE,
)
_NAME_RE = re.compile(r"\b([A-Z][a-z]{1,}(?:\s+[A-Z][a-z]{1,}){1,3})\b")
_STOPWORDS = {
    "South", "North", "East", "West", "New", "Old", "The", "This", "That",
    "Google", "Twitter", "Facebook", "Instagram", "YouTube", "Netflix",
    "Indian", "British", "American", "Pakistani", "Sports", "Minister",
    "Kerala", "Delhi", "Mumbai", "Bihar", "Punjab", "Rajasthan",
    "Profile", "Images", "Movie", "Database", "Photo", "Photos", "Image",
    "Actor", "Singer", "Watch", "Read", "News", "Latest", "Best",
}

def extract_person_name(all_titles: list[str]) -> Optional[str]:
    counter: Counter = Counter()
    for title in all_titles:
        m = _BEFORE_DASH_RE.match(title.strip())
        if m:
            name = m.group(1).strip()
            if len(name.split()) >= 2 and not any(w in _STOPWORDS for w in name.split()):
                counter[name] += 5

        for m in _CONTEXT_RE.finditer(title):
            name = m.group(1).strip()
            if len(name.split()) >= 2 and name not in _STOPWORDS:
                counter[name] += 3

        for m in _NAME_RE.finditer(title):
            name = m.group(1).strip()
            if len(name.split()) >= 2 and not any(w in _STOPWORDS for w in name.split()):
                counter[name] += 1

    return counter.most_common(1)[0][0] if counter else None


# ── Enrichment Fetchers ────────────────────────────────────────

async def _fetch_wikipedia(client: httpx.AsyncClient, name: str) -> dict:
    summary = {}
    try:
        resp = await client.get(
            WIKI_SEARCH_URL,
            params={"action": "query", "list": "search", "srsearch": name, 
                    "srlimit": 1, "format": "json", "origin": "*"},
        )
        hits = resp.json().get("query", {}).get("search", [])
        if hits:
            page_title = hits[0]["title"]
            url = WIKI_SUMMARY_URL.format(title=page_title.replace(" ", "_"))
            summ_resp = await client.get(url)
            if summ_resp.status_code == 200:
                summary = summ_resp.json()
    except Exception as e:
        logger.warning("Wiki fetch failed: %s", e)
    return summary


def _label_of(entity: dict, prop_id: str) -> Optional[str]:
    try:
        dv = entity.get("claims", {}).get(prop_id, [])[0]["mainsnak"]["datavalue"]["value"]
        if isinstance(dv, dict) and "time" in dv:
            raw = dv["time"]
            parts = raw.lstrip("+").split("T")[0].split("-")
            months = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
            return f"{int(parts[2])} {months[int(parts[1])]} {parts[0]}"
        if isinstance(dv, dict) and "id" in dv:
            return dv["id"]
    except Exception:
        pass
    return None

async def _fetch_wikidata(client: httpx.AsyncClient, qid: str) -> dict:
    if not qid: return {}
    res = {}
    try:
        resp = await client.get(WIKIDATA_ENTITY.format(qid=qid), params={"flavor": "simple"})
        if resp.status_code != 200: return res
        
        entity = resp.json().get("entities", {}).get(qid, {})
        res["birth_date"] = _label_of(entity, P_DOB)
        
        # Resolve nat/occ
        nat_qid = _label_of(entity, P_CITIZENSHIP)
        occ_qid = _label_of(entity, P_OCCUPATION)
        for field, dq in [("nationality", nat_qid), ("occupation", occ_qid)]:
            if dq:
                try:
                    r = await client.get("https://www.wikidata.org/w/api.php", 
                        params={"action": "wbgetentities", "ids": dq, "props": "labels", "languages": "en", "format": "json"})
                    if r.status_code == 200:
                        res[field] = r.json().get("entities", {}).get(dq, {}).get("labels", {}).get("en", {}).get("value")
                except Exception: pass
    except Exception as e:
        logger.warning("Wikidata fetch failed: %s", e)
    return res


# ── Main Pipeline ──────────────────────────────────────────────

async def identify_person(
    image_bytes: bytes,
    candidates: list[CandidateRecord],
    search_results: Optional[list[SearchResult]] = None,
) -> Optional[PersonProfile]:
    all_titles = [c.title for c in candidates if c.title]
    if search_results:
        all_titles += [r.title for r in search_results if r.title]

    logger.info("Person ID: Starting multi-modal pipeline (Gemini Primary)")
    
    # 1. Identify Name
    name = None
    gemini_data = None
    try:
        gemini_data = await identify_with_gemini(image_bytes, all_titles)
        if gemini_data and gemini_data.get("identified") and gemini_data.get("name"):
            name = gemini_data["name"]
            logger.info("Gemini identified name: %s", name)
    except Exception as e:
        logger.warning("Gemini pipeline failed: %s", e)

    if not name:
        name = extract_person_name(all_titles)
        logger.info("Regex fallback extracted name: %s", name)

    if not name:
        return None

    # 2. Fetch Enrichments parallelly
    async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
        wiki_task = asyncio.create_task(_fetch_wikipedia(client, name))
        tmdb_task = asyncio.create_task(search_tmdb_person(name))
        
        wiki_data = await wiki_task
        tmdb_data = await tmdb_task
        
        wikidata = {}
        qid = wiki_data.get("wikibase_item")
        if qid:
            wikidata = await _fetch_wikidata(client, qid)

    # 3. Merge data (Priority: TMDB > Wikidata > Gemini > Wiki)
    g = gemini_data or {}
    t = tmdb_data or {}
    w = wiki_data or {}
    wd = wikidata or {}

    thumb = w.get("thumbnail", {}).get("source")
    
    return PersonProfile(
        name=w.get("title") or t.get("name") or g.get("name") or name,
        description=g.get("description") or w.get("description"),
        extract=(w.get("extract") or g.get("extract") or "")[:700] or None,
        image_url=t.get("image_url") or thumb or g.get("image_url"),
        wikipedia_url=w.get("content_urls", {}).get("desktop", {}).get("page"),
        page_id=str(w.get("pageid", "")) if w.get("pageid") else None,
        wikidata_id=qid,
        birth_date=wd.get("birth_date") or g.get("birth_date"),
        nationality=wd.get("nationality") or g.get("nationality"),
        occupation=wd.get("occupation") or t.get("department") or g.get("occupation"),
        known_for=t.get("known_for") or g.get("known_for")
    )
