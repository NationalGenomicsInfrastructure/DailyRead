import pytest

from daily_read import config, statusdb


def test_no_statusdb_conn(data_repo_full, get_env_file_path):
    """Test error thrown when statusdb conn fails"""
    config_values = config.Config(get_env_file_path)
    # Escape special chars because match uses regex
    display_url_string = (
        rf"https:\/\/{config_values.STHLM_STATUSDB_USERNAME}:\*\*\*\*\*\*\*\*\*@{config_values.STHLM_STATUSDB_URL}"
    )
    with pytest.raises(ConnectionError, match=rf"^Couchdb connection failed for url {display_url_string}") as err:
        statusdb.StatusDBSession(config_values)
