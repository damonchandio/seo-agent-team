"""Everything comes from environment variables (or a .env file next to where you run it). See .env.example.

Values are read when this module is imported. Tests and scripts can change them directly:
`settings.SITE_URL = "https://example.com"`.
"""
import os
from pathlib import Path

try:   # a .env file in the folder you run from, if python-dotenv is installed
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


# Your WordPress site, signed in with an Application Password (Users > Profile > Application Passwords)
SITE_URL = _env("SEO_SITE_URL")                       # https://example.com
WP_USER = _env("SEO_WP_USER")
WP_APP_PASSWORD = _env("SEO_WP_APP_PASSWORD")

# Any OpenAI-compatible chat endpoint. Defaults to Groq's free tier; Gemini, OpenRouter or a local Ollama work too.
LLM_BASE_URL = _env("SEO_LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_API_KEY = _env("SEO_LLM_API_KEY")
LLM_MODEL = _env("SEO_LLM_MODEL", "openai/gpt-oss-120b")
LLM_MAX_TOKENS = int(_env("SEO_LLM_MAX_TOKENS", "8000"))   # cap per call: free tiers limit tokens per minute

# Google Search Console (optional): a service account key file, and the property exactly as Search Console names it
GSC_SITE = _env("SEO_GSC_SITE")                       # sc-domain:example.com or https://example.com/
GSC_KEY_FILE = _env("SEO_GSC_KEY_FILE")               # path to the service account JSON (keep it out of git)

# Bing Webmaster Tools API key (optional): instant URL submission to Bing and its IndexNow partners
BING_KEY = _env("SEO_BING_KEY")

# What you write about and who for
BUSINESS = _env("SEO_BUSINESS", "a small business")   # one line: what the business does, used in the prompts
BUSINESS_NAME = _env("SEO_BUSINESS_NAME", "we")
AUDIENCE = _env("SEO_AUDIENCE", "small-business owners")
COUNTRY = _env("SEO_COUNTRY", "gb")                   # Google suggestions region
COUNTRY_NAME = _env("SEO_COUNTRY_NAME", "UK")
SEEDS = [s.strip() for s in _env("SEO_SEEDS").split("|") if s.strip()]   # starting phrases for keyword research

# The Editor's gate: articles at or above this Rank Math score publish on their own; anything lower waits for you
TARGET = int(_env("SEO_TARGET_SCORE", "95"))
AUTO_PUBLISH = _env("SEO_AUTO_PUBLISH", "1") == "1"   # 0: every article waits for a human, whatever its score
WEB_RESEARCH = _env("SEO_WEB_RESEARCH", "1") == "1"   # search the web for sourced facts before writing

# `python -m seo_agent_team run` (once a day): write on these days, refresh on this day
WRITE_DAYS = [d.strip().lower()[:3] for d in _env("SEO_WRITE_DAYS", "mon,thu").split(",") if d.strip()]
REFRESH_DAY = _env("SEO_REFRESH_DAY", "sat").lower()[:3]

DATA_DIR = Path(_env("SEO_DATA_DIR", "seo-data"))     # drafts, images, tracking and state live here
