# MicroStack

![OpenStack][openstack-badge] [![OpenDev Zuul Builds - MicroStack][gated-badge]][zuul-jobs] [![MicroStack Docs][microstack-docs-badge]][microstack-docs]

## The smallest, simplest OpenStack

Pure upstream, lightweight OpenStack in a single package that makes OpenStack
simple to setup, manage and maintain.

Perfect for:
* Developer workstations
* Edge
* Small-scale private cloud deployments
* CI/CD

## Why MicroStack?

* **Small.** Developers want the smallest and simplest stable OpenStack for
  laptop and workstation development. 
* **Simple.** Minimize administration and operations with a single-package install
  that has no moving parts for simplicity and certainty. All dependencies and batteries
  included.
* **Compact.** MicroStack comes with minimal footprint which makes it ideal for
  devices with limited hardware resources.
* **Comprehensive** - MicroStack contains core OpenStack services and world class
  virtualisation software for your cloud needs:
  * Keystone
  * Horizon
  * Glance
  * Nova (KVM)
  * Neutron (OVN)

For more information, check the [MicroStack documentation][microstack-docs].

## Quickstart

MicroStack is going in a whole new direction - in a good way! We've listened to feedback from users and there is a general desire to go from a single-node trial run on a developer workstatation / solitary server and grow that installation into a production-grade OpenStack.

## Quickstart (Sunbeam)

Please refer to the [official tutorial][tutorial] for details on how to get started with Sunbeam.

## Quickstart (Beta)

Install MicroStack from the Beta channel. Note, this must be installed in devmode:

    sudo snap install microstack --devmode --beta

Initialise MicroStack for your environment. This will set up databases, networks,
security groups, flavors, and a CirrOS image for testing your installation:

    sudo microstack init --auto --control

Launch your first instance:

    microstack launch cirros --name test

SSH to your test instance. SSH Keys are setup as part of the initialisation step and
can be used to access the CirrOS instance just launched:

    ssh -i ~/.ssh/id_microstack cirros@<ip-address>

# Requirements

A system running MicroStack should have the following minimum requirements:

* multi-core CPU
* 8 GiB of RAM
* 100 GiB of Disk space

## OpenStack client

The OpenStack client can be installed by running `sudo snap install openstackclients`.
Once installed, you will be able to use the openstack client as normal:

    openstack network list
    openstack flavor list
    openstack keypair list
    openstack image list
    openstack security group rule list

## Accessing Horizon

To create an instance (called "awesome") based on the CirrOS image:

    microstack.launch cirros --name awesome

## SSH to an instance

The launch output will show you how to connect to the instance. For the CirrOS
image, the user account is 'cirros'.

    ssh -i ~/.ssh/id_microstack cirros@<ip-address>

## Horizon

The launch output will also provide information for the Horizon dashboard. The
username is 'admin' and the password can be obtained in this way:

    sudo snap get microstack config.credentials.keystone-password

## Getting Help

The great team behind MicroStack are available in the following places:

[![Discourse][discourse-badge]][discourse] [![#openstack-snaps on OFTC][oftc-badge]][oftc-webaccess]

## Reporting a bug

Please report bugs to the [MicroStack][microstack] project on Launchpad.

[![Get it from the Snap Store][snap-store-badge]][snap-store-link]

<!-- LINKS -->

[discourse]: https://discourse.charmhub.io/search?q=MicroStack
[discourse-badge]: https://img.shields.io/discourse/status?color=E95420&logo=ubuntu&server=https%3A%2F%2Fdiscourse.ubuntu.com&logoColor=white
[microstack-docs]: https://microstack.run/docs/
[microstack-docs-badge]: https://img.shields.io/badge/MicroStack-Docs-E95420?logo=ubuntu&logoColor=white
[oftc-badge]: https://img.shields.io/badge/chat-%23openstack--snaps%20on%20oftc-brightgreen.svg
[oftc-webaccess]: https://webchat.oftc.net/?channels=%23openstack-snaps
[openstack-badge]: https://img.shields.io/badge/Openstack-yoga-%23f01742.svg?logo=openstack&logoColor=white
[gated-badge]: https://zuul-ci.org/gated.svg
[zuul-jobs]: https://zuul.opendev.org/t/openstack/builds?project=x%2Fmicrostack#
[snap-store-badge]: https://snapcraft.io/static/images/badges/en/snap-store-black.svg
[snap-store-link]: https://snapcraft.io/microstack
[microstack]: https://bugs.launchpad.net/microstack
[tutorial]: https://discourse.ubuntu.com/t/install-and-configure-microstack-sunbeam-single-node
