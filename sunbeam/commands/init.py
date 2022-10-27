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

import enum
import logging
import os

import click
from rich.console import Console
from snaphelpers import Snap

from sunbeam import utils
from sunbeam.commands import juju, microk8s, ohv  # noqa: H301
from sunbeam.jobs.common import ResultType

LOG = logging.getLogger(__name__)
console = Console()


def get_snap():
    """Returns the current snap environment.

    :return:
    """
    return Snap()


class Role(enum.Enum):
    """The role that the current node will play

    This determines if the role will be a control plane node, a Compute node,
    or a Converged node. The role will help determine which particular services
    need to be configured and installed on the system.
    """

    CONTROL = 1
    COMPUTE = 2
    CONVERGED = 3

    def is_control_node(self) -> bool:
        """Returns True if the node requires control services.

        Control plane services are installed on nodes which are not designated
        for compute nodes only. This helps determine the role that the local
        node will play.

        :return: True if the node should have control-plane services,
                 False otherwise
        """
        return self != Role.COMPUTE

    def is_compute_node(self) -> bool:
        """Returns True if the node requires compute services.

        Compute services are installed on nodes which are not designated as
        control nodes only. This helps determine the services which are
        necessary to install.

        :return: True if the node should run Compute services,
                 False otherwise
        """
        return self != Role.CONTROL

    def is_converged_node(self) -> bool:
        """Returns True if the node requires control and compute services.

        Control and Compute services are installed on nodes which are
        designated as converged nodes. This helps determine the services
        which are necessary to install.

        :return: True if the node should run Control and Compute services,
                 False otherwise
        """
        return self == Role.CONVERGED


@click.command()
@click.option(
    "--auto",
    default=False,
    is_flag=True,
    help="Automatically configure using the preselected defaults",
)
@click.option(
    "--role",
    default="converged",
    type=click.Choice(["control", "compute", "converged"], case_sensitive=False),
    help="Specify whether the node will be a control node, a "
    "compute node, or a converged node (default)",
)
def init(auto: bool, role: str) -> None:
    """Initialises the local node.

    When initializing the local node you must choose the role the node will
    function as. The local node can be initialised as a control plane node,
    a Compute node, or a Converged node where both control plane and compute
    services run on the same machine. The default option is to run both control
    plane services and compute node services on the same node in a converged
    architecture.
    """
    # context = click.get_current_context(silent=True)
    # This command needs to have root privileges for some of the commands that
    # it will invoke in the microk8s snap for configuration purposes.
    if not utils.has_superuser_privileges():
        raise click.UsageError(
            "The init command needs to be run with root "
            "privileges. Try again with sudo."
        )

    snap = get_snap()
    snap.config.set({"node.role": role.upper()})
    node_role = Role[role.upper()]
    microk8s_channel = snap.config.get("snap.channel.microk8s")
    juju_channel = snap.config.get("snap.channel.juju")
    ohv_channel = snap.config.get("snap.channel.openstack-hypervisor")

    LOG.debug(f"Initialising: auto {auto}, role {role}")

    plan = []

    if node_role.is_control_node():
        plan.append(juju.EnsureJujuInstalled(channel=juju_channel))
        plan.append(microk8s.EnsureMicrok8sInstalled(channel=microk8s_channel))
        plan.append(microk8s.EnableHighAvailability())
        plan.append(microk8s.EnableDNS())
        plan.append(microk8s.EnableStorage())
        plan.append(microk8s.EnableMetalLB())
        sudo_user = os.environ.get("SUDO_USER")
        LOG.debug(f"Enabling microk8s access to {sudo_user}")
        if sudo_user:
            plan.append(microk8s.EnableAccessToUser(sudo_user))

    if node_role.is_compute_node():
        LOG.debug("This is where we would append steps for the compute node")
        plan.append(ohv.EnsureOVHInstalled(channel=ohv_channel))

    for step in plan:
        LOG.debug(f"Starting step {step.name}")
        message = f"{step.description} ... "

        with console.status(f"{step.description} ... ") as status:
            if step.is_skip(status=status):
                LOG.debug(f"Skipping step {step.name}")
                console.print(f"{message}[green]Done[/green]")
                continue

            if not auto and step.has_prompts():
                status.stop()
                step.prompt(console)
                status.start()

            LOG.debug(f"Running step {step.name}")
            result = step.run(status=status)
            LOG.debug(
                f"Finished running step {step.name}. " f"Result: {result.result_type}"
            )

        if result.result_type == ResultType.FAILED:
            console.print(f"{message}[red]Failed[/red]")
            raise click.ClickException(result.message)

        console.print(f"{message}[green]Done[/green]")

    console.print(f"Node has been initialised as a [bold]{role}[/bold] node")
    console.print("\nRun following commands to bootstrap:\n")
    if node_role.is_compute_node():
        # TODO(hemanth): snap connect should be done via plan
        console.print(
            "  sudo snap connect microstack:hypervisor-config "
            "openstack-hypervisor:hypervisor-config\n"
        )
    console.print("  newgrp snap_microk8s\n  microstack bootstrap")


if __name__ == "__main__":
    init()
