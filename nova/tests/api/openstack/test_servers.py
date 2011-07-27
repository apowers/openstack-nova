# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack LLC.
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

import base64
import json
import unittest
from xml.dom import minidom

import stubout
import webob

from nova import context
from nova import db
from nova import exception
from nova import flags
from nova import test
from nova import utils
import nova.api.openstack
from nova.api.openstack import servers
from nova.api.openstack import create_instance_helper
import nova.compute.api
from nova.compute import instance_types
from nova.compute import power_state
import nova.db.api
import nova.scheduler.api
from nova.db.sqlalchemy.models import Instance
from nova.db.sqlalchemy.models import InstanceMetadata
import nova.image.fake
import nova.rpc
from nova.tests.api.openstack import common
from nova.tests.api.openstack import fakes


FLAGS = flags.FLAGS
FLAGS.verbose = True


FAKE_UUID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'


def fake_gen_uuid():
    return FAKE_UUID


def return_server_by_id(context, id):
    return stub_instance(id)


def return_server_by_uuid(context, uuid):
    id = 1
    return stub_instance(id, uuid=uuid)


def return_server_with_addresses(private, public):
    def _return_server(context, id):
        return stub_instance(id, private_address=private,
                             public_addresses=public)
    return _return_server


def return_server_with_power_state(power_state):
    def _return_server(context, id):
        return stub_instance(id, power_state=power_state)
    return _return_server


def return_servers(context, user_id=1):
    return [stub_instance(i, user_id) for i in xrange(5)]


def return_servers_by_reservation(context, reservation_id=""):
    return [stub_instance(i, reservation_id) for i in xrange(5)]


def return_servers_by_reservation_empty(context, reservation_id=""):
    return []


def return_servers_from_child_zones_empty(*args, **kwargs):
    return []


def return_servers_from_child_zones(*args, **kwargs):
    class Server(object):
        pass

    zones = []
    for zone in xrange(3):
        servers = []
        for server_id in xrange(5):
            server = Server()
            server._info = stub_instance(server_id, reservation_id="child")
            servers.append(server)

        zones.append(("Zone%d" % zone, servers))
    return zones


def return_security_group(context, instance_id, security_group_id):
    pass


def instance_update(context, instance_id, kwargs):
    return stub_instance(instance_id)


def instance_addresses(context, instance_id):
    return None


def stub_instance(id, user_id=1, private_address=None, public_addresses=None,
                  host=None, power_state=0, reservation_id="",
                  uuid=FAKE_UUID):
    metadata = []
    metadata.append(InstanceMetadata(key='seq', value=id))

    inst_type = instance_types.get_instance_type_by_flavor_id(1)

    if public_addresses is None:
        public_addresses = list()

    if host is not None:
        host = str(host)

    # ReservationID isn't sent back, hack it in there.
    server_name = "server%s" % id
    if reservation_id != "":
        server_name = "reservation_%s" % (reservation_id, )

    instance = {
        "id": int(id),
        "admin_pass": "",
        "user_id": user_id,
        "project_id": "",
        "image_ref": "10",
        "kernel_id": "",
        "ramdisk_id": "",
        "launch_index": 0,
        "key_name": "",
        "key_data": "",
        "state": power_state,
        "state_description": "",
        "memory_mb": 0,
        "vcpus": 0,
        "local_gb": 0,
        "hostname": "",
        "host": host,
        "instance_type": dict(inst_type),
        "user_data": "",
        "reservation_id": reservation_id,
        "mac_address": "",
        "scheduled_at": utils.utcnow(),
        "launched_at": utils.utcnow(),
        "terminated_at": utils.utcnow(),
        "availability_zone": "",
        "display_name": server_name,
        "display_description": "",
        "locked": False,
        "metadata": metadata,
        "uuid": uuid}

    instance["fixed_ips"] = {
        "address": private_address,
        "floating_ips": [{"address":ip} for ip in public_addresses]}

    return instance


def fake_compute_api(cls, req, id):
    return True


def find_host(self, context, instance_id):
    return "nova"


class MockSetAdminPassword(object):
    def __init__(self):
        self.instance_id = None
        self.password = None

    def __call__(self, context, instance_id, password):
        self.instance_id = instance_id
        self.password = password


