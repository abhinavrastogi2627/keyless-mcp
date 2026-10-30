"""Compact xkcd metadata with links back to the comic and its image."""

from collections.abc import Callable
from random import randint
from typing import Annotated, Any

from pydantic import Field

from keyless_mcp.core import AdapterHttp, InvalidInput, ToolRegistry, UpstreamError, truncate

BASE_URL = "https://xkcd.com"


def choose_number(latest: int) -> int:
    """Choose uniformly from published numbers, excluding the deliberately absent 404."""
    number = randint(1, latest - (latest >= 404))
    return number + 1 if number >= 404 else number


def describe_comic(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": data["num"],
        "title": truncate(data["title"], 200),
        "alt": truncate(data["alt"], 1000),
        "image_url": data["img"],
        "date": f"{int(data['year']):04d}-{int(data['month']):02d}-{int(data['day']):02d}",
        "url": f"{BASE_URL}/{data['num']}/",
    }


def register(
    tools: ToolRegistry, http: AdapterHttp, *, chooser: Callable[[int], int] = choose_number
) -> None:
    async def fetch(number: int | None) -> dict[str, Any]:
        suffix = f"/{number}" if number is not None else ""
        try:
            return await http.get_json(f"{BASE_URL}{suffix}/info.0.json")
        except UpstreamError as exc:
            if exc.status == 404:
                raise InvalidInput(
                    f"xkcd comic {number} was not found. Try another positive number or omit "
                    "number for the latest comic; comic 404 deliberately does not exist."
                ) from None
            raise

    @tools.tool(title="Get xkcd comic")
    async def xkcd_get_comic(
        number: Annotated[
            int | None,
            Field(description="Positive comic number, e.g. 614. Omit or use null for the latest."),
        ] = None,
    ) -> dict[str, Any]:
        """Get xkcd metadata by comic number, or the latest comic when omitted. Returns
        number, title, alt text, image URL, publication date and a link to xkcd. Images are
        linked, never downloaded. Use the alt text to understand the comic's context."""
        if number is not None and number < 1:
            raise InvalidInput("number must be a positive integer, e.g. 614, or omitted.")
        return describe_comic(await fetch(number))

    @tools.tool(title="Get random xkcd comic")
    async def xkcd_get_random_comic() -> dict[str, Any]:
        """Pick a random xkcd comic up to the latest published number, excluding missing
        comic 404. Returns number, title, alt text, image URL, date and source page link.
        Use this to discover a comic without choosing a number; images are not downloaded."""
        latest = await fetch(None)
        return describe_comic(await fetch(chooser(latest["num"])))
