# NewsPulse AI: Product Documentation

NewsPulse AI is a production-ready intelligence engine designed to automate the discovery, analysis, and communication of high-impact AI news. It transforms raw web data into actionable business intelligence through semantic clustering, impact scoring, and automated content generation.

---

## 🚀 Core Value Proposition

In the rapidly evolving AI landscape, noise often drowns out signals. NewsPulse AI helps decision-makers and content creators stay ahead by:
1. **Automating Discovery**: Monitoring RSS feeds and static HTML sources for the latest AI updates.
2. **Deduplicating Information**: Grouping similar articles into "Trends" (Clusters) to provide a single source of truth.
3. **Quantifying Impact**: Using a proprietary impact engine to score news based on business relevance, adoption potential, and source authority.
4. **Actionable Communication**: Generating summarized briefs for executives and video scripts for creators.

---

## ✨ Key Features

### 1. Intelligence Hub (Scraping)
- **Selective Sources**: Curated monitoring of:
  - **AI Companies**: OpenAI, Anthropic, Google, Microsoft, Apple, Meta.
  - **Industry News**: Reuters, The Verge, MIT Tech Review, TechCrunch, VentureBeat.
  - **Research**: Hugging Face, DeepMind.
  - **Creators**: Selective YouTube channels like Two Minute Papers and AI Explained.
- **Relevance Filtering**: A multi-layered filter ensures only signal reaches the dashboard:
  - Rejects general news, gossip, and non-AI topics.
  - Prioritizes launches, capabilities (how-tos), and business impact over broad commentary.
  - Selective lookback (7 days) and item limits per feed.
- **Extraction**: Intelligent cleaning of HTML using specific selectors (article, main, entry-content) and noise removal (site chrome, navigation).

### 2. Semantic Clustering
- Uses **Gemini Embeddings** (`models/embedding-001`) to map articles into a vector space.
- Calculates cosine similarity between articles.
- Groups articles with a similarity score > 0.85 into cohesive trends/clusters.

### 3. Impact Engine (Scoring)
- Evaluates trends using a dual approach:
  - **Model-Based**: Uses Gemini-1.5-Flash to analyze content against a business-centric rubric (Business impact, Reach, Urgency, Execution certainty).
  - **Heuristic-Based**: A fallback mechanism that scores based on keyword density (ROI, Enterprise, Regulation), funding amounts, and source authority.
- Scores range from 0 to 100, where items > 70 are considered "High Signal."

### 4. Script Engine
- Automatically generates 2-minute YouTube/social media scripts for top trends.
- Structured JSON output includes:
  - **Hook**: High-energy opening.
  - **Context**: Simple explanation of the event.
  - **Why it Matters**: C-level and general audience takeaways.
  - **Deep Insight**: Technical nuance in plain English.
  - **Closing**: Engagement question.

### 5. Multi-Channel Alerts
- Real-time Slack integration for high-impact signals.
- Manual "Send to Slack" capability from the dashboard for any trend.

### 6. High-Fidelity Dashboard
- Built with **Next.js 14**, featuring a premium dark mode UI.
- Real-time updates via **Server-Sent Events (SSE)**.
- Detailed trend views with source links, impact breakdowns, and generated scripts.

---

## 🛠 Technical Architecture

NewsPulse AI is built as a modern, containerized monorepo.

### Backend (FastAPI)
- **Framework**: FastAPI (Python 3.12).
- **Service Layer**:
  - [ScraperService](file:///d:/AI%20news%20engine/backend/app/services/scraper.py#14-283): Manages article discovery and extraction.
  - [IntelligenceService](file:///d:/AI%20news%20engine/backend/app/services/intelligence.py#11-325): Handles embeddings, clustering, scoring, and script generation using Google Gemini.
  - `SlackService`: Manages outgoing notifications.
- **Task Queue**: Celery with Redis for background scraping and processing.
- **Database**: PostgreSQL with SQLAlchemy (Async).

### Frontend (Next.js)
- **Framework**: Next.js 14 (App Router).
- **Styling**: Tailwind CSS with Radix UI components.
- **Real-time**: EventSource (SSE) for automatic dashboard refreshes.

### Infrastructure
- **Docker**: Orchestrated via [docker-compose.yml](file:///d:/AI%20news%20engine/docker-compose.yml).
- **Worker**: Dedicated Celery worker for the intelligence pipeline.
- **Database**: Persistent PostgreSQL volume.

---

## 📡 API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/trends` | `GET` | Returns a paginated list of clusters sorted by impact score. |
| `/api/trends/{id}` | `GET` | Detailed view of a cluster, articles, and its AI script. |
| `/api/signals` | `GET` | Latest 5 raw articles/signals discovered. |
| `/api/events` | `GET` | SSE stream for live dashboard "data changed" notifications. |
| `/api/trigger` | `POST` | Manually triggers the scraping and processing pipeline. |
| `/api/trends/{id}/slack` | `POST` | Manually push a specific trend to the configured Slack channel. |
| `/api/trends/{id}/generate-script-and-slack` | `POST` | Upsert script for a trend and broadcast to Slack. |

---

## 🗄 Database Model

- **Article**: Stores raw and cleaned content, source URL, publication date, and Gemini embeddings.
- **Cluster**: Represents a "Trend." Contains representative title, summary, impact score, and category.
- **Script**: Links to a Cluster; stores the multi-part video script content.

---

## ⚙ Configuration (.env)

| Variable | Description |
| :--- | :--- |
| `POSTGRES_*` | Database credentials and host. |
| `REDIS_URL` | Redis endpoint for Celery task queuing. |
| `GEMINI_API_KEYS` | Comma-separated list of Gemini keys (supports rotation). |
| `SLACK_WEBHOOK_URL` | The endpoint for Slack channel notifications. |
| `GEMINI_EFFICIENT_MODE` | Boolean; if true, uses heuristic summaries for smaller clusters to save API quota. |

---

## 🚀 Development & Deployment

### Running Locally
1. Ensure Docker Desktop is running.
2. Configure [.env](file:///d:/AI%20news%20engine/.env) from [.env.example](file:///d:/AI%20news%20engine/.env.example).
3. Run `docker-compose up --build`.

### Deploying to Production
- The repository includes a [render.yaml](file:///d:/AI%20news%20engine/render.yaml) blueprint for easy deployment on Render.
- GitHub Actions are configured in [.github/workflows/render-deploy.yml](file:///d:/AI%20news%20engine/.github/workflows/render-deploy.yml) to trigger deploys on push to [main](file:///d:/AI%20news%20engine/backend/app/services/scraper.py#245-266).
