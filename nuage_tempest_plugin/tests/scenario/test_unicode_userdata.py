# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from tempest.test import decorators

from nuage_tempest_plugin.lib.test.nuage_test import NuageBaseTest
from nuage_tempest_plugin.lib.topology import Topology

LOG = Topology.get_logger(__name__)
CONF = Topology.get_conf()


class UnicodeUserDataTest(NuageBaseTest):

    @classmethod
    def skip_checks(cls):
        super(UnicodeUserDataTest, cls).skip_checks()
        if not CONF.compute_feature_enabled.metadata_service:
            raise cls.skipException('Test requires functional metadata agent')

    def _test_unicode_userdata(self, l3=None, ip_versions=None):
        # Verifying that nuage-metadata-agent can handle user-data with
        # unicode.

        # Provision OpenStack network resources
        network = self.create_network()
        for ip_version in ip_versions:
            subnet = self.create_subnet(
                network, ip_version=ip_version,
                mask_bits=24 if ip_version == 4 else 64,
                enable_dhcp=True)
        if l3:
            router = self.create_router(
                external_network_id=CONF.network.public_network_id
            )
            self.router_attach(router, subnet)

        security_group = self.create_open_ssh_security_group()

        user_data = (u'\u0445\u0440\u0435\u043d-\u0441-'
                     u'\u0440\u0443\u0447\u043a\u043e\u0439')

        server1 = self.create_tenant_server(
            networks=[network],
            security_groups=[security_group],
            user_data=user_data,
            prepare_for_connectivity=True)

        curl_cmd = 'curl http://169.254.169.254/2009-04-04/user-data'
        result = server1.send(curl_cmd)
        self.assertIn(user_data, result)

    @decorators.attr(type='smoke')
    def test_unicode_userdata_l3_v4(self):
        self._test_unicode_userdata(l3=True, ip_versions=[4])

    @decorators.attr(type='smoke')
    def test_unicode_userdata_l2_v4(self):
        self._test_unicode_userdata(l3=False, ip_versions=[4])

    @decorators.attr(type='smoke')
    def test_unicode_userdata_l3_v6(self):
        self._test_unicode_userdata(l3=True, ip_versions=[6])

    @decorators.attr(type='smoke')
    def test_unicode_userdata_l2_v6(self):
        self._test_unicode_userdata(l3=False, ip_versions=[6])

    @decorators.attr(type='smoke')
    def test_unicode_userdata_l3_dualstack(self):
        self._test_unicode_userdata(l3=True, ip_versions=[6, 4])

    @decorators.attr(type='smoke')
    def test_unicode_userdata_l2_dualstack(self):
        self._test_unicode_userdata(l3=False, ip_versions=[6, 4])
