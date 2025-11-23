# Frank Bot - MCP Server

A Model Context Protocol (MCP) server for ChatGPT integration, running in Docker.

## What is MCP?

MCP (Model Context Protocol) is a protocol that allows AI assistants to securely connect to external tools and data sources. This server exposes tools that ChatGPT can use.

## Quick Start

### 1. Set up environment variables

```bash
# Copy the example env file
cp .env.example .env

# Edit .env with your configuration (if needed)
```

### 2. Build the Docker image

```bash
docker build -t frank-bot .
```

### 3. Run the container

```bash
docker run frank-bot
```

Note: MCP servers communicate via stdio, so they don't expose HTTP ports.

## Development

To run locally without Docker:

```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the MCP server
python app.py
```

## Available Tools

- `hello_world` - A simple hello world tool that greets the user
  - Optional parameter: `name` (string) - The name to greet (defaults to "World")

## Environment Variables

See `.env.example` for available configuration options. Copy it to `.env` and customize as needed.

## Integration with ChatGPT

To use this MCP server with ChatGPT:

1. Configure ChatGPT to use this MCP server
2. The server exposes tools via the MCP protocol over stdio
3. ChatGPT can call the `hello_world` tool to interact with the server

## Project Structure

```
frank_bot/
├── app.py              # MCP server implementation
├── requirements.txt    # Python dependencies
├── Dockerfile         # Docker configuration
├── .env.example       # Environment variable template
├── .env               # Your environment variables (not in git)
└── README.md          # This file
```

## Next Steps

- Add more tools to the MCP server
- Add prompts and resources
- Extend functionality based on your needs

