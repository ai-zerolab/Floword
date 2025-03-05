import random
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mock-server")


@mcp.tool()
async def generate_random_number(min_value: int = 0, max_value: int = 100) -> float:
    """Generate a random number between min_value and max_value"""
    return random.uniform(min_value, max_value)  # noqa: S311


@mcp.tool()
async def echo_text(text: str) -> str:
    """Echo the input text"""
    return text


@mcp.tool()
async def get_user_info(user_id: int) -> dict[str, Any]:
    """Get user information by ID"""
    return {"id": user_id, "name": f"User {user_id}", "email": f"user{user_id}@example.com"}


@mcp.tool()
async def raise_error(message: str = "An error occurred") -> None:
    """Raise an error with the given message"""
    raise ValueError(message)


@mcp.tool()
async def complex_operation(
    data: dict[str, Any], options: list[str] | None = None, verbose: bool = False
) -> dict[str, Any]:
    """Perform a complex operation with multiple parameters"""
    options = options or ["default"]
    return {
        "processed": True,
        "input_data": data,
        "options_used": options,
        "verbose_mode": verbose,
        "result": "Success",
    }


if __name__ == "__main__":
    mcp.run("stdio")
