import copy
import couchdb
import git
import json
import os
import pytest

from datetime import date, timedelta

from daily_read import ngi_data, config, order_portal

dummy_order_open = {
    "orderer": "dummy@dummy.se",
    "project_dates": {
        "2023-06-15": ["Samples Received"],
        "2023-06-28": ["Reception Control Finished", "Library QC Finished"],
    },
    "internal_id": "P123456",
    "internal_name": "D.Dummysson_23_01",
    "internal_proj_status": "Ongoing",
}

dummy_order_closed = {
    "orderer": "dummy@dummy.se",
    "project_dates": {
        "2023-06-15": ["Samples Received"],
        "2023-06-28": ["Reception Control Finished", "Library QC Finished"],
        "2023-07-28": ["All Samples Sequenced"],
        "2023-07-29": ["All Raw Data Delivered"],
    },
    "internal_id": "P123455",
    "internal_name": "D.Dummysson_23_02",
    "internal_proj_status": "Ongoing",
}

order_portal_resp_order_processing = {
    "identifier": "NGI123456",
    "title": "Test run with nano",
    "iuid": "2b896d9fb38349d0b04943f345efq123",
    "form": {
        "iuid": "63c21673c16c4034120277d809dcd577",
        "title": "Illumina Sequencing",
        "version": "2023-09-01",
        "links": {"api": {"href": "https://orderportal.example.com/orders/form/63c21673c16c4034120277d809dcd577"}},
    },
    "owner": {
        "email": "dummy@dummy.se",
        "name": "Dummysson, Dummy",
        "links": {
            "api": {"href": "https://orderportal.example.com/orders/api/v1/account/dummy%40dummy.se"},
            "display": {"href": "https://orderportal.example.com/orders/account/dummy%40dummy.se"},
        },
    },
    "status": "processing",
    "reports": [],
    "history": {
        "preparation": "2023-12-06",
        "submitted": "2023-12-06",
        "review": "2023-12-06",
        "accepted": "2023-12-06",
        "rejected": None,
        "processing": "2023-12-20",
        "aborted": None,
        "closed": None,
        "undefined": None,
    },
    "tags": [],
    "modified": "2023-12-20T02:30:49.541Z",
    "created": "2023-12-06T10:15:11.081Z",
    "links": {
        "api": {"href": "https://orderportal.example.com/orders/api/v1/order/NGI123456"},
        "display": {"href": "https://orderportal.example.com/orders/order/NGI123456"},
    },
    "fields": {
        "assigned_node": "Stockholm",
        "project_ngi_identifier": "P123456",
        "project_ngi_name": "D.Dummysson_23_01",
    },
}

order_portal_resp_order_processing_single_report = copy.deepcopy(order_portal_resp_order_processing)
order_portal_resp_order_processing_single_report["identifier"] = "NGI123453"
order_portal_resp_order_processing_single_report["reports"] = [
    {
        "iuid": "c5ee942",
        "name": "Project Progress",
        "filename": "project_progress.html",
        "status": "published",
        "modified": "2023-12-28T15:09:18.732Z",
        "links": {
            "api": {"href": "https://orderportal.example.com/orders/api/v1/report/c5ee942"},
            "file": {"href": "https://orderportal.example.com/orders/report/c5ee942"},
        },
    },
]

order_portal_resp_order_processing_mult_reports = copy.deepcopy(order_portal_resp_order_processing)

order_portal_resp_order_processing_mult_reports["identifier"] = "NGI123454"
order_portal_resp_order_processing_mult_reports["reports"] = [
    {
        "iuid": "c5ee942",
        "name": "Project Progress",
        "filename": "project_progress.html",
        "status": "published",
        "modified": "2023-12-28T15:09:18.732Z",
        "links": {
            "api": {"href": "https://orderportal.example.com/orders/api/v1/report/c5ee942"},
            "file": {"href": "https://orderportal.example.com/orders/report/c5ee942"},
        },
    },
    {
        "iuid": "c5ee941",
        "name": "Project Progress",
        "filename": "project_progress.html",
        "status": "published",
        "modified": "2023-12-28T15:09:18.732Z",
        "links": {
            "api": {"href": "https://orderportal.example.com/orders/api/v1/report/c5ee941"},
            "file": {"href": "https://orderportal.example.com/orders/report/c5ee941"},
        },
    },
]

