# Copyright 2015 OpenStack Foundation
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from tempest.api.network import base
from tempest.common import utils
from tempest.lib.common.utils import data_utils

from .external_id import ExternalId

from nuage_tempest_plugin.lib.test import nuage_test
from nuage_tempest_plugin.lib.topology import Topology
from nuage_tempest_plugin.lib.utils import constants as n_constants
from nuage_tempest_plugin.lib.utils import exceptions as n_exceptions
from nuage_tempest_plugin.services.nuage_client import NuageRestClient
from nuage_tempest_plugin.services.vpnaas.vpnaas_mixins import VPNMixin

CONF = Topology.get_conf()
LOG = Topology.get_logger(__name__)


class ExternalIdForVpnServiceTest(VPNMixin, base.BaseNetworkTest):
    class MatchingVsdVpnServiceObjects(object):
        def __init__(self, outer, vpn_service):
            self.test = outer
            self.vpn_service = vpn_service
            self.vsd_dummy_router = None
            self.vsd_floating_ip = None

        def has_dummy_router(self, with_external_id=None):
            # vsd dummy router object name is 'r_d_<router-id>'
            vsd_dummy_routers = self.test.nuage_client.get_resource(
                resource=n_constants.DOMAIN,
                filters='description',
                filter_value="r_d_" + self.vpn_service['router_id'])

            self.test.assertEqual(
                len(vsd_dummy_routers), 1,
                "Dummy router not found by VSD domain description")
            self.vsd_dummy_router = vsd_dummy_routers[0]

        def has_floating_ip(self, with_external_id=None):
            vsd_floating_ips = self.test.nuage_client.get_child_resource(
                resource=n_constants.DOMAIN,
                resource_id=self.vsd_dummy_router['ID'],
                child_resource=n_constants.FLOATINGIP,
                filters='address',
                filter_value=self.vpn_service['external_v4_ip'])

            self.test.assertEqual(
                len(vsd_floating_ips), 1,
                "VPN Floating IP router not found by IP address")

            if with_external_id is None:
                self.test.assertIsNone(vsd_floating_ips[0]['externalID'])
            else:
                vsd_floating_ips = \
                    self.test.nuage_client.get_child_resource(
                        resource=n_constants.DOMAIN,
                        resource_id=self.vsd_dummy_router['ID'],
                        child_resource=n_constants.FLOATINGIP,
                        filters='externalID',
                        filter_value=with_external_id)

                self.test.assertEqual(
                    len(vsd_floating_ips), 1,
                    "VPN Floating IP router not found by External ID")
                self.vsd_floating_ip = vsd_floating_ips[0]

        def verify_cannot_delete(self):
            # Can't delete floating IP in VSD
            self.test.assertRaisesRegex(
                n_exceptions.MultipleChoices,
                "Multiple choices",
                self.test.nuage_client.delete_resource,
                n_constants.FLOATINGIP, self.vsd_floating_ip['ID'])

    @classmethod
    def setUpClass(cls):
        super(ExternalIdForVpnServiceTest, cls).setUpClass()
        cls.test_upgrade = not Topology.within_ext_id_release()

    @classmethod
    def setup_clients(cls):
        super(ExternalIdForVpnServiceTest, cls).setup_clients()
        cls.nuage_client = NuageRestClient()

    @nuage_test.header()
    @utils.requires_ext(extension='vpnaas', service='network')
    def test_vpn_service_floating_ips(self):
        """test_vpn_service_floating_ips

        Create delete vpnservice with environment and also verifies the
        dummy router and subnet created by plugin
        """

        # Create a network 1
        network_a1 = self.create_network(
            network_name=data_utils.rand_name('networkA1'))
        subnet_a1 = self.create_subnet(network_a1)
        router_a1 = self.create_router(
            data_utils.rand_name('routerA1'),
            external_network_id=CONF.network.public_network_id)
        self.create_router_interface(router_a1['id'], subnet_a1['id'])

        # Creating the vpn service
        kwargs = {'name': 'vpnservice'}
        with self.vpnservice(router_a1['id'], subnet_a1['id'],
                             **kwargs) as created_vpnservice, \
                self.ikepolicy('ikepolicy') as created_ikepolicy, \
                self.ipsecpolicy('ipsecpolicy') as created_ipsecpolicy:

            self.vpnservice_client.list_vpnservice()

            ipnkwargs = {'name': 'ipsecconn'}
            with self.ipsecsiteconnection(
                    created_vpnservice['id'], created_ikepolicy['id'],
                    created_ipsecpolicy['id'],
                    peer_address='172.20.0.2',
                    peer_id='172.20.0.2',
                    peer_cidrs='2.0.0.0/24',
                    psk='secret',
                    **ipnkwargs) as created_ipsecsiteconnection:

                self.assertIsNotNone(created_ipsecsiteconnection)

                vpn_service_match = self.MatchingVsdVpnServiceObjects(
                    self, created_vpnservice)
                vpn_service_match.has_dummy_router(with_external_id=None)
                vpn_service_match.has_floating_ip(
                    with_external_id=ExternalId(created_vpnservice['id']
                                                ).at_cms_id())

                # Delete
                vpn_service_match.verify_cannot_delete()
