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

        self.sources = sources
        self.source_names = [source.name for source in sources]

        self.data_location = self.config.DATA_LOCATION
        self.data_repo = self.__setup_data_repo()

        self._data_fetched = False
        self._data_saved = False

        self.data = {}

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

    @property
    def staged_files(self):
        return [diff.b_path for diff in self.data_repo.index.diff("HEAD")]

    @property
    def modified_not_staged_files(self):
        """Modifed and not staged files"""
        return [diff.b_path for diff in self.data_repo.index.diff(None)]

    def get_data(self):
        """Downloads data for each source into memory"""

        for source in self.sources:
            try:
                self.data.update(source.get_data())
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
                raise ValueError(f"Error with paths, dirname of {abs_path} should be {year_dir}")

            with open(abs_path, mode="w") as fh:
                log.debug(f"Writing data for {project_record.project_id} to {abs_path}")
                fh.write(json.dumps(project_record.data))

        self._data_saved = True

    def any_modified_or_new(self):
        """Checks if there are modified or new projects and returns True or False.

        True if any of these files are found:
         - Modified and staged
         - Modified but not staged
         - Untracked files

        """
        return any([self.data_repo.is_dirty(), self.data_repo.untracked_files, self.staged_files])

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
        for project_path in projects:
            portal_id = ProjectDataRecord.portal_id_from_path(project_path)
            if portal_id in self.data:
                project_record = self.data[portal_id]
            else:
                project_record = ProjectDataRecord(project_path)
            projects_list.append(project_record)

        return projects_list

    def find_unique_orderers(self):
        projects_list = self.get_modified_or_new_projects()
        orderers = set()
        for project in projects_list:
            orderers.add(project.orderer)

        return orderers

    def stage_data_for_project(self, project_record):
        self.data_repo.index.add([project_record.file_name])

    def commit_staged_data(self, message):
        self.data_repo.index.commit(message)


class ProjectDataRecord(object):
    """Class to represent a single project

    Raises ValueError if orderer is not present in data, if data is given
    """

    def __init__(self, relative_path, data=None):
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

        self.orderer = None
        self.data = None

        if data is not None:
            if "orderer" not in data:
                raise ValueError(f"Orderer missing for project_id: {project_id}, NGI node: {node}")

            self.orderer = data["orderer"]

            self.data = data
        else:
            # TODO read from json file here.
            pass

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

    def get_data(self, project_id=None):
        self.data = {}
        if project_id is not None:
            self.get_entry(project_id)
        else:
            close_date = (datetime.datetime.now() - relativedelta(months=6)).strftime("%Y-%m-%d")
            for row in self.statusdb_session.rows(close_date=close_date):
                order_year = "2023"  # TODO - get order year from data
                portal_id = row.value["portal_id"]
                relative_path = f"{self.dirname}/{order_year}/{portal_id}.json"
                self.data[portal_id] = ProjectDataRecord(relative_path, data=row.value)
        return self.data


class SNPSEQProjectData(object):
    """Data class for fetching NGI SNP&SEQ data"""

    def __init__(self, config):
        self.name = "SNP&SEQ"
        self.dirname = "SNPSEQ"

    def get_data(self, project_id=None):
        pass


class UGCProjectData(object):
    """Data class for fetching NGI UGC data"""

    def __init__(self, config):
        self.name = "Uppsala Genome Center"
        self.dirname = "UGC"

    def get_data(self, project_id=None):
        pass