class ServersTest(test.TestCase):

    def setUp(self):
        super(ServersTest, self).setUp()
        self.stubs = stubout.StubOutForTesting()
        fakes.FakeAuthManager.reset_fake_data()
        fakes.FakeAuthDatabase.data = {}
        fakes.stub_out_networking(self.stubs)
        fakes.stub_out_rate_limiting(self.stubs)
        fakes.stub_out_auth(self.stubs)
        fakes.stub_out_key_pair_funcs(self.stubs)
        fakes.stub_out_image_service(self.stubs)
        self.stubs.Set(utils, 'gen_uuid', fake_gen_uuid)
        self.stubs.Set(nova.db.api, 'instance_get_all', return_servers)
        self.stubs.Set(nova.db.api, 'instance_get', return_server_by_id)
        self.stubs.Set(nova.db, 'instance_get_by_uuid',
                       return_server_by_uuid)
        self.stubs.Set(nova.db.api, 'instance_get_all_by_user',
                       return_servers)
        self.stubs.Set(nova.db.api, 'instance_add_security_group',
                       return_security_group)
        self.stubs.Set(nova.db.api, 'instance_update', instance_update)
        self.stubs.Set(nova.db.api, 'instance_get_fixed_addresses',
                       instance_addresses)
        self.stubs.Set(nova.db.api, 'instance_get_floating_address',
                       instance_addresses)
        self.stubs.Set(nova.compute.API, 'pause', fake_compute_api)
        self.stubs.Set(nova.compute.API, 'unpause', fake_compute_api)
        self.stubs.Set(nova.compute.API, 'suspend', fake_compute_api)
        self.stubs.Set(nova.compute.API, 'resume', fake_compute_api)
        self.stubs.Set(nova.compute.API, "get_diagnostics", fake_compute_api)
        self.stubs.Set(nova.compute.API, "get_actions", fake_compute_api)
        self.allow_admin = FLAGS.allow_admin_api

        self.webreq = common.webob_factory('/v1.0/servers')

    def tearDown(self):
        self.stubs.UnsetAll()
        FLAGS.allow_admin_api = self.allow_admin
        super(ServersTest, self).tearDown()

    def test_get_server_by_id(self):
        req = webob.Request.blank('/v1.0/servers/1')
        res = req.get_response(fakes.wsgi_app())
        res_dict = json.loads(res.body)
        self.assertEqual(res_dict['server']['id'], 1)
        self.assertEqual(res_dict['server']['name'], 'server1')

    def test_get_server_by_uuid(self):
        """
        The steps involved with resolving a UUID are pretty complicated;
        here's what's happening in this scenario:

        1. Show is calling `routing_get`

        2. `routing_get` is wrapped by `reroute_compute` which does the work
           of resolving requests to child zones.

        3. `reroute_compute` looks up the UUID by hitting the stub
           (returns_server_by_uuid)

        4. Since the stub return that the record exists, `reroute_compute`
           considers the request to be 'zone local', so it replaces the UUID
           in the argument list with an integer ID and then calls the inner
           function ('get').

        5. The call to `get` hits the other stub 'returns_server_by_id` which
           has the UUID set to FAKE_UUID

        So, counterintuitively, we call `get` twice on the `show` command.
        """
        req = webob.Request.blank('/v1.0/servers/%s' % FAKE_UUID)
        res = req.get_response(fakes.wsgi_app())
        res_dict = json.loads(res.body)
        self.assertEqual(res_dict['server']['id'], 1)
        self.assertEqual(res_dict['server']['uuid'], FAKE_UUID)
        self.assertEqual(res_dict['server']['name'], 'server1')

    def test_get_server_by_id_v1_1(self):
        req = webob.Request.blank('/v1.1/servers/1')
        res = req.get_response(fakes.wsgi_app())
        res_dict = json.loads(res.body)
        self.assertEqual(res_dict['server']['id'], 1)
        self.assertEqual(res_dict['server']['name'], 'server1')

        expected_links = [
            {
                "rel": "self",
                "href": "http://localhost/v1.1/servers/1",
            },
            {
                "rel": "bookmark",
                "type": "application/json",
                "href": "http://localhost/v1.1/servers/1",
            },
            {
                "rel": "bookmark",
                "type": "application/xml",
                "href": "http://localhost/v1.1/servers/1",
            },
        ]

        self.assertEqual(res_dict['server']['links'], expected_links)

    def test_get_server_by_id_with_addresses_xml(self):
        private = "192.168.0.3"
        public = ["1.2.3.4"]
        new_return_server = return_server_with_addresses(private, public)
        self.stubs.Set(nova.db.api, 'instance_get', new_return_server)
        req = webob.Request.blank('/v1.0/servers/1')
        req.headers['Accept'] = 'application/xml'
        res = req.get_response(fakes.wsgi_app())
        dom = minidom.parseString(res.body)
        server = dom.childNodes[0]
        self.assertEquals(server.nodeName, 'server')
        self.assertEquals(server.getAttribute('id'), '1')
        self.assertEquals(server.getAttribute('name'), 'server1')
        (public,) = server.getElementsByTagName('public')
        (ip,) = public.getElementsByTagName('ip')
        self.assertEquals(ip.getAttribute('addr'), '1.2.3.4')
        (private,) = server.getElementsByTagName('private')
        (ip,) = private.getElementsByTagName('ip')
        self.assertEquals(ip.getAttribute('addr'),  '192.168.0.3')

    def test_get_server_by_id_with_addresses(self):
        private = "192.168.0.3"
        public = ["1.2.3.4"]
        new_return_server = return_server_with_addresses(private, public)
        self.stubs.Set(nova.db.api, 'instance_get', new_return_server)
        req = webob.Request.blank('/v1.0/servers/1')
        res = req.get_response(fakes.wsgi_app())
        res_dict = json.loads(res.body)
        self.assertEqual(res_dict['server']['id'], 1)
        self.assertEqual(res_dict['server']['name'], 'server1')
        addresses = res_dict['server']['addresses']
        self.assertEqual(len(addresses["public"]), len(public))
        self.assertEqual(addresses["public"][0], public[0])
        self.assertEqual(len(addresses["private"]), 1)
        self.assertEqual(addresses["private"][0], private)

    def test_get_server_addresses_v1_0(self):
        private = '192.168.0.3'
        public = ['1.2.3.4']
        new_return_server = return_server_with_addresses(private, public)
        self.stubs.Set(nova.db.api, 'instance_get', new_return_server)
        req = webob.Request.blank('/v1.0/servers/1/ips')
        res = req.get_response(fakes.wsgi_app())
        res_dict = json.loads(res.body)
        self.assertEqual(res_dict, {
            'addresses': {'public': public, 'private': [private]}})

    def test_get_server_addresses_xml_v1_0(self):
        private_expected = "192.168.0.3"
        public_expected = ["1.2.3.4"]
        new_return_server = return_server_with_addresses(private_expected,
                                                         public_expected)
        self.stubs.Set(nova.db.api, 'instance_get', new_return_server)
        req = webob.Request.blank('/v1.0/servers/1/ips')
        req.headers['Accept'] = 'application/xml'
        res = req.get_response(fakes.wsgi_app())
        dom = minidom.parseString(res.body)
        (addresses,) = dom.childNodes
        self.assertEquals(addresses.nodeName, 'addresses')
        (public,) = addresses.getElementsByTagName('public')
        (ip,) = public.getElementsByTagName('ip')
        self.assertEquals(ip.getAttribute('addr'), public_expected[0])
        (private,) = addresses.getElementsByTagName('private')
        (ip,) = private.getElementsByTagName('ip')
        self.assertEquals(ip.getAttribute('addr'), private_expected)

    def test_get_server_addresses_public_v1_0(self):
        private = "192.168.0.3"
        public = ["1.2.3.4"]
        new_return_server = return_server_with_addresses(private, public)
        self.stubs.Set(nova.db.api, 'instance_get', new_return_server)
        req = webob.Request.blank('/v1.0/servers/1/ips/public')
        res = req.get_response(fakes.wsgi_app())
        res_dict = json.loads(res.body)
        self.assertEqual(res_dict, {'public': public})

    def test_get_server_addresses_private_v1_0(self):
        private = "192.168.0.3"
        public = ["1.2.3.4"]
        new_return_server = return_server_with_addresses(private, public)
        self.stubs.Set(nova.db.api, 'instance_get', new_return_server)
        req = webob.Request.blank('/v1.0/servers/1/ips/private')
        res = req.get_response(fakes.wsgi_app())
        res_dict = json.loads(res.body)
        self.assertEqual(res_dict, {'private': [private]})

    def test_get_server_addresses_public_xml_v1_0(self):
        private = "192.168.0.3"
        public = ["1.2.3.4"]
        new_return_server = return_server_with_addresses(private, public)
        self.stubs.Set(nova.db.api, 'instance_get', new_return_server)
        req = webob.Request.blank('/v1.0/servers/1/ips/public')
        req.headers['Accept'] = 'application/xml'
        res = req.get_response(fakes.wsgi_app())
        dom = minidom.parseString(res.body)
        (public_node,) = dom.childNodes
        self.assertEquals(public_node.nodeName, 'public')
        (ip,) = public_node.getElementsByTagName('ip')
        self.assertEquals(ip.getAttribute('addr'), public[0])

    def test_get_server_addresses_private_xml_v1_0(self):
        private = "192.168.0.3"
        public = ["1.2.3.4"]
        new_return_server = return_server_with_addresses(private, public)
        self.stubs.Set(nova.db.api, 'instance_get', new_return_server)
        req = webob.Request.blank('/v1.0/servers/1/ips/private')
        req.headers['Accept'] = 'application/xml'
        res = req.get_response(fakes.wsgi_app())
        dom = minidom.parseString(res.body)
        (private_node,) = dom.childNodes
        self.assertEquals(private_node.nodeName, 'private')
        (ip,) = private_node.getElementsByTagName('ip')
        self.assertEquals(ip.getAttribute('addr'), private)

    def test_get_server_by_id_with_addresses_v1_1(self):
        private = "192.168.0.3"
        public = ["1.2.3.4"]
        new_return_server = return_server_with_addresses(private, public)
        self.stubs.Set(nova.db.api, 'instance_get', new_return_server)
        req = webob.Request.blank('/v1.1/servers/1')
        res = req.get_response(fakes.wsgi_app())
        res_dict = json.loads(res.body)
        self.assertEqual(res_dict['server']['id'], 1)
        self.assertEqual(res_dict['server']['name'], 'server1')
        addresses = res_dict['server']['addresses']
        # RM(4047): Figure otu what is up with the 1.1 api and multi-nic
        #self.assertEqual(len(addresses["public"]), len(public))
        #self.assertEqual(addresses["public"][0],
        #    {"version": 4, "addr": public[0]})
        #self.assertEqual(len(addresses["private"]), 1)
        #self.assertEqual(addresses["private"][0],
        #    {"version": 4, "addr": private})

    def test_get_server_list(self):
        req = webob.Request.blank('/v1.0/servers')
        res = req.get_response(fakes.wsgi_app())
        res_dict = json.loads(res.body)

        i = 0
        for s in res_dict['servers']:
            self.assertEqual(s['id'], i)
            self.assertEqual(s['name'], 'server%d' % i)
            self.assertEqual(s.get('imageId', None), None)
            i += 1

    def test_get_server_list_with_reservation_id(self):
        self.stubs.Set(nova.db.api, 'instance_get_all_by_reservation',
                       return_servers_by_reservation)
        self.stubs.Set(nova.scheduler.api, 'call_zone_method',
                       return_servers_from_child_zones)
        req = webob.Request.blank('/v1.0/servers?reservation_id=foo')
        res = req.get_response(fakes.wsgi_app())
        res_dict = json.loads(res.body)

        i = 0
        for s in res_dict['servers']:
            if '_is_precooked' in s:
                self.assertEqual(s.get('reservation_id'), 'child')
            else:
                self.assertEqual(s.get('name'), 'server%d' % i)
                i += 1

    def test_get_server_list_with_reservation_id_empty(self):
        self.stubs.Set(nova.db.api, 'instance_get_all_by_reservation',
                       return_servers_by_reservation_empty)
        self.stubs.Set(nova.scheduler.api, 'call_zone_method',
                       return_servers_from_child_zones_empty)
        req = webob.Request.blank('/v1.0/servers/detail?reservation_id=foo')
        res = req.get_response(fakes.wsgi_app())
        res_dict = json.loads(res.body)

        i = 0
        for s in res_dict['servers']:
            if '_is_precooked' in s:
                self.assertEqual(s.get('reservation_id'), 'child')
            else:
                self.assertEqual(s.get('name'), 'server%d' % i)
                i += 1

    def test_get_server_list_with_reservation_id_details(self):
        self.stubs.Set(nova.db.api, 'instance_get_all_by_reservation',
                       return_servers_by_reservation)
        self.stubs.Set(nova.scheduler.api, 'call_zone_method',
                       return_servers_from_child_zones)
        req = webob.Request.blank('/v1.0/servers/detail?reservation_id=foo')
        res = req.get_response(fakes.wsgi_app())
        res_dict = json.loads(res.body)

        i = 0
        for s in res_dict['servers']:
            if '_is_precooked' in s:
                self.assertEqual(s.get('reservation_id'), 'child')
            else:
                self.assertEqual(s.get('name'), 'server%d' % i)
                i += 1

    def test_get_server_list_v1_1(self):
        req = webob.Request.blank('/v1.1/servers')
        res = req.get_response(fakes.wsgi_app())
        res_dict = json.loads(res.body)

        for i, s in enumerate(res_dict['servers']):
            self.assertEqual(s['id'], i)
            self.assertEqual(s['name'], 'server%d' % i)
            self.assertEqual(s.get('imageId', None), None)

            expected_links = [
            {
                "rel": "self",
                "href": "http://localhost/v1.1/servers/%d" % (i,),
            },
            {
                "rel": "bookmark",
                "type": "application/json",
                "href": "http://localhost/v1.1/servers/%d" % (i,),
            },
            {
                "rel": "bookmark",
                "type": "application/xml",
                "href": "http://localhost/v1.1/servers/%d" % (i,),
            },
        ]

        self.assertEqual(s['links'], expected_links)

    def test_get_servers_with_limit(self):
        req = webob.Request.blank('/v1.0/servers?limit=3')
        res = req.get_response(fakes.wsgi_app())
        servers = json.loads(res.body)['servers']
        self.assertEqual([s['id'] for s in servers], [0, 1, 2])

        req = webob.Request.blank('/v1.0/servers?limit=aaa')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)
        self.assertTrue('limit' in res.body)

    def test_get_servers_with_offset(self):
        req = webob.Request.blank('/v1.0/servers?offset=2')
        res = req.get_response(fakes.wsgi_app())
        servers = json.loads(res.body)['servers']
        self.assertEqual([s['id'] for s in servers], [2, 3, 4])

        req = webob.Request.blank('/v1.0/servers?offset=aaa')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)
        self.assertTrue('offset' in res.body)

    def test_get_servers_with_limit_and_offset(self):
        req = webob.Request.blank('/v1.0/servers?limit=2&offset=1')
        res = req.get_response(fakes.wsgi_app())
        servers = json.loads(res.body)['servers']
        self.assertEqual([s['id'] for s in servers], [1, 2])

    def test_get_servers_with_bad_limit(self):
        req = webob.Request.blank('/v1.0/servers?limit=asdf&offset=1')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)
        self.assertTrue(res.body.find('limit param') > -1)

    def test_get_servers_with_bad_offset(self):
        req = webob.Request.blank('/v1.0/servers?limit=2&offset=asdf')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)
        self.assertTrue(res.body.find('offset param') > -1)

    def test_get_servers_with_marker(self):
        req = webob.Request.blank('/v1.1/servers?marker=2')
        res = req.get_response(fakes.wsgi_app())
        servers = json.loads(res.body)['servers']
        self.assertEqual([s['id'] for s in servers], [3, 4])

    def test_get_servers_with_limit_and_marker(self):
        req = webob.Request.blank('/v1.1/servers?limit=2&marker=1')
        res = req.get_response(fakes.wsgi_app())
        servers = json.loads(res.body)['servers']
        self.assertEqual([s['id'] for s in servers], [2, 3])

    def test_get_servers_with_bad_marker(self):
        req = webob.Request.blank('/v1.1/servers?limit=2&marker=asdf')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)
        self.assertTrue(res.body.find('marker param') > -1)

    def _setup_for_create_instance(self):
        """Shared implementation for tests below that create instance"""
        def instance_create(context, inst):
            return {'id': 1, 'display_name': 'server_test',
                    'uuid': FAKE_UUID}

        def server_update(context, id, params):
            return instance_create(context, id)

        def fake_method(*args, **kwargs):
            pass

        def project_get_networks(context, user_id):
            return dict(id='1', host='localhost')

        def queue_get_for(context, *args):
            return 'network_topic'

        def kernel_ramdisk_mapping(*args, **kwargs):
            return (1, 1)

        def image_id_from_hash(*args, **kwargs):
            return 2

        self.stubs.Set(nova.db.api, 'project_get_networks',
                       project_get_networks)
        self.stubs.Set(nova.db.api, 'instance_create', instance_create)
        self.stubs.Set(nova.rpc, 'cast', fake_method)
        self.stubs.Set(nova.rpc, 'call', fake_method)
        self.stubs.Set(nova.db.api, 'instance_update',
            server_update)
        self.stubs.Set(nova.db.api, 'queue_get_for', queue_get_for)
        self.stubs.Set(nova.network.manager.VlanManager, 'allocate_fixed_ip',
            fake_method)
        self.stubs.Set(
            nova.api.openstack.create_instance_helper.CreateInstanceHelper,
            "_get_kernel_ramdisk_from_image", kernel_ramdisk_mapping)
        self.stubs.Set(nova.compute.api.API, "_find_host", find_host)

    def _test_create_instance_helper(self):
        self._setup_for_create_instance()

        body = dict(server=dict(
            name='server_test', imageId=3, flavorId=2,
            metadata={'hello': 'world', 'open': 'stack'},
            personality={}))
        req = webob.Request.blank('/v1.0/servers')
        req.method = 'POST'
        req.body = json.dumps(body)
        req.headers["content-type"] = "application/json"

        res = req.get_response(fakes.wsgi_app())

        server = json.loads(res.body)['server']
        self.assertEqual(16, len(server['adminPass']))
        self.assertEqual('server_test', server['name'])
        self.assertEqual(1, server['id'])
        self.assertEqual(2, server['flavorId'])
        self.assertEqual(3, server['imageId'])
        self.assertEqual(FAKE_UUID, server['uuid'])
        self.assertEqual(res.status_int, 200)

    def test_create_instance(self):
        self._test_create_instance_helper()

    def test_create_instance_has_uuid(self):
        """Tests at the db-layer instead of API layer since that's where the
           UUID is generated
        """
        ctxt = context.RequestContext(1, 1)
        values = {}
        instance = nova.db.api.instance_create(ctxt, values)
        expected = FAKE_UUID
        self.assertEqual(instance['uuid'], expected)

    def test_create_instance_via_zones(self):
        """Server generated ReservationID"""
        self._setup_for_create_instance()
        FLAGS.allow_admin_api = True

        body = dict(server=dict(
            name='server_test', imageId=3, flavorId=2,
            metadata={'hello': 'world', 'open': 'stack'},
            personality={}))
        req = webob.Request.blank('/v1.0/zones/boot')
        req.method = 'POST'
        req.body = json.dumps(body)
        req.headers["content-type"] = "application/json"

        res = req.get_response(fakes.wsgi_app())

        reservation_id = json.loads(res.body)['reservation_id']
        self.assertEqual(res.status_int, 200)
        self.assertNotEqual(reservation_id, "")
        self.assertNotEqual(reservation_id, None)
        self.assertTrue(len(reservation_id) > 1)

    def test_create_instance_via_zones_with_resid(self):
        """User supplied ReservationID"""
        self._setup_for_create_instance()
        FLAGS.allow_admin_api = True

        body = dict(server=dict(
            name='server_test', imageId=3, flavorId=2,
            metadata={'hello': 'world', 'open': 'stack'},
            personality={}, reservation_id='myresid'))
        req = webob.Request.blank('/v1.0/zones/boot')
        req.method = 'POST'
        req.body = json.dumps(body)
        req.headers["content-type"] = "application/json"

        res = req.get_response(fakes.wsgi_app())

        reservation_id = json.loads(res.body)['reservation_id']
        self.assertEqual(res.status_int, 200)
        self.assertEqual(reservation_id, "myresid")

    def test_create_instance_no_key_pair(self):
        fakes.stub_out_key_pair_funcs(self.stubs, have_key_pair=False)
        self._test_create_instance_helper()

    def test_create_instance_no_name(self):
        self._setup_for_create_instance()

        body = {
            'server': {
                'imageId': 3,
                'flavorId': 1,
                'metadata': {
                    'hello': 'world',
                    'open': 'stack',
                },
                'personality': {},
            },
        }

        req = webob.Request.blank('/v1.0/servers')
        req.method = 'POST'
        req.body = json.dumps(body)
        req.headers["content-type"] = "application/json"
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

    def test_create_instance_nonstring_name(self):
        self._setup_for_create_instance()

        body = {
            'server': {
                'name': 12,
                'imageId': 3,
                'flavorId': 1,
                'metadata': {
                    'hello': 'world',
                    'open': 'stack',
                },
                'personality': {},
            },
        }

        req = webob.Request.blank('/v1.0/servers')
        req.method = 'POST'
        req.body = json.dumps(body)
        req.headers["content-type"] = "application/json"
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

    def test_create_instance_whitespace_name(self):
        self._setup_for_create_instance()

        body = {
            'server': {
                'name': '    ',
                'imageId': 3,
                'flavorId': 1,
                'metadata': {
                    'hello': 'world',
                    'open': 'stack',
                },
                'personality': {},
            },
        }

        req = webob.Request.blank('/v1.0/servers')
        req.method = 'POST'
        req.body = json.dumps(body)
        req.headers["content-type"] = "application/json"
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

    def test_create_instance_v1_1(self):
        self._setup_for_create_instance()

        image_href = 'http://localhost/v1.1/images/2'
        flavor_ref = 'http://localhost/v1.1/flavors/3'
        body = {
            'server': {
                'name': 'server_test',
                'imageRef': image_href,
                'flavorRef': flavor_ref,
                'metadata': {
                    'hello': 'world',
                    'open': 'stack',
                },
                'personality': {},
            },
        }

        req = webob.Request.blank('/v1.1/servers')
        req.method = 'POST'
        req.body = json.dumps(body)
        req.headers["content-type"] = "application/json"

        res = req.get_response(fakes.wsgi_app())

        server = json.loads(res.body)['server']
        self.assertEqual(16, len(server['adminPass']))
        self.assertEqual('server_test', server['name'])
        self.assertEqual(1, server['id'])
        self.assertEqual(flavor_ref, server['flavorRef'])
        self.assertEqual(image_href, server['imageRef'])
        self.assertEqual(res.status_int, 200)

    def test_create_instance_v1_1_bad_href(self):
        self._setup_for_create_instance()

        image_href = 'http://localhost/v1.1/images/asdf'
        flavor_ref = 'http://localhost/v1.1/flavors/3'
        body = dict(server=dict(
            name='server_test', imageRef=image_href, flavorRef=flavor_ref,
            metadata={'hello': 'world', 'open': 'stack'},
            personality={}))
        req = webob.Request.blank('/v1.1/servers')
        req.method = 'POST'
        req.body = json.dumps(body)
        req.headers["content-type"] = "application/json"
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

    def test_create_instance_v1_1_local_href(self):
        self._setup_for_create_instance()

        image_id = 2
        flavor_ref = 'http://localhost/v1.1/flavors/3'
        body = {
            'server': {
                'name': 'server_test',
                'imageRef': image_id,
                'flavorRef': flavor_ref,
            },
        }

        req = webob.Request.blank('/v1.1/servers')
        req.method = 'POST'
        req.body = json.dumps(body)
        req.headers["content-type"] = "application/json"

        res = req.get_response(fakes.wsgi_app())

        server = json.loads(res.body)['server']
        self.assertEqual(1, server['id'])
        self.assertEqual(flavor_ref, server['flavorRef'])
        self.assertEqual(image_id, server['imageRef'])
        self.assertEqual(res.status_int, 200)

    def test_create_instance_with_admin_pass_v1_0(self):
        self._setup_for_create_instance()

        body = {
            'server': {
                'name': 'test-server-create',
                'imageId': 3,
                'flavorId': 1,
                'adminPass': 'testpass',
            },
        }

        req = webob.Request.blank('/v1.0/servers')
        req.method = 'POST'
        req.body = json.dumps(body)
        req.headers['content-type'] = "application/json"
        res = req.get_response(fakes.wsgi_app())
        res = json.loads(res.body)
        self.assertNotEqual(res['server']['adminPass'],
                            body['server']['adminPass'])

    def test_create_instance_with_admin_pass_v1_1(self):
        self._setup_for_create_instance()

        image_href = 'http://localhost/v1.1/images/2'
        flavor_ref = 'http://localhost/v1.1/flavors/3'
        body = {
            'server': {
                'name': 'server_test',
                'imageRef': image_href,
                'flavorRef': flavor_ref,
                'adminPass': 'testpass',
            },
        }

        req = webob.Request.blank('/v1.1/servers')
        req.method = 'POST'
        req.body = json.dumps(body)
        req.headers['content-type'] = "application/json"
        res = req.get_response(fakes.wsgi_app())
        server = json.loads(res.body)['server']
        self.assertEqual(server['adminPass'], body['server']['adminPass'])

    def test_create_instance_with_empty_admin_pass_v1_1(self):
        self._setup_for_create_instance()

        image_href = 'http://localhost/v1.1/images/2'
        flavor_ref = 'http://localhost/v1.1/flavors/3'
        body = {
            'server': {
                'name': 'server_test',
                'imageRef': image_href,
                'flavorRef': flavor_ref,
                'adminPass': '',
            },
        }

        req = webob.Request.blank('/v1.1/servers')
        req.method = 'POST'
        req.body = json.dumps(body)
        req.headers['content-type'] = "application/json"
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

    def test_update_no_body(self):
        req = webob.Request.blank('/v1.0/servers/1')
        req.method = 'PUT'
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 422)

    def test_update_nonstring_name(self):
        """ Confirm that update is filtering params """
        inst_dict = dict(name=12, adminPass='bacon')
        self.body = json.dumps(dict(server=inst_dict))

        req = webob.Request.blank('/v1.0/servers/1')
        req.method = 'PUT'
        req.content_type = "application/json"
        req.body = self.body
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

    def test_update_whitespace_name(self):
        """ Confirm that update is filtering params """
        inst_dict = dict(name='   ', adminPass='bacon')
        self.body = json.dumps(dict(server=inst_dict))

        req = webob.Request.blank('/v1.0/servers/1')
        req.method = 'PUT'
        req.content_type = "application/json"
        req.body = self.body
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

    def test_update_null_name(self):
        """ Confirm that update is filtering params """
        inst_dict = dict(name='', adminPass='bacon')
        self.body = json.dumps(dict(server=inst_dict))

        req = webob.Request.blank('/v1.0/servers/1')
        req.method = 'PUT'
        req.content_type = "application/json"
        req.body = self.body
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

    def test_update_server_v1_0(self):
        inst_dict = dict(name='server_test', adminPass='bacon')
        self.body = json.dumps(dict(server=inst_dict))

        def server_update(context, id, params):
            filtered_dict = dict(display_name='server_test')
            self.assertEqual(params, filtered_dict)
            return filtered_dict

        self.stubs.Set(nova.db.api, 'instance_update',
            server_update)
        self.stubs.Set(nova.compute.api.API, "_find_host", find_host)
        mock_method = MockSetAdminPassword()
        self.stubs.Set(nova.compute.api.API, 'set_admin_password', mock_method)

        req = webob.Request.blank('/v1.0/servers/1')
        req.method = 'PUT'
        req.content_type = "application/json"
        req.body = self.body
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 204)
        self.assertEqual(mock_method.instance_id, '1')
        self.assertEqual(mock_method.password, 'bacon')

    def test_update_server_adminPass_ignored_v1_1(self):
        inst_dict = dict(name='server_test', adminPass='bacon')
        self.body = json.dumps(dict(server=inst_dict))

        def server_update(context, id, params):
            filtered_dict = dict(display_name='server_test')
            self.assertEqual(params, filtered_dict)
            return filtered_dict

        self.stubs.Set(nova.db.api, 'instance_update',
            server_update)

        req = webob.Request.blank('/v1.1/servers/1')
        req.method = 'PUT'
        req.content_type = "application/json"
        req.body = self.body
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 204)

    def test_create_backup_schedules(self):
        req = webob.Request.blank('/v1.0/servers/1/backup_schedule')
        req.method = 'POST'
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 501)

    def test_delete_backup_schedules(self):
        req = webob.Request.blank('/v1.0/servers/1/backup_schedule/1')
        req.method = 'DELETE'
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 501)

    def test_get_server_backup_schedules(self):
        req = webob.Request.blank('/v1.0/servers/1/backup_schedule')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 501)

    def test_get_server_backup_schedule(self):
        req = webob.Request.blank('/v1.0/servers/1/backup_schedule/1')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 501)

    def test_server_backup_schedule_deprecated_v1_1(self):
        req = webob.Request.blank('/v1.1/servers/1/backup_schedule')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 404)

    def test_get_all_server_details_xml_v1_0(self):
        req = webob.Request.blank('/v1.0/servers/detail')
        req.headers['Accept'] = 'application/xml'
        res = req.get_response(fakes.wsgi_app())
        dom = minidom.parseString(res.body)
        for i, server in enumerate(dom.getElementsByTagName('server')):
            self.assertEqual(server.getAttribute('id'), str(i))
            self.assertEqual(server.getAttribute('hostId'), '')
            self.assertEqual(server.getAttribute('name'), 'server%d' % i)
            self.assertEqual(server.getAttribute('imageId'), '10')
            self.assertEqual(server.getAttribute('status'), 'BUILD')
            (meta,) = server.getElementsByTagName('meta')
            self.assertEqual(meta.getAttribute('key'), 'seq')
            self.assertEqual(meta.firstChild.data.strip(), str(i))

    def test_get_all_server_details_v1_0(self):
        req = webob.Request.blank('/v1.0/servers/detail')
        res = req.get_response(fakes.wsgi_app())
        res_dict = json.loads(res.body)

        for i, s in enumerate(res_dict['servers']):
            self.assertEqual(s['id'], i)
            self.assertEqual(s['hostId'], '')
            self.assertEqual(s['name'], 'server%d' % i)
            self.assertEqual(s['imageId'], 10)
            self.assertEqual(s['flavorId'], 1)
            self.assertEqual(s['status'], 'BUILD')
            self.assertEqual(s['metadata']['seq'], str(i))

    def test_get_all_server_details_v1_1(self):
        req = webob.Request.blank('/v1.1/servers/detail')
        res = req.get_response(fakes.wsgi_app())
        res_dict = json.loads(res.body)

        for i, s in enumerate(res_dict['servers']):
            self.assertEqual(s['id'], i)
            self.assertEqual(s['hostId'], '')
            self.assertEqual(s['name'], 'server%d' % i)
            self.assertEqual(s['imageRef'], 10)
            self.assertEqual(s['flavorRef'], 'http://localhost/v1.1/flavors/1')
            self.assertEqual(s['status'], 'BUILD')
            self.assertEqual(s['metadata']['seq'], str(i))

    def test_get_all_server_details_with_host(self):
        '''
        We want to make sure that if two instances are on the same host, then
        they return the same hostId. If two instances are on different hosts,
        they should return different hostId's. In this test, there are 5
        instances - 2 on one host and 3 on another.
        '''

        def return_servers_with_host(context, user_id=1):
            return [stub_instance(i, 1, None, None, i % 2) for i in xrange(5)]

        self.stubs.Set(nova.db.api, 'instance_get_all_by_user',
            return_servers_with_host)

        req = webob.Request.blank('/v1.0/servers/detail')
        res = req.get_response(fakes.wsgi_app())
        res_dict = json.loads(res.body)

        server_list = res_dict['servers']
        host_ids = [server_list[0]['hostId'], server_list[1]['hostId']]
        self.assertTrue(host_ids[0] and host_ids[1])
        self.assertNotEqual(host_ids[0], host_ids[1])

        for i, s in enumerate(res_dict['servers']):
            self.assertEqual(s['id'], i)
            self.assertEqual(s['hostId'], host_ids[i % 2])
            self.assertEqual(s['name'], 'server%d' % i)
            self.assertEqual(s['imageId'], 10)
            self.assertEqual(s['flavorId'], 1)

    def test_server_pause(self):
        FLAGS.allow_admin_api = True
        body = dict(server=dict(
            name='server_test', imageId=2, flavorId=2, metadata={},
            personality={}))
        req = webob.Request.blank('/v1.0/servers/1/pause')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)

    def test_server_unpause(self):
        FLAGS.allow_admin_api = True
        body = dict(server=dict(
            name='server_test', imageId=2, flavorId=2, metadata={},
            personality={}))
        req = webob.Request.blank('/v1.0/servers/1/unpause')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)

    def test_server_suspend(self):
        FLAGS.allow_admin_api = True
        body = dict(server=dict(
            name='server_test', imageId=2, flavorId=2, metadata={},
            personality={}))
        req = webob.Request.blank('/v1.0/servers/1/suspend')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)

    def test_server_resume(self):
        FLAGS.allow_admin_api = True
        body = dict(server=dict(
            name='server_test', imageId=2, flavorId=2, metadata={},
            personality={}))
        req = webob.Request.blank('/v1.0/servers/1/resume')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)

    def test_server_reset_network(self):
        FLAGS.allow_admin_api = True
        body = dict(server=dict(
            name='server_test', imageId=2, flavorId=2, metadata={},
            personality={}))
        req = webob.Request.blank('/v1.0/servers/1/reset_network')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)

    def test_server_inject_network_info(self):
        FLAGS.allow_admin_api = True
        body = dict(server=dict(
            name='server_test', imageId=2, flavorId=2, metadata={},
            personality={}))
        req = webob.Request.blank(
              '/v1.0/servers/1/inject_network_info')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)

    def test_server_diagnostics(self):
        req = webob.Request.blank("/v1.0/servers/1/diagnostics")
        req.method = "GET"
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 404)

    def test_server_actions(self):
        req = webob.Request.blank("/v1.0/servers/1/actions")
        req.method = "GET"
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 404)

    def test_server_change_password(self):
        body = {'changePassword': {'adminPass': '1234pass'}}
        req = webob.Request.blank('/v1.0/servers/1/action')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 501)

    def test_server_change_password_xml(self):
        req = webob.Request.blank('/v1.0/servers/1/action')
        req.method = 'POST'
        req.content_type = 'application/xml'
        req.body = '<changePassword adminPass="1234pass">'
