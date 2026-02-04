# Morning Markets - Prediction Market App

A web-based prediction market application for trivia-style questions. Users can trade on market outcomes, and an admin settles markets with the actual answer to determine winners.

## Quick Start (Local Development)

### Prerequisites
- Python 3.10+
- Docker (for PostgreSQL)

### Setup

```bash
# 1. Start PostgreSQL with Docker
docker-compose up -d

# 2. Create virtual environment (if not exists)
python3 -m venv .venv

# 3. Activate virtual environment
source .venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Start the server
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/morning_markets cd src && uvicorn main:app --host 0.0.0.0 --port 8000

# 6. Open in browser
open http://localhost:8000
```

### Quick Commands

```bash
# Start database (if not running)
docker-compose up -d

# Check database is running
docker-compose ps

# Stop database
docker-compose down

# Stop database and delete all data
docker-compose down -v
```

## Deploy to Render.com

Render.com provides free hosting with PostgreSQL. Follow these steps:

### Step 1: Push to GitHub

```bash
git add .
git commit -m "Ready for deployment"
git push origin main
```

### Step 2: Create Render Account

1. Go to [render.com](https://render.com)
2. Sign up with GitHub (recommended) or email

### Step 3: Deploy with Blueprint

1. In Render dashboard, click **New** → **Blueprint**
2. Connect your GitHub repository
3. Render will automatically detect `render.yaml` and configure:
   - **Web Service**: Python app running uvicorn
   - **PostgreSQL Database**: Free tier database
4. Click **Apply** to start deployment
5. Wait for build (~2-3 minutes)

### Step 4: Access Your App

Once deployed, Render provides a URL like:
```
https://morning-markets.onrender.com
```

### Render Free Tier Notes

- **Database**: Free PostgreSQL expires after 90 days
- **Web Service**: Sleeps after 15 minutes of inactivity (~30s cold start)
- **Custom Domain**: Available on paid plans

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `PORT` | Server port (set by Render automatically) | On Render |

### Local Development

```bash
# Set DATABASE_URL for local PostgreSQL (from docker-compose)
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/morning_markets

# Or inline when starting server
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/morning_markets \
  cd src && uvicorn main:app --host 0.0.0.0 --port 8000
```

### On Render.com

The `DATABASE_URL` is automatically set when you link the PostgreSQL database.

## Features

- **Kahoot-style joining**: Participants enter a display name (no passwords)
- **Admin controls**: Create markets, close them, settle with actual values
- **Order book trading**: Place bids and offers that auto-match when crossing
- **Real-time updates**: Order book refreshes every second via HTMX polling
- **Position limits**: Configurable max position per user (default: 20 lots)
- **P&L tracking**: Both linear P&L (dollar amount) and binary P&L (lots won/lost)
- **Leaderboard**: Aggregate scores across all settled markets

## How to Play

### As a Participant

1. Go to `http://localhost:8000` (or your Render URL)
2. Enter a unique display name and click "Join as Participant"
3. Click on an open market to view the trading page
4. Place bids (to buy) or offers (to sell) at your chosen price
5. Orders that cross (bid >= best offer) automatically match
6. View your position and recent trades in real-time
7. After settlement, check the results page for your P&L

### As Admin

1. Go to the app URL
2. Click "Enter as Admin" and login:
   - Username: `chrson`
   - Password: `optiver`
3. From the admin panel:
   - Create new markets with trivia questions
   - Close markets to stop new orders
   - Settle markets by entering the actual answer
   - Adjust the global position limit

## Trading Rules

- **Crossing orders**: A bid at or above the best offer price will automatically match (and vice versa)
- **Price-time priority**: When matching, takers get the maker's price; earlier orders fill first
- **Self-trade prevention**: You cannot match with your own orders
- **Position limits**: Orders that would exceed your position limit are rejected
- **Shorting allowed**: You can go short (negative position) up to the position limit

## P&L Calculation

### Linear P&L
For each user's position:
```
Linear P&L = Net Quantity × (Settlement Value - Average Price)
```
Example: Long 10 lots at avg price 50, market settles at 60 → P&L = +100

### Binary P&L
Counted per trade as "lots won" or "lots lost":
- **BUY**: If settlement > trade price → +quantity (won), else -quantity (lost)
- **SELL**: If settlement < trade price → +quantity (won), else -quantity (lost)

## Running Tests

Tests require a running PostgreSQL database.

```bash
# 1. Make sure PostgreSQL is running
docker-compose up -d

# 2. Activate virtual environment
source .venv/bin/activate

# 3. Set DATABASE_URL
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/morning_markets

# 4. Run all tests
pytest tests/ -v

# Run specific test files
pytest tests/test_matching.py -v      # Matching engine tests
pytest tests/test_settlement.py -v    # Settlement/P&L tests
pytest tests/test_api.py -v           # API integration tests
pytest tests/test_concurrent.py -v    # Concurrent user tests
```

### Test Summary

| Test File | Tests | Description |
|-----------|-------|-------------|
| `test_matching.py` | 11 | Order matching, price-time priority, position limits |
| `test_settlement.py` | 24 | Linear P&L, binary P&L, settlement flow |
| `test_api.py` | 12 | API endpoints, authentication, full lifecycle |
| `test_concurrent.py` | 6 | Concurrent users, race conditions |

Total: 53 tests

## Project Structure

```
morning-_markets_app/
├── src/
│   ├── main.py          # FastAPI routes and endpoints
│   ├── database.py      # PostgreSQL setup and queries
│   ├── models.py        # Pydantic data models
│   ├── matching.py      # Order matching engine
│   ├── settlement.py    # Settlement and P&L calculation
│   ├── auth.py          # Session management
│   └── templates/       # Jinja2 HTML templates
│       ├── base.html
│       ├── index.html   # Join page
│       ├── markets.html # Market list
│       ├── market.html  # Trading view
│       ├── admin.html   # Admin panel
│       ├── settle.html  # Settlement form
│       ├── results.html # Settlement results
│       ├── leaderboard.html
│       └── partials/    # HTMX polling components
├── tests/
│   ├── conftest.py      # Pytest fixtures
│   ├── test_matching.py
│   ├── test_settlement.py
│   ├── test_api.py
│   └── test_concurrent.py
├── docker-compose.yml   # Local PostgreSQL setup
├── render.yaml          # Render.com deployment config
├── requirements.txt
└── README.md
```

## Network Access (Local)

To let others on the same network access the app:

1. Find your IP address:
   ```bash
   # Linux
   hostname -I | awk '{print $1}'

   # macOS
   ipconfig getifaddr en0
   ```

2. Start the server (it already binds to 0.0.0.0):
   ```bash
   DATABASE_URL=postgresql://postgres:postgres@localhost:5432/morning_markets \
     cd src && uvicorn main:app --host 0.0.0.0 --port 8000
   ```

3. Others can access via `http://<your-ip>:8000`

## Tech Stack

- **Backend**: Python 3.10+ with FastAPI
- **Frontend**: HTML + Jinja2 + HTMX (1-second polling)
- **Database**: PostgreSQL (via asyncpg)
- **Testing**: pytest + pytest-asyncio + httpx
- **Deployment**: Render.com

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Landing page |
| POST | `/join` | Join as participant |
| POST | `/admin/login` | Admin login |
| GET | `/markets` | List all markets |
| GET | `/markets/{id}` | Market trading view |
| POST | `/markets/{id}/orders` | Place order |
| POST | `/orders/{id}/cancel` | Cancel order |
| GET | `/markets/{id}/results` | Settlement results |
| GET | `/leaderboard` | Aggregate leaderboard |
| GET | `/admin` | Admin panel |
| POST | `/admin/markets` | Create market |
| POST | `/admin/markets/{id}/close` | Close market |
| POST | `/admin/markets/{id}/settle` | Settle market |
| POST | `/admin/config` | Update position limit |

## License

MIT
