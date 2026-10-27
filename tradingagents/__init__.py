"""TradingAgents: multi-agent LLM financial trading framework."""

__version__ = "0.7.1"

import os

from dotenv import find_dotenv, load_dotenv

# Load .env at package import so DEFAULT_CONFIG's env-var overlay and every LLM
# client see the user's keys whichever entry point started the process.
# usecwd=True walks from the working directory, so the installed console script
# finds the project's .env rather than looking beside site-packages. Values the
# caller has already exported are never overridden.
load_dotenv(find_dotenv(usecwd=True))
load_dotenv(find_dotenv(".env.enterprise", usecwd=True), override=False)

# Cloud sessions reserve the name ANTHROPIC_API_KEY for their own sign-in, so
# the key for this program can be stored as TA_ANTHROPIC_API_KEY instead.
# When set, it wins.
if os.environ.get("TA_ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = os.environ["TA_ANTHROPIC_API_KEY"]