order_portal_resp_order_processing_to_aborted = copy.deepcopy(order_portal_resp_order_processing)
order_portal_resp_order_processing_to_aborted["identifier"] = "NGI123461"
order_portal_resp_order_processing_to_aborted["reports"] = [
    {
        "iuid": "c5ee943",
        "name": "Project Progress",
        "filename": "project_progress.html",
        "status": "published",
        "modified": "2024-01-15T15:09:18.732Z",
        "links": {
            "api": {"href": "https://orderportal.example.com/orders/api/v1/report/c5ee943"},
            "file": {"href": "https://orderportal.example.com/orders/report/c5ee943"},
        },
    },
]
order_portal_resp_order_processing_to_aborted["status"] = "Rejected"
order_portal_resp_order_processing_to_aborted["history"]["rejected"] = "2024-01-16"
order_portal_resp_order_processing_to_aborted["fields"]["project_ngi_identifier"] = "P123461"
order_portal_resp_order_processing_to_aborted["fields"]["project_ngi_name"] = "D.Dummysson_23_07"

order_portal_resp_order_closed = {
    "identifier": "NGI123455",
    "title": "Test run with closed",
    "iuid": "2b896d9fb38349d0b04943f345123123",
    "form": {
        "iuid": "12321673c16c4034120277d809dcd577",
        "title": "Illumina Sequencing",
        "version": "2023-09-01",
        "links": {"api": {"href": "https://orderportal.example.com/orders/form/12321673c16c4034120277d809dcd577"}},
    },
    "owner": {
        "email": "dummy@dummy.se",
        "name": "Dummysson, Dummy",
        "links": {
            "api": {"href": "https://orderportal.example.com/orders/api/v1/account/dummy%40dummy.se"},
            "display": {"href": "https://orderportal.example.com/orders/account/dummy%40dummy.se"},
        },
    },
    "status": "closed",
    "reports": [],
    "history": {
        "preparation": "2023-07-06",
        "submitted": "2023-07-06",
        "review": "2023-07-06",
        "accepted": "2023-07-06",
        "rejected": None,
        "processing": "2023-07-20",
        "aborted": None,
        "closed": (date.today() - timedelta(days=31)).strftime("%Y-%m-%d"),
        "undefined": None,
    },
    "tags": [],
    "modified": "2023-12-20T02:30:49.541Z",
    "created": "2023-07-06T10:15:11.081Z",
    "links": {
        "api": {"href": "https://orderportal.example.com/orders/api/v1/order/NGI123455"},
        "display": {"href": "https://orderportal.example.com/orders/order/NGI123455"},
    },
    "fields": {
        "assigned_node": "Stockholm",
        "project_ngi_identifier": "P123455",
        "project_ngi_name": "D.Dummysson_23_02",
    },
}


def _create_all_files(file_list, data_location):
    """Helper method to create files in file_list inside data_location"""
    for file_relpath in file_list:
        file_path = os.path.join(data_location, file_relpath)
        os.makedirs(os.path.split(file_path)[0], exist_ok=True)
        with open(file_path, "w") as fh:
            fh.write(json.dumps(dummy_order_open))


####################################################### FIXTURES #########################################################


@pytest.fixture
def data_repo(tmp_path):
    data_location = os.path.join(tmp_path, "git_repo")
    os.environ["DAILY_READ_DATA_LOCATION"] = str(data_location)
    os.mkdir(data_location)
    data_repo = git.Repo.init(data_location)

    # Need an empty commit to be able to do "repo.index.diff("HEAD")"
    new_file_path = os.path.join(data_location, ".empty")
    open(new_file_path, "a").close()
    data_repo.index.add([new_file_path])
    data_repo.index.commit("Empty file from tests as a first commit")

    return data_repo


