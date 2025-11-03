import datetime
import json
import logging
import os

from dateutil.relativedelta import relativedelta
import git
import gitdb

from daily_read import statusdb

log = logging.getLogger(__name__)


class ProjectDataMaster(object):
    def __init__(self, config):
        self.config = config
        sources = []
        if config.FETCH_FROM_NGIS:
            sources.append(StockholmProjectData(config))
        if config.FETCH_FROM_SNPSEQ:
            sources.append(SNPSEQProjectData(config))
        if config.FETCH_FROM_UGC:
            sources.append(UGCProjectData(config))

        if len(sources) == 0:
            raise ValueError("There are no sources specified to fetch data from!")

        self.sources = sources
        self.source_names = [source.name for source in sources]

        self.data_location = self.config.DATA_LOCATION
        self.data_repo = self.__setup_data_repo()

        self._data_fetched = False
        self._data_saved = False

        self.data = {}  # Key: Portal_id, Value: ProjectDataRecord

        self.user_list = self._read_user_list(config.USERS_LIST_LOCATION)

    def __setup_data_repo(self):
        # Safety check of path
        if not os.path.isabs(self.data_location):
            raise ValueError(f"Data location is not an absolute path: {self.data_location}")

        if os.path.exists(self.data_location) and not os.path.isdir(self.data_location):
            raise ValueError(f"Data Location exists but is not a directory: {self.data_location}")

        # This seems to work with both existing git repos, empty directories
        # and non-existing directories
        data_repo = git.Repo.init(self.data_location)

        # Make sure there is at least 1 commit (ref HEAD exists)
        try:
            data_repo.index.diff("HEAD")
        except gitdb.exc.BadName as e:
            # No commit exists yet
            # Make sure no files are staged to be committed
            if any([data_repo.is_dirty(), data_repo.untracked_files]):
                raise ValueError(
                    f"Data location has no commits but has modifications, "
                    "please commit those or use an empty directory as the data location"
                )

            # Create empty file to include in the commit
            new_file_path = os.path.join(self.data_location, ".empty")
            open(new_file_path, "a").close()
            data_repo.index.add([new_file_path])
            data_repo.index.commit("Empty file as a first commit")

        return data_repo

    def _read_user_list(self, users_list_location):
        users_list = []
        if users_list_location:
            if os.path.exists(users_list_location):
                with open(users_list_location, "r") as fh:
                    users_list = [line.strip() for line in fh]

        return users_list

    @property
    def staged_files(self):
        return [diff.b_path for diff in self.data_repo.index.diff("HEAD")]

    @property
    def modified_not_staged_files(self):
        """Modifed and not staged files"""
        return [diff.b_path for diff in self.data_repo.index.diff(None)]

    def get_data(self, project_id=None, source_name=None, close_date=None):
        """Downloads data for each source into memory"""

        for source in self.sources:
            if source_name is not None and source.name != source_name:
                continue
            try:
                self.data.update(source.get_data(project_id=project_id, close_date=close_date))
            except Exception as e:
                log.error(f"Failed to fetch data from {source.name}")
                log.exception(e)
                raise

        self._data_fetched = True

    def save_data(self):
        """Saves data to disk, where each project is located in its own file, e.g.:

        DATA_LOCATION/ngi_stockholm/2023/NGI09442.json

        """
        assert self._data_fetched

        if self.any_modified_or_new():
            log.info("Changes for projects detected from previous run!")
            for project_record in self.get_modified_or_new_projects():
                log.info(f"{project_record.project_id} from {project_record.ngi_node} had changes not yet reported.")

        for portal_id, project_record in self.data.items():
            source_year_dir = os.path.join(self.data_location, project_record.relative_dirpath)

            # Save individual projects to json files
            # Safety check on directory
            os.makedirs(source_year_dir, exist_ok=True)

            if not os.path.isdir(source_year_dir):
                raise ValueError(
                    f"Failed to use data directory {source_year_dir} for download, path exists but is not a directory."
                )

            abs_path = os.path.join(self.data_location, project_record.relative_path)
            if os.path.dirname(abs_path) != source_year_dir:  # This should really never happen
                raise ValueError(f"Error with paths, dirname of {abs_path} should be {source_year_dir}")

            with open(abs_path, mode="w") as fh:
                log.debug(f"Writing data for {project_record.project_id} to {abs_path}")
                fh.write(json.dumps(project_record.data_for_file()))

        self._data_saved = True

    def any_modified_or_new(self):
        """Checks if there are modified or new projects and returns True or False.

        True if any of these files are found:
         - Modified and staged
         - Modified but not staged
         - Untracked files

        """
        return any(
            [
                self.data_repo.is_dirty(),
                self.data_repo.untracked_files,
                self.staged_files,
            ]
        )

    def get_modified_or_new_projects(self):
        """Returns files which are either:
        - Modified and staged
        - Modified but not staged
        - Untracked files
        """
        projects = set()
        if not self.any_modified_or_new():
            return []

        # Modified and staged files
        projects.update(self.staged_files)

        # Modified and not staged files
        projects.update(self.modified_not_staged_files)

        # Modified untracked files
        projects.update(self.data_repo.untracked_files)

        projects_list = []

        for project_relpath in projects:
            portal_id = ProjectDataRecord.portal_id_from_path(project_relpath)
            if portal_id in self.data:
                project_record = self.data[portal_id]
            else:
                log.info(f"Data not fetched this time for {portal_id}, read data from file")
                project_path = os.path.join(self.data_location, project_relpath)

                (
                    orderer,
                    project_dates,
                    internal_id,
                    internal_name,
                    internal_proj_status,
                ) = ProjectDataRecord.data_from_file(project_path)
                project_record = ProjectDataRecord(
                    project_path,
                    orderer,
                    project_dates,
                    internal_id,
                    internal_name,
                    self.config.STATUS_PRIORITY_REV,
                    internal_proj_status,
                )
            projects_list.append(project_record)

        return projects_list

    def find_unique_orderers(self):
        projects_list = self.get_modified_or_new_projects()
        orderers = set()
        for project in projects_list:
            if self.user_list:
                if project.orderer in self.user_list:
                    orderers.add(project.orderer)
            else:
                orderers.add(project.orderer)

        return orderers

    def stage_data_for_project(self, project_record):
        self.data_repo.index.add([project_record.relative_path])

    def commit_staged_data(self, message):
        self.data_repo.index.commit(message)


