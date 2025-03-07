import asyncio
from functools import wraps

import click
import uvicorn

from floword.app import app
from floword.config import get_config
from floword.dbutils import init_and_migrate, remove_all_data


def coro(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))

    return wrapper


def _migrate():
    db_url = get_config().get_db_url(async_mode=False)
    init_and_migrate(db_url)


@click.command()
def ui():
    """
    Start the UI.
    """
    from floword.ui.app import main as ui_app

    ui_app()


@click.command()
@click.option("--host", type=click.STRING, default="localhost")
@click.option("--port", type=click.INT, default=9772)
@click.option("--auto-migrate", type=click.BOOL, default=True, envvar="FLOWORD_AUTO_MIGRATE")
def start(host, port, auto_migrate):
    """
    Start the server.
    """
    if auto_migrate:
        _migrate()
    uvicorn.run(app, host=host, port=port)


@click.command()
def migrate():
    """
    Init and migrate the database.
    """
    _migrate()


@click.command()
@click.option("--yes", "-y", is_flag=True, default=False)
def clear(yes):
    """
    Drop all data before testing or other purposes.

    This command is not visible in the CLI. Only use it in tests for now.
    """
    if not yes:
        click.confirm("Are you sure you want to remove all data?", abort=True)

    click.echo("Remove all data...")

    db_url = get_config().get_db_url(async_mode=False)
    remove_all_data(db_url)


@click.group()
def cli():
    pass


cli.add_command(migrate)
cli.add_command(start)
cli.add_command(ui)
# cli.add_command(clear) # noqa: not visible in CLI
