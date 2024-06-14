import base64
import logging
import pytest

from unittest import mock

from daily_read import order_portal, config, ngi_data


def test_get_and_process_orders_open_upload_fail(data_repo_full, mock_project_data_record, caplog, get_env_file_path):
    """Test getting and processing an open order and upload to Order portal failing"""
    orderer = "dummy@dummy.se"
    order_id = "NGI123456"
    config_values = config.Config(get_env_file_path)
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)

    data_master.data = {order_id: mock_project_data_record("open")}

    op = order_portal.OrderPortal(config_values, data_master)
    op.get_orders(orderer=orderer)

    assert op.all_orders[0]["identifier"] == order_id
    modified_orders = op.process_orders(config_values.STATUS_PRIORITY_REV)
    assert modified_orders[orderer]["projects"]["Library QC Finished"][0] == data_master.data[order_id]
    with mock.patch("daily_read.order_portal.requests.post") as mock_post:
        mock_post.return_value.status_code = 404
        uploaded = op.upload_report_to_order_portal(
            "<html>test data</html>", modified_orders[orderer]["projects"]["Library QC Finished"][0], "published"
        )
        assert not uploaded
        assert f"Report not updated for order with project id: {order_id}\nReason: 404" in caplog.text


def test_get_and_process_orders_open_and_upload(data_repo_full, mock_project_data_record, get_env_file_path):
    """Test getting and processing an open order and uploading its Project progress report and uploading the report to the Order portal"""
    orderer = "dummy@dummy.se"
    order_id = "NGI123456"
    config_values = config.Config(get_env_file_path)
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)

    data_master.data = {order_id: mock_project_data_record("open")}

    op = order_portal.OrderPortal(config_values, data_master)
    op.get_orders(orderer=orderer)

    assert op.all_orders[0]["identifier"] == order_id
    modified_orders = op.process_orders(config_values.STATUS_PRIORITY_REV)
    assert modified_orders[orderer]["projects"]["Library QC Finished"][0] == data_master.data[order_id]
    with mock.patch("daily_read.order_portal.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        op.upload_report_to_order_portal(
            "<html>test data</html>", modified_orders[orderer]["projects"]["Library QC Finished"][0], "published"
        )
        url = f"{config_values.ORDER_PORTAL_URL}/api/v1/report"
        indata = dict(
            order=order_id,
            name="Project Progress",
            status="published",
            file=dict(
                data=base64.b64encode("<html>test data</html>".encode()).decode("utf-8"),
                filename="project_progress.html",
                content_type="text/html",
            ),
        )
        mock_post.assert_called_once_with(
            url, headers={"X-OrderPortal-API-key": config_values.ORDER_PORTAL_API_KEY}, json=indata
        )


def test_get_and_process_orders_open_with_report_and_upload(
    data_repo_full, mock_project_data_record, caplog, get_env_file_path
):
    """Test getting, processing an open order with an existing Project progress report and uploading the report to the Order portal"""
    orderer = "dummy@dummy.se"
    order_id = "NGI123453"
    config_values = config.Config(get_env_file_path)
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)

    data_master.data = {order_id: mock_project_data_record("open_with_report")}

    op = order_portal.OrderPortal(config_values, data_master)
    op.get_orders(orderer=orderer)

    assert op.all_orders[3]["identifier"] == order_id
    modified_orders = op.process_orders(config_values.STATUS_PRIORITY_REV)
    assert modified_orders[orderer]["projects"]["Library QC Finished"][0] == data_master.data[order_id]
    with mock.patch("daily_read.order_portal.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        with caplog.at_level(logging.INFO):
            uploaded = op.upload_report_to_order_portal(
                "<html>test data</html>", modified_orders[orderer]["projects"]["Library QC Finished"][0], "published"
            )
            url = f"{config_values.ORDER_PORTAL_URL}/api/v1/report/{op.all_orders[3]['reports'][0]['iuid']}"
            indata = dict(
                order=order_id,
                name="Project Progress",
                status="published",
                file=dict(
                    data=base64.b64encode("<html>test data</html>".encode()).decode("utf-8"),
                    filename="project_progress.html",
                    content_type="text/html",
                ),
            )
            assert uploaded
            mock_post.assert_called_once_with(
                url, headers={"X-OrderPortal-API-key": config_values.ORDER_PORTAL_API_KEY}, json=indata
            )
            assert f"Report updated for order with project id: {order_id}" in caplog.text


def test_get_and_process_orders_open_to_aborted_with_report_and_upload(
    data_repo_full, mock_project_data_record, get_env_file_path
):
    """Test getting, processing an open order with an existing Project progress report and uploading the report to the Order portal"""
    orderer = "dummy@dummy.se"
    order_id = "NGI123461"
    config_values = config.Config(get_env_file_path)
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)

    data_master.data = {order_id: mock_project_data_record("open_to_aborted_with_report")}

    op = order_portal.OrderPortal(config_values, data_master)
    op.get_orders(orderer=orderer)

    assert op.all_orders[4]["identifier"] == order_id
    modified_orders = op.process_orders(config_values.STATUS_PRIORITY_REV)

    assert modified_orders[orderer]["delete_report_for"]["Library QC Finished"][0] == data_master.data[order_id]
    with mock.patch("daily_read.order_portal.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        op.upload_report_to_order_portal(
            "", modified_orders[orderer]["delete_report_for"]["Library QC Finished"][0], "review"
        )
        url = f"{config_values.ORDER_PORTAL_URL}/api/v1/report/{op.all_orders[4]['reports'][0]['iuid']}"
        indata = dict(
            order=order_id,
            name="Project Progress",
            status="review",
        )
        mock_post.assert_called_once_with(
            url, headers={"X-OrderPortal-API-key": config_values.ORDER_PORTAL_API_KEY}, json=indata
        )


