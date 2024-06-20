import os

from unittest import mock
import pytest
import logging

from daily_read import ngi_data, config

####################################################### TESTS #########################################################


def test_create_project_data_master(data_repo_full, get_env_file_path):
    """With existing git repo, test creation of a ProjectDataMaster class"""
    config_values = config.Config(get_env_file_path)
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)

    assert len(data_master.sources) == 3
    assert data_master.source_names == ["NGI Stockholm", "SNP&SEQ", "Uppsala Genome Center"]
    assert data_master._data_saved == False
    assert data_master._data_fetched == False


def test_create_project_data_master_no_commit(data_repo_no_commit, get_env_file_path):
    """With existing git repo but without commits, test creation of a ProjectDataMaster class"""
    config_values = config.Config(get_env_file_path)
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)

    assert len(data_master.sources) == 3
    assert data_master.source_names == ["NGI Stockholm", "SNP&SEQ", "Uppsala Genome Center"]
    assert data_master._data_saved == False
    assert data_master._data_fetched == False

    assert data_master.data_repo.commit().message == "Empty file as a first commit"


def test_modified_or_new_no_commit(data_repo_no_commit, get_env_file_path):
    config_values = config.Config(get_env_file_path)
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)

    assert not data_master.any_modified_or_new()

    modified_or_new = data_master.get_modified_or_new_projects()
    file_names = [project.relative_path for project in modified_or_new]
    assert len(set(file_names)) == 0


def test_modified_or_new(data_repo_full, get_env_file_path):
    config_values = config.Config(get_env_file_path)
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)

    assert data_master.any_modified_or_new()

    modified_or_new = data_master.get_modified_or_new_projects()
    file_names = [project.relative_path for project in modified_or_new]
    assert len(set(file_names)) == 12


def test_modified_or_new_untracked(data_repo_untracked, get_env_file_path):
    config_values = config.Config(get_env_file_path)
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)

    assert data_master.any_modified_or_new()

    modified_or_new = data_master.get_modified_or_new_projects()
    file_names = [project.relative_path for project in modified_or_new]
    assert len(set(file_names)) == 2

    assert "untracked_file" in file_names[0]


def test_modified_or_new_staged(data_repo_new_staged, get_env_file_path):
    config_values = config.Config(get_env_file_path)
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)

    assert data_master.any_modified_or_new()

    modified_or_new = data_master.get_modified_or_new_projects()
    file_names = [project.relative_path for project in modified_or_new]
    assert len(set(file_names)) == 6
    assert any("staged_file" in s for s in file_names)


def test_modified_or_new_modified_not_staged(data_repo_modified_not_staged, get_env_file_path):
    config_values = config.Config(get_env_file_path)
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)

    assert data_master.any_modified_or_new()

    modified_or_new = data_master.get_modified_or_new_projects()
    file_names = [project.relative_path for project in modified_or_new]
    assert len(set(file_names)) == 2

    assert "modified_file" in file_names[0]


def test_modified_or_new_modified_staged(data_repo_modified_staged, get_env_file_path):
    config_values = config.Config(get_env_file_path)
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)

    assert data_master.any_modified_or_new()

    modified_or_new = data_master.get_modified_or_new_projects()
    file_names = [project.relative_path for project in modified_or_new]
    assert len(set(file_names)) == 2

    assert "modified_staged_file" in file_names[0]


def test_modified_or_new_tracked(data_repo_tracked, get_env_file_path):
    config_values = config.Config(get_env_file_path)
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)

    assert not data_master.any_modified_or_new()

    modified_or_new = data_master.get_modified_or_new_projects()
    file_names = [project.relative_path for project in modified_or_new]

    assert len(set(file_names)) == 0


def test_get_unique_orderers(data_repo_full, get_env_file_path):
    """Test getting unique orders in the project data from statusdb"""
    config_values = config.Config(get_env_file_path)
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)
        data_master.get_data()
        orderers = data_master.find_unique_orderers()
        assert orderers == set(["dummy@dummy.se"])


