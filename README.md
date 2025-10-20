# Knowledge Transfer: POC - Sync Google Sheets Data to Shopify Using Temporal

## Part 1: Setting Up Temporal Server (Development Environment)

TheThis section outlines the official setup for running Temporal Server locally using Docker, as per Temporal's documentation and guided by the official video: [Installing Temporal Server on Docker]([[https://www.youtube.com/watch?v=f6N3ZcWHygU](https://www.youtube.com/watch?v=f6N3ZcWHygU)](https://www.youtube.com/watch?v=f6N3ZcWHygU)). For production setups, refer to [Temporal Production Deployment Docs](https://docs.temporal.io/cluster-deployment/overview). Temporal Server provides resiliency, event handling, timers, queues, storage, and a Web UI for monitoring workflows.

### Prerequisites

* Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) for your OS (includes Docker Compose on macOS/Windows).
* If needed, install [Docker Compose](https://docs.docker.com/compose/install/) separately.

### Docker Setup Steps

1.  Clone the official Temporal Docker Compose repository:
    ```bash
    git clone https://github.com/temporalio/docker-compose
    cd docker-compose
    ```
    This repo includes configs for Cassandra (default storage); alternatives like MySQL/PostgreSQL are available in the repo.

2.  Start the services (uses default `docker-compose.yml` with Cassandra):
    ```bash
    docker compose up
    ```
    This launches Temporal services (frontend, history, matching, worker) and Cassandra.

3.  Monitor progress via `docker container ls` or the Docker Desktop dashboard.

4.  Verify setup:
    * Access the **Temporal Web UI** at [http://localhost:8080](http://localhost:8080) (default namespace "default" is pre-installed).
    * The **frontend service** runs on `localhost:7233` for client connections.


### Official Resources:

* **Temporal Docs:** [Self-Hosted Quick Install](https://docs.temporal.io/self-hosted-guide/quick-install)
* **GitHub:** [Temporal Docker Compose](https://github.com/temporalio/docker-compose)
* **Community:** [Temporal Forum](https://community.temporal.io/)

---

## Part 2: POC Explanation - Sheets to Shopify Sync Workflow

This POC demonstrates a resilient data sync from Google Sheets to Shopify using Temporal's Python SDK (v0.30+). It fetches product data (title, price) from a Google Sheet, validates/maps to Shopify format, and syncs in parallel with retries. The workflow handles failures (e.g., simulated API outage) via Temporal's built-in retry and orchestration.

### Architecture Overview

* **Workflow:** `SheetsToShopifyWorkflow` orchestrates activities sequentially (fetch → map) then in parallel (syncs).
* **Activities:**
    * `fetch_from_sheets`: Reads `Sheet1!A2:C` using Google Sheets API v4.
    * `map_and_validate_data`: Transforms to Shopify product schema (title, active status, variants with price); validates via JSON Schema.
    * `sync_to_shopify`: Simulates Shopify API sync (1s delay); retries up to 3x on transient errors (e.g., "crash" in title triggers non-retryable simulation).
* **Client/Worker:** Connects to Temporal frontend (`localhost:7233`), polls task queue `sheets-to-shopify-queue`.
* **Auth/Env:** Google Service Account (`shopify-sync-credentials.json`) for Sheets read access. Set `SPREADSHEET_ID` in `.env`.

### Key Temporal Features Used:

* **Timeouts:** Activity start-to-close (e.g., 2min for fetch).
* **Retries:** Policy with 3s initial interval, max 3 attempts.
* **Parallelism:** `asyncio.gather` for sync tasks.
* **Sandbox:** Restricted runner for safe third-party libs (Google API, JSON Schema).

### Prerequisites for POC

* Temporal Server running (Part 1).
* Python 3.10+ with Temporal SDK: `pip install temporalio google-api-python-client google-auth jsonschema python-dotenv colorlog`.
* Google Service Account JSON and Sheet ID (shareable link with read access).
* Sample Sheet data: Column A=Title, B=Price (e.g., "Product1", "10.00"; include "crash product" for failure demo).

### Running the POC

1.  Save code as `sheets_to_shopify.py`.
2.  Set env: Create `.env` with `SPREADSHEET_ID=your_sheet_id`.
3.  Run: `python sheets_to_shopify.py`
    * Starts worker and triggers workflow (unique ID printed).
4.  Monitors via Web UI: Search namespace "default", queue `sheets-to-shopify-queue`.
5.  Output: "Sync complete. Synced N products." (or error if no data).

### ✅ POC Summary: Sheets to Shopify Sync using Temporal

This POC demonstrates a resilient and parallelized data sync workflow from Google Sheets to Shopify using Temporal’s Python SDK. It fetches product data (title, price), maps and validates it to Shopify’s format, and then syncs each product to Shopify concurrently.

The key highlight is **Temporal's retry mechanism** — if any product’s title contains the word **“crash”**, the `sync_to_shopify` activity is designed to **intentionally fail on the first attempt** to simulate a transient Shopify API outage. Temporal detects this failure and **automatically retries** the activity.

On the **second attempt**, the sync succeeds, showcasing how Temporal can **gracefully handle intermittent errors** without requiring manual intervention.
