# video-generation-mcp

Reusable MCP wrapper for AI short-drama video generation providers.

Supported provider adapters:

- hailuo / MiniMax
- runway
- veo / Gemini API
- kling

Default behavior is dry-run. Live API calls require `live=true` and provider
API keys in environment variables.

