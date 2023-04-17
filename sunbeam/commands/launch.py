# Copyright (c) 2023 Canonical Ltd.
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
import os
import subprocess

from typing import List

import click
import openstack
import petname


from rich.console import Console
from snaphelpers import Snap

LOG = logging.getLogger(__name__)
console = Console()
snap = Snap()


def check_output(*args: List[str]) -> str:
    """Execute a shell command, returning the output of the command.

    :param args: strings to be composed into the bash call.

    Include our env; pass in any extra keyword args.
    """
    return subprocess.check_output(args, universal_newlines=True,
                                   env=os.environ).strip()


def check(*args: List[str]) -> int:
    """Execute a shell command, raising an error on failed excution.

    :param args: strings to be composed into the bash call.

    """
    return subprocess.check_call(args, env=os.environ)


def check_keypair(openstack_conn: openstack.connection.Connection):
    """
    Check for the sunbeam keypair's existence, creating it if it doesn't.

    """
    console.print("Checking for sunbeam key in OpenStack ... ")
    home = os.environ.get("SNAP_REAL_HOME")
    key_path = f"{home}/sunbeam"
    try:
        openstack_conn.compute.get_keypair("sunbeam")
        console.print("Found sunbeam key!")
    except openstack.exceptions.ResourceNotFound:
        console.print(
            f"No sunbeam key found. Creating SSH key at {key_path}/sunbeam"
        )
        id_ = openstack_conn.compute.create_keypair(name="sunbeam")
        with open(key_path, 'w', encoding="utf-8") as file_:
            file_.write(id_.private_key)
            check('chmod', '600', key_path)
    return key_path


@click.command()
@click.option(
    "-k",
    "--key",
    default="sunbeam",
    help="The SSH key to use for the instance"
)
def launch(
    key: str = "sunbeam"
) -> None:
    """
    Launch an OpenStack instance
    """
    console.print("Launching an OpenStack instance ... ")
    try:
        conn = openstack.connect(
            cloud="sunbeam"
        )
    except Exception:
        console.print(
                "Unable to connect to OpenStack.",
                " Is OpenStack running?",
                " Have you run the configure command?",
                " Do you have a clouds.yaml file?"
        )
        return

    with console.status("Checking for SSH key pair ... "):
        if key == "sunbeam":
            # Make sure that we have a default ssh key to hand off to the
            # instance.
            key_path = check_keypair(conn)
        else:
            # We've been passed an ssh key with an unknown path. Drop in
            # some placeholder text for the message at the end of this
            # routine, but don't worry about verifying it. We trust the
            # caller to have created it!
            home = os.environ.get("SNAP_REAL_HOME")
            key_path = f"{home}/.ssh/{key}"

    with console.status("Creating the OpenStack instance ... "):
        instance_name = petname.Generate()
        image = conn.compute.find_image("ubuntu-jammy")
        flavor = conn.compute.find_flavor("m1.tiny")
        network = conn.network.find_network("demo-network")
        keypair = conn.compute.find_keypair(key)
        server = conn.compute.create_server(
            name=instance_name,
            image_id=image.id,
            flavor_id=flavor.id,
            networks=[{"uuid": network.id}],
            key_name=keypair.name
        )

        server = conn.compute.wait_for_server(server)
        server_id = server.id

    with console.status("Allocating IP address to instance ... "):
        external_network = conn.network.find_network("external-network")
        ip_ = conn.network.create_ip(floating_network_id=external_network.id)
        conn.compute.add_floating_ip_to_server(
            server_id,
            ip_.floating_ip_address
        )

    console.print(
            "Access instance with",
            f"`ssh -i {key_path} ubuntu@{ip_.floating_ip_address}"
    )
