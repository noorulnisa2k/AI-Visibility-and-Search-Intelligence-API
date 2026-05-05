# AI Visibility Intelligence API

A RESTful Flask API that discovers high-value AI search queries in a business's competitive space, scores them by opportunity, and generates actionable content recommendations — powered by a multi-agent AI pipeline.

---

## Quick Start

```bash
# 1. Clone and install
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# 3. Initialize database
flask --app run:app db upgrade

# 4. Run
python run.py
# Server starts at http://localhost:5000
```

### Docker (with async support)

```bash
docker-compose up --build
```

This starts the API on port 5000, a Celery worker, and a Redis broker.

---

## Architecture

```
┌─────────────┐     ┌──────────────────────────────────────────────────────────┐
│   Client    │────▶│                    Flask API (Blueprints)                │
│             │     │  /api/v1/profiles     /api/v1/profiles/{id}/run          │
└─────────────┘     │  /api/v1/queries        /api/v1/tasks/{id}/status       │
                    └──────────────┬───────────────────────────────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │   PipelineOrchestrator      │
                    │  Sequential agent execution │
                    │  + partial failure handling │
                    └──────┬───────┬──────┬───────┘
                           │       │       │
              ┌────────────▼┐  ┌───▼────┐  ┌─▼───────────────────┐
              │  Agent 1    │  │Agent 2 │  │     Agent 3         │
              │  Discovery  │  │Scoring │  │  Recommendation     │
              │  (GPT-4o)   │  │(GPT-4o)│  │     (GPT-4o)        │
              └──────┬──────┘  └───┬────┘  └─────────┬───────────┘
                     │             │                  │
              ┌──────▼─────────────▼──────────────────▼──────┐
              │           SQLite / PostgreSQL                 │
              │  BusinessProfile → PipelineRun → Queries     │
              │                    → Recommendations          │
              └──────────────────────────────────────────────┘
```

### Component Breakdown

| Component | Location | Responsibility |
|---|---|---|
| App factory | `app/__init__.py` | Creates Flask app, config, DB, blueprints, error handlers, rate limiter |
| Models | `app/models/` | SQLAlchemy models with relationships, serialization (`to_dict()`), summary stats |
| Agents | `app/agents/` | Three LLM agents inheriting from `BaseAgent` — discovery, scoring, recommendation |
| Pipeline | `app/services/pipeline.py` | Orchestrates agents sequentially, persists results, handles partial failures |
| API | `app/api/` | Two blueprints — profiles and queries — with Pydantic validation |
| Tasks | `app/tasks.py` | Celery async task for background pipeline execution |
| Scoring | `app/utils/scoring.py` | Opportunity score formula implementation |

---

## Agent Design

### Model Selection

All agents use **GPT-4o** (OpenAI). The rationale:

- **Agent 1 (Discovery)** — GPT-4o's broader knowledge and higher creativity window (temp=0.7) produces diverse, realistic questions across industries
- **Agent 2 (Scoring)** — GPT-4o with low temperature (0.1) for consistent, deterministic numerical estimates
- **Agent 3 (Recommendation)** — GPT-4o with moderate temperature (0.5) balances actionable specificity with creative content ideas

Why not Claude? Anthropic's models are excellent at structured output, but GPT-4o currently has better support for JSON mode and more consistent schema adherence across varied prompt patterns. For a production system, A/B testing both providers per agent would be worthwhile.

### Prompt Engineering Strategy

Each agent follows the same pattern:

1. **System prompt** — sets persona, constraints, output schema, and explicit JSON instruction
2. **User prompt** — domain-specific data substituted into a template
3. **Parsing** — `BaseAgent._parse_json()` strips markdown fences, falls back to brace extraction
4. **Validation** — each agent validates the parsed output against expected shape, raises on invalid

This ensures the pipeline never crashes on malformed LLM output.

### Partial Failure Handling

The orchestrator wraps Agent 2 scoring per-query. If one query fails, the error is logged, a fallback result is stored, and processing continues. The pipeline reports how many queries were successfully scored vs total discovered.

---

## Opportunity Score Formula

```
score = 0.35 × volume_score + 0.25 × difficulty_score + 0.25 × visibility_gap + 0.15 × commercial_intent
```

