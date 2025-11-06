"""Classes for handling various utility functions"""

from ibmcloudant import CouchDbSessionAuthenticator, cloudant_v1
import logging

log = logging.getLogger(__name__)


class StatusDBSession(object):
    def __init__(self, config):
        display_url_string = f"https://{config.STHLM_STATUSDB_USERNAME}:*********@{config.STHLM_STATUSDB_URL}"
        cloudant = cloudant_v1.CloudantV1(
            authenticator=CouchDbSessionAuthenticator(config.STHLM_STATUSDB_USERNAME, config.STHLM_STATUSDB_PASSWORD)
        )
        cloudant.set_service_url(config.STHLM_STATUSDB_URL)
        self.connection = cloudant
        try:
            self.connection.get_server_information().get_result()
        except Exception as e:
            raise ConnectionError(f"Couchdb connection failed for url {display_url_string} with error {e}")

    def rows(self, close_date=None):
        view = self.connection.post_view(
            db="projects", ddoc="project", view="dailyread_dates", descending=True, end_key=[close_date, "ZZZZ"]
        ).get_result()
        return view["rows"]
