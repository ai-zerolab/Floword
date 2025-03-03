import random

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("email")


@mcp.tool()
async def generate_ramdon_number() -> float:
    return random.random()


if __name__ == "__main__":
    mcp.run("stdio")
