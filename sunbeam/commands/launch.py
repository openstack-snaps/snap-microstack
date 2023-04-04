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

import asyncio
import logging
import os
import subprocess

import click
import openstack
import petname

from typing import List

from rich.console import Console
from snaphelpers import Snap

from sunbeam.commands import juju

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
    key_path = f"~/.ssh/sunbeam"
    LOG.debug(f"check_keypair Key Path is: {key_path}")
    if os.path.exists(key_path):
        return key_path
    console.print('Creating local "sunbeam" ssh key at {}'.format(key_path))
    # TODO: make sure that we get rid of this path on snap
    # uninstall. If we don't, check to make sure that Sunbeam
    # has a sunbeam ssh key, in addition to checking for the
    # existence of the file.
    key_dir = os.sep.join(key_path.split(os.sep)[:-1])
    check('mkdir', '-p', key_dir)
    check('chmod', '700', key_dir)

    id_ = openstack_conn.compute.create_keypair(name="sunbeam")

    with open(key_path, 'w') as file_:
        file_.write(id_.private_key)
        check('chmod', '600', key_path)

    return key_path

@click.command()
@click.option("-k", "--key", default="sunbeam", help="The SSH key to use for the instance")
def launch(
    key: str = "sunbeam"
) -> None:
    """
    Launch an OpenStack instance
    """
    LOG.debug(f"The supplied key name is {key}.")
    model = snap.config.get("control-plane.model")
    jhelper = juju.JujuHelper()
    server_id = ""
    keypath = ""
    console.print("Launching an OpenStack instance ... ")
    with console.status("Getting Keystone admin information ... "):
        app = "keystone"
        action_cmd = "get-admin-account"
        action_result = asyncio.get_event_loop().run_until_complete(
            jhelper.run_action(model, app, action_cmd)
        )

        if action_result.get("return-code", 0) > 1:
            _message = "Unable to retrieve OpenStack credentials from Keystone service"
            raise click.ClickException(_message)
        else:
            LOG.debug("Successfully retrieved admin info from Keystone")
            
        os_username = action_result.get("username")
        os_password = action_result.get("password")
        os_auth_url = action_result.get("public-endpoint")
        os_user_domain_name = action_result.get("user-domain-name")
        os_project_domain_name = action_result.get("project-domain-name")
        os_project_name = action_result.get("project-name")
        os_auth_version = action_result.get("api-version")
        os_identity_api_version = action_result.get("api_version")

    conn = openstack.connect(
        os_auth_url=os_auth_url,
        project_name=os_project_name,
        username=os_username,
        password=os_password,
        user_domain_name=os_user_domain_name,
        project_domain_name=os_project_domain_name,
    )

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
            key_path = '/path/to/ssh/key'

    with console.status("Creating the OpenStack instance ... "):
        instance_name = petname.Generate()
        image = conn.compute.find_image("ubuntu-jammy")
        flavor = conn.compute.find_flavor("m1.tiny")
        network = conn.network.find_network("demo-network")
        keypair = conn.compute.find_keypair(key)
        LOG.debug(
            """
Creating an instance with this configuration:
name     = %s,
image    = %s,
flavor   = %s,
network  = %s,
key_name = %s
            """ % (instance_name, image.id, flavor.id, network.id, keypair.name)
            )
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
        ip = conn.network.create_ip(floating_network_id=external_network.id)
        conn.compute.add_floating_ip_to_server(server_id, ip.floating_ip_address)

    console.print("Access the instance with `ssh -i {key_path} ubuntu@{ip.floating_ip_address}")