@pytest.fixture
def data_repo_no_commit(tmp_path):
    data_location = os.path.join(tmp_path, "git_repo")
    os.environ["DAILY_READ_DATA_LOCATION"] = str(data_location)
    os.mkdir(data_location)
    data_repo = git.Repo.init(data_location)
    return data_repo


@pytest.fixture
def data_repo_untracked(data_repo):
    """Adds two untracked files."""
    untracked_files = ["NGIS/2023/untracked_file1.json", "UGC/2022/untracked_file2.json"]
    _create_all_files(untracked_files, data_repo.working_dir)

    return data_repo


@pytest.fixture
def data_repo_new_staged(data_repo):
    """Adds two new files to the index to be committed."""
    staged_files = [
        "NGIS/2023/staged_file1.json",
        "UGC/2023/staged_file2.json",
        "NGIS/2023/staged_file2.json",
        "NGIS/2023/P123456.json",
        "NGIS/2023/P123453.json",
        "NGIS/2023/P123461.json",
    ]
    _create_all_files(staged_files, data_repo.working_dir)
    data_repo.index.add(staged_files)

    return data_repo


@pytest.fixture
def data_repo_modified_not_staged(data_repo):
    """Adds two previously committed files with new modifications that is not staged to be committed."""
    modified_not_staged_files = ["SNPSEQ/2023/modified_file1.json", "NGIS/2021/modified_file2.json"]
    _create_all_files(modified_not_staged_files, data_repo.working_dir)
    data_repo.index.add(modified_not_staged_files)
    # Check that nothing else is committed by mistake
    assert len(data_repo.index.diff("HEAD")) == len(modified_not_staged_files)
    data_repo.index.commit("Commit Message")

    for file_relpath in modified_not_staged_files:
        file_path = os.path.join(data_repo.working_dir, file_relpath)
        with open(file_path) as fh:
            json_list = json.load(fh)
        json_list["project_dates"].update({"2023-07-09": ["All Samples Sequenced"]})
        with open(file_path, "w") as fh:
            fh.write(json.dumps(json_list))

    return data_repo


@pytest.fixture
def data_repo_modified_staged(data_repo):
    """Adds two previously committed files with new modifications that is staged to be committed."""
    modified_not_staged_files = ["SNPSEQ/2022/modified_staged_file1.json", "NGIS/2020/modified_staged_file2.json"]
    _create_all_files(modified_not_staged_files, data_repo.working_dir)
    data_repo.index.add(modified_not_staged_files)
    data_repo.index.commit("Commit Message")

    for file_relpath in modified_not_staged_files:
        file_path = os.path.join(data_repo.working_dir, file_relpath)
        with open(file_path) as fh:
            json_list = json.load(fh)
        json_list["project_dates"].update({"2023-07-09": ["All Samples Sequenced"]})
        with open(file_path, "w") as fh:
            fh.write(json.dumps(json_list))

    return data_repo


@pytest.fixture
def data_repo_tracked(data_repo):
    """Adds three tracked files to the repository"""
    tracked_files = ["SNPSEQ/2022/tracked_file1.json", "UGC/2022/tracked_file2.json", "NGIS/2021/tracked_file3.json"]
    _create_all_files(tracked_files, data_repo.working_dir)
    data_repo.index.add(tracked_files)
    # Make sure nothing else is committed by mistake
    assert len(data_repo.index.diff("HEAD")) == len(tracked_files)
    data_repo.index.commit("Commit Message")

    return data_repo


@pytest.fixture
def data_repo_full(
    data_repo_untracked,
    data_repo_modified_not_staged,
    data_repo_tracked,
    data_repo_modified_staged,
    data_repo_new_staged,
):
    """Represents a data repository with all five different kinds of files.

    Note that the order of the fixtures matter since commits cannot be made if staged files exist.
    So files are staged in the final fixtures only.
    """
    return data_repo_new_staged


