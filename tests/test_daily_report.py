import datetime
import os

from unittest import mock

from daily_read import daily_report, config, ngi_data, order_portal


def test_write_report_to_out_dir(data_repo_full, mock_project_data_record, create_report_path, get_env_file_path):
    """Test existence of html report when provided with out_dir"""
    orderer = "dummy@dummy.se"
    order_id = "NGI123456"
    config_values = config.Config(env_file_path=get_env_file_path)
    daily_rep = daily_report.DailyReport()
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)

    data_master.data = {order_id: mock_project_data_record("open")}

    op = order_portal.OrderPortal(config_values, data_master)
    op.get_orders(orderer=orderer)

    assert op.all_orders[0]["identifier"] == order_id
    modified_orders = op.process_orders(config_values.STATUS_PRIORITY_REV)
    assert modified_orders[orderer]["projects"]["Library QC Finished"][0] == data_master.data[order_id]
    pull_date = f"{datetime.datetime.strptime(modified_orders[orderer]['pull_date'], '%Y-%m-%d %H:%M:%S.%f').date()}"
    report_path = os.path.join(config_values.REPORTS_LOCATION, f"{orderer.split('@')[0]}_{pull_date}.html")

    report = daily_rep.populate_and_write_report(
        orderer,
        modified_orders[orderer],
        config_values.STATUS_PRIORITY,
        out_dir=config_values.REPORTS_LOCATION,
    )

    assert os.path.isfile(report_path)
    # TODO: compare html outputs maybe?