#        res = req.get_response(fakes.wsgi_app())
#        self.assertEqual(res.status_int, 501)

    def test_server_change_password_v1_1(self):
        mock_method = MockSetAdminPassword()
        self.stubs.Set(nova.compute.api.API, 'set_admin_password', mock_method)
        body = {'changePassword': {'adminPass': '1234pass'}}
        req = webob.Request.blank('/v1.1/servers/1/action')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)
        self.assertEqual(mock_method.instance_id, '1')
        self.assertEqual(mock_method.password, '1234pass')

    def test_server_change_password_bad_request_v1_1(self):
        body = {'changePassword': {'pass': '12345'}}
        req = webob.Request.blank('/v1.1/servers/1/action')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

    def test_server_change_password_empty_string_v1_1(self):
        body = {'changePassword': {'adminPass': ''}}
        req = webob.Request.blank('/v1.1/servers/1/action')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

    def test_server_change_password_none_v1_1(self):
        body = {'changePassword': {'adminPass': None}}
        req = webob.Request.blank('/v1.1/servers/1/action')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

    def test_server_change_password_not_a_string_v1_1(self):
        body = {'changePassword': {'adminPass': 1234}}
        req = webob.Request.blank('/v1.1/servers/1/action')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

    def test_server_reboot(self):
        body = dict(server=dict(
            name='server_test', imageId=2, flavorId=2, metadata={},
            personality={}))
        req = webob.Request.blank('/v1.0/servers/1/action')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)
        res = req.get_response(fakes.wsgi_app())

    def test_server_rebuild_accepted(self):
        body = {
            "rebuild": {
                "imageId": 2,
            },
        }

        req = webob.Request.blank('/v1.0/servers/1/action')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)
        self.assertEqual(res.body, "")

    def test_server_rebuild_rejected_when_building(self):
        body = {
            "rebuild": {
                "imageId": 2,
            },
        }

        state = power_state.BUILDING
        new_return_server = return_server_with_power_state(state)
        self.stubs.Set(nova.db.api, 'instance_get', new_return_server)

        req = webob.Request.blank('/v1.0/servers/1/action')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 409)

    def test_server_rebuild_bad_entity(self):
        body = {
            "rebuild": {
            },
        }

        req = webob.Request.blank('/v1.0/servers/1/action')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

    def test_server_rebuild_accepted_minimum_v1_1(self):
        body = {
            "rebuild": {
                "imageRef": "http://localhost/images/2",
            },
        }

        req = webob.Request.blank('/v1.1/servers/1/action')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)

    def test_server_rebuild_rejected_when_building_v1_1(self):
        body = {
            "rebuild": {
                "imageRef": "http://localhost/images/2",
            },
        }

        state = power_state.BUILDING
        new_return_server = return_server_with_power_state(state)
        self.stubs.Set(nova.db.api, 'instance_get', new_return_server)

        req = webob.Request.blank('/v1.1/servers/1/action')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 409)

    def test_server_rebuild_accepted_with_metadata_v1_1(self):
        body = {
            "rebuild": {
                "imageRef": "http://localhost/images/2",
                "metadata": {
                    "new": "metadata",
                },
            },
        }

        req = webob.Request.blank('/v1.1/servers/1/action')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)

    def test_server_rebuild_accepted_with_bad_metadata_v1_1(self):
        body = {
            "rebuild": {
                "imageRef": "http://localhost/images/2",
                "metadata": "stack",
            },
        }

        req = webob.Request.blank('/v1.1/servers/1/action')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

    def test_server_rebuild_bad_entity_v1_1(self):
        body = {
            "rebuild": {
                "imageId": 2,
            },
        }

        req = webob.Request.blank('/v1.1/servers/1/action')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

    def test_server_rebuild_bad_personality_v1_1(self):
        body = {
            "rebuild": {
                "imageRef": "http://localhost/images/2",
                "personality": [{
                    "path": "/path/to/file",
                    "contents": "INVALID b64",
                }]
            },
        }

        req = webob.Request.blank('/v1.1/servers/1/action')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

    def test_server_rebuild_personality_v1_1(self):
        body = {
            "rebuild": {
                "imageRef": "http://localhost/images/2",
                "personality": [{
                    "path": "/path/to/file",
                    "contents": base64.b64encode("Test String"),
                }]
            },
        }

        req = webob.Request.blank('/v1.1/servers/1/action')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)

    def test_delete_server_instance(self):
        req = webob.Request.blank('/v1.0/servers/1')
        req.method = 'DELETE'

        self.server_delete_called = False

        def instance_destroy_mock(context, id):
            self.server_delete_called = True

        self.stubs.Set(nova.db.api, 'instance_destroy',
            instance_destroy_mock)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status, '202 Accepted')
        self.assertEqual(self.server_delete_called, True)

    def test_resize_server(self):
        req = self.webreq('/1/action', 'POST', dict(resize=dict(flavorId=3)))

        self.resize_called = False

        def resize_mock(*args):
            self.resize_called = True

        self.stubs.Set(nova.compute.api.API, 'resize', resize_mock)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)
        self.assertEqual(self.resize_called, True)

    def test_resize_server_v11(self):

        req = webob.Request.blank('/v1.1/servers/1/action')
        req.content_type = 'application/json'
        req.method = 'POST'
        body_dict = dict(resize=dict(flavorRef="http://localhost/3"))
        req.body = json.dumps(body_dict)

        self.resize_called = False

        def resize_mock(*args):
            self.resize_called = True

        self.stubs.Set(nova.compute.api.API, 'resize', resize_mock)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)
        self.assertEqual(self.resize_called, True)

    def test_resize_bad_flavor_fails(self):
        req = self.webreq('/1/action', 'POST', dict(resize=dict(derp=3)))

        self.resize_called = False

        def resize_mock(*args):
            self.resize_called = True

        self.stubs.Set(nova.compute.api.API, 'resize', resize_mock)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 422)
        self.assertEqual(self.resize_called, False)

    def test_resize_raises_fails(self):
        req = self.webreq('/1/action', 'POST', dict(resize=dict(flavorId=3)))

        def resize_mock(*args):
            raise Exception('hurr durr')

        self.stubs.Set(nova.compute.api.API, 'resize', resize_mock)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

    def test_resized_server_has_correct_status(self):
        req = self.webreq('/1', 'GET')

        def fake_migration_get(*args):
            return {}

        self.stubs.Set(nova.db, 'migration_get_by_instance_and_status',
                fake_migration_get)
        res = req.get_response(fakes.wsgi_app())
        body = json.loads(res.body)
        self.assertEqual(body['server']['status'], 'RESIZE-CONFIRM')

    def test_confirm_resize_server(self):
        req = self.webreq('/1/action', 'POST', dict(confirmResize=None))

        self.resize_called = False

        def confirm_resize_mock(*args):
            self.resize_called = True

        self.stubs.Set(nova.compute.api.API, 'confirm_resize',
                confirm_resize_mock)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 204)
        self.assertEqual(self.resize_called, True)

    def test_confirm_resize_server_fails(self):
        req = self.webreq('/1/action', 'POST', dict(confirmResize=None))

        def confirm_resize_mock(*args):
            raise Exception('hurr durr')

        self.stubs.Set(nova.compute.api.API, 'confirm_resize',
                confirm_resize_mock)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

    def test_revert_resize_server(self):
        req = self.webreq('/1/action', 'POST', dict(revertResize=None))

        self.resize_called = False

        def revert_resize_mock(*args):
            self.resize_called = True

        self.stubs.Set(nova.compute.api.API, 'revert_resize',
                revert_resize_mock)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)
        self.assertEqual(self.resize_called, True)

    def test_revert_resize_server_fails(self):
        req = self.webreq('/1/action', 'POST', dict(revertResize=None))

        def revert_resize_mock(*args):
            raise Exception('hurr durr')

        self.stubs.Set(nova.compute.api.API, 'revert_resize',
                revert_resize_mock)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

    def test_shutdown_status(self):
        new_server = return_server_with_power_state(power_state.SHUTDOWN)
        self.stubs.Set(nova.db.api, 'instance_get', new_server)
        req = webob.Request.blank('/v1.0/servers/1')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)
        res_dict = json.loads(res.body)
        self.assertEqual(res_dict['server']['status'], 'SHUTDOWN')

    def test_shutoff_status(self):
        new_server = return_server_with_power_state(power_state.SHUTOFF)
        self.stubs.Set(nova.db.api, 'instance_get', new_server)
        req = webob.Request.blank('/v1.0/servers/1')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)
        res_dict = json.loads(res.body)
        self.assertEqual(res_dict['server']['status'], 'SHUTOFF')