| Component | Weight | Formula | Rationale |
|---|---|---|---|
| **Volume** | 35% | `min(search_volume / 10000, 1.0)` | Higher volume = more traffic opportunity. Capped at 10k to avoid skew |
| **Difficulty** | 25% | `(100 - competitive_difficulty) / 100` | Lower difficulty = easier to capture. Inverted so higher score = better opportunity |
| **Visibility gap** | 25% | `1.0` if not visible, `0.0` if visible | The core value proposition — queries where the domain is absent are the biggest opportunity |
| **Commercial intent** | 0.15 × `min(matches / 3, 1.0)` | Keyword matching: best, vs, compare, review, tool, software, pricing, etc. | Comparison/best-of queries signal purchase intent and are more valuable than informational queries |

Example scores:
- High-volume, low-difficulty, invisible, commercial → **0.75**
- Low-volume, high-difficulty, visible, informational → **0.03**
- Mid-volume, mid-difficulty, invisible, semi-commercial → **0.45**

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/profiles` | Register a business profile (201) |
| `GET` | `/api/v1/profiles/{id}` | Get profile with summary stats |
| `POST` | `/api/v1/profiles/{id}/run` | Trigger pipeline (sync or `?async=true`) |
| `GET` | `/api/v1/profiles/{id}/queries` | List queries with filters and pagination |
| `GET` | `/api/v1/profiles/{id}/recommendations` | List content recommendations |
| `POST` | `/api/v1/queries/{id}/recheck` | Re-score a single query |
| `GET` | `/api/v1/tasks/{id}/status` | Poll async pipeline task status |

### Example: Register and Run

```bash
# Register profile
curl -X POST http://localhost:5000/api/v1/profiles \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Frase",
    "domain": "frase.io",
    "industry": "SEO Content Tools",
    "description": "AI-powered content briefs and SEO research",
    "competitors": ["surferseo.com", "marketmuse.com", "clearscope.io"]
  }'

# Trigger pipeline (sync)
curl -X POST http://localhost:5000/api/v1/profiles/{id}/run

# Or async
curl -X POST "http://localhost:5000/api/v1/profiles/{id}/run?async=true"

# Get results
curl http://localhost:5000/api/v1/profiles/{id}/queries?min_score=0.7&status=not_visible
curl http://localhost:5000/api/v1/profiles/{id}/recommendations
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | Yes | — | OpenAI API key |
| `DATABASE_URL` | No | `sqlite:///dev.db` | SQLAlchemy connection string |
| `SECRET_KEY` | No | `dev-secret-key` | Flask secret key |
| `DATAFORSEO_USER` | No | — | DataForSEO API username (real search volume) |
| `DATAFORSEO_PASS` | No | — | DataForSEO API password |
| `CELERY_BROKER_URL` | No | `redis://localhost:6379/0` | Redis broker for async tasks |
| `CELERY_RESULT_BACKEND` | No | `redis://localhost:6379/1` | Redis result backend |

---

## Database Schema

```
BusinessProfile (1) ──┬── (N) PipelineRun
                      ├── (N) DiscoveredQuery ── (N) ContentRecommendation
                      └── (N) ContentRecommendation
```

All tables use UUID string primary keys. JSON columns store `competitors` and `target_keywords`. Timestamps use UTC. Cascade deletes propagate from profile to all related records.

---

## Running Tests

```bash
python -m pytest tests/test_agents.py -v
```

33 tests covering: opportunity score formula, all 3 agents (with mocked LLM), pipeline orchestrator, and all API endpoints.

---

## Tradeoffs & Decisions

- **SQLite default** — simpler setup for assessment. PostgreSQL supported via `DATABASE_URL`
- **Sync by default** — async requires Redis. `?async=true` falls back to sync if Celery unavailable
- **No real DataForSEO by default** — fallback to AI-estimated volume when credentials not configured
- **`Query.get()` legacy warning** — acceptable for this scope; would migrate to `db.session.get()` in production
- **No authentication** — per spec. Production would add JWT or API key auth
- **Rate limiting** — memory-backed storage (in-memory). Redis-backed in production/docker

---

## AI Tools Used

This project was built with the assistance of an AI coding assistant for boilerplate generation and test writing. All architecture decisions, agent design, prompt engineering, and scoring formula are human-authored.
