import dotenv
import pytest
from unittest import mock
from conftest import mocked_requests_get

from daily_read import order_portal, config, ngi_data

dotenv.load_dotenv()


def test_get_and_process_orders_open_and_upload(data_repo_full, mock_project_data_record):
    """Test getting and processing an open order and uploading its Project progress report"""
    orderer = "dummy@dummy.se"
    order_id = "NGI123456"
    config_values = config.Config()
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)

    data_master.data = {order_id: mock_project_data_record("open")}

    op = order_portal.OrderPortal(config_values, data_master)
    with mock.patch("daily_read.order_portal.OrderPortal._get", side_effect=mocked_requests_get):
        op.get_orders(orderer=orderer)

    assert op.all_orders[0]["identifier"] == order_id
    modified_orders = op.process_orders(config_values.STATUS_PRIORITY_REV)
    assert modified_orders[orderer]["projects"]["Library QC finished"][0] == data_master.data[order_id]
    with mock.patch("daily_read.order_portal.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        op.upload_report_to_order_portal(
            "<html>test data</html>", modified_orders[orderer]["projects"]["Library QC finished"][0], "published"
        )


def test_get_and_process_orders_open_with_report_and_upload(data_repo_full, mock_project_data_record):
    """Test getting and processing an open order with an existing Project progress report"""
    orderer = "dummy@dummy.se"
    order_id = "NGI123453"
    config_values = config.Config()
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)

    data_master.data = {order_id: mock_project_data_record("open")}

    op = order_portal.OrderPortal(config_values, data_master)
    with mock.patch("daily_read.order_portal.OrderPortal._get", side_effect=mocked_requests_get):
        op.get_orders(orderer=orderer)

    assert op.all_orders[3]["identifier"] == order_id
    modified_orders = op.process_orders(config_values.STATUS_PRIORITY_REV)
    assert modified_orders[orderer]["projects"]["Library QC finished"][0] == data_master.data[order_id]
    with mock.patch("daily_read.order_portal.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        op.upload_report_to_order_portal(
            "<html>test data</html>", modified_orders[orderer]["projects"]["Library QC finished"][0], "published"
        )


def test_get_and_process_orders_closed(data_repo_full, mock_project_data_record):
    """Test getting and processing an order closed within the timeframe of Project progress report deletion"""
    orderer = "dummy@dummy.se"
    order_id = "NGI123455"
    config_values = config.Config()
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)

    data_master.data = {order_id: mock_project_data_record("closed")}

    op = order_portal.OrderPortal(config_values, data_master)
    with mock.patch("daily_read.order_portal.OrderPortal._get", side_effect=mocked_requests_get):
        op.get_orders(orderer=orderer)

    assert op.all_orders[1]["identifier"] == order_id
    modified_orders = op.process_orders(config_values.STATUS_PRIORITY_REV)
    assert modified_orders[orderer]["delete_report_for"]["All Raw data Delivered"][0] == data_master.data[order_id]


def test_get_and_process_orders_mult_reports(data_repo_full, mock_project_data_record):
    """Test getting and processing orders with multiple Project progress reports"""
    orderer = "dummy@dummy.se"
    order_id = "NGI123454"
    config_values = config.Config()
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)

    data_master.data = {order_id: mock_project_data_record("open")}

    op = order_portal.OrderPortal(config_values, data_master)
    with mock.patch("daily_read.order_portal.OrderPortal._get", side_effect=mocked_requests_get):
        op.get_orders(orderer=orderer)

    assert op.all_orders[2]["identifier"] == order_id
    with pytest.raises(ValueError) as err:
        op.process_orders(config_values.STATUS_PRIORITY_REV)
        assert err.value == f"Multiple reports for Project Progress found in the Order Portal for order {order_id}"


def test_base_url_and_api_key_not_set(data_repo_full, mock_project_data_record):
    """Test the conditions when environment variables ORDER_PORTAL_URL and ORDER_PORTAL_API_KEY are not set"""
    order_id = "NGI123456"
    config_values = config.Config()

    order_portal_url = config_values.ORDER_PORTAL_URL
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)

    data_master.data = {order_id: mock_project_data_record("open")}
    config_values.ORDER_PORTAL_URL = None
    config_values.ORDER_PORTAL_API_KEY = None
    with pytest.raises(ValueError) as err:
        order_portal.OrderPortal(config_values, data_master)
        assert err.value == "environment variable ORDER_PORTAL_URL not set"
    config_values.ORDER_PORTAL_URL = order_portal_url
    with pytest.raises(ValueError) as err:
        order_portal.OrderPortal(config_values, data_master)
        assert err.value == "Environment variable ORDER_PORTAL_API_KEY not set"