@pytest.fixture
def mock_project_data_record():
    def _method(status):
        config_values = config.Config(env_file_path=".test.env")
        if status == "open":
            mock_record = ngi_data.ProjectDataRecord(
                "NGIS/2023/NGI123456.json",
                dummy_order_open["orderer"],
                dummy_order_open["project_dates"],
                dummy_order_open["internal_id"],
                dummy_order_open["internal_name"],
                config_values.STATUS_PRIORITY_REV,
                dummy_order_open["internal_proj_status"],
            )
        if status == "closed":
            mock_record = ngi_data.ProjectDataRecord(
                "NGIS/2023/staged_file2.json",
                dummy_order_closed["orderer"],
                dummy_order_closed["project_dates"],
                dummy_order_closed["internal_id"],
                dummy_order_closed["internal_name"],
                config_values.STATUS_PRIORITY_REV,
                dummy_order_closed["internal_proj_status"],
            )
        if status == "open_with_report":
            mock_record = ngi_data.ProjectDataRecord(
                "NGIS/2023/NGI123453.json",
                dummy_order_open["orderer"],
                dummy_order_open["project_dates"],
                dummy_order_open["internal_id"],
                dummy_order_open["internal_name"],
                config_values.STATUS_PRIORITY_REV,
                dummy_order_open["internal_proj_status"],
            )
        if status == "open_to_aborted_with_report":
            mock_record = ngi_data.ProjectDataRecord(
                "NGIS/2023/NGI123461.json",
                dummy_order_open["orderer"],
                dummy_order_open["project_dates"],
                "P123461",
                "D.Dummysson_23_07",
                config_values.STATUS_PRIORITY_REV,
                "Aborted",
            )
        return mock_record

    return _method


@pytest.fixture
def create_report_path(tmp_path):
    os.environ["DAILY_READ_REPORTS_LOCATION"] = os.path.join(tmp_path, os.environ["DAILY_READ_REPORTS_LOCATION"])
    os.makedirs(os.environ["DAILY_READ_REPORTS_LOCATION"])
    return create_report_path


@pytest.fixture(autouse=True)
def mocked_requests_get(monkeypatch):
    """order_portal.OrderPortal._get() mocked to return {'items': [order list]}."""

    class MockResponse:
        def json(self):
            return {
                "items": [
                    order_portal_resp_order_processing,
                    order_portal_resp_order_closed,
                    order_portal_resp_order_processing_mult_reports,
                    order_portal_resp_order_processing_single_report,
                    order_portal_resp_order_processing_to_aborted,
                ]
            }

    def mock_get(*args, **kwargs):
        return MockResponse()

    monkeypatch.setattr(order_portal.OrderPortal, "_get", mock_get)


@pytest.fixture
def mocked_statusdb_conn_rows():
    """To substitute return value for the daily_read.statusdb.StatusDBSession.rows method"""
    row1 = couchdb.client.Row(
        id="b77d4f",
        key=["XXXX-XX-XX", "P123457"],
        value={
            "orderer": "dummy@dummy.se",
            "portal_id": "NGI123457",
            "order_year": "2023",
            "project_id": "P123457",
            "project_name": "D.Dummysson_23_03",
            "proj_dates": dummy_order_open["project_dates"],
            "status": "Ongoing",
        },
    )
    row2 = couchdb.client.Row(
        id="b77d4g",
        key=[(date.today() - timedelta(days=31)).strftime("%Y-%m-%d"), "P123458"],
        value={
            "orderer": "test@dummy.se",
            "portal_id": "NGI123458",
            "order_year": "2023",
            "project_id": "P123458",
            "project_name": "T.Dummysson_23_04",
            "proj_dates": dummy_order_closed["project_dates"],
            "status": "Closed",
        },
    )
    row3 = couchdb.client.Row(
        id="b77d4d",
        key=["XXXX-XX-XX", "P123460"],
        value={
            "orderer": "dummy@dummy.se",
            "portal_id": "NGI123460",
            "order_year": "",
            "project_id": "P123460",
            "project_name": "D.Dummysson_23_06",
            "proj_dates": {},
            "status": "Reception control",
        },
    )
    return [row1, row2, row3]


@pytest.fixture(autouse=True)
def get_env_file_path():
    """returns the test env file path"""

    return ".test.env"
