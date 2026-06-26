.PHONY: help download-files dev clean langgraph-dev dev-all frontend streamlit-frontend

# Default target
help:
	@echo "Available targets:"
	@echo "  make download-files  - Download required files"
	@echo "  make dev            - Run the LiveKit agent in development mode"
	@echo "  make langgraph-dev  - Run the LangGraph dev server (uv run langgraph dev)"
	@echo "  make dev-all        - Start LangGraph server and LiveKit agent together"
	@echo "  make frontend       - Run Python FastAPI voice UI (http://127.0.0.1:8080)"
	@echo "  make streamlit-frontend - Run Streamlit wrapper around the FastAPI UI"
	@echo "  make clean          - Clean up any generated files"
	@echo "  make help           - Show this help message"

# Download required files
download-files:
	uv run -m src.livekit.agent download-files

# Run the LiveKit agent in development mode
dev:
	uv run -m src.livekit.agent dev

# Run the LangGraph dev server (default port 2024)
langgraph-dev:
	uv run langgraph dev

# Start both LangGraph server and LiveKit agent
# Note: Runs LangGraph in background, then starts the agent.
# Stop processes with your terminal controls (Ctrl+C) as needed.
dev-all:
	( uv run langgraph dev & ); sleep 2; uv run -m src.livekit.agent dev

# Python voice UI (replaces Next.js frontend)
frontend:
	uv run python -m src.frontend

streamlit-frontend:
	uv run streamlit run src/frontend/streamlit_app.py

# Clean up any generated files
clean:
	@echo "Cleaning up..."
	rm -rf __pycache__
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf src/**/__pycache__
	rm -rf src/**/*.pyc 