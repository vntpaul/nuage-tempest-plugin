# Copyright 2017 NOKIA
# All Rights Reserved.
from netaddr import IPNetwork

from nuage_tempest_plugin.lib.test.nuage_test import NuageAdminNetworksTest
from nuage_tempest_plugin.lib.test.nuage_test import NuageBaseTest
from nuage_tempest_plugin.lib.topology import Topology
from nuage_tempest_plugin.lib.utils import constants
from nuage_tempest_plugin.services.nuage_client import NuageRestClient

from tempest.common import waiters
from tempest.lib import exceptions
from tempest.scenario import manager
from tempest.test import decorators

CONF = Topology.get_conf()
LOG = Topology.get_logger(__name__)


class PortsTest(NuageBaseTest, NuageAdminNetworksTest,
                manager.NetworkScenarioTest):
    @classmethod
    def setup_clients(cls):
        super(PortsTest, cls).setup_clients()
        cls.vsd_client = NuageRestClient()

    def show_port(self, port_id):
        """Wrapper utility that shows a given port."""
        body = self.ports_client.show_port(port_id)
        return body['port']

    def _create_server(self, name, network, port_id=None):
        keypair = self.create_keypair()
        network = {'uuid': network['id']}
        if port_id is not None:
            network['port'] = port_id
        return self.create_server(
            name=name,
            networks=[network],
            key_name=keypair['name'],
            wait_until='ACTIVE')

    def _delete_server(self, server_id, clients=None):
        if clients is None:
            clients = self.os_primary
        clients.servers_client.delete_server(server_id)
        waiters.wait_for_server_termination(clients.servers_client, server_id)

    @decorators.attr(type='smoke')
    def test_nuage_dhcp_port_create_check_status(self):
        network = self.create_network()
        self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                           mask_bits=24)
        filters = {
            'device_owner': 'network:dhcp:nuage',
            'network_id': network['id']
        }
        dhcp_port = self.ports_client.list_ports(**filters)['ports'][0]
        self.assertEqual('ACTIVE', dhcp_port['status'])

    @decorators.attr(type='smoke')
    def test_nuage_dhcp_port_with_router_detach_check_status(self):
        network = self.create_network()
        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=24)
        router = self.create_router(
            admin_state_up=True,
            external_network_id=CONF.network.public_network_id)
        self.create_router_interface(router_id=router["id"],
                                     subnet_id=subnet["id"],
                                     cleanup=False)

        self.routers_client.remove_router_interface(router_id=router["id"],
                                                    subnet_id=subnet["id"])
        filters = {
            'device_owner': 'network:dhcp:nuage',
            'network_id': network['id']
        }
        dhcp_port = self.ports_client.list_ports(**filters)['ports'][0]
        self.assertEqual('ACTIVE', dhcp_port['status'])

    @decorators.attr(type='smoke')
    def test_nuage_port_create_show_check_status(self):
        network = self.create_network()
        self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                           mask_bits=24)
        port = self.create_port(network)
        self.assertEqual('DOWN', port['status'])
        port = self.show_port(port['id'])
        # state has to remain DOWN as long as port is not bound
        self.assertEqual('DOWN', port['status'])

    @decorators.attr(type='smoke')
    def test_nuage_port_create_server_create_delete_check_status(self):
        network = self.create_network()
        self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                           mask_bits=24)
        port = self.create_port(network)
        server = self._create_server('s1', network, port['id'])
        port = self.show_port(port['id'])
        self.assertEqual('ACTIVE', port['status'])
        self._delete_server(server['id'])
        port = self.show_port(port['id'])
        self.assertEqual('DOWN', port['status'])

    @decorators.attr(type='smoke')
    def test_nuage_port_create_fixed_ips_negative(self):
        # Set up resources
        # Base resources
        if self.is_dhcp_agent_present():
            raise self.skipException(
                'Cannot run this test case when DHCP agent is enabled')
        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")
        subnet2 = self.create_subnet(network, cidr=IPNetwork("20.0.0.0/24"),
                                     mask_bits=28)
        self.assertIsNotNone(subnet2, "Unable to create second subnet")

        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "20.0.0.4",
                "subnet_id": subnet2["id"]
            }
        ]
        # Fail
        msg = "Port can't have multiple IPv4 IPs of different subnets"
        self.assertRaisesRegex(exceptions.BadRequest,
                               msg,
                               self.create_port,
                               network=network, fixed_ips=fixed_ips)

    def test_nuage_os_managed_subnet_port_create_with_nuage_policy_negative(
            self):

        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")

        msg = ("Cannot use VSP policy groups on OS managed subnets,"
               " use neutron security groups instead.")

        self.assertRaisesRegex(exceptions.BadRequest,
                               msg,
                               self.create_port,
                               network=network,
                               nuage_policy_groups=['Random_value'])

    def test_nuage_os_managed_subnet_port_update_with_nuage_policy_negative(
            self):

        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")

        port = self.create_port(network=network)

        self.assertIsNotNone(port, "Unable to create port")

        msg = ("Cannot use VSP policy groups on OS managed subnets,"
               " use neutron security groups instead.")

        self.assertRaisesRegex(exceptions.BadRequest,
                               msg,
                               self.update_port,
                               port=port,
                               nuage_policy_groups=['Random_value'])

    @decorators.attr(type='smoke')
    def test_nuage_port_update_fixed_ips_negative(self):
        if self.is_dhcp_agent_present():
            raise self.skipException(
                'Multiple subnets in a network not supported when DHCP agent '
                'is enabled.')
        # Set up resources
        # Base resources
        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")
        subnet2 = self.create_subnet(network, cidr=IPNetwork("20.0.0.0/24"),
                                     mask_bits=28)
        self.assertIsNotNone(subnet2, "Unable to create second subnet")
        router = self.create_router(
            admin_state_up=True,
            external_network_id=CONF.network.public_network_id)
        self.assertIsNotNone(router, "Unable to create router")
        # Attach subnet
        self.create_router_interface(router_id=router["id"],
                                     subnet_id=subnet["id"])
        self.create_router_interface(router_id=router["id"],
                                     subnet_id=subnet2["id"])
        # Create port
        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            }
        ]
        port = self.create_port(network=network, fixed_ips=fixed_ips)
        self.assertIsNotNone(port, "Unable to create port on network")

        # update within subnet should succeed
        fixed_ips = [
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            }

        ]
        port = self.update_port(port=port, fixed_ips=fixed_ips)
        self.assertIsNotNone(port, "Unable to update port")
        self.assertEqual(port["fixed_ips"][0]["ip_address"], "10.0.0.5",
                         message="The port did not update properly.")

        # Update to subnet2 should fail
        fixed_ips = [
            {
                "ip_address": "20.0.0.4",
                "subnet_id": subnet2["id"]
            }
        ]
        try:
            self.update_port(port=port, fixed_ips=fixed_ips)
            self.fail("Exception expected when updating to"
                      " a different subnet!")
        except exceptions.BadRequest as e:
            if "Updating fixed ip of port" in e._error_string:
                pass
            else:
                # Differentiate between VSD failure and update failure
                LOG.debug(e._error_string)
                self.fail("A different NuageBadRequest exception"
                          " was expected for this operation.")

    @decorators.attr(type='smoke')
    def test_nuage_port_create_fixed_ips_same_subnet_l2(self):
        # Set up resources
        # Base resources
        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")

        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            }

        ]

        port = self.create_port(network=network, fixed_ips=fixed_ips)
        self.assertIsNotNone(port, "Unable to create port on network")
        vsd_vport_parent = self.vsd_client.get_global_resource(
            constants.L2_DOMAIN,
            filters='externalID',
            filter_value=subnet['id'])[0]
        nuage_vport = self.vsd_client.get_vport(
            constants.L2_DOMAIN,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.INHERITED,
                         nuage_vport[0]['addressSpoofing'])

    @decorators.attr(type='smoke')
    def test_nuage_port_update_fixed_ips_same_subnet_l2(self):
        # Set up resources
        # Base resources
        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")
        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            }
        ]
        port = self.create_port(network=network, fixed_ips=fixed_ips)
        self.assertIsNotNone(port, "Unable to create port on network")
        vsd_vport_parent = self.vsd_client.get_global_resource(
            constants.L2_DOMAIN,
            filters='externalID',
            filter_value=subnet['id'])[0]
        nuage_vport = self.vsd_client.get_vport(
            constants.L2_DOMAIN,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.INHERITED,
                         nuage_vport[0]['addressSpoofing'])

        # update within subnet should succeed
        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            }

        ]
        port = self.update_port(port=port, fixed_ips=fixed_ips)
        self.assertIsNotNone(port, "Unable to update port")
        nuage_vport = self.vsd_client.get_vport(
            constants.L2_DOMAIN,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.INHERITED,
                         nuage_vport[0]['addressSpoofing'])

    @decorators.attr(type='smoke')
    def test_nuage_port_create_fixed_ips_same_subnet_l3(self):
        # Set up resources
        # Base resources
        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")
        router = self.create_router(
            admin_state_up=True,
            external_network_id=CONF.network.public_network_id)
        self.assertIsNotNone(router, "Unable to create router")
        # Attach subnet
        self.create_router_interface(router_id=router["id"],
                                     subnet_id=subnet["id"])
        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            }

        ]
        port = self.create_port(network=network, fixed_ips=fixed_ips)
        self.assertIsNotNone(port, "Unable to create port on network")
        vsd_vport_parent = self.vsd_client.get_global_resource(
            constants.SUBNETWORK,
            filters='externalID',
            filter_value=subnet['id'])[0]
        nuage_vport = self.vsd_client.get_vport(
            constants.SUBNETWORK,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.INHERITED,
                         nuage_vport[0]['addressSpoofing'])
        nuage_vport_vips = self.vsd_client.get_virtual_ip(
            constants.VPORT,
            nuage_vport[0]['ID'])
        valid_vips = ['10.0.0.4']
        vip_mismatch = False
        mac_mismatch = False
        if valid_vips and not nuage_vport_vips:
            vip_mismatch = True
        for nuage_vport_vip in nuage_vport_vips:
            if nuage_vport_vip['virtualIP'] not in valid_vips:
                vip_mismatch = True
            if nuage_vport_vip['MAC'] != port['mac_address']:
                mac_mismatch = True
        self.assertEqual(vip_mismatch, False)
        self.assertEqual(mac_mismatch, False)

    @decorators.attr(type='smoke')
    def test_nuage_port_create_fixed_ips_same_subnet_l3_no_security(self):
        # Set up resources
        # Base resources
        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")
        router = self.create_router(
            admin_state_up=True,
            external_network_id=CONF.network.public_network_id)
        self.assertIsNotNone(router, "Unable to create router")
        # Attach subnet
        self.create_router_interface(router_id=router["id"],
                                     subnet_id=subnet["id"])
        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            }

        ]
        port = self.create_port(network=network, fixed_ips=fixed_ips,
                                port_security_enabled=False)
        self.assertIsNotNone(port, "Unable to create port on network")
        vsd_vport_parent = self.vsd_client.get_global_resource(
            constants.SUBNETWORK,
            filters='externalID',
            filter_value=subnet['id'])[0]
        nuage_vport = self.vsd_client.get_vport(
            constants.SUBNETWORK,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.ENABLED,
                         nuage_vport[0]['addressSpoofing'])
        nuage_vport_vips = self.vsd_client.get_virtual_ip(
            constants.VPORT,
            nuage_vport[0]['ID'])
        valid_vips = ['10.0.0.4']
        vip_mismatch = False
        mac_mismatch = False
        if valid_vips and not nuage_vport_vips:
            vip_mismatch = True
        for nuage_vport_vip in nuage_vport_vips:
            if nuage_vport_vip['virtualIP'] not in valid_vips:
                vip_mismatch = True
            if nuage_vport_vip['MAC'] != port['mac_address']:
                mac_mismatch = True
        self.assertEqual(vip_mismatch, False)
        self.assertEqual(mac_mismatch, False)

    @decorators.attr(type='smoke')
    def test_nuage_port_update_fixed_ips_same_subnet_l3_no_security(self):
        # Set up resources
        # Base resources
        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")
        router = self.create_router(
            admin_state_up=True,
            external_network_id=CONF.network.public_network_id)
        self.assertIsNotNone(router, "Unable to create router")
        # Attach subnet
        self.create_router_interface(router_id=router["id"],
                                     subnet_id=subnet["id"])
        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            }
        ]
        allowed_address_pairs = [{'ip_address': '10.0.0.5',
                                  'mac_address': 'fe:a0:36:4b:c8:70'}]
        port = self.create_port(network=network,
                                fixed_ips=fixed_ips,
                                allowed_address_pairs=allowed_address_pairs)
        self.assertIsNotNone(port, "Unable to create port on network")
        vsd_vport_parent = self.vsd_client.get_global_resource(
            constants.SUBNETWORK,
            filters='externalID',
            filter_value=subnet['id'])[0]
        nuage_vport = self.vsd_client.get_vport(
            constants.SUBNETWORK,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.INHERITED,
                         nuage_vport[0]['addressSpoofing'])

        # update within subnet should succeed
        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            }
        ]
        port = self.update_port(port=port, fixed_ips=fixed_ips,
                                allowed_address_pairs=[],
                                security_groups=[],
                                port_security_enabled=False)
        self.assertIsNotNone(port, "Unable to update port")
        nuage_vport = self.vsd_client.get_vport(
            constants.SUBNETWORK,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.ENABLED,
                         nuage_vport[0]['addressSpoofing'])
        nuage_vport_vips = self.vsd_client.get_virtual_ip(
            constants.VPORT,
            nuage_vport[0]['ID'])
        valid_vips = ['10.0.0.4']
        vip_mismatch = False
        mac_mismatch = False
        if valid_vips and not nuage_vport_vips:
            vip_mismatch = True
        for nuage_vport_vip in nuage_vport_vips:
            if nuage_vport_vip['virtualIP'] not in valid_vips:
                vip_mismatch = True
            if nuage_vport_vip['MAC'] != port['mac_address']:
                mac_mismatch = True
        self.assertEqual(vip_mismatch, False)
        self.assertEqual(mac_mismatch, False)

    @decorators.attr(type='smoke')
    def test_nuage_port_update_fixed_ips_same_subnet_l3(self):
        # Set up resources
        # Base resources
        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")
        router = self.create_router(
            admin_state_up=True,
            external_network_id=CONF.network.public_network_id)
        self.assertIsNotNone(router, "Unable to create router")
        # Attach subnet
        self.create_router_interface(router_id=router["id"],
                                     subnet_id=subnet["id"])
        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            }
        ]
        port = self.create_port(network=network, fixed_ips=fixed_ips)
        self.assertIsNotNone(port, "Unable to create port on network")
        vsd_vport_parent = self.vsd_client.get_global_resource(
            constants.SUBNETWORK,
            filters='externalID',
            filter_value=subnet['id'])[0]
        nuage_vport = self.vsd_client.get_vport(
            constants.SUBNETWORK,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.INHERITED,
                         nuage_vport[0]['addressSpoofing'])

        # update within subnet should succeed
        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            }

        ]
        port = self.update_port(port=port, fixed_ips=fixed_ips)
        self.assertIsNotNone(port, "Unable to update port")
        nuage_vport = self.vsd_client.get_vport(
            constants.SUBNETWORK,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.INHERITED,
                         nuage_vport[0]['addressSpoofing'])
        nuage_vport_vips = self.vsd_client.get_virtual_ip(
            constants.VPORT,
            nuage_vport[0]['ID'])
        valid_vips = ['10.0.0.4']
        vip_mismatch = False
        mac_mismatch = False
        if valid_vips and not nuage_vport_vips:
            vip_mismatch = True
        for nuage_vport_vip in nuage_vport_vips:
            if nuage_vport_vip['virtualIP'] not in valid_vips:
                vip_mismatch = True
            if nuage_vport_vip['MAC'] != port['mac_address']:
                mac_mismatch = True
        self.assertEqual(vip_mismatch, False)
        self.assertEqual(mac_mismatch, False)

    @decorators.attr(type='smoke')
    def test_nuage_port_create_fixed_ips_same_subnet_l2_with_aap(self):
        # Set up resources
        # Base resources
        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")

        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            }

        ]
        allowed_address_pairs = [{'ip_address': '10.0.0.50',
                                  'mac_address': 'fe:a0:36:4b:c8:70'}]
        port = self.create_port(network=network, fixed_ips=fixed_ips,
                                allowed_address_pairs=allowed_address_pairs)
        self.assertIsNotNone(port, "Unable to create port on network")
        vsd_vport_parent = self.vsd_client.get_global_resource(
            constants.L2_DOMAIN,
            filters='externalID',
            filter_value=subnet['id'])[0]
        nuage_vport = self.vsd_client.get_vport(
            constants.L2_DOMAIN,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.ENABLED,
                         nuage_vport[0]['addressSpoofing'])

    @decorators.attr(type='smoke')
    def test_nuage_port_update_fixed_ips_same_subnet_l2_with_aap(self):
        # Set up resources
        # Base resources
        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")
        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            }
        ]
        port = self.create_port(network=network, fixed_ips=fixed_ips)
        self.assertIsNotNone(port, "Unable to create port on network")
        vsd_vport_parent = self.vsd_client.get_global_resource(
            constants.L2_DOMAIN,
            filters='externalID',
            filter_value=subnet['id'])[0]
        nuage_vport = self.vsd_client.get_vport(
            constants.L2_DOMAIN,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.INHERITED,
                         nuage_vport[0]['addressSpoofing'])

        # update within subnet should succeed
        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            }

        ]
        allowed_address_pairs = [{'ip_address': '10.0.0.50',
                                  'mac_address': 'fe:a0:36:4b:c8:70'}]
        port = self.update_port(port=port,
                                fixed_ips=fixed_ips,
                                allowed_address_pairs=allowed_address_pairs)
        self.assertIsNotNone(port, "Unable to update port")
        nuage_vport = self.vsd_client.get_vport(
            constants.L2_DOMAIN,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.ENABLED,
                         nuage_vport[0]['addressSpoofing'])

    @decorators.attr(type='smoke')
    def test_nuage_port_create_fixed_ips_same_subnet_l3_with_aap(self):
        # Set up resources
        # Base resources
        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")
        router = self.create_router(
            admin_state_up=True,
            external_network_id=CONF.network.public_network_id)
        self.assertIsNotNone(router, "Unable to create router")
        # Attach subnet
        self.create_router_interface(router_id=router["id"],
                                     subnet_id=subnet["id"])
        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            }

        ]
        allowed_address_pairs = [{'ip_address': '10.0.0.6',
                                  'mac_address': 'fe:a0:36:4b:c8:70'}]
        port = self.create_port(network=network, fixed_ips=fixed_ips,
                                allowed_address_pairs=allowed_address_pairs)
        self.assertIsNotNone(port, "Unable to create port on network")
        vsd_vport_parent = self.vsd_client.get_global_resource(
            constants.SUBNETWORK,
            filters='externalID',
            filter_value=subnet['id'])[0]
        nuage_vport = self.vsd_client.get_vport(
            constants.SUBNETWORK,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.INHERITED,
                         nuage_vport[0]['addressSpoofing'])
        nuage_vport_vips = self.vsd_client.get_virtual_ip(
            constants.VPORT,
            nuage_vport[0]['ID'])
        valid_vips = ['10.0.0.4', allowed_address_pairs[0]['ip_address']]
        vip_mismatch = False
        if valid_vips and not nuage_vport_vips:
            vip_mismatch = True
        for nuage_vport_vip in nuage_vport_vips:
            if nuage_vport_vip['virtualIP'] not in valid_vips:
                vip_mismatch = True
            self.assertEqual(vip_mismatch, False)

    @decorators.attr(type='smoke')
    def test_nuage_port_create_fixed_ips_same_subnet_l3_with_aap_outside_cidr(
            self):
        # Set up resources
        # Base resources
        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")
        router = self.create_router(
            admin_state_up=True,
            external_network_id=CONF.network.public_network_id)
        self.assertIsNotNone(router, "Unable to create router")
        # Attach subnet
        self.create_router_interface(router_id=router["id"],
                                     subnet_id=subnet["id"])
        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            }
        ]
        allowed_address_pairs = [{'ip_address': '1.1.1.5',
                                  'mac_address': 'fe:a0:36:4b:c8:70'}]
        port = self.create_port(network=network, fixed_ips=fixed_ips,
                                allowed_address_pairs=allowed_address_pairs)
        self.assertIsNotNone(port, "Unable to create port on network")
        vsd_vport_parent = self.vsd_client.get_global_resource(
            constants.SUBNETWORK,
            filters='externalID',
            filter_value=subnet['id'])[0]
        nuage_vport = self.vsd_client.get_vport(
            constants.SUBNETWORK,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.ENABLED,
                         nuage_vport[0]['addressSpoofing'])
        nuage_vport_vips = self.vsd_client.get_virtual_ip(
            constants.VPORT,
            nuage_vport[0]['ID'])
        valid_vips = ['10.0.0.4']
        vip_mismatch = False
        if valid_vips and not nuage_vport_vips:
            vip_mismatch = True
        for nuage_vport_vip in nuage_vport_vips:
            if nuage_vport_vip['virtualIP'] not in valid_vips:
                vip_mismatch = True
            self.assertEqual(vip_mismatch, False)

    @decorators.attr(type='smoke')
    def test_nuage_port_update_fixed_ips_same_subnet_l3_with_aap(self):
        # Set up resources
        # Base resources
        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")
        router = self.create_router(
            admin_state_up=True,
            external_network_id=CONF.network.public_network_id)
        self.assertIsNotNone(router, "Unable to create router")
        # Attach subnet
        self.create_router_interface(router_id=router["id"],
                                     subnet_id=subnet["id"])
        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            }
        ]
        port = self.create_port(network=network, fixed_ips=fixed_ips)
        self.assertIsNotNone(port, "Unable to create port on network")
        vsd_vport_parent = self.vsd_client.get_global_resource(
            constants.SUBNETWORK,
            filters='externalID',
            filter_value=subnet['id'])[0]
        nuage_vport = self.vsd_client.get_vport(
            constants.SUBNETWORK,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.INHERITED,
                         nuage_vport[0]['addressSpoofing'])

        # update within subnet should succeed
        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            }

        ]
        allowed_address_pairs = [{'ip_address': '10.0.0.6',
                                  'mac_address': 'fe:a0:36:4b:c8:70'}]
        port = self.update_port(port=port, fixed_ips=fixed_ips,
                                allowed_address_pairs=allowed_address_pairs)
        self.assertIsNotNone(port, "Unable to update port")
        nuage_vport = self.vsd_client.get_vport(
            constants.SUBNETWORK,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.INHERITED,
                         nuage_vport[0]['addressSpoofing'])
        nuage_vport_vips = self.vsd_client.get_virtual_ip(
            constants.VPORT,
            nuage_vport[0]['ID'])
        valid_vips = ['10.0.0.4', allowed_address_pairs[0]['ip_address']]
        vip_mismatch = False
        if valid_vips and not nuage_vport_vips:
            vip_mismatch = True
        for nuage_vport_vip in nuage_vport_vips:
            if nuage_vport_vip['virtualIP'] not in valid_vips:
                vip_mismatch = True
            self.assertEqual(vip_mismatch, False)

    @decorators.attr(type='smoke')
    def test_nuage_port_update_fixed_ips_same_subnet_l3_with_aap_with_vm(self):
        # Set up resources
        # Base resources
        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")
        router = self.create_router(
            admin_state_up=True,
            external_network_id=CONF.network.public_network_id)
        self.assertIsNotNone(router, "Unable to create router")
        # Attach subnet
        self.create_router_interface(router_id=router["id"],
                                     subnet_id=subnet["id"])
        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            }
        ]
        allowed_address_pairs = [{'ip_address': '10.0.0.10',
                                  'mac_address': 'fe:a0:36:4b:c8:70'}]
        port = self.create_port(network=network, fixed_ips=fixed_ips,
                                allowed_address_pairs=allowed_address_pairs)
        self.assertIsNotNone(port, "Unable to create port on network")
        vsd_vport_parent = self.vsd_client.get_global_resource(
            constants.SUBNETWORK,
            filters='externalID',
            filter_value=subnet['id'])[0]
        nuage_vport = self.vsd_client.get_vport(
            constants.SUBNETWORK,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.INHERITED,
                         nuage_vport[0]['addressSpoofing'])
        nuage_vport_vips = self.vsd_client.get_virtual_ip(
            constants.VPORT,
            nuage_vport[0]['ID'])
        valid_vips = [fixed_ips[0]["ip_address"],
                      allowed_address_pairs[0]['ip_address']]
        vip_mismatch = False
        if valid_vips and not nuage_vport_vips:
            vip_mismatch = True
        for nuage_vport_vip in nuage_vport_vips:
            if nuage_vport_vip['virtualIP'] not in valid_vips:
                vip_mismatch = True
            self.assertEqual(vip_mismatch, False)

        self._create_server(name='vm-' + network['name'],
                            network=network, port_id=port['id'])

        # update within subnet should succeed
        fixed_ips = [
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "10.0.0.6",
                "subnet_id": subnet["id"]
            }
        ]
        allowed_address_pairs = [{'ip_address': '10.0.0.7',
                                  'mac_address': 'fe:a0:36:4b:c8:70'},
                                 {'ip_address': '10.0.0.10',
                                  'mac_address': 'fe:a0:36:4b:c8:70'}]
        port = self.update_port(port=port, fixed_ips=fixed_ips,
                                allowed_address_pairs=allowed_address_pairs)
        self.assertIsNotNone(port, "Unable to update port")
        nuage_vport = self.vsd_client.get_vport(
            constants.SUBNETWORK,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.INHERITED,
                         nuage_vport[0]['addressSpoofing'])
        nuage_vport_vips = self.vsd_client.get_virtual_ip(
            constants.VPORT,
            nuage_vport[0]['ID'])
        valid_vips = [fixed_ips[0]["ip_address"],
                      allowed_address_pairs[0]['ip_address'],
                      allowed_address_pairs[1]['ip_address']]
        vip_mismatch = False
        if valid_vips and not nuage_vport_vips:
            vip_mismatch = True
        for nuage_vport_vip in nuage_vport_vips:
            if nuage_vport_vip['virtualIP'] not in valid_vips:
                vip_mismatch = True
            self.assertEqual(vip_mismatch, False)

    @decorators.attr(type='smoke')
    def test_nuage_port_update_app_to_fixed_ips_l3_with_vm(self):
        # Set up resources
        # Base resources
        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")
        router = self.create_router(
            admin_state_up=True,
            external_network_id=CONF.network.public_network_id)
        self.assertIsNotNone(router, "Unable to create router")
        # Attach subnet
        self.create_router_interface(router_id=router["id"],
                                     subnet_id=subnet["id"])
        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            }
        ]
        allowed_address_pairs = [{'ip_address': '10.0.0.6',
                                  'mac_address': 'fe:a0:36:4b:c8:70'}]
        port = self.create_port(network=network, fixed_ips=fixed_ips,
                                allowed_address_pairs=allowed_address_pairs)
        self.assertIsNotNone(port, "Unable to create port on network")
        vsd_vport_parent = self.vsd_client.get_global_resource(
            constants.SUBNETWORK,
            filters='externalID',
            filter_value=subnet['id'])[0]
        nuage_vport = self.vsd_client.get_vport(
            constants.SUBNETWORK,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.INHERITED,
                         nuage_vport[0]['addressSpoofing'])
        nuage_vport_vips = self.vsd_client.get_virtual_ip(
            constants.VPORT,
            nuage_vport[0]['ID'])
        valid_vips = [fixed_ips[0]["ip_address"],
                      allowed_address_pairs[0]['ip_address']]
        vip_mismatch = False
        if valid_vips and not nuage_vport_vips:
            vip_mismatch = True
        for nuage_vport_vip in nuage_vport_vips:
            if nuage_vport_vip['virtualIP'] not in valid_vips:
                vip_mismatch = True
            self.assertEqual(vip_mismatch, False)

        self._create_server(name='vm-' + network['name'],
                            network=network, port_id=port['id'])

        # update within subnet should succeed
        fixed_ips = [
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "10.0.0.6",
                "subnet_id": subnet["id"]
            }
        ]
        allowed_address_pairs = [{'ip_address': '10.0.0.7',
                                  'mac_address': 'fe:a0:36:4b:c8:70'},
                                 {'ip_address': '10.0.0.10',
                                  'mac_address': 'fe:a0:36:4b:c8:70'}]
        port = self.update_port(port=port, fixed_ips=fixed_ips,
                                allowed_address_pairs=allowed_address_pairs)
        self.assertIsNotNone(port, "Unable to update port")
        nuage_vport = self.vsd_client.get_vport(
            constants.SUBNETWORK,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.INHERITED,
                         nuage_vport[0]['addressSpoofing'])
        nuage_vport_vips = self.vsd_client.get_virtual_ip(
            constants.VPORT,
            nuage_vport[0]['ID'])
        valid_vips = [fixed_ips[0]["ip_address"],
                      allowed_address_pairs[0]['ip_address'],
                      allowed_address_pairs[1]['ip_address']]
        vip_mismatch = False
        if valid_vips and not nuage_vport_vips:
            vip_mismatch = True
        for nuage_vport_vip in nuage_vport_vips:
            if nuage_vport_vip['virtualIP'] not in valid_vips:
                vip_mismatch = True
            self.assertEqual(vip_mismatch, False)

    @decorators.attr(type='smoke')
    def test_nuage_port_update_fixed_ip_with_vm_and_conflict_with_aap_neg(
            self):
        # Set up resources
        # Base resources
        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")
        router = self.create_router(
            admin_state_up=True,
            external_network_id=CONF.network.public_network_id)
        self.assertIsNotNone(router, "Unable to create router")
        # Attach subnet
        self.create_router_interface(router_id=router["id"],
                                     subnet_id=subnet["id"])
        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            }
        ]
        allowed_address_pairs = [{'ip_address': '10.0.0.10',
                                  'mac_address': 'fe:a0:36:4b:c8:70'}]
        port = self.create_port(network=network, fixed_ips=fixed_ips,
                                allowed_address_pairs=allowed_address_pairs)
        self.assertIsNotNone(port, "Unable to create port on network")
        vsd_vport_parent = self.vsd_client.get_global_resource(
            constants.SUBNETWORK,
            filters='externalID',
            filter_value=subnet['id'])[0]
        nuage_vport = self.vsd_client.get_vport(
            constants.SUBNETWORK,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.INHERITED,
                         nuage_vport[0]['addressSpoofing'])
        nuage_vport_vips = self.vsd_client.get_virtual_ip(
            constants.VPORT,
            nuage_vport[0]['ID'])
        valid_vips = [fixed_ips[0]["ip_address"],
                      allowed_address_pairs[0]['ip_address']]
        vip_mismatch = False
        if valid_vips and not nuage_vport_vips:
            vip_mismatch = True
        for nuage_vport_vip in nuage_vport_vips:
            if nuage_vport_vip['virtualIP'] not in valid_vips:
                vip_mismatch = True
            self.assertEqual(vip_mismatch, False)

        self._create_server(name='vm-' + network['name'],
                            network=network, port_id=port['id'])
        fixed_ips = [
            {
                "ip_address": "10.0.0.8",
                "subnet_id": subnet["id"]
            }
        ]
        allowed_address_pairs = [{'ip_address': '10.0.0.6',
                                  'mac_address': 'fe:a0:36:4b:c8:70'}]
        self.create_port(network=network, fixed_ips=fixed_ips,
                         allowed_address_pairs=allowed_address_pairs)

        # update within subnet should succeed
        fixed_ips = [
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "10.0.0.6",
                "subnet_id": subnet["id"]
            }
        ]
        # below update will fail with proper roll back
        try:
            self.update_port(port=port, fixed_ips=fixed_ips)
            self.fail("Exception expected when updating to"
                      " a different subnet!")
        except exceptions.BadRequest as e:
            if ('Bad request: The IP Address 10.0.0.6 is'
                    ' currently in use by subnet' in e._error_string):
                vsd_vport_parent = self.vsd_client.get_global_resource(
                    constants.SUBNETWORK,
                    filters='externalID',
                    filter_value=subnet['id'])[0]
                nuage_vport = self.vsd_client.get_vport(
                    constants.SUBNETWORK,
                    vsd_vport_parent['ID'],
                    filters='externalID',
                    filter_value=port['id'])
                self.assertEqual(constants.INHERITED,
                                 nuage_vport[0]['addressSpoofing'])
                nuage_vport_vips = self.vsd_client.get_virtual_ip(
                    constants.VPORT,
                    nuage_vport[0]['ID'])
                vip_mismatch = False
                if valid_vips and not nuage_vport_vips:
                    vip_mismatch = True
                for nuage_vport_vip in nuage_vport_vips:
                    if nuage_vport_vip['virtualIP'] not in valid_vips:
                        vip_mismatch = True
                    self.assertEqual(vip_mismatch, False)
                pass
            else:
                # Differentiate between VSD failure and update failure
                LOG.debug(e._error_string)
                self.fail("A different NuageBadRequest exception"
                          " was expected for this operation.")

    @decorators.attr(type='smoke')
    def test_nuage_port_create_fixed_ip_same_as_aap(self):
        # Set up resources
        # Base resources
        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")
        router = self.create_router(
            admin_state_up=True,
            external_network_id=CONF.network.public_network_id)
        self.assertIsNotNone(router, "Unable to create router")
        # Attach subnet
        self.create_router_interface(router_id=router["id"],
                                     subnet_id=subnet["id"])
        fixed_ips = [
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "10.0.0.6",
                "subnet_id": subnet["id"]
            }
        ]
        allowed_address_pairs = [{'ip_address': '10.0.0.6',
                                  'mac_address': 'fe:a0:36:4b:c8:70'}]
        port = self.create_port(network=network, fixed_ips=fixed_ips,
                                allowed_address_pairs=allowed_address_pairs)
        self.assertIsNotNone(port, "Unable to create port on network")
        vsd_vport_parent = self.vsd_client.get_global_resource(
            constants.SUBNETWORK,
            filters='externalID',
            filter_value=subnet['id'])[0]
        nuage_vport = self.vsd_client.get_vport(
            constants.SUBNETWORK,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.ENABLED,
                         nuage_vport[0]['addressSpoofing'])
        nuage_vport_vips = self.vsd_client.get_virtual_ip(
            constants.VPORT,
            nuage_vport[0]['ID'])
        valid_vips = [fixed_ips[0]["ip_address"],
                      allowed_address_pairs[0]['ip_address']]
        vip_mismatch = False
        mac_mismatch = False
        if valid_vips and not nuage_vport_vips:
            vip_mismatch = True
        for nuage_vport_vip in nuage_vport_vips:
            if nuage_vport_vip['virtualIP'] not in valid_vips:
                vip_mismatch = True
            if nuage_vport_vip['MAC'] != port['mac_address']:
                mac_mismatch = True
            self.assertEqual(vip_mismatch, False)
            self.assertEqual(mac_mismatch, False)

    @decorators.attr(type='smoke')
    def test_nuage_port_update_fixed_ips_same_as_aap(self):
        # Set up resources
        # Base resources
        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")
        router = self.create_router(
            admin_state_up=True,
            external_network_id=CONF.network.public_network_id)
        self.assertIsNotNone(router, "Unable to create router")
        # Attach subnet
        self.create_router_interface(router_id=router["id"],
                                     subnet_id=subnet["id"])
        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            }
        ]
        allowed_address_pairs = [{'ip_address': '10.0.0.6',
                                  'mac_address': 'fe:a0:36:4b:c8:70'}]
        port = self.create_port(network=network, fixed_ips=fixed_ips,
                                allowed_address_pairs=allowed_address_pairs)
        self.assertIsNotNone(port, "Unable to create port on network")
        vsd_vport_parent = self.vsd_client.get_global_resource(
            constants.SUBNETWORK,
            filters='externalID',
            filter_value=subnet['id'])[0]
        nuage_vport = self.vsd_client.get_vport(
            constants.SUBNETWORK,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.INHERITED,
                         nuage_vport[0]['addressSpoofing'])
        nuage_vport_vips = self.vsd_client.get_virtual_ip(
            constants.VPORT,
            nuage_vport[0]['ID'])
        valid_vips = [fixed_ips[0]["ip_address"],
                      allowed_address_pairs[0]['ip_address']]
        vip_mismatch = False
        if valid_vips and not nuage_vport_vips:
            vip_mismatch = True
        for nuage_vport_vip in nuage_vport_vips:
            if nuage_vport_vip['virtualIP'] not in valid_vips:
                vip_mismatch = True
            self.assertEqual(vip_mismatch, False)

        fixed_ips = [
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "10.0.0.6",
                "subnet_id": subnet["id"]
            }
        ]
        port = self.update_port(port=port, fixed_ips=fixed_ips)
        self.assertIsNotNone(port, "Unable to update port")
        nuage_vport = self.vsd_client.get_vport(
            constants.SUBNETWORK,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.ENABLED,
                         nuage_vport[0]['addressSpoofing'])
        nuage_vport_vips = self.vsd_client.get_virtual_ip(
            constants.VPORT,
            nuage_vport[0]['ID'])
        valid_vips = [fixed_ips[0]["ip_address"],
                      allowed_address_pairs[0]['ip_address']]
        vip_mismatch = False
        mac_mismatch = False
        if valid_vips and not nuage_vport_vips:
            vip_mismatch = True
        for nuage_vport_vip in nuage_vport_vips:
            if nuage_vport_vip['virtualIP'] not in valid_vips:
                vip_mismatch = True
            self.assertEqual(vip_mismatch, False)
            if nuage_vport_vip['MAC'] != port['mac_address']:
                mac_mismatch = True
            self.assertEqual(vip_mismatch, False)
            self.assertEqual(mac_mismatch, False)

    @decorators.attr(type='smoke')
    def test_nuage_port_create_fixed_ips_same_subnet_with_aap_router_attach(
            self):
        # Set up resources
        # Base resources
        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")
        router = self.create_router(
            admin_state_up=True,
            external_network_id=CONF.network.public_network_id)
        self.assertIsNotNone(router, "Unable to create router")

        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            }

        ]
        allowed_address_pairs = [{'ip_address': '10.0.0.6',
                                  'mac_address': 'fe:a0:36:4b:c8:70'}]
        port = self.create_port(network=network, fixed_ips=fixed_ips,
                                allowed_address_pairs=allowed_address_pairs)
        self.assertIsNotNone(port, "Unable to create port on network")

        vsd_vport_parent = self.vsd_client.get_global_resource(
            constants.L2_DOMAIN,
            filters='externalID',
            filter_value=subnet['id'])[0]
        nuage_vport = self.vsd_client.get_vport(
            constants.L2_DOMAIN,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.ENABLED,
                         nuage_vport[0]['addressSpoofing'])
        # Attach subnet
        self.create_router_interface(router_id=router["id"],
                                     subnet_id=subnet["id"])

        vsd_vport_parent = self.vsd_client.get_global_resource(
            constants.SUBNETWORK,
            filters='externalID',
            filter_value=subnet['id'])[0]
        nuage_vport_vips = self.vsd_client.get_virtual_ip(
            constants.VPORT,
            nuage_vport[0]['ID'])
        valid_vips = ['10.0.0.4', allowed_address_pairs[0]['ip_address']]
        vip_mismatch = False
        if valid_vips and not nuage_vport_vips:
            vip_mismatch = True
        for nuage_vport_vip in nuage_vport_vips:
            if nuage_vport_vip['virtualIP'] not in valid_vips:
                vip_mismatch = True
            self.assertEqual(vip_mismatch, False)
        nuage_vport = self.vsd_client.get_vport(
            constants.SUBNETWORK,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.INHERITED,
                         nuage_vport[0]['addressSpoofing'])

    @decorators.attr(type='smoke')
    def test_nuage_port_update_fixed_ips_same_subnet_with_aap_router_detach(
            self):
        # Set up resources
        # Base resources
        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")
        router = self.create_router(
            admin_state_up=True,
            external_network_id=CONF.network.public_network_id)
        self.assertIsNotNone(router, "Unable to create router")
        # Attach subnet
        self.create_router_interface(router_id=router["id"],
                                     subnet_id=subnet["id"], cleanup=False)
        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            }
        ]
        port = self.create_port(network=network, fixed_ips=fixed_ips)
        self.assertIsNotNone(port, "Unable to create port on network")
        vsd_vport_parent = self.vsd_client.get_global_resource(
            constants.SUBNETWORK,
            filters='externalID',
            filter_value=subnet['id'])[0]
        nuage_vport = self.vsd_client.get_vport(
            constants.SUBNETWORK,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.INHERITED,
                         nuage_vport[0]['addressSpoofing'])

        # update within subnet should succeed
        fixed_ips = [
            {
                "ip_address": "10.0.0.4",
                "subnet_id": subnet["id"]
            },
            {
                "ip_address": "10.0.0.5",
                "subnet_id": subnet["id"]
            }

        ]
        allowed_address_pairs = [{'ip_address': '10.0.0.6',
                                  'mac_address': 'fe:a0:36:4b:c8:70'}]
        port = self.update_port(port=port, fixed_ips=fixed_ips,
                                allowed_address_pairs=allowed_address_pairs)
        self.assertIsNotNone(port, "Unable to update port")
        nuage_vport = self.vsd_client.get_vport(
            constants.SUBNETWORK,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.INHERITED,
                         nuage_vport[0]['addressSpoofing'])
        valid_vips = ['10.0.0.4', allowed_address_pairs[0]['ip_address']]
        nuage_vport_vips = self.vsd_client.get_virtual_ip(
            constants.VPORT,
            nuage_vport[0]['ID'])
        vip_mismatch = False
        if valid_vips and not nuage_vport_vips:
            vip_mismatch = True
        for nuage_vport_vip in nuage_vport_vips:
            if nuage_vport_vip['virtualIP'] not in valid_vips:
                vip_mismatch = True
            self.assertEqual(vip_mismatch, False)

        self.admin_routers_client.remove_router_interface(
            router['id'],
            subnet_id=subnet['id'])
        vsd_vport_parent = self.vsd_client.get_global_resource(
            constants.L2_DOMAIN,
            filters='externalID',
            filter_value=subnet['id'])[0]
        nuage_vport = self.vsd_client.get_vport(
            constants.L2_DOMAIN,
            vsd_vport_parent['ID'],
            filters='externalID',
            filter_value=port['id'])
        self.assertEqual(constants.ENABLED,
                         nuage_vport[0]['addressSpoofing'])

    @decorators.attr(type='smoke')
    def test_delete_unbound_port_with_hanging_vminterface(self):
        # OPENSTACK-2797
        network = self.create_network()
        self.assertIsNotNone(network, "Unable to create network")

        subnet = self.create_subnet(network, cidr=IPNetwork("10.0.0.0/24"),
                                    mask_bits=28)
        self.assertIsNotNone(subnet, "Unable to create subnet")
        port = self.create_port(network=network, cleanup=False)
        self.addCleanup(self._try_delete,
                        self.manager.ports_client.delete_port,
                        port['id'])

        # Find vport
        l2domain = self.vsd.get_l2domain(by_subnet_id=subnet['id'])
        vport = self.vsd.get_vport(l2domain=l2domain, by_port_id=port['id'])

        # Create "Fake" VM interface to simulate following behavior:
        # -> Port is being bound -> VM created -> port deleted ->
        # Port not bound but leftover VM on VSD
        vminterface = self.vsd.vspk.NUVMInterface(
            name='test-fip-vm', vport_id=vport.id,
            external_id=self.vsd.external_id(port['id']),
            mac='E6:04:AA:7A:AA:86', ip_address='10.0.0.10')
        vm = self.vsd.vspk.NUVM(name='test-port-delete-vm',
                                uuid='1339f7f4-f7a0-445f-b257-8dbfaf0d6fc8',
                                external_id=self.vsd.external_id(
                                    '1339f7f4-f7a0-445f-b257-8dbfaf0d6fc8'),
                                interfaces=[vminterface])
        # Impersonate tenant user for appropriate permissions on VM
        self.vsd.session().impersonate(port['tenant_id'],
                                       self.default_netpartition_name)
        self.vsd.session().user.create_child(vm)
        self.vsd.session().stop_impersonate()

        # Delete port, VM should be deleted in this request
        self.delete_port(port)

        # Verify that vport is deleted
        vport = self.vsd.get_vport(l2domain=l2domain, by_port_id=port['id'])
        self.assertIsNone(vport, 'Vport not deleted by Port delete statement')
