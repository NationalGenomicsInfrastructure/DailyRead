#!/usr/bin/env python
"""The Daily Read, a utility to generate and upload automatic progress reports for NGI Sweden."""

# Standard
import datetime
import logging
import logging.handlers
import os
import sys

# Installed
import click
from dateutil.relativedelta import relativedelta
from rich.logging import RichHandler

# Own
import daily_read.config
import daily_read.daily_report
import daily_read.ngi_data
import daily_read.order_portal
import daily_read.utils


@click.group(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option("--env_file_path", type=click.Path())
@click.pass_context
def daily_read_cli(ctx, env_file_path):
    config_values = daily_read.config.Config(env_file_path=env_file_path)
    if ctx.obj is None:
        ctx.obj = dict()
    ctx.obj["config_values"] = config_values

    rich_handler = RichHandler()
    rich_handler.setFormatter(logging.Formatter("%(message)s"))
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - Commit: %(commit)s - %(message)s"

    if not os.path.isabs(config_values.LOG_LOCATION):
        raise ValueError(f"Log location is not an absolute path: {config_values.LOG_LOCATION}")

    if os.path.exists(config_values.LOG_LOCATION) and not os.path.isdir(config_values.LOG_LOCATION):
        raise ValueError(f"Log Location exists but is not a directory: {config_values.LOG_LOCATION}")

    log_file = os.path.join(config_values.LOG_LOCATION, "DailyRead.log")

    rotating_file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=1024 * 1024 * 100, backupCount=5
    )  # 5 files of 100MB
    rotating_file_handler.addFilter(daily_read.utils.ContextFilter())
    error_handler = daily_read.utils.ErrorCollectorHandler()

    logging.basicConfig(
        level="INFO",
        format=LOG_FORMAT,
        handlers=[rich_handler, rotating_file_handler, error_handler],
    )


log = logging.getLogger(__name__)


### GENERATE ###
@daily_read_cli.group()
@click.pass_context
def generate(ctx):
    """Generate reports and save in a local git repository"""
    pass


@generate.command(name="all")
@click.option("-u", "--upload", is_flag=True, help="Trigger upload of reports.")
@click.option("--develop", is_flag=True, help="Only generate max 5 reports, for dev purposes.")
@click.pass_context
def generate_all(ctx, upload=False, develop=False):
    # Fetch data from all sources (configurable)
    config_values = ctx.obj["config_values"]
    projects_data = daily_read.ngi_data.ProjectDataMaster(config_values)

    log.info(f"Fetching data for {projects_data.source_names}")
    projects_data.get_data()
    log.info("Data fetched successfully")
    projects_data.save_data()
    log.info("Data saved to disk")

    orderer_with_modified_projects = projects_data.find_unique_orderers()

    op = daily_read.order_portal.OrderPortal(config_values, projects_data=projects_data)
    nr_orderers = 0
    for orderer in orderer_with_modified_projects:
        if orderer:
            op.get_orders(orderer=orderer)
            nr_orderers += 1
        if nr_orderers > 4 and develop:
            break
    modified_orders = op.process_orders(config_values.STATUS_PRIORITY_REV)
    daily_rep = daily_read.daily_report.DailyReport()

    for owner in modified_orders:
        if upload:
            report = daily_rep.populate_and_write_report(owner, modified_orders[owner], config_values.STATUS_PRIORITY)
            # Publish reports with published, hide reports with review
            for upload_category, report_state in {"projects": "published", "delete_report_for": "review"}.items():
                for status in modified_orders[owner][upload_category].keys():
                    for project in modified_orders[owner][upload_category][status]:
                        request_success = False
                        report_upload = report if upload_category == "projects" else ""
                        try:
                            request_success = op.upload_report_to_order_portal(report_upload, project, report_state)
                            # Stage changes
                            if request_success:
                                op.projects_data.stage_data_for_project(project)
                        # catch any and every exception during upload
                        except Exception as e:
                            log.error(
                                f"Exception Raised: Issue in uploading/hiding reports for {project.project_id}: {e}\nContinuing to next project"
                            )

        else:
            log.info("Saving report to disk instead of uploading")
            report = daily_rep.populate_and_write_report(
                owner,
                modified_orders[owner],
                config_values.STATUS_PRIORITY,
                out_dir=config_values.REPORTS_LOCATION,
            )
    if upload:
        # Commit all uploaded projects
        op.projects_data.commit_staged_data(f"Commit reports updates for {datetime.datetime.now()}")

    daily_read.utils.error_reporting(log)


@generate.command(
    name="single",
    help="Generate a report for a single project and save it locally. Mostly used for development",
)
@click.option(
    "-p",
    "--project",
    help="A project id to generate the report for.",
    type=str,
)
@click.option(
    "-o",
    "--include-older",
    help="Include projects that are older than 6 months.",
    is_flag=True,
)
@click.pass_context
def generate_single(ctx, project, include_older=False):
    config_values = ctx.obj["config_values"]
    projects_data = daily_read.ngi_data.ProjectDataMaster(config_values)
    # Fetch all projects so that the report will look the same
    log.info("Fetching data from NGI sources")
    if include_older:
        close_date = (datetime.datetime.now() - relativedelta(months=120)).strftime("%Y-%m-%d")
    else:
        close_date = None

    projects_data.get_data(close_date=close_date)

    op = daily_read.order_portal.OrderPortal(config_values, projects_data=projects_data)
    orderer = None
    for project_id, project_data in projects_data.data.items():
        if project_id == project:
            if project_data.orderer is None:
                log.error(f"Could not find orderer for project {project}")
                sys.exit(1)
            orderer = project_data.orderer
            break

    if orderer is None:
        log.error(f"Could not find project with id {project}")
        sys.exit(1)

    op.get_orders(orderer=orderer)
    filtered_orders = op.process_orders(config_values.STATUS_PRIORITY_REV)
    daily_rep = daily_read.daily_report.DailyReport()

    for owner, owner_orders in filtered_orders.items():
        _ = daily_rep.populate_and_write_report(
            owner, owner_orders, config_values.STATUS_PRIORITY, out_dir=config_values.REPORTS_LOCATION
        )

    log.info(f"Wrote report to {config_values.REPORTS_LOCATION}")
