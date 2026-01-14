# Research, Analysis, Design, and Verification Agent (a Finance Agent) for AgentBeats

A financial research agent that answers questions using SEC filings, web search, and document analysis. Built with Google ADK and compatible with the A2A protocol for agent interoperability.

## Features

- 🔍 **Web Search**: Query financial information from the web using SerpAPI
- 📊 **SEC EDGAR Search**: Access company filings from the SEC database
- 📄 **HTML Parsing**: Extract and analyze content from web pages
- 🤖 **AI-Powered Analysis**: Use Google's Gemini model for information retrieval and synthesis

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd RADV

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Create a `.env` file with your API keys:

```bash
GOOGLE_API_KEY=your_google_api_key_here
SERP_API_KEY=your_serpapi_key_here
SEC_EDGAR_API_KEY=your_sec_edgar_api_key_here
```

Get your API keys from:
- [Google AI Studio](https://ai.google.dev/gemini-api/docs/api-key)
- [SerpAPI](https://serpapi.com/)
- [SEC EDGAR API](https://sec-api.io/)

### 3. Run the Agent

**For local testing:**
```bash
python scenarios/finance/finance_agent.py --host 127.0.0.1 --port 9099
```

**For AgentBeats platform submission:**
```bash
# Start Cloudflare tunnel
cloudflared tunnel --url http://127.0.0.1:9099

# In another terminal, start agent with public URL
python scenarios/finance/finance_agent.py --host 127.0.0.1 --port 9099 --card-url https://YOUR-URL.trycloudflare.com
```

### 4. Query the Agent

```bash
python query_finance_agent.py "What was Apple's revenue in 2023?"
```

## Project Structure

```
RADV/
├── data/
│   └── public.csv              # Validation dataset
├── scenarios/
│   └── finance/
│       ├── finance_agent.py    # Main agent implementation
│       ├── finance_evaluator.py # Evaluator for testing
│       ├── finance_tools.py    # Tool adapters for Google ADK
│       ├── tools.py            # Core tool implementations
│       ├── utils.py            # Utility functions
│       ├── scenario.toml       # Scenario configuration
│       └── README.md           # Detailed documentation
├── query_finance_agent.py      # Direct query utility
├── run_scenario.py             # Scenario runner
├── requirements.txt            # Python dependencies
├── pyproject.toml             # Project configuration
└── .env                        # API keys (not in repo)
```

## Documentation

For detailed usage instructions, see [scenarios/finance/README.md](scenarios/finance/README.md)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Docker Deployment

### Build the Docker Image

**Local build:**
```bash
docker build -t finance-agent .
```

### Build and Push to Registry

To build and push the Docker image to a container registry (Docker Hub, GitHub Container Registry, etc.):

**Using the build script:**
```bash
# Docker Hub (default)
./build-and-push.sh docker.io username/finance-agent latest

# With version tag
./build-and-push.sh docker.io username/finance-agent 0.1.0

# GitHub Container Registry
./build-and-push.sh ghcr.io username/finance-agent latest

# Custom registry
./build-and-push.sh registry.example.com finance-agent latest
```

**Manual build and push:**
```bash
# Build with full image name
docker build -t registry/repository:tag .

# Push to registry
docker push registry/repository:tag
```

**Image naming format:**
- **Registry**: `docker.io` (Docker Hub), `ghcr.io` (GitHub Container Registry), or your custom registry
- **Repository**: `username/finance-agent` (Docker Hub) or `finance-agent` (other registries)
- **Tag**: `latest`, `0.1.0` (version), or any custom tag

**Example Docker image URLs:**
- Docker Hub: `docker.io/username/finance-agent:latest`
- GitHub Container Registry: `ghcr.io/username/finance-agent:latest`
- Custom registry: `registry.example.com/finance-agent:0.1.0`

**Note:** Make sure you're authenticated with the registry before pushing:
- Docker Hub: `docker login`
- GitHub Container Registry: `docker login ghcr.io`
- Other registries: `docker login <registry-url>`

### Run with Docker Compose

**Option 1: Using environment variables**
```bash
# Set environment variables
export GOOGLE_API_KEY=your_key
export SERP_API_KEY=your_key
export SEC_EDGAR_API_KEY=your_key

# Start services
docker-compose up -d
```

**Option 2: Using .env file**
```bash
# Copy example override file
cp docker-compose.override.yml.example docker-compose.override.yml
# Edit docker-compose.override.yml with your API keys

# Start services
docker-compose up -d
```

### Available Services

- **finance-agent**: Finance agent on port 9099
- **finance-evaluator**: Evaluator on port 9000
- **agentbeats-green-agent**: AgentBeats agent with launcher (6000) and agent (6003)

### Run Individual Services

**Finance Agent:**
```bash
docker run -d \
  -p 9099:9099 \
  -e GOOGLE_API_KEY=your_key \
  -e SERP_API_KEY=your_key \
  -e SEC_EDGAR_API_KEY=your_key \
  finance-agent \
  python scenarios/finance/finance_agent.py --host 0.0.0.0 --port 9099
```

**Finance Evaluator:**
```bash
docker run -d \
  -p 9000:9000 \
  -e GOOGLE_API_KEY=your_key \
  -e SERP_API_KEY=your_key \
  -e SEC_EDGAR_API_KEY=your_key \
  finance-agent \
  python scenarios/finance/finance_evaluator.py --host 0.0.0.0 --port 9000
```

**AgentBeats Green Agent:**
```bash
docker run -d \
  -p 6000:6000 \
  -p 6003:6003 \
  -e GOOGLE_API_KEY=your_key \
  -e SERP_API_KEY=your_key \
  -e SEC_EDGAR_API_KEY=your_key \
  finance-agent \
  agentbeats run scenarios/finance/green_agent_card.toml \
    --launcher_host 0.0.0.0 --launcher_port 6000 \
    --agent_host 0.0.0.0 --agent_port 6003 \
    --model_type gemini --model_name gemini-2.5-flash
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f finance-agent
```

### Stop Services

```bash
docker-compose down
```

## Building and Pushing Docker Images

This project uses **separate Docker images** for the finance agent and finance evaluator.

### Build Both Images

To build and push both images to a registry:

```bash
# Make script executable (first time only)
chmod +x build-and-push-both.sh

# Build and push to GitHub Container Registry
./build-and-push-both.sh ghcr.io username/finance latest

# Build and push to Docker Hub
./build-and-push-both.sh docker.io username/finance latest

# Using defaults (Docker Hub)
./build-and-push-both.sh
```

This will create two images:
- `{registry}/{prefix}-agent:{tag}` (e.g., `ghcr.io/username/finance-agent:latest`)
- `{registry}/{prefix}-evaluator:{tag}` (e.g., `ghcr.io/username/finance-evaluator:latest`)

### Build Individual Images

**Finance Agent only:**
```bash
chmod +x build-and-push.sh
./build-and-push.sh ghcr.io username/finance-agent latest
# Finance Agent
docker build -f Dockerfile.finance-agent -t your-registry/finance-agent:latest .
docker push your-registry/finance-agent:latest
```

**Finance Evaluator only:**
```bash
# Finance Evaluator
docker build -f Dockerfile.finance-evaluator -t your-registry/finance-evaluator:latest .
docker push your-registry/finance-evaluator:latest
```

### Using Pre-built Images in docker-compose.yml

After pushing images, update `docker-compose.yml`:

```yaml
services:
  finance-agent:
    image: ghcr.io/username/finance-agent:latest
    # ... rest of config

  finance-evaluator:
    image: ghcr.io/username/finance-evaluator:latest
    # ... rest of config
```

### Dockerfiles

- `Dockerfile.finance-agent` - Finance Agent (Purple Agent) image
- `Dockerfile.finance-evaluator` - Finance Evaluator (Green Agent) image

Both images share the same base dependencies but have different entry points and exposed ports.

## Acknowledgments

- Built with [Google ADK](https://github.com/google/adk)
- Compatible with [AgentBeats](https://agentbeats.org) evaluation platform
- Uses the [A2A Protocol](https://a2a.ai) for agent interoperability