def test_user_list(data_repo_full, tmp_path, mocked_statusdb_conn_rows, get_env_file_path):
    """Test getting and reading users from the user list url"""
    config_values = config.Config(get_env_file_path)
    temp_file = tmp_path / "test_file.txt"
    temp_file.write_text("dummy@dummy.se\ntest@dummy.se")
    config_values.USERS_LIST_LOCATION = temp_file
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)
        assert not set(["dummy@dummy.se", "test@dummy.se"]) ^ set(data_master.user_list)

        data_master.sources[0].statusdb_session.rows.return_value = mocked_statusdb_conn_rows
        data_master.get_data()
        data_master.save_data()
        orderers = data_master.find_unique_orderers()
        assert orderers == set(["dummy@dummy.se", "test@dummy.se"])


def test_save_data_to_disk(data_repo_full, mocked_statusdb_conn_rows, get_env_file_path):
    """Test saving in git repo the data gotten from statusdb"""
    config_values = config.Config(get_env_file_path)
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)
        data_master.sources[0].statusdb_session.rows.return_value = mocked_statusdb_conn_rows
        data_master.get_data()
        data_master.save_data()
        assert os.path.exists(os.path.join(config_values.DATA_LOCATION, "NGIS/2023/NGI123457.json"))
        assert os.path.exists(os.path.join(config_values.DATA_LOCATION, "NGIS/2023/NGI123458.json"))


def test_get_data_with_project(data_repo_full, mocked_statusdb_conn_rows, get_env_file_path):
    """Test getting data for a specific order"""
    config_values = config.Config(get_env_file_path)
    order_id = "NGI123457"
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)
        data_master.sources[0].statusdb_session.rows.return_value = mocked_statusdb_conn_rows
        data_master.get_data(order_id)
        assert len(data_master.data.keys()) == 1
        assert order_id in data_master.data
        assert data_master.data[order_id].internal_id_or_portal_id == "P123457"


def test_get_data_with_project_unknown(data_repo_full, mocked_statusdb_conn_rows, get_env_file_path):
    """Test error thrown when the order specified is not found in statusdb"""
    config_values = config.Config(get_env_file_path)
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)
        data_master.sources[0].statusdb_session.rows.return_value = mocked_statusdb_conn_rows
        with pytest.raises(ValueError, match="Project NGI123 not found in statusdb") as err:
            data_master.get_data("NGI123")


@mock.patch("daily_read.statusdb.StatusDBSession")
def test_data_loc_not_abs(mock_status, get_env_file_path):
    """Test error thrown when given data location is not an absolute path"""
    config_values = config.Config(get_env_file_path)
    config_values.DATA_LOCATION = "tests/test_data_location"
    with pytest.raises(
        ValueError, match=f"Data location is not an absolute path: {config_values.DATA_LOCATION}"
    ) as err:
        ngi_data.ProjectDataMaster(config_values)


@mock.patch("daily_read.statusdb.StatusDBSession")
def test_data_loc_not_dir(mock_status, tmp_path, get_env_file_path):
    """Test error thrown when data location is not a directory"""
    config_values = config.Config(get_env_file_path)
    temp_file = tmp_path / "test_file.txt"
    temp_file.write_text("test")
    config_values.DATA_LOCATION = temp_file
    with pytest.raises(
        ValueError, match=f"Data Location exists but is not a directory: {config_values.DATA_LOCATION}"
    ) as err:
        ngi_data.ProjectDataMaster(config_values)


def test_get_data_with_no_project_dates_closed(data_repo_full, mocked_statusdb_conn_rows, caplog, get_env_file_path):
    """Test log output when no project dates are found in statusdb for a Closed project"""
    from copy import deepcopy

    config_values = config.Config(get_env_file_path)
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)
        data_master.sources[0].statusdb_session.rows.return_value = mocked_statusdb_conn_rows
        proj_no_dates = deepcopy(data_master.sources[0].statusdb_session.rows.return_value[1])
        proj_no_dates.value["proj_dates"] = {}
        proj_no_dates.value["portal_id"] = "NGI123459"
        proj_no_dates.value["project_id"] = "NGI123459"
        proj_no_dates.key[1] = "NGI123459"
        data_master.sources[0].statusdb_session.rows.return_value.append(proj_no_dates)
        with caplog.at_level(logging.INFO):
            data_master.get_data("NGI123459")
            assert len(data_master.data.keys()) == 1
            assert "NGI123459" in data_master.data
            assert "No project dates found for NGI123459, trying to find status from internal_proj_status" in caplog.text
            assert data_master.data["NGI123459"].status == "Closed"

