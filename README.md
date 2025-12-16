# MoneyFlow 💸

**Version 1.2.0**

A comprehensive personal finance management application built with FastAPI, SQLAlchemy, and Jinja2 templates. Track your income, expenses, budgets, taxes, investments, and run Monte Carlo simulations all in one place.

## Features

### 🏠 Dashboard
- **Money Flow Sankey Chart**: Visual representation of how your income flows through taxes, deductions, and expenses
- **Spending Trends**: Track your spending patterns by category and subcategory
- **Monthly Summary**: Quick overview of income, expenses, and surplus/deficit
- **Toggle Detail Level**: Switch between category summary and detailed subcategory views

### 📋 Budget Management
- **Fixed Recurring Costs**: Track monthly bills, subscriptions, and fixed expenses
- **Variable Expenses**: Budget for groceries, entertainment, and other variable costs
- **50/30/20 Rule Tracking**: Monitor your spending against recommended budgeting guidelines
- **Linked Expense Categories**: Connect budget items to tracked expenses for automatic averaging
- **Tax Integration**: View monthly tax breakdown directly in budget overview

### 💰 Expense Tracking
- **Categorized Expenses**: Organize expenses by custom categories and subcategories
- **Recurring Expenses**: Mark expenses as recurring with flexible frequency options
- **Visual Analytics**: Stacked bar charts, category breakdowns, and subcategory analysis
- **Bulk Import**: Upload expenses via CSV file directly on the Expenses page
- **CSV Export**: Export all expense data as CSV

### 📊 Income & Taxes
- **Multi-Year Tax Support**: Calculate taxes for 2023-2026 with year-specific brackets
- **Federal Tax Calculation**: Progressive tax brackets with detailed breakdown
- **State Tax (Missouri)**: Full Missouri tax calculation support
- **FICA Taxes**: Social Security and Medicare calculations
- **AMT Analysis**: Alternative Minimum Tax calculation with proper ISO stock option integration
- **Tax Credits**: Add custom tax credits with detailed breakdown
- **Retirement Contributions**: Track 401k, IRA, and other retirement accounts

### 🛠️ Financial Tools
- **Mortgage Calculator**: Comprehensive calculator with scenario comparison, amortization schedules, and saved scenarios (max 5)
- **Net Worth Manager**: Track assets (max 15) and liabilities (max 15) with historical balance tracking
- **Investment Projections**: Project portfolio growth with contributions and returns
- **Monte Carlo Simulations**: Run 1000+ simulations using historical market data with inflation adjustments
- **Portfolio Allocation**: Specify stocks/bonds/cash percentages for each account
- **CSV Bulk Upload/Export**: Import and export net worth data as CSV files

### 📚 Financial Resources
- Curated links to reputable financial blogs and tools
- Tax resources and calculators
- Investment and retirement planning guides

### 👤 User Management
- **Dark Mode**: Toggle between light and dark themes
- **Profile Pictures**: Upload custom avatar images
- **Data Management**: Export data and delete account options

## Tech Stack

- **Backend**: FastAPI (Python 3.11+)
- **Database**: SQLite with SQLAlchemy ORM
- **Migrations**: Alembic
- **Templates**: Jinja2
- **Frontend**: Vanilla JavaScript, Chart.js, Google Charts
- **Scientific Computing**: NumPy for Monte Carlo simulations
- **CSS**: Custom CSS with dark mode support

## Prerequisites

- Python 3.11+
- Poetry (package manager)

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/SimulatorK/MoneyFlow
cd MoneyFlow
```

# Make sure pyenv is setup properly
# Check if pyenv is in your PATH
```bash
which pyenv
```

# Initialize pyenv in your current shell
```bash
eval "$(pyenv init -)"
```
# Check what Python versions are installed
```bash
pyenv versions
```
# Install Python 3.11 if not present
```bash
pyenv install 3.11
```
# Set it as global or local version
```bash
pyenv global 3.11
```
# OR for just this project:
```bash
cd /Users/mason.kelchner/Desktop/Personal/PersonalProjects/MoneyFlow
pyenv local 3.11
```

### 2. Install Dependencies

```bash
# Install Poetry if not already installed
curl -sSL https://install.python-poetry.org | python3 -

# Install project dependencies
poetry install

# Activate the virtual environment
poetry shell
```

### 3. Initialize the Database

```bash
poetry run alembic upgrade head
```

### 4. Run the Application

**Using the run script (recommended):**
```bash
# Development mode with ngrok tunnel
./run.sh

# Production mode with ngrok tunnel
./run.sh --prod

# With periodic refresh (restarts every 6 hours)
./run.sh --prod --refresh

# Check status
./run.sh --status

# Stop all services
./run.sh --stop
```

**Manual commands:**

Development mode with auto-reload:
```bash
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Production mode:
```bash
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 5. Access the Application

Open your browser and navigate to:
- Local: `http://localhost:8000`
- Network: `http://<your-local-ip>:8000`

---

## 🌐 Remote Access Setup (Access from Phone/Internet)

To access MoneyFlow from outside your local network (e.g., from your phone when not on WiFi):

### Option 1: Cloudflare Tunnel (Recommended - Free & Secure)

This is the best option for permanent remote access with a custom domain.

**Step 1: Get a Free Domain (if needed)**
- Purchase a domain from Cloudflare Registrar, Namecheap, or GoDaddy (~$10-15/year)
- Or use a free subdomain from services like FreeDNS (freedns.afraid.org)