def test_get_and_process_orders_closed(data_repo_full, mock_project_data_record, get_env_file_path):
    """Test getting and processing an order closed within the timeframe of Project progress report deletion"""
    orderer = "dummy@dummy.se"
    order_id = "NGI123455"
    config_values = config.Config(get_env_file_path)
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)

    data_master.data = {order_id: mock_project_data_record("closed")}

    op = order_portal.OrderPortal(config_values, data_master)
    op.get_orders(orderer=orderer)

    assert op.all_orders[1]["identifier"] == order_id
    modified_orders = op.process_orders(config_values.STATUS_PRIORITY_REV)
    assert modified_orders[orderer]["delete_report_for"]["All Raw Data Delivered"][0] == data_master.data[order_id]


def test_get_and_process_orders_mult_reports(data_repo_full, mock_project_data_record, get_env_file_path):
    """Test getting and processing orders with multiple Project progress reports"""
    orderer = "dummy@dummy.se"
    order_id = "NGI123454"
    config_values = config.Config(get_env_file_path)
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)

    data_master.data = {order_id: mock_project_data_record("open")}

    op = order_portal.OrderPortal(config_values, data_master)
    op.get_orders(orderer=orderer)

    assert op.all_orders[2]["identifier"] == order_id
    with pytest.raises(
        ValueError, match=f"Multiple reports for Project Progress found in the Order Portal for order {order_id}"
    ) as err:
        op.process_orders(config_values.STATUS_PRIORITY_REV)


def test_base_url_and_api_key_not_set(data_repo_full, mock_project_data_record, get_env_file_path):
    """Test the conditions when environment variables ORDER_PORTAL_URL and ORDER_PORTAL_API_KEY are not set"""
    order_id = "NGI123456"
    config_values = config.Config(get_env_file_path)

    order_portal_url = config_values.ORDER_PORTAL_URL
    api_key = config_values.ORDER_PORTAL_API_KEY
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)

    data_master.data = {order_id: mock_project_data_record("open")}
    config_values.ORDER_PORTAL_URL = None
    config_values.ORDER_PORTAL_API_KEY = None
    with pytest.raises(ValueError, match="environment variable ORDER_PORTAL_URL not set") as err:
        order_portal.OrderPortal(config_values, data_master)
    config_values.ORDER_PORTAL_URL = order_portal_url
    with pytest.raises(ValueError, match="Environment variable ORDER_PORTAL_API_KEY not set") as err:
        order_portal.OrderPortal(config_values, data_master)

    config_values.ORDER_PORTAL_API_KEY = api_key
    config_values.ORDER_PORTAL_URL = order_portal_url.rstrip("/")
    op = order_portal.OrderPortal(config_values, data_master)
    assert op.base_url.endswith("/")