class ProjectDataRecord(object):
    """Class to represent a single project

    Raises ValueError if orderer is not present in data, if data is given
    """

    def __init__(
        self,
        relative_path,
        orderer,
        project_dates,
        internal_id=None,
        internal_name=None,
        dates_prio=None,
        internal_proj_status=None,
    ):
        """relative_path: e.g. "NGIS/2023/NGI0002313.json" """
        node_year, file_name = os.path.split(relative_path)
        node, year = os.path.split(node_year)
        # Removes the last extension, we'll assume we only have one (.json)
        project_id = os.path.splitext(file_name)[0]

        self.ngi_node = node
        self.year = year
        self.file_name = file_name
        self.relative_path = relative_path
        self.relative_dirpath = node_year
        self.project_id = project_id
        self.report_iuid = None

        self.orderer = orderer
        self.project_dates = project_dates

        self.internal_id = internal_id
        self.internal_name = internal_name
        self.events = []  # List of tuples (date_value, (date_status, <ProjectDataRecord>))
        self.status = None
        self.internal_proj_status = internal_proj_status

        for date_value, date_statuses in project_dates.items():
            for date_status in date_statuses:
                self.events.append((date_value, (date_status, self)))

        # Figure out project status from the latest status(es)

        if project_dates:
            latest_date, latest_statuses = sorted(project_dates.items(), reverse=True)[0]

            # If multiple statuses for the same date, choose the one with highest prio
            if len(latest_statuses) > 1:
                self.status = sorted(latest_statuses, key=lambda s: dates_prio[s], reverse=True)[0]
            else:
                self.status = latest_statuses[0]
        else:
            log.info(f"No project dates found for {project_id}, trying to find status from internal_proj_status")
            if internal_proj_status in ["Pending", "Aborted", "Closed"]:
                self.status = internal_proj_status
            else:
                log.error(
                    f"ERROR! No project dates or incorrect internal_proj_status found for {project_id}, no status set!"
                )

    @property
    def internal_id_or_portal_id(self):
        """Returns internal id if set, otherwise portal id"""
        if self.internal_id:
            return self.internal_id
        return self.project_id

    @property
    def internal_name_or_portal_id(self):
        """Returns internal name if set, otherwise portal id"""
        if self.internal_name:
            return self.internal_name
        return self.project_id

    def data_for_file(self):
        """Returns data in a dictionary suitable for saving as json"""
        return {
            "orderer": self.orderer,
            "project_dates": self.project_dates,
            "internal_id": self.internal_id,
            "internal_name": self.internal_name,
            "internal_proj_status": self.internal_proj_status,
        }

    def data_from_file(relative_path):
        """Returns orderer and project dates from info in json file"""
        with open(relative_path, "r") as fh:
            data = json.load(fh)

        internal_id = None
        if "internal_id" in data:
            internal_id = data["internal_id"]

        internal_name = None
        if "internal_name" in data:
            internal_name = data["internal_name"]

        internal_proj_status = None
        if "internal_proj_status" in data:
            internal_proj_status = data["internal_proj_status"]

        return data["orderer"], data["project_dates"], internal_id, internal_name, internal_proj_status

    def portal_id_from_path(path):
        """Class method to parse out project portal id (e.g. filename without extension) from given path"""
        _, file_name = os.path.split(path)
        portal_id = os.path.splitext(file_name)[0]
        return portal_id


