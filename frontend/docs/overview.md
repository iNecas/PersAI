# Frontend implementation overview

## Project Structure

(excluding boilerplate code)

```
src/
└── explore/
    └─── persai-explorer/
        ├── PersaiExplorer.tsx       # Entry-point component of the AI chat interface
        ├── api.ts                   # HTTP client for backend communication
        ├── types.ts                 # Common types definitions
        └── components/
            ├── Messages.tsx         # Chat message rendering
            └── ToolCall.tsx         # AI tool call visualization
```

