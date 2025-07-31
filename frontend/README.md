# PersAI: UI plugin

## Quick Start

PersAI is not yet pushed to packages registry. Therefore only development
installation is available at the moment.

### Prerequisites

- Perses running in development environment
- `percli` CLI configured configured
- PersAI back-end running (see [back-end installation instructions](../backend/README.md#quick-start))

### Installation

```bash
# Install dependencies
npm install

# Start the plugin
percli plugin start "$(readlink -f .)"

# Let the frontend know where to find the backend
PERSAI_BACKEND_URL="http://localhost:8000"
echo \
    '{ "kind":"GlobalVariable","metadata":{"name":"persai_url"},'\
    '  "spec":{"kind":"TextVariable","spec":{"value":"'$PERSAI_BACKEND_URL'"}}}'| \
    percli apply -f -
```


## Development

See [the docs directory](./docs) to learn more details about the project
structure, conventions, testing etc.

## License

See [LICENSE](LICENSE) file for details.
