"""Adapter registry. Run order matters for de-duplication: first-hand sources (RSS, OParl, GDELT) go before Google News."""
from .apify import Apify
from .bluesky import Bluesky
from .exa import Exa
from .gdelt import Gdelt
from .gnews import GNews
from .mastodon import Mastodon
from .oparl import OParl
from .pagewatch import PageWatch
from .rss import Rss
from .tavily import Tavily
from .youtube import YouTube

ADAPTERS = [Rss, OParl, PageWatch, Gdelt, Bluesky, Mastodon, YouTube, Exa, Tavily, Apify, GNews]
