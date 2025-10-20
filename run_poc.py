import asyncio
from datetime import timedelta
import logging
import os
import requests
import json
import uuid

import colorlog
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from jsonschema import validate

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.exceptions import ApplicationError
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions
from temporalio.common import RetryPolicy

load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
TASK_QUEUE_NAME = "sheets-to-shopify-queue"
SHOPIFY_PRODUCT_SCHEMA = { "type": "object", "properties": { "title": {"type": "string"}, "variants": { "type": "array", "minItems": 1, "items": {"type": "object", "properties": {"price": {"type": "string"}}}, }, }, "required": ["title", "variants"], }

@activity.defn
async def fetch_from_sheets() -> list:
    activity.logger.info("Fetching data from Google Sheets...")
    creds = Credentials.from_service_account_file("shopify-sync-credentials.json", scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A2:C").execute()
    values = result.get("values", [])
    data = [{"title": row[0], "price": row[1]} for row in values if row and len(row) >= 2]
    activity.logger.info(f"Successfully fetched {len(data)} rows from sheet.")
    return data

@activity.defn
async def map_and_validate_data(sheet_data: list) -> list:
    activity.logger.info(f"Mapping and validating {len(sheet_data)} items...")
    products = []
    for item in sheet_data:
        product = {"title": item["title"], "status": "active", "variants": [{"price": str(item["price"])}]}
        validate(instance=product, schema=SHOPIFY_PRODUCT_SCHEMA)
        products.append(product)
    activity.logger.info("Validation complete.")
    return products

@activity.defn
async def sync_to_shopify(product_data: dict) -> str:
    title = product_data['title']
    attempt = activity.info().attempt
    activity.logger.info(f"Syncing product '{title}'... (Attempt: {attempt})")
    
    if "crash" in title.lower() and attempt == 1:
        activity.logger.error(f"Simulating a temporary failure for '{title}' on attempt {attempt}!")
        raise ApplicationError("Simulating a temporary API outage", non_retryable=False)
    
    await asyncio.sleep(1)
    activity.logger.info(f"Successfully synced '{title}' on attempt {attempt}!")
    return title

@workflow.defn
class SheetsToShopifyWorkflow:
    @workflow.run
    async def run(self) -> str:
        sheet_data = await workflow.execute_activity(fetch_from_sheets, start_to_close_timeout=timedelta(minutes=2))
        if not sheet_data: return "Sync skipped: No data found."
        mapped_data = await workflow.execute_activity(map_and_validate_data, sheet_data, start_to_close_timeout=timedelta(seconds=30))
        sync_tasks = []
        for product in mapped_data:
            task = workflow.execute_activity(
                sync_to_shopify,
                product,
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(initial_interval=timedelta(seconds=3), maximum_attempts=3),
            )
            sync_tasks.append(task)
        await asyncio.gather(*sync_tasks)
        return f"Sync complete. Synced {len(sync_tasks)} products."

def setup_logging():
    handler = colorlog.StreamHandler()
    formatter = colorlog.ColoredFormatter(
        '%(log_color)s%(levelname)-8s%(reset)s %(message)s',
        log_colors={
            'DEBUG': 'cyan', 'INFO': 'green', 'WARNING': 'yellow', 'ERROR': 'red', 'CRITICAL': 'red,bg_white',
        }
    )
    handler.setFormatter(formatter)
    logger = logging.getLogger()
    if not logger.handlers:
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)

async def main():
    client = await Client.connect("localhost:7233")
    restrictions = SandboxRestrictions.default.with_passthrough_modules("googleapiclient", "google", "jsonschema", "requests", "urllib3")
    worker = Worker(
        client,
        task_queue=TASK_QUEUE_NAME,
        workflows=[SheetsToShopifyWorkflow],
        activities=[fetch_from_sheets, map_and_validate_data, sync_to_shopify],
        workflow_runner=SandboxedWorkflowRunner(restrictions=restrictions),
    )
    async def run_and_trigger():
        handle = await client.start_workflow(
            SheetsToShopifyWorkflow.run, id=f"sheets-to-shopify-demo-{uuid.uuid4()}", task_queue=TASK_QUEUE_NAME
        )
        print(f"Workflow started with ID: {handle.id}")
        result = await handle.result()
        print(f"\nWorkflow finished. Result: {result}")
        await worker.shutdown()
    await asyncio.gather(worker.run(), run_and_trigger())

if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())