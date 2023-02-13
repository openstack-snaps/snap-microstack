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

import asyncio
import logging
import shutil
from typing import Optional

import click
from rich.console import Console
from snaphelpers import Snap

from sunbeam import utils
from sunbeam.commands import juju, ohv
from sunbeam.commands.init import Role
from sunbeam.commands.terraform import (
    TerraformException,
    TerraformHelper,
    TerraformInitStep,
)
from sunbeam.jobs.checks import (
    JujuSnapCheck,
    Microk8sSnapCheck,
    OpenStackHypervisorSnapCheck,
    OpenStackHypervisorSnapHealth,
)
from sunbeam.jobs.common import BaseStep, Result, ResultType, Status

LOG = logging.getLogger(__name__)
console = Console()
snap = Snap()


class DeployControlPlaneStep(BaseStep):
    """Deploy control plane using Terraform"""

    def __init__(
        self,
        jhelper: juju.JujuHelper,
        tfhelper: TerraformHelper,
        model: str,
        cloud: str,
    ):
        super().__init__(
            "Deploying OpenStack Control Plane",
            "Deploying OpenStack Control Plane to Kubernetes",
        )
        self.path = snap.paths.user_common / "etc" / "deploy"
        self.model = model
        self.cloud = cloud
        self.jhelper = jhelper
        self.tfhelper = tfhelper

    def run(self, status: Optional[Status] = None) -> Result:
        """Execute configuration using terraform."""
        # TODO(jamespage):
        # This needs to evolve to add support for things like:
        # - Enabling HA
        # - Enabling/disabling specific services
        # - Switch channels for the charmed operators
        self.tfhelper.write_tfvars(
            {
                "model": self.model,
                "cloud": self.cloud,
            }
        )
        try:
            self.tfhelper.apply()
            asyncio.get_event_loop().run_until_complete(
                self.jhelper.wait_until_active(self.model)
            )
            return Result(ResultType.COMPLETED)
        except TerraformException as e:
            LOG.exception("Error configuring cloud")
            return Result(ResultType.FAILED, str(e))


@click.command()
def bootstrap() -> None:
    """Bootstrap the local node.

    Bootstrap juju.
    Deploy control plane if the node role is CONTROL.
    Deploy openstack-hypervisor snap if the node role
    is COMPUTE.
    """
    # context = click.get_current_context(silent=True)

    if utils.has_superuser_privileges():
        raise click.UsageError(
            "The bootstrap command should not be run with root "
            "privileges. Try again without sudo."
        )

    # NOTE: install to user writable location
    src = snap.paths.snap / "etc" / "deploy"
    dst = snap.paths.user_common / "etc" / "deploy"
    LOG.debug(f"Updating {dst} from {src}...")
    shutil.copytree(src, dst, dirs_exist_ok=True)

    role = snap.config.get("node.role")
    node_role = Role[role.upper()]

    LOG.debug(f"Bootstrap node: role {role}")

    cloud = snap.config.get("control-plane.cloud")
    model = snap.config.get("control-plane.model")

    preflight_checks = []
    if node_role.is_control_node():
        preflight_checks.extend([JujuSnapCheck(), Microk8sSnapCheck()])
    if node_role.is_compute_node():
        preflight_checks.extend(
            [
                OpenStackHypervisorSnapCheck(),
                # Just check config service is responding as hypervisor will report
                # that it is not ready until it has recieved required config.
                OpenStackHypervisorSnapHealth(check_health_report=False),
            ]
        )

    for check in preflight_checks:
        LOG.debug(f"Starting pre-flight check {check.name}")
        message = f"{check.description} ... "
        with console.status(f"{check.description} ... "):
            result = check.run()
            if result:
                console.print(f"{message}[green]done[/green]")
            else:
                console.print(f"{message}[red]failed[/red]")
                console.print()
                raise click.ClickException(check.message)

    jhelper = juju.JujuHelper()
    tfhelper = TerraformHelper(
        path=snap.paths.user_common / "etc" / "deploy", parallelism=1
    )
    plan = []

    if node_role.is_control_node():
        plan.append(juju.BootstrapJujuStep(cloud=cloud))
        plan.append(TerraformInitStep(tfhelper=tfhelper))
        plan.append(
            DeployControlPlaneStep(
                jhelper=jhelper, tfhelper=tfhelper, model=model, cloud=cloud
            )
        )

    if node_role.is_compute_node():
        LOG.debug("This is where we would append steps for the compute node")
        plan.append(ohv.UpdateIdentityServiceConfigStep(jhelper=jhelper, model=model))
        plan.append(ohv.UpdateRabbitMQConfigStep(jhelper=jhelper, model=model))
        plan.append(ohv.UpdateNetworkConfigStep(jhelper=jhelper, model=model))

    for step in plan:
        LOG.debug(f"Starting step {step.name}")
        message = f"{step.description} ... "
        with console.status(f"{step.description} ... "):
            if step.is_skip():
                LOG.debug(f"Skipping step {step.name}")
                console.print(f"{message}[green]done[/green]")
                continue

            LOG.debug(f"Running step {step.name}")
            result = step.run()
            LOG.debug(
                f"Finished running step {step.name}. " f"Result: {result.result_type}"
            )

        if result.result_type == ResultType.FAILED:
            console.print(f"{message}[red]failed[/red]")
            raise click.ClickException(result.message)

        console.print(f"{message}[green]done[/green]")

    click.echo(f"Node has been bootstrapped as a {role} node")
    asyncio.get_event_loop().run_until_complete(jhelper.disconnect_controller())


if __name__ == "__main__":
    bootstrap()
