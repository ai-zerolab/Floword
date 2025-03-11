# floword

[![Release](https://img.shields.io/github/v/release/ai-zerolab/floword)](https://img.shields.io/github/v/release/ai-zerolab/floword)
[![Build status](https://img.shields.io/github/actions/workflow/status/ai-zerolab/floword/main.yml?branch=main)](https://github.com/ai-zerolab/floword/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/ai-zerolab/floword/branch/main/graph/badge.svg)](https://codecov.io/gh/ai-zerolab/floword)
[![Commit activity](https://img.shields.io/github/commit-activity/m/ai-zerolab/floword)](https://img.shields.io/github/commit-activity/m/ai-zerolab/floword)
[![License](https://img.shields.io/github/license/ai-zerolab/floword)](https://img.shields.io/github/license/ai-zerolab/floword)

Backend implementation for building workflow with natural language

- **Github repository**: <https://github.com/ai-zerolab/floword/>
- (WIP)**Documentation** <https://ai-zerolab.github.io/floword/>

## Installation

We recommend using [uv](https://github.com/astral-sh/uv) to manage your environment.

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh  # For macOS/Linux
# or
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"  # For Windows
```

Then you can use `uvx floword@latest strat` as commands for running the floword server.

Docker is also supported. You can use `docker pull ghcr.io/ai-zerolab/floword:latest` to pull the image from Github Container Registry.

(WIP) You can found deployment instructions in [deploy](./deploy) directory.

## Configuration

### Via Environment Variables

You can use `.env` file or environment variables to configure floword. All environment variables should be prefixed with `FLOWORD_` (case-insensitive).

Available options:

#### Authentication

- `FLOWORD_JWT_SECRET_TOKEN`: Secret token for JWT authentication. Default: `None`
- `FLOWORD_ALLOW_ANONYMOUS`: Allow anonymous access. Default: `True`

#### Database Configuration

- `FLOWORD_SQLITE_FILE_PATH`: Path to SQLite database file. Default: `./floword.sqlite` (in current working directory)
- `FLOWORD_USE_POSTGRES`: Use PostgreSQL instead of SQLite. Default: `False`
- `FLOWORD_PG_USER`: PostgreSQL username. Default: `postgres`
- `FLOWORD_PG_PASSWORD`: PostgreSQL password. Default: `postgres`
- `FLOWORD_PG_HOST`: PostgreSQL host. Default: `localhost`
- `FLOWORD_PG_PORT`: PostgreSQL port. Default: `5432`
- `FLOWORD_PG_DATABASE`: PostgreSQL database name. Default: `floword`

#### Streamer Configuration

- `FLOWORD_REDIS_URL`: Redis URL for streaming messages in distributed mode. Default: `None`

#### Model Configuration

- `FLOWORD_DEFAULT_MODEL_PROVIDER`: Default LLM provider. Default: `openai`
- `FLOWORD_DEFAULT_MODEL_NAME`: Default model name. Default: `None`
- `FLOWORD_DEFAULT_MODEL_KWARGS`: Additional arguments for the model (as JSON string). Default: `None`
- `FLOWORD_DEFAULT_CONVERSATION_SYSTEM_PROMPT`: Default system prompt for conversations. Default: Content from `floword/prompts/system-conversation.md`
- `FLOWORD_DEFAULT_WORKFLOW_SYSTEM_PROMPT`: Default system prompt for workflows. Default: Content from `floword/prompts/system-workflow.md`

### Config MCP Server

Use `FLOWORD_MCP_CONFIG_PATH` to specify the path to the MCP configuration file. Default: `./mcp.json` (in current working directory)

The MCP configuration file should be a json file with the following structure:

```json
{
  "mcpServers": {
    "zerolab-toolbox": {
      "args": ["mcp-toolbox@latest", "stdio"],
      "command": "uvx",
      "env": {
        "FIGMA_API_KEY": "your-figma-api-key"
      }
    },
    "sse-server": {
      "url": "http://localhost:8000",
      "headers": {},
      "timeout": 5,
      "sse_read_timeout": 300
    }
  }
}
```

## Development

### Local Setup

Fork the repository and clone it to your local machine.

```bash
# Install in development mode
make install
# Activate a virtual environment
source .venv/bin/activate  # For macOS/Linux
# or
.venv\Scripts\activate  # For Windows
```

### Running Tests

```bash
make test
```

### Running Checks

```bash
make check
```

### Building Documentation

```bash
make docs
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
1. Create a feature branch (`git checkout -b feature/amazing-feature`)
1. Commit your changes (`git commit -m 'Add some amazing feature'`)
1. Push to the branch (`git push origin feature/amazing-feature`)
1. Open a Pull Request

## License

This project is licensed under the terms of the license included in the repository.