class TestServerCreateRequestXMLDeserializer(unittest.TestCase):

    def setUp(self):
        self.deserializer = create_instance_helper.ServerXMLDeserializer()

    def test_minimal_request(self):
        serial_request = """
<server xmlns="http://docs.rackspacecloud.com/servers/api/v1.0"
 name="new-server-test" imageId="1" flavorId="1"/>"""
        request = self.deserializer.deserialize(serial_request, 'create')
        expected = {"server": {
                "name": "new-server-test",
                "imageId": "1",
                "flavorId": "1",
                }}
        self.assertEquals(request, expected)

    def test_request_with_empty_metadata(self):
        serial_request = """
<server xmlns="http://docs.rackspacecloud.com/servers/api/v1.0"
 name="new-server-test" imageId="1" flavorId="1">
    <metadata/>
</server>"""
        request = self.deserializer.deserialize(serial_request, 'create')
        expected = {"server": {
                "name": "new-server-test",
                "imageId": "1",
                "flavorId": "1",
                "metadata": {},
                }}
        self.assertEquals(request, expected)

    def test_request_with_empty_personality(self):
        serial_request = """
<server xmlns="http://docs.rackspacecloud.com/servers/api/v1.0"
 name="new-server-test" imageId="1" flavorId="1">
    <personality/>
</server>"""
        request = self.deserializer.deserialize(serial_request, 'create')
        expected = {"server": {
                "name": "new-server-test",
                "imageId": "1",
                "flavorId": "1",
                "personality": [],
                }}
        self.assertEquals(request, expected)

    def test_request_with_empty_metadata_and_personality(self):
        serial_request = """
<server xmlns="http://docs.rackspacecloud.com/servers/api/v1.0"
 name="new-server-test" imageId="1" flavorId="1">
    <metadata/>
    <personality/>
</server>"""
        request = self.deserializer.deserialize(serial_request, 'create')
        expected = {"server": {
                "name": "new-server-test",
                "imageId": "1",
                "flavorId": "1",
                "metadata": {},
                "personality": [],
                }}
        self.assertEquals(request, expected)

    def test_request_with_empty_metadata_and_personality_reversed(self):
        serial_request = """
<server xmlns="http://docs.rackspacecloud.com/servers/api/v1.0"
 name="new-server-test" imageId="1" flavorId="1">
    <personality/>
    <metadata/>
</server>"""
        request = self.deserializer.deserialize(serial_request, 'create')
        expected = {"server": {
                "name": "new-server-test",
                "imageId": "1",
                "flavorId": "1",
                "metadata": {},
                "personality": [],
                }}
        self.assertEquals(request, expected)

    def test_request_with_one_personality(self):
        serial_request = """
<server xmlns="http://docs.rackspacecloud.com/servers/api/v1.0"
 name="new-server-test" imageId="1" flavorId="1">
    <personality>
        <file path="/etc/conf">aabbccdd</file>
    </personality>
</server>"""
        request = self.deserializer.deserialize(serial_request, 'create')
        expected = [{"path": "/etc/conf", "contents": "aabbccdd"}]
        self.assertEquals(request["server"]["personality"], expected)

    def test_request_with_two_personalities(self):
        serial_request = """
<server xmlns="http://docs.rackspacecloud.com/servers/api/v1.0"
 name="new-server-test" imageId="1" flavorId="1">
<personality><file path="/etc/conf">aabbccdd</file>
<file path="/etc/sudoers">abcd</file></personality></server>"""
        request = self.deserializer.deserialize(serial_request, 'create')
        expected = [{"path": "/etc/conf", "contents": "aabbccdd"},
                    {"path": "/etc/sudoers", "contents": "abcd"}]
        self.assertEquals(request["server"]["personality"], expected)

    def test_request_second_personality_node_ignored(self):
        serial_request = """
<server xmlns="http://docs.rackspacecloud.com/servers/api/v1.0"
 name="new-server-test" imageId="1" flavorId="1">
    <personality>
        <file path="/etc/conf">aabbccdd</file>
    </personality>
    <personality>
        <file path="/etc/ignoreme">anything</file>
    </personality>
</server>"""
        request = self.deserializer.deserialize(serial_request, 'create')
        expected = [{"path": "/etc/conf", "contents": "aabbccdd"}]
        self.assertEquals(request["server"]["personality"], expected)

    def test_request_with_one_personality_missing_path(self):
        serial_request = """
<server xmlns="http://docs.rackspacecloud.com/servers/api/v1.0"
 name="new-server-test" imageId="1" flavorId="1">
<personality><file>aabbccdd</file></personality></server>"""
        request = self.deserializer.deserialize(serial_request, 'create')
        expected = [{"contents": "aabbccdd"}]
        self.assertEquals(request["server"]["personality"], expected)

    def test_request_with_one_personality_empty_contents(self):
        serial_request = """
<server xmlns="http://docs.rackspacecloud.com/servers/api/v1.0"
 name="new-server-test" imageId="1" flavorId="1">
<personality><file path="/etc/conf"></file></personality></server>"""
        request = self.deserializer.deserialize(serial_request, 'create')
        expected = [{"path": "/etc/conf", "contents": ""}]
        self.assertEquals(request["server"]["personality"], expected)

    def test_request_with_one_personality_empty_contents_variation(self):
        serial_request = """
<server xmlns="http://docs.rackspacecloud.com/servers/api/v1.0"
 name="new-server-test" imageId="1" flavorId="1">
<personality><file path="/etc/conf"/></personality></server>"""
        request = self.deserializer.deserialize(serial_request, 'create')
        expected = [{"path": "/etc/conf", "contents": ""}]
        self.assertEquals(request["server"]["personality"], expected)

    def test_request_with_one_metadata(self):
        serial_request = """
<server xmlns="http://docs.rackspacecloud.com/servers/api/v1.0"
 name="new-server-test" imageId="1" flavorId="1">
    <metadata>
        <meta key="alpha">beta</meta>
    </metadata>
</server>"""
        request = self.deserializer.deserialize(serial_request, 'create')
        expected = {"alpha": "beta"}
        self.assertEquals(request["server"]["metadata"], expected)

    def test_request_with_two_metadata(self):
        serial_request = """
<server xmlns="http://docs.rackspacecloud.com/servers/api/v1.0"
 name="new-server-test" imageId="1" flavorId="1">
    <metadata>
        <meta key="alpha">beta</meta>
        <meta key="foo">bar</meta>
    </metadata>
</server>"""
        request = self.deserializer.deserialize(serial_request, 'create')
        expected = {"alpha": "beta", "foo": "bar"}
        self.assertEquals(request["server"]["metadata"], expected)

    def test_request_with_metadata_missing_value(self):
        serial_request = """
<server xmlns="http://docs.rackspacecloud.com/servers/api/v1.0"
 name="new-server-test" imageId="1" flavorId="1">
    <metadata>
        <meta key="alpha"></meta>
    </metadata>
</server>"""
        request = self.deserializer.deserialize(serial_request, 'create')
        expected = {"alpha": ""}
        self.assertEquals(request["server"]["metadata"], expected)

    def test_request_with_two_metadata_missing_value(self):
        serial_request = """
<server xmlns="http://docs.rackspacecloud.com/servers/api/v1.0"
 name="new-server-test" imageId="1" flavorId="1">
    <metadata>
        <meta key="alpha"/>
        <meta key="delta"/>
    </metadata>
</server>"""
        request = self.deserializer.deserialize(serial_request, 'create')
        expected = {"alpha": "", "delta": ""}
        self.assertEquals(request["server"]["metadata"], expected)

    def test_request_with_metadata_missing_key(self):
        serial_request = """
<server xmlns="http://docs.rackspacecloud.com/servers/api/v1.0"
 name="new-server-test" imageId="1" flavorId="1">
    <metadata>
        <meta>beta</meta>
    </metadata>
</server>"""
        request = self.deserializer.deserialize(serial_request, 'create')
        expected = {"": "beta"}
        self.assertEquals(request["server"]["metadata"], expected)

    def test_request_with_two_metadata_missing_key(self):
        serial_request = """
<server xmlns="http://docs.rackspacecloud.com/servers/api/v1.0"
 name="new-server-test" imageId="1" flavorId="1">
    <metadata>
        <meta>beta</meta>
        <meta>gamma</meta>
    </metadata>
</server>"""
        request = self.deserializer.deserialize(serial_request, 'create')
        expected = {"": "gamma"}
        self.assertEquals(request["server"]["metadata"], expected)

    def test_request_with_metadata_duplicate_key(self):
        serial_request = """
<server xmlns="http://docs.rackspacecloud.com/servers/api/v1.0"
 name="new-server-test" imageId="1" flavorId="1">
    <metadata>
        <meta key="foo">bar</meta>
        <meta key="foo">baz</meta>
    </metadata>
</server>"""
        request = self.deserializer.deserialize(serial_request, 'create')
        expected = {"foo": "baz"}
        self.assertEquals(request["server"]["metadata"], expected)

    def test_canonical_request_from_docs(self):
        serial_request = """
<server xmlns="http://docs.rackspacecloud.com/servers/api/v1.0"
 name="new-server-test" imageId="1" flavorId="1">
    <metadata>
        <meta key="My Server Name">Apache1</meta>
    </metadata>
    <personality>
        <file path="/etc/banner.txt">\
ICAgICAgDQoiQSBjbG91ZCBkb2VzIG5vdCBrbm93IHdoeSBp\
dCBtb3ZlcyBpbiBqdXN0IHN1Y2ggYSBkaXJlY3Rpb24gYW5k\
IGF0IHN1Y2ggYSBzcGVlZC4uLkl0IGZlZWxzIGFuIGltcHVs\
c2lvbi4uLnRoaXMgaXMgdGhlIHBsYWNlIHRvIGdvIG5vdy4g\
QnV0IHRoZSBza3kga25vd3MgdGhlIHJlYXNvbnMgYW5kIHRo\
ZSBwYXR0ZXJucyBiZWhpbmQgYWxsIGNsb3VkcywgYW5kIHlv\
dSB3aWxsIGtub3csIHRvbywgd2hlbiB5b3UgbGlmdCB5b3Vy\
c2VsZiBoaWdoIGVub3VnaCB0byBzZWUgYmV5b25kIGhvcml6\
b25zLiINCg0KLVJpY2hhcmQgQmFjaA==</file>
    </personality>
</server>"""
        expected = {"server": {
            "name": "new-server-test",
            "imageId": "1",
            "flavorId": "1",
            "metadata": {
                "My Server Name": "Apache1",
            },
            "personality": [
                {
                    "path": "/etc/banner.txt",
                    "contents": """\
ICAgICAgDQoiQSBjbG91ZCBkb2VzIG5vdCBrbm93IHdoeSBp\
dCBtb3ZlcyBpbiBqdXN0IHN1Y2ggYSBkaXJlY3Rpb24gYW5k\
IGF0IHN1Y2ggYSBzcGVlZC4uLkl0IGZlZWxzIGFuIGltcHVs\
c2lvbi4uLnRoaXMgaXMgdGhlIHBsYWNlIHRvIGdvIG5vdy4g\
QnV0IHRoZSBza3kga25vd3MgdGhlIHJlYXNvbnMgYW5kIHRo\
ZSBwYXR0ZXJucyBiZWhpbmQgYWxsIGNsb3VkcywgYW5kIHlv\
dSB3aWxsIGtub3csIHRvbywgd2hlbiB5b3UgbGlmdCB5b3Vy\
c2VsZiBoaWdoIGVub3VnaCB0byBzZWUgYmV5b25kIGhvcml6\
b25zLiINCg0KLVJpY2hhcmQgQmFjaA==""",
                },
            ],
        }}
        request = self.deserializer.deserialize(serial_request, 'create')
        self.assertEqual(request, expected)

    def test_request_xmlser_with_flavor_image_href(self):
        serial_request = """
                <server xmlns="http://docs.openstack.org/compute/api/v1.1"
                    name="new-server-test"
                    imageRef="http://localhost:8774/v1.1/images/1"
                    flavorRef="http://localhost:8774/v1.1/flavors/1">
                </server>"""
        request = self.deserializer.deserialize(serial_request, 'create')
        self.assertEquals(request["server"]["flavorRef"],
                          "http://localhost:8774/v1.1/flavors/1")
        self.assertEquals(request["server"]["imageRef"],
                          "http://localhost:8774/v1.1/images/1")