class StockholmProjectData(object):
    """Data class for fetching NGI Stockholm data"""

    def __init__(self, config):
        self.name = "NGI Stockholm"
        self.dirname = "NGIS"
        self.statusdb_session = statusdb.StatusDBSession(config)
        self.dates_prio = config.STATUS_PRIORITY_REV

    def get_data(self, project_id=None, close_date=None):
        """Fetch data from Stockholm StatusDB.

        If close_date is not given, defaults to 6 months ago.
        Close date should be a relative delta.
        """
        self.data = {}
        if project_id is not None:
            self.get_entry(project_id)
        else:
            if close_date is None:
                close_date = (datetime.datetime.now() - relativedelta(months=6)).strftime("%Y-%m-%d")
            for row in self.statusdb_session.rows(close_date=close_date):
                if "portal_id" not in row["value"]:
                    # Probably a project with no associated order(e.g legacy ESCG), log it and skip
                    log.error(f"No portal_id found in row {row['id']}, skipping it!")
                    continue
                portal_id = row["value"]["portal_id"]
                order_year = row["value"]["order_year"]
                # Should not happen, upstream manual entry error if it happens
                if not order_year:
                    log.error(f"No order year found for order {portal_id}, skipping it!")
                    continue
                relative_path = f"{self.dirname}/{order_year}/{portal_id}.json"

                project_dates = row["value"]["proj_dates"]
                orderer = row["value"]["orderer"]
                internal_id = row["value"]["project_id"]
                internal_name = row["value"]["project_name"]
                internal_proj_status = row["value"]["status"]

                self.data[portal_id] = ProjectDataRecord(
                    relative_path,
                    orderer,
                    project_dates,
                    internal_id,
                    internal_name,
                    self.dates_prio,
                    internal_proj_status,
                )

        return self.data

    def get_entry(self, project_id):
        """Fetches data for a single project from statusdb"""
        close_date = (datetime.datetime.now() - relativedelta(months=6)).strftime("%Y-%m-%d")
        rows = self.statusdb_session.rows(close_date=close_date)
        for row in rows:
            if row["value"]["portal_id"] == project_id:
                portal_id = row["value"]["portal_id"]
                order_year = row["value"]["order_year"]
                # Should not happen, upstream manual entry error if it happens
                if not order_year:
                    log.error(f"No order year found for order {portal_id}, skipping it!")
                    return
                relative_path = f"{self.dirname}/{order_year}/{portal_id}.json"

                project_dates = row["value"]["proj_dates"]
                orderer = row["value"]["orderer"]
                internal_id = row["value"]["project_id"]
                internal_name = row["value"]["project_name"]
                internal_proj_status = row["value"]["status"]

                self.data[portal_id] = ProjectDataRecord(
                    relative_path,
                    orderer,
                    project_dates,
                    internal_id,
                    internal_name,
                    self.dates_prio,
                    internal_proj_status,
                )
                return
        raise ValueError(f"Project {project_id} not found in statusdb")


class SNPSEQProjectData(object):
    """Data class for fetching NGI SNP&SEQ data"""

    def __init__(self, config):
        self.name = "SNP&SEQ"
        self.dirname = "SNPSEQ"

    def get_data(self, project_id=None, close_date=None):
        return {}


class UGCProjectData(object):
    """Data class for fetching NGI UGC data"""

    def __init__(self, config):
        self.name = "Uppsala Genome Center"
        self.dirname = "UGC"

    def get_data(self, project_id=None, close_date=None):
        return {}
