"""xkcd metadata through MCP and a deterministic random-selection seam."""

from datetime import date

import anyio
import pytest

from keyless_mcp.core import ToolRegistry
from m3_tests._support.cassettes import recorded
from m3_tests._support.results import result_text
from m3_tests._support.servers import keyless_server

pytestmark = pytest.mark.m3(suite_name="xkcd")


def test_catalog(connect):
    with connect("xkcd") as client:
        tools = {t.name: t for t in client.list_all_tools() if t.name.startswith("xkcd_")}
    assert set(tools) == {"xkcd_get_comic", "xkcd_get_random_comic"}
    assert not tools["xkcd_get_comic"].input_schema.get("required")
    assert tools["xkcd_get_comic"].input_schema["properties"]["number"]["default"] is None


def test_numbered_comic_is_documented_614(connect):
    with connect("xkcd") as client:
        result = client.call_tool("xkcd_get_comic", {"number": 614})
    assert not result.is_error, result_text(result)
    data = result.structured_content
    assert data["number"] == 614
    assert data["title"] == "Woodpecker"
    assert data["date"] == "2009-07-24"
    assert data["url"] == "https://xkcd.com/614/"
    assert data["image_url"].endswith("/woodpecker.png")
    assert data["alt"].endswith("Because we're friends! Right?")
    assert "transcript" not in data


def test_latest_comic(connect, replaying):
    with connect("xkcd") as client:
        result = client.call_tool("xkcd_get_comic", {})
    assert not result.is_error, result_text(result)
    data = result.structured_content
    assert data["number"] >= 614
    assert data["title"] and data["image_url"].startswith("https://imgs.xkcd.com/")
    assert date.fromisoformat(data["date"])
    assert data["url"] == f"https://xkcd.com/{data['number']}/"
    if replaying:
        assert data["number"] == recorded("xkcd", "https://xkcd.com/info.0.json")["num"]


@pytest.mark.parametrize("number", [0, -1])
def test_nonpositive_number_is_refused(connect, number):
    with connect("xkcd") as client:
        result = client.call_tool("xkcd_get_comic", {"number": number})
    assert result.is_error
    assert "positive" in result_text(result)


def test_unknown_comic_html_404_is_readable(connect):
    with connect("xkcd") as client:
        result = client.call_tool("xkcd_get_comic", {"number": 999999})
    assert result.is_error
    assert "999999" in result_text(result) and "not found" in result_text(result)


def test_random_comic_through_mcp_with_recorded_responses(m3_kit):
    # Pin the random slot in this child process, keeping HTTP and MCP serialization real.
    # Slot 613 maps to comic 614 because nonexistent comic 404 is excluded.
    bootstrap = (
        "from keyless_mcp.adapters.xkcd import tools; tools.randint = lambda low, high: 613; "
        "from keyless_mcp.__main__ import main; main()"
    )
    server = keyless_server("xkcd").model_copy(update={"args": ("-c", bootstrap)})
    with m3_kit.direct(server) as client:
        result = client.call_tool("xkcd_get_random_comic", {})
    assert not result.is_error, result_text(result)
    data = result.structured_content
    assert data["number"] == 614
    assert data["title"] == "Woodpecker"
    assert data["date"] == "2009-07-24"
    assert data["url"] == "https://xkcd.com/614/"
    assert data["image_url"] == "https://imgs.xkcd.com/comics/woodpecker.png"
    assert data["alt"].endswith("Because we're friends! Right?")


@pytest.mark.parametrize("chosen", [1, 614, 999])
def test_random_uses_latest_bound_and_fetches_chosen_comic(chosen):
    from keyless_mcp.adapters.xkcd.tools import register

    requests, bounds = [], []

    class Http:
        async def get_json(self, url):
            requests.append(url)
            return {
                "num": 999 if url.endswith("com/info.0.json") else chosen,
                "title": "Comic",
                "alt": "Alt",
                "img": "https://imgs.xkcd.com/comic.png",
                "year": "2009",
                "month": "7",
                "day": "24",
            }

    class Server:
        def __init__(self):
            self.tools = {}

        def add_tool(self, fn, *, name, **kwargs):
            self.tools[name] = fn

    def choose(latest):
        bounds.append(latest)
        return chosen

    server = Server()
    register(ToolRegistry(server, "xkcd"), Http(), chooser=choose)
    result = anyio.run(server.tools["xkcd_get_random_comic"])
    assert bounds == [999]
    assert result["number"] == chosen
    assert requests == ["https://xkcd.com/info.0.json", f"https://xkcd.com/{chosen}/info.0.json"]


@pytest.mark.parametrize(
    "latest,pick,expected",
    [
        (1, 1, 1),
        (403, 403, 403),
        (404, 403, 403),
        (405, 404, 405),
        (1000, 404, 405),
        (1000, 999, 1000),
    ],
)
def test_random_excludes_missing_404(monkeypatch, latest, pick, expected):
    from keyless_mcp.adapters.xkcd import tools

    def randint(low, high):
        assert low == 1
        assert high == latest - (latest >= 404)
        return pick

    monkeypatch.setattr(tools, "randint", randint)
    assert tools.choose_number(latest) == expected


@pytest.mark.live
def test_live_random(connect):
    with connect("xkcd", mode="live") as client:
        result = client.call_tool("xkcd_get_random_comic", {})
    assert not result.is_error, result_text(result)
    data = result.structured_content
    assert data["number"] > 0 and data["number"] != 404
    assert data["title"] and data["url"].startswith("https://xkcd.com/")
