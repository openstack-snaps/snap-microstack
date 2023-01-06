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

import click
from rich.console import Console
from snaphelpers import Snap

from sunbeam.commands import juju
from sunbeam.jobs.common import ResultType

LOG = logging.getLogger(__name__)
console = Console()
snap = Snap()


@click.command()
@click.option(
    "--wait-ready", default=False, is_flag=True, help="Wait for microstack to be Active"
)
@click.option(
    "--timeout", default=300, type=int, help="Timeout in seconds for microstack status"
)
def status(wait_ready: bool, timeout: int) -> None:
    """Status of the node.

    Print status of the cluster.
    """
    # context = click.get_current_context(silent=True)

    model = snap.config.get("control-plane.model")
    jhelper = juju.JujuHelper()

    plan = []

    if wait_ready:
        plan.append(juju.ModelStatusStep(jhelper=jhelper, model=model, timeout=timeout))
    else:
        # from sunbeam.commands import ohv
        # plan.append(ohv.UpdateRabbitMQConfigStep(jhelper=jhelper, model=model))
        # plan.append(ohv.UpdateNetworkConfigStep(jhelper=jhelper, model=model))
        plan.append(juju.ModelStatusStep(jhelper=jhelper, model=model))

    bootstrapped = False
    status_overall = []
    for step in plan:
        LOG.debug(f"Starting step {step.name}")
        message = f"{step.description} ... "
        with console.status(f"{step.description} ... "):
            if step.is_skip():
                LOG.debug(f"Skipping step {step.name}")
                continue

            bootstrapped = True
            LOG.debug(f"Running step {step.name}")
            result = step.run()
            if result.result_type == ResultType.COMPLETED:
                if isinstance(result.message, list):
                    status_overall.extend(result.message)
                elif isinstance(result.message, str):
                    status_overall.append(result.message)
            LOG.debug(
                f"Finished running step {step.name}. " f"Result: {result.result_type}"
            )

        if result.result_type == ResultType.FAILED:
            console.print(f"{message}[red]failed[/red]")
            raise click.ClickException(result.message)

    console.print("Microstack status:")
    role = snap.config.get("node.role")
    console.print(f"Bootstrapped: {bootstrapped}")
    console.print(f"Node role: {role.lower()}")
    for message in status_overall:
        if "active" in message:
            console.print(f"[green]{message}[/green]")
        else:
            console.print(f"[red]{message}[/red]")

    console.print()
    console.print("User Survey: https://microstack.run/survey")

    asyncio.get_event_loop().run_until_complete(jhelper.disconnect_controller())