class TestServerInstanceCreation(test.TestCase):

    def setUp(self):
        super(TestServerInstanceCreation, self).setUp()
        self.stubs = stubout.StubOutForTesting()
        fakes.FakeAuthManager.auth_data = {}
        fakes.FakeAuthDatabase.data = {}
        fakes.stub_out_auth(self.stubs)
        fakes.stub_out_image_service(self.stubs)
        fakes.stub_out_key_pair_funcs(self.stubs)
        self.allow_admin = FLAGS.allow_admin_api

    def tearDown(self):
        self.stubs.UnsetAll()
        FLAGS.allow_admin_api = self.allow_admin
        super(TestServerInstanceCreation, self).tearDown()

    def _setup_mock_compute_api_for_personality(self):

        class MockComputeAPI(nova.compute.API):

            def __init__(self):
                self.injected_files = None

            def create(self, *args, **kwargs):
                if 'injected_files' in kwargs:
                    self.injected_files = kwargs['injected_files']
                else:
                    self.injected_files = None
                return [{'id': '1234', 'display_name': 'fakeinstance',
                         'uuid': FAKE_UUID}]

            def set_admin_password(self, *args, **kwargs):
                pass

        def make_stub_method(canned_return):
            def stub_method(*args, **kwargs):
                return canned_return
            return stub_method

        compute_api = MockComputeAPI()
        self.stubs.Set(nova.compute, 'API', make_stub_method(compute_api))
        self.stubs.Set(
            nova.api.openstack.create_instance_helper.CreateInstanceHelper,
            '_get_kernel_ramdisk_from_image', make_stub_method((1, 1)))
        return compute_api

    def _create_personality_request_dict(self, personality_files):
        server = {}
        server['name'] = 'new-server-test'
        server['imageId'] = 1
        server['flavorId'] = 1
        if personality_files is not None:
            personalities = []
            for path, contents in personality_files:
                personalities.append({'path': path, 'contents': contents})
            server['personality'] = personalities
        return {'server': server}

    def _get_create_request_json(self, body_dict):
        req = webob.Request.blank('/v1.0/servers')
        req.content_type = 'application/json'
        req.method = 'POST'
        req.body = json.dumps(body_dict)
        return req

    def _run_create_instance_with_mock_compute_api(self, request):
        compute_api = self._setup_mock_compute_api_for_personality()
        response = request.get_response(fakes.wsgi_app())
        return compute_api, response

    def _format_xml_request_body(self, body_dict):
        server = body_dict['server']
        body_parts = []
        body_parts.extend([
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<server xmlns="http://docs.rackspacecloud.com/servers/api/v1.0"',
            ' name="%s" imageId="%s" flavorId="%s">' % (
                    server['name'], server['imageId'], server['flavorId'])])
        if 'metadata' in server:
            metadata = server['metadata']
            body_parts.append('<metadata>')
            for item in metadata.iteritems():
                body_parts.append('<meta key="%s">%s</meta>' % item)
            body_parts.append('</metadata>')
        if 'personality' in server:
            personalities = server['personality']
            body_parts.append('<personality>')
            for file in personalities:
                item = (file['path'], file['contents'])
                body_parts.append('<file path="%s">%s</file>' % item)
            body_parts.append('</personality>')
        body_parts.append('</server>')
        return ''.join(body_parts)

    def _get_create_request_xml(self, body_dict):
        req = webob.Request.blank('/v1.0/servers')
        req.content_type = 'application/xml'
        req.accept = 'application/xml'
        req.method = 'POST'
        req.body = self._format_xml_request_body(body_dict)
        return req

    def _create_instance_with_personality_json(self, personality):
        body_dict = self._create_personality_request_dict(personality)
        request = self._get_create_request_json(body_dict)
        compute_api, response = \
            self._run_create_instance_with_mock_compute_api(request)
        return request, response, compute_api.injected_files

    def _create_instance_with_personality_xml(self, personality):
        body_dict = self._create_personality_request_dict(personality)
        request = self._get_create_request_xml(body_dict)
        compute_api, response = \
            self._run_create_instance_with_mock_compute_api(request)
        return request, response, compute_api.injected_files

    def test_create_instance_with_no_personality(self):
        request, response, injected_files = \
                self._create_instance_with_personality_json(personality=None)
        self.assertEquals(response.status_int, 200)
        self.assertEquals(injected_files, [])

    def test_create_instance_with_no_personality_xml(self):
        request, response, injected_files = \
                self._create_instance_with_personality_xml(personality=None)
        self.assertEquals(response.status_int, 200)
        self.assertEquals(injected_files, [])

    def test_create_instance_with_personality(self):
        path = '/my/file/path'
        contents = '#!/bin/bash\necho "Hello, World!"\n'
        b64contents = base64.b64encode(contents)
        personality = [(path, b64contents)]
        request, response, injected_files = \
            self._create_instance_with_personality_json(personality)
        self.assertEquals(response.status_int, 200)
        self.assertEquals(injected_files, [(path, contents)])

    def test_create_instance_with_personality_xml(self):
        path = '/my/file/path'
        contents = '#!/bin/bash\necho "Hello, World!"\n'
        b64contents = base64.b64encode(contents)
        personality = [(path, b64contents)]
        request, response, injected_files = \
            self._create_instance_with_personality_xml(personality)
        self.assertEquals(response.status_int, 200)
        self.assertEquals(injected_files, [(path, contents)])

    def test_create_instance_with_personality_no_path(self):
        personality = [('/remove/this/path',
            base64.b64encode('my\n\file\ncontents'))]
        body_dict = self._create_personality_request_dict(personality)
        del body_dict['server']['personality'][0]['path']
        request = self._get_create_request_json(body_dict)
        compute_api, response = \
            self._run_create_instance_with_mock_compute_api(request)
        self.assertEquals(response.status_int, 400)
        self.assertEquals(compute_api.injected_files, None)

    def _test_create_instance_with_personality_no_path_xml(self):
        personality = [('/remove/this/path',
            base64.b64encode('my\n\file\ncontents'))]
        body_dict = self._create_personality_request_dict(personality)
        request = self._get_create_request_xml(body_dict)
        request.body = request.body.replace(' path="/remove/this/path"', '')
        compute_api, response = \
            self._run_create_instance_with_mock_compute_api(request)
        self.assertEquals(response.status_int, 400)
        self.assertEquals(compute_api.injected_files, None)

    def test_create_instance_with_personality_no_contents(self):
        personality = [('/test/path',
            base64.b64encode('remove\nthese\ncontents'))]
        body_dict = self._create_personality_request_dict(personality)
        del body_dict['server']['personality'][0]['contents']
        request = self._get_create_request_json(body_dict)
        compute_api, response = \
            self._run_create_instance_with_mock_compute_api(request)
        self.assertEquals(response.status_int, 400)
        self.assertEquals(compute_api.injected_files, None)

    def test_create_instance_with_personality_not_a_list(self):
        personality = [('/test/path', base64.b64encode('test\ncontents\n'))]
        body_dict = self._create_personality_request_dict(personality)
        body_dict['server']['personality'] = \
            body_dict['server']['personality'][0]
        request = self._get_create_request_json(body_dict)
        compute_api, response = \
            self._run_create_instance_with_mock_compute_api(request)
        self.assertEquals(response.status_int, 400)
        self.assertEquals(compute_api.injected_files, None)

    def test_create_instance_with_personality_with_non_b64_content(self):
        path = '/my/file/path'
        contents = '#!/bin/bash\necho "Oh no!"\n'
        personality = [(path, contents)]
        request, response, injected_files = \
            self._create_instance_with_personality_json(personality)
        self.assertEquals(response.status_int, 400)
        self.assertEquals(injected_files, None)

    def test_create_instance_with_null_personality(self):
        personality = None
        body_dict = self._create_personality_request_dict(personality)
        body_dict['server']['personality'] = None
        request = self._get_create_request_json(body_dict)
        compute_api, response = \
            self._run_create_instance_with_mock_compute_api(request)
        self.assertEquals(response.status_int, 200)

    def test_create_instance_with_three_personalities(self):
        files = [
            ('/etc/sudoers', 'ALL ALL=NOPASSWD: ALL\n'),
            ('/etc/motd', 'Enjoy your root access!\n'),
            ('/etc/dovecot.conf', 'dovecot\nconfig\nstuff\n'),
            ]
        personality = []
        for path, content in files:
            personality.append((path, base64.b64encode(content)))
        request, response, injected_files = \
            self._create_instance_with_personality_json(personality)
        self.assertEquals(response.status_int, 200)
        self.assertEquals(injected_files, files)

    def test_create_instance_personality_empty_content(self):
        path = '/my/file/path'
        contents = ''
        personality = [(path, contents)]
        request, response, injected_files = \
            self._create_instance_with_personality_json(personality)
        self.assertEquals(response.status_int, 200)
        self.assertEquals(injected_files, [(path, contents)])

    def test_create_instance_admin_pass_json(self):
        request, response, dummy = \
            self._create_instance_with_personality_json(None)
        self.assertEquals(response.status_int, 200)
        response = json.loads(response.body)
        self.assertTrue('adminPass' in response['server'])
        self.assertEqual(16, len(response['server']['adminPass']))

    def test_create_instance_admin_pass_xml(self):
        request, response, dummy = \
            self._create_instance_with_personality_xml(None)
        self.assertEquals(response.status_int, 200)
        dom = minidom.parseString(response.body)
        server = dom.childNodes[0]
        self.assertEquals(server.nodeName, 'server')
        self.assertEqual(16, len(server.getAttribute('adminPass')))


