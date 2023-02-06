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

import base64
import binascii
import os
import socket
import typing

from netifaces import AF_INET, ifaddresses, interfaces
from semver import VersionInfo
from snaphelpers import Snap

UNKNOWN_VERSION = VersionInfo(0, 0, 0)

LOCAL_ACCESS = "local"
REMOTE_ACCESS = "remote"


def get_snap():
    """Returns the current snap environment.

    :return:
    """
    return Snap()


def has_superuser_privileges() -> bool:
    """Determines if the current user has superuser privileges.

    This method will return True if the effective UID is 0. This should work
    for standard linux distributions.

    :return: True if the current user has superuser privileges, False otherwise
    :rtype: bool
    """
    return os.geteuid() == 0


def parse_version(version: str) -> VersionInfo:
    """Parse the version string and return a semver.VersionInfo.

    Attempts tot parse the version string and return a semver.VersionInfo.
    However, not all the versions that we will find conform to the semantic
    versioned strings. This method will attempt to provide a few known
    adjustments (such as expanding to MAJOR.MINOR.PATCH for versions that only
    have MAJOR.MINOR).

    In the event that the string cannot be coerced to be a valid semantic
    versioning form, this method will raise a ValueError indicating that it
    cannot parse the version.

    :param version: the version string to prase
    :type version: str
    :return: the semver.VersionInfo containing the versioning information
    :rtype: VersionInfo
    """
    try:
        return VersionInfo.parse(version)
    except ValueError:
        # Microk8s prefixes its version info with a 'v'. Let's strip it and get
        # rid of it.
        if version[0] == "v":
            return VersionInfo.parse(version[1:])

        # Juju uses 3.0 instead of 3.0.0 for major releases, so attempt to
        # convert it into a 3.0.0 (and include any pre-release information).
        if version.count(".") == 1:
            parts = version.split("-")
            new_version = f"{parts[0]}.0-{parts[1]}"
            return VersionInfo.parse(new_version)

        # Not a known condition, let's just re-raise.
        raise


def get_hostname() -> str:
    """Get hostname of the machine"""
    return socket.gethostname()


def get_fqdn() -> str:
    """Get FQDN of the machine"""
    return socket.getfqdn()


def get_local_ip_addresses() -> typing.List:
    """Get IP addresses of the local host."""
    addresses = []
    for ifaceName in interfaces():
        address = [
            i["addr"]
            for i in ifaddresses(ifaceName).setdefault(AF_INET, [])
            if "addr" in i
        ]
        addresses.extend(address)

    if "127.0.0.1" in addresses:
        addresses.remove("127.0.0.1")

    return addresses


def get_local_ip_by_default_route() -> str:
    """Get IP address of host associated with default gateway"""
    interface = "lo"
    ip = "127.0.0.1"

    # TOCHK: Gathering only IPv4
    if "default" in gateways():
        interface = gateways()["default"][AF_INET][1]

    ip_list = ifaddresses(interface)[AF_INET]
    if len(ip_list) > 0 and "addr" in ip_list[0]:
        ip = ip_list[0]["addr"]

    return ip


def encode_tls(cert_or_key: str) -> str:
    """Encode key or cert.

    :param cert: key/cert
    :type cert: str
    :return: base64 encoded data or None
    :rtype: str
    """
    try:
        cert_in_bytes = base64.b64encode(bytes(cert_or_key, "utf-8"))
        return cert_in_bytes.decode()
    except (binascii.Error, TypeError):
        return cert_or_key
