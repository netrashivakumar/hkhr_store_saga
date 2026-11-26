import os
from urllib.parse import quote

import requests


def get_order_status(order_id):
    """Read-only: ask order-service for the current status of one order."""
    base_url = os.environ.get("ORDER_SERVICE_URL", "http://localhost:5001")
    url = f"{base_url}/api/order/{quote(str(order_id))}"
    try:
        response = requests.get(url, timeout=10)
    except requests.RequestException as error:
        return {"error": f"order-service unreachable: {error}"}
    if response.status_code == 404:
        return {"error": f"order {order_id} not found"}
    if not response.ok:
        return {"error": f"order-service returned HTTP {response.status_code}"}
    try:
        return response.json()
    except ValueError:
        return {"error": "order-service returned a reply that is not JSON"}