class TestGetKernelRamdiskFromImage(test.TestCase):
    """
    If we're building from an AMI-style image, we need to be able to fetch the
    kernel and ramdisk associated with the machine image. This information is
    stored with the image metadata and return via the ImageService.

    These tests ensure that we parse the metadata return the ImageService
    correctly and that we handle failure modes appropriately.
    """

    def test_status_not_active(self):
        """We should only allow fetching of kernel and ramdisk information if
        we have a 'fully-formed' image, aka 'active'
        """
        image_meta = {'id': 1, 'status': 'queued'}
        self.assertRaises(exception.Invalid, self._get_k_r, image_meta)

    def test_not_ami(self):
        """Anything other than ami should return no kernel and no ramdisk"""
        image_meta = {'id': 1, 'status': 'active', 'container_format': 'vhd'}
        kernel_id, ramdisk_id = self._get_k_r(image_meta)
        self.assertEqual(kernel_id, None)
        self.assertEqual(ramdisk_id, None)

    def test_ami_no_kernel(self):
        """If an ami is missing a kernel it should raise NotFound"""
        image_meta = {'id': 1, 'status': 'active', 'container_format': 'ami',
                      'properties': {'ramdisk_id': 1}}
        self.assertRaises(exception.NotFound, self._get_k_r, image_meta)

    def test_ami_no_ramdisk(self):
        """If an ami is missing a ramdisk it should raise NotFound"""
        image_meta = {'id': 1, 'status': 'active', 'container_format': 'ami',
                      'properties': {'kernel_id': 1}}
        self.assertRaises(exception.NotFound, self._get_k_r, image_meta)

    def test_ami_kernel_ramdisk_present(self):
        """Return IDs if both kernel and ramdisk are present"""
        image_meta = {'id': 1, 'status': 'active', 'container_format': 'ami',
                      'properties': {'kernel_id': 1, 'ramdisk_id': 2}}
        kernel_id, ramdisk_id = self._get_k_r(image_meta)
        self.assertEqual(kernel_id, 1)
        self.assertEqual(ramdisk_id, 2)

    @staticmethod
    def _get_k_r(image_meta):
        """Rebinding function to a shorter name for convenience"""
        kernel_id, ramdisk_id = create_instance_helper.CreateInstanceHelper. \
                                _do_get_kernel_ramdisk_from_image(image_meta)
        return kernel_id, ramdisk_id