**Step 2: Set Up Cloudflare**
```bash
# Install cloudflared
brew install cloudflare/cloudflare/cloudflared  # macOS
# or: sudo apt install cloudflared  # Debian/Ubuntu

# Authenticate with Cloudflare
cloudflared tunnel login

# Create a tunnel
cloudflared tunnel create moneyflow

# Create config file (~/.cloudflared/config.yml)
cat << EOF > ~/.cloudflared/config.yml
tunnel: <your-tunnel-id>
credentials-file: ~/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: moneyflow.yourdomain.com
    service: http://localhost:8000
  - service: http_status:404
EOF

# Add DNS record
cloudflared tunnel route dns moneyflow moneyflow.yourdomain.com

# Run the tunnel
cloudflared tunnel run moneyflow

# Or install as system service (recommended for permanent access)
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

Now access your app at: `https://moneyflow.yourdomain.com`

### Option 2: Port Forwarding (Router)

1. Find your local IP: `ifconfig | grep "inet " | grep -v 127.0.0.1`
2. Access router admin panel (usually `192.168.1.1`)
3. Create port forward rule: External Port `8000` → Internal IP:Port `8000`
4. Find public IP: `curl ifconfig.me`
5. Access via: `http://<public-ip>:8000`

### Option 3: ngrok (Quick Testing)

```bash
brew install ngrok
ngrok config add-authtoken <your-auth-token>
ngrok http 8000

ngrok http http://localhost:8000
```
# navigate to
https://maximiliano-shipless-unliberally.ngrok-free.dev/home

### Option 4: Tailscale (VPN - Free for Personal Use)

1. Install Tailscale on both devices
2. Access via Tailscale IP: `http://100.x.x.x:8000`

---

## Project Structure

```
MoneyFlow/
├── alembic/                        # Database migrations
│   ├── env.py                      # Alembic environment config
│   ├── script.py.mako              # Migration template
│   └── versions/                   # Migration scripts
├── app/
│   ├── __init__.py
│   ├── db.py                       # Database connection & session
│   ├── logging_config.py           # Logging setup
│   ├── main.py                     # FastAPI application entry point
│   ├── models/                     # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── budget.py               # FixedCost, BudgetItem
│   │   ├── expense.py              # Expense, Category, SubCategory
│   │   ├── income_taxes.py         # IncomeTaxes model
│   │   ├── mortgage.py             # MortgageScenario
│   │   ├── networth.py             # Account, AccountBalance, MonteCarloScenario
│   │   └── user.py                 # User model
│   ├── routes/                     # API route handlers
│   │   ├── auth.py                 # Login, register, logout
│   │   ├── budget.py               # Budget management
│   │   ├── expenses.py             # Expense tracking & CSV
│   │   ├── forum.py                # Financial resources
│   │   ├── home.py                 # Dashboard & Sankey
│   │   ├── income_taxes.py         # Tax calculations
│   │   ├── profile.py              # User settings
│   │   └── tools.py                # Mortgage, NetWorth, Monte Carlo
│   ├── static/
│   │   └── app.css                 # Global styles & dark mode
│   ├── templates/                  # Jinja2 HTML templates
│   │   ├── about.html
│   │   ├── budget.html
│   │   ├── expenses.html
│   │   ├── forum.html
│   │   ├── home.html
│   │   ├── income_taxes.html
│   │   ├── login.html
│   │   ├── profile.html
│   │   ├── register.html
│   │   └── tools.html
│   └── utils/
│       └── auth.py                 # Password hashing utilities
├── logs/                           # Application logs
│   ├── errors.log                  # Error-only log
│   └── moneyflow.log               # Full application log
├── tests/                          # Unit tests
│   ├── __init__.py
│   ├── conftest.py                 # Pytest fixtures
│   ├── test_auth.py
│   ├── test_budget.py
│   ├── test_expenses.py
│   └── test_income_taxes.py
├── alembic.ini                     # Alembic configuration
├── moneyflow.db                    # SQLite database (created on first run)
├── poetry.lock                     # Locked dependencies
├── pyproject.toml                  # Project config & dependencies
└── README.md                       # This file
```

## Configuration

### Database

The application uses SQLite by default. The database file (`moneyflow.db`) is created automatically on first run in the project root. The database path can be customized via the `DATABASE_URL` environment variable.

### Logging

Logs are written to the `logs/` directory:
- `moneyflow.log` - All application logs
- `errors.log` - Errors only

## Development

### Running Tests

```bash
poetry run pytest tests/
```

### Database Migrations

**Create a new migration:**
```bash
poetry run alembic revision --autogenerate -m "description of changes"
```

**Apply migrations:**
```bash
poetry run alembic upgrade head
```

**Rollback migration:**
```bash
poetry run alembic downgrade -1
```

### Code Style

```bash
poetry run black app/
poetry run isort app/
```

## API Documentation

When the app is running, access the auto-generated API docs at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Limits

- **Saved Scenarios**: Max 5 per type (mortgage, Monte Carlo) per user
- **Net Worth Accounts**: Max 15 assets + 15 liabilities per user

## Security Notes

⚠️ **Important for Production:**

1. Use HTTPS in production (Cloudflare Tunnel handles this)
2. Consider adding rate limiting
3. Use a production-ready database (PostgreSQL recommended)
4. Don't expose port 8000 directly; use a reverse proxy

## Version History

- **v1.2.0** - Monte Carlo simulations, portfolio allocation, CSV bulk upload, ISO/AMT fix, inflation adjustments
- **v1.1.0** - Investment projections, net worth tracking, mortgage calculator improvements
- **v1.0.0** - Initial release with budget, expenses, taxes, and basic tools

## License

MIT License - see LICENSE file for details.
