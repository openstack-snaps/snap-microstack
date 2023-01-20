# Copyright (c) 2022 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging

import click

from sunbeam import log
from sunbeam.commands import bootstrap as bootstrap_cmds
from sunbeam.commands import configure as configure_cmds
from sunbeam.commands import inspect as inspect_cmds
from sunbeam.commands import install_script as install_script_cmds
from sunbeam.commands import openrc as openrc_cmds
from sunbeam.commands import reset as reset_cmds
from sunbeam.commands import status as status_cmds

LOG = logging.getLogger()

# Update the help options to allow -h in addition to --help for
# triggering the help for various commands
CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


@click.group("init", context_settings=CONTEXT_SETTINGS)
@click.option("--quiet", "-q", default=False, is_flag=True)
@click.option("--verbose", "-v", default=False, is_flag=True)
@click.pass_context
def cli(ctx, quiet, verbose):
    """Microstack is a small lightweight OpenStack distribution.

    To get started with a single node, all-in-one OpenStack installation, start
    with by initializing the local node. Once the local node has been initialized,
    run the bootstrap process to get a live cloud.
    """


def main():
    log.setup_root_logging()
    cli.add_command(bootstrap_cmds.bootstrap)
    cli.add_command(reset_cmds.reset)
    cli.add_command(status_cmds.status)
    cli.add_command(openrc_cmds.openrc)
    cli.add_command(configure_cmds.configure)
    cli.add_command(inspect_cmds.inspect)
    cli.add_command(install_script_cmds.install_script)
    cli()


if __name__ == "__main__":
    main()
