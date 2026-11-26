from unittest.mock import Mock, patch

import requests

from tools.orders import get_order_status


def fake_response(status_code=200, payload=None):
    response = Mock()
    response.status_code = status_code
    response.ok = status_code < 400
    response.json.return_value = payload
    return response


@patch("tools.orders.requests.get")
def test_returns_order_data(mock_get):
    mock_get.return_value = fake_response(200, {"order_id": "123", "status": "COMPLETED"})
    assert get_order_status("123") == {"order_id": "123", "status": "COMPLETED"}


@patch("tools.orders.requests.get")
def test_order_not_found(mock_get):
    mock_get.return_value = fake_response(404)
    assert "not found" in get_order_status("999")["error"]


@patch("tools.orders.requests.get")
def test_service_unreachable(mock_get):
    mock_get.side_effect = requests.ConnectionError("refused")
    assert "unreachable" in get_order_status("123")["error"]


@patch("tools.orders.requests.get")
def test_server_error(mock_get):
    mock_get.return_value = fake_response(500)
    assert "HTTP 500" in get_order_status("123")["error"]