def test_get_data_with_no_project_dates_ongoing(data_repo_full, mocked_statusdb_conn_rows, caplog, get_env_file_path):
    """Test log output when no project dates are found in statusdb for a specific project"""
    from copy import deepcopy

    config_values = config.Config(get_env_file_path)
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)
        data_master.sources[0].statusdb_session.rows.return_value = mocked_statusdb_conn_rows
        proj_no_dates = deepcopy(data_master.sources[0].statusdb_session.rows.return_value[0])
        proj_no_dates.value["proj_dates"] = {}
        proj_no_dates.value["portal_id"] = "NGI123459"
        proj_no_dates.value["project_id"] = "NGI123459"
        proj_no_dates.key[1] = "NGI123459"
        data_master.sources[0].statusdb_session.rows.return_value.append(proj_no_dates)
        with caplog.at_level(logging.INFO):
            data_master.get_data("NGI123459")
            assert len(data_master.data.keys()) == 1
            assert "NGI123459" in data_master.data
            assert "No project dates found for NGI123459, trying to find status from internal_proj_status" in caplog.text
            assert "ERROR! No project dates or incorrect internal_proj_status found for NGI123459, no status set!" in caplog.text

def test_skip_order_with_no_year(data_repo_full, mocked_statusdb_conn_rows, caplog, get_env_file_path):
    """Test that orders with no order year (i.e. with no contract signed) are skipped"""

    config_values = config.Config(get_env_file_path)
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)
        data_master.sources[0].statusdb_session.rows.return_value = mocked_statusdb_conn_rows
        with caplog.at_level(logging.INFO):
            data_master.get_data("NGI123460")
            assert len(data_master.data.keys()) == 0
            assert "NGI123460" not in data_master.data
            assert "No order year found for order NGI123460, skipping it!" in caplog.text


@mock.patch("daily_read.statusdb.StatusDBSession")
def test_no_source_specified(mock_status, get_env_file_path):
    """Test error thrown when no sources are specified"""

    config_values = config.Config(get_env_file_path)
    config_values.FETCH_FROM_NGIS = ""
    config_values.FETCH_FROM_SNPSEQ = ""
    config_values.FETCH_FROM_UGC = ""
    with pytest.raises(ValueError, match="There are no sources specified to fetch data from!") as err:
        ngi_data.ProjectDataMaster(config_values)


def test_commit_staged_data(data_repo_full, mocked_statusdb_conn_rows, get_env_file_path):
    """Test file is staged for commit and committed and then try adding it for staging again"""
    config_values = config.Config(get_env_file_path)
    with mock.patch("daily_read.statusdb.StatusDBSession"):
        data_master = ngi_data.ProjectDataMaster(config_values)
        data_master.sources[0].statusdb_session.rows.return_value = mocked_statusdb_conn_rows
        data_master.get_data()
        data_master.save_data()
        project_rec = data_master.data["NGI123457"]
        assert project_rec.relative_path in data_master.data_repo.untracked_files

        # Test add data for staging
        data_master.stage_data_for_project(project_rec)
        assert project_rec.relative_path in data_master.staged_files
        no_of_staged_files = len(data_master.staged_files)

        # Test commit staged data
        data_master.commit_staged_data("Commit updates")

        # Make sure everything staged is committed and nothing else
        assert len(data_master.staged_files) == 0
        assert len(data_master.data_repo.head.commit.diff("HEAD~1")) == no_of_staged_files

        assert data_master.data_repo.head.commit.message == "Commit updates"
        assert data_master.data_repo.head.commit.diff("HEAD~1")[0].a_path == project_rec.relative_path

        # Test adding something that isn't changed
        data_master.stage_data_for_project(project_rec)
        assert project_rec.relative_path not in data_master.staged_files

        # If nothing is added to stage
        assert len(data_master.data_repo.head.commit.diff()) == 0


# Planned tests #


def test_getting_data():
    # When some source fails
    # When all sources fails
    # When some source is not enabled
    FETCH_FROM_NGIS = os.getenv("DAILY_READ_FETCH_FROM_NGIS")
    FETCH_FROM_SNPSEQ = os.getenv("DAILY_READ_FETCH_FROM_SNPSEQ")
    FETCH_FROM_UGC = os.getenv("DAILY_READ_FETCH_FROM_UGC")
    pass
