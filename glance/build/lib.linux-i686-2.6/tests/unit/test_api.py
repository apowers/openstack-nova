# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack, LLC
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

import datetime
import hashlib
import httplib
import os
import json
import unittest

import stubout
import webob

from glance.api import v1 as server
from glance.registry import server as rserver
import glance.registry.db.api
from tests import stubs

VERBOSE = False
DEBUG = False


class TestRegistryAPI(unittest.TestCase):
    def setUp(self):
        """Establish a clean test environment"""
        self.stubs = stubout.StubOutForTesting()
        stubs.stub_out_registry_and_store_server(self.stubs)
        stubs.stub_out_registry_db_image_api(self.stubs)
        stubs.stub_out_filesystem_backend()
        self.api = rserver.API({'verbose': VERBOSE,
                                'debug': DEBUG})

    def tearDown(self):
        """Clear the test environment"""
        stubs.clean_out_fake_filesystem_backend()
        self.stubs.UnsetAll()

    def test_get_root(self):
        """Tests that the root registry API returns "index",
        which is a list of public images

        """
        fixture = {'id': 2,
                   'name': 'fake image #2',
                   'size': 19,
                   'checksum': None}
        req = webob.Request.blank('/')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        for k, v in fixture.iteritems():
            self.assertEquals(v, images[0][k])

    def test_get_index(self):
        """Tests that the /images registry API returns list of
        public images

        """
        fixture = {'id': 2,
                   'name': 'fake image #2',
                   'size': 19,
                   'checksum': None}
        req = webob.Request.blank('/images')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        for k, v in fixture.iteritems():
            self.assertEquals(v, images[0][k])

    def test_get_index_marker(self):
        """Tests that the /images registry API returns list of
        public images that conforms to a marker query param

        """

        time1 = datetime.datetime.utcnow() + datetime.timedelta(seconds=5)
        time2 = datetime.datetime.utcnow()

        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None,
                         'created_at': time1}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None,
                         'created_at': time1}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 5,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None,
                         'created_at': time2}

        glance.registry.db.api.image_create(None, extra_fixture)

        req = webob.Request.blank('/images?marker=4')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        # should be sorted by created_at desc, id desc
        # page should start after marker 4
        self.assertEquals(len(images), 3)
        self.assertEquals(int(images[0]['id']), 3)
        self.assertEquals(int(images[1]['id']), 5)
        self.assertEquals(int(images[2]['id']), 2)

    def test_get_index_limit(self):
        """Tests that the /images registry API returns list of
        public images that conforms to a limit query param

        """
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        req = webob.Request.blank('/images?limit=1')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        # expect list to be sorted by created_at desc
        self.assertTrue(int(images[0]['id']), 4)

    def test_get_index_limit_negative(self):
        """Tests that the /images registry API returns list of
        public images that conforms to a limit query param

        """
        req = webob.Request.blank('/images?limit=-1')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

    def test_get_index_limit_non_int(self):
        """Tests that the /images registry API returns list of
        public images that conforms to a limit query param

        """
        req = webob.Request.blank('/images?limit=a')
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 400)

    def test_get_index_limit_marker(self):
        """Tests that the /images registry API returns list of
        public images that conforms to limit and marker query params

        """
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        req = webob.Request.blank('/images?marker=3&limit=1')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        # expect list to be sorted by created_at desc
        self.assertEqual(int(images[0]['id']), 2)

    def test_get_index_filter_name(self):
        """Tests that the /images registry API returns list of
        public images that have a specific name. This is really a sanity
        check, filtering is tested more in-depth using /images/detail

        """
        fixture = {'id': 2,
                   'name': 'fake image #2',
                   'size': 19,
                   'checksum': None}

        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        req = webob.Request.blank('/images?name=new name! #123')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 2)

        for image in images:
            self.assertEqual('new name! #123', image['name'])

    def test_get_details(self):
        """Tests that the /images/detail registry API returns
        a mapping containing a list of detailed image information

        """
        fixture = {'id': 2,
                   'name': 'fake image #2',
                   'is_public': True,
                   'size': 19,
                   'checksum': None,
                   'disk_format': 'vhd',
                   'container_format': 'ovf',
                   'status': 'active'}

        req = webob.Request.blank('/images/detail')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        for k, v in fixture.iteritems():
            self.assertEquals(v, images[0][k])

    def test_get_details_limit_marker(self):
        """Tests that the /images/details registry API returns list of
        public images that conforms to limit and marker query params.
        This functionality is tested more thoroughly on /images, this is
        just a sanity check

        """
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        req = webob.Request.blank('/images/detail?marker=3&limit=1')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        # expect list to be sorted by created_at desc
        self.assertEqual(int(images[0]['id']), 2)

    def test_get_details_filter_name(self):
        """Tests that the /images/detail registry API returns list of
        public images that have a specific name

        """
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        req = webob.Request.blank('/images/detail?name=new name! #123')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 2)

        for image in images:
            self.assertEqual('new name! #123', image['name'])

    def test_get_details_filter_status(self):
        """Tests that the /images/detail registry API returns list of
        public images that have a specific status

        """
        extra_fixture = {'id': 3,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #4',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        req = webob.Request.blank('/images/detail?status=saving')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        for image in images:
            self.assertEqual('saving', image['status'])

    def test_get_details_filter_container_format(self):
        """Tests that the /images/detail registry API returns list of
        public images that have a specific container_format

        """
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vdi',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'fake image #4',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        req = webob.Request.blank('/images/detail?container_format=ovf')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 2)

        for image in images:
            self.assertEqual('ovf', image['container_format'])

    def test_get_details_filter_disk_format(self):
        """Tests that the /images/detail registry API returns list of
        public images that have a specific disk_format

        """
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'fake image #4',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        req = webob.Request.blank('/images/detail?disk_format=vhd')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 2)

        for image in images:
            self.assertEqual('vhd', image['disk_format'])

    def test_get_details_filter_size_min(self):
        """Tests that the /images/detail registry API returns list of
        public images that have a size greater than or equal to size_min

        """
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 18,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'fake image #4',
                         'size': 20,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        req = webob.Request.blank('/images/detail?size_min=19')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 2)

        for image in images:
            self.assertTrue(image['size'] >= 19)

    def test_get_details_filter_size_max(self):
        """Tests that the /images/detail registry API returns list of
        public images that have a size less than or equal to size_max

        """
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 18,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'fake image #4',
                         'size': 20,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        req = webob.Request.blank('/images/detail?size_max=19')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 2)

        for image in images:
            self.assertTrue(image['size'] <= 19)

    def test_get_details_filter_size_min_max(self):
        """Tests that the /images/detail registry API returns list of
        public images that have a size less than or equal to size_max
        and greater than or equal to size_min

        """
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 18,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'fake image #4',
                         'size': 20,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 5,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'fake image #5',
                         'size': 6,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        req = webob.Request.blank('/images/detail?size_min=18&size_max=19')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 2)

        for image in images:
            self.assertTrue(image['size'] <= 19 and image['size'] >= 18)

    def test_get_details_filter_property(self):
        """Tests that the /images/detail registry API returns list of
        public images that have a specific custom property

        """
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'fake image #3',
                         'size': 19,
                         'checksum': None,
                         'properties': {'prop_123': 'v a'}}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'ami',
                         'container_format': 'ami',
                         'name': 'fake image #4',
                         'size': 19,
                         'checksum': None,
                         'properties': {'prop_123': 'v b'}}

        glance.registry.db.api.image_create(None, extra_fixture)

        req = webob.Request.blank('/images/detail?property-prop_123=v%20a')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        images = res_dict['images']
        self.assertEquals(len(images), 1)

        for image in images:
            self.assertEqual('v a', image['properties']['prop_123'])

    def test_create_image(self):
        """Tests that the /images POST registry API creates the image"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf'}

        req = webob.Request.blank('/images')

        req.method = 'POST'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)

        self.assertEquals(res.status_int, 200)

        res_dict = json.loads(res.body)

        for k, v in fixture.iteritems():
            self.assertEquals(v, res_dict['image'][k])

        # Test ID auto-assigned properly
        self.assertEquals(3, res_dict['image']['id'])

        # Test status was updated properly
        self.assertEquals('active', res_dict['image']['status'])

    def test_create_image_with_bad_container_format(self):
        """Tests proper exception is raised if a bad disk_format is set"""
        fixture = {'id': 3,
                   'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'invalid'}

        req = webob.Request.blank('/images')

        req.method = 'POST'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid container format' in res.body)

    def test_create_image_with_bad_disk_format(self):
        """Tests proper exception is raised if a bad disk_format is set"""
        fixture = {'id': 3,
                   'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'invalid',
                   'container_format': 'ovf'}

        req = webob.Request.blank('/images')

        req.method = 'POST'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid disk format' in res.body)

    def test_create_image_with_mismatched_formats(self):
        """Tests that exception raised for bad matching disk and container
        formats"""
        fixture = {'name': 'fake public image #3',
                   'container_format': 'aki',
                   'disk_format': 'ari'}

        req = webob.Request.blank('/images')

        req.method = 'POST'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid mix of disk and container formats'
                        in res.body)

    def test_create_image_with_bad_status(self):
        """Tests proper exception is raised if a bad status is set"""
        fixture = {'id': 3,
                   'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf',
                   'status': 'bad status'}

        req = webob.Request.blank('/images')

        req.method = 'POST'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid image status' in res.body)

    def test_update_image(self):
        """Tests that the /images PUT registry API updates the image"""
        fixture = {'name': 'fake public image #2',
                   'disk_format': 'raw'}

        req = webob.Request.blank('/images/2')

        req.method = 'PUT'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)

        self.assertEquals(res.status_int, 200)

        res_dict = json.loads(res.body)

        for k, v in fixture.iteritems():
            self.assertEquals(v, res_dict['image'][k])

    def test_update_image_not_existing(self):
        """Tests proper exception is raised if attempt to update non-existing
        image"""
        fixture = {'status': 'killed'}

        req = webob.Request.blank('/images/3')

        req.method = 'PUT'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int,
                          webob.exc.HTTPNotFound.code)

    def test_update_image_with_bad_status(self):
        """Tests that exception raised trying to set a bad status"""
        fixture = {'status': 'invalid'}

        req = webob.Request.blank('/images/2')

        req.method = 'PUT'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid image status' in res.body)

    def test_update_image_with_bad_disk_format(self):
        """Tests that exception raised trying to set a bad disk_format"""
        fixture = {'disk_format': 'invalid'}

        req = webob.Request.blank('/images/2')

        req.method = 'PUT'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid disk format' in res.body)

    def test_update_image_with_bad_container_format(self):
        """Tests that exception raised trying to set a bad container_format"""
        fixture = {'container_format': 'invalid'}

        req = webob.Request.blank('/images/2')

        req.method = 'PUT'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid container format' in res.body)

    def test_update_image_with_mismatched_formats(self):
        """Tests that exception raised for bad matching disk and container
        formats"""
        fixture = {'container_format': 'ari'}

        req = webob.Request.blank('/images/2')  # Image 2 has disk format 'vhd'

        req.method = 'PUT'
        req.body = json.dumps(dict(image=fixture))

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid mix of disk and container formats'
                        in res.body)

    def test_delete_image(self):
        """Tests that the /images DELETE registry API deletes the image"""

        # Grab the original number of images
        req = webob.Request.blank('/images')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        orig_num_images = len(res_dict['images'])

        # Delete image #2
        req = webob.Request.blank('/images/2')

        req.method = 'DELETE'

        res = req.get_response(self.api)

        self.assertEquals(res.status_int, 200)

        # Verify one less image
        req = webob.Request.blank('/images')
        res = req.get_response(self.api)
        res_dict = json.loads(res.body)
        self.assertEquals(res.status_int, 200)

        new_num_images = len(res_dict['images'])
        self.assertEquals(new_num_images, orig_num_images - 1)

    def test_delete_image_not_existing(self):
        """Tests proper exception is raised if attempt to delete non-existing
        image"""

        req = webob.Request.blank('/images/3')

        req.method = 'DELETE'

        res = req.get_response(self.api)
        self.assertEquals(res.status_int,
                          webob.exc.HTTPNotFound.code)


class TestGlanceAPI(unittest.TestCase):
    def setUp(self):
        """Establish a clean test environment"""
        # NOTE(sirp): in-memory DBs don't play well with sqlalchemy migrate
        # (see http://code.google.com/p/sqlalchemy-migrate/
        #            issues/detail?id=72)
        self.db_file = 'test_glance_api.sqlite'
        os.environ['GLANCE_SQL_CONNECTION'] = 'sqlite:///%s' % self.db_file

        self.stubs = stubout.StubOutForTesting()
        stubs.stub_out_registry_and_store_server(self.stubs)
        stubs.stub_out_registry_db_image_api(self.stubs)
        stubs.stub_out_filesystem_backend()
        sql_connection = os.environ.get('GLANCE_SQL_CONNECTION', "sqlite://")
        options = {'verbose': VERBOSE,
                   'debug': DEBUG,
                   'registry_host': '0.0.0.0',
                   'registry_port': '9191',
                   'sql_connection': sql_connection,
                   'default_store': 'file',
                   'filesystem_store_datadir': stubs.FAKE_FILESYSTEM_ROOTDIR}
        self.api = server.API(options)

    def tearDown(self):
        """Clear the test environment"""
        stubs.clean_out_fake_filesystem_backend()
        self.stubs.UnsetAll()
        if os.path.exists(self.db_file):
            os.unlink(self.db_file)

    def test_bad_disk_format(self):
        fixture_headers = {'x-image-meta-store': 'bad',
                   'x-image-meta-name': 'bogus',
                   'x-image-meta-location': 'http://example.com/image.tar.gz',
                   'x-image-meta-disk-format': 'invalid',
                   'x-image-meta-container-format': 'ami'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid disk format' in res.body, res.body)

    def test_bad_container_format(self):
        fixture_headers = {'x-image-meta-store': 'bad',
                   'x-image-meta-name': 'bogus',
                   'x-image-meta-location': 'http://example.com/image.tar.gz',
                   'x-image-meta-disk-format': 'vhd',
                   'x-image-meta-container-format': 'invalid'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)
        self.assertTrue('Invalid container format' in res.body)

    def test_add_image_no_location_no_image_as_body(self):
        """Tests creates a queued image for no body and no loc header"""
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.CREATED)

        res_body = json.loads(res.body)['image']
        self.assertEquals('queued', res_body['status'])

    def test_add_image_bad_store(self):
        """Tests raises BadRequest for invalid store header"""
        fixture_headers = {'x-image-meta-store': 'bad',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)

    def test_add_image_basic_file_store(self):
        """Tests to add a basic image in the file store"""
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = "chunk00000remainder"
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.CREATED)

        res_body = json.loads(res.body)['image']
        self.assertEquals(res_body['location'],
                          'file:///tmp/glance-tests/3')

        # Test that the Location: header is set to the URI to
        # edit the newly-created image, as required by APP.
        # See LP Bug #719825
        self.assertTrue('location' in res.headers,
                        "'location' not in response headers.\n"
                        "res.headerlist = %r" % res.headerlist)
        self.assertTrue('/images/3' in res.headers['location'])

    def test_image_is_checksummed(self):
        """Test that the image contents are checksummed properly"""
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}
        image_contents = "chunk00000remainder"
        image_checksum = hashlib.md5(image_contents).hexdigest()

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = image_contents
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.CREATED)

        res_body = json.loads(res.body)['image']
        self.assertEquals(res_body['location'],
                          'file:///tmp/glance-tests/3')
        self.assertEquals(image_checksum, res_body['checksum'],
                          "Mismatched checksum. Expected %s, got %s" %
                          (image_checksum, res_body['checksum']))

    def test_etag_equals_checksum_header(self):
        """Test that the ETag header matches the x-image-meta-checksum"""
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3'}
        image_contents = "chunk00000remainder"
        image_checksum = hashlib.md5(image_contents).hexdigest()

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = image_contents
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.CREATED)

        # HEAD the image and check the ETag equals the checksum header...
        expected_headers = {'x-image-meta-checksum': image_checksum,
                            'etag': image_checksum}
        req = webob.Request.blank("/images/3")
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        for key in expected_headers.keys():
            self.assertTrue(key in res.headers,
                            "required header '%s' missing from "
                            "returned headers" % key)
        for key, value in expected_headers.iteritems():
            self.assertEquals(value, res.headers[key])

    def test_bad_checksum_kills_image(self):
        """Test that the image contents are checksummed properly"""
        image_contents = "chunk00000remainder"
        bad_checksum = hashlib.md5("invalid").hexdigest()
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-disk-format': 'vhd',
                           'x-image-meta-container-format': 'ovf',
                           'x-image-meta-name': 'fake image #3',
                           'x-image-meta-checksum': bad_checksum}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v

        req.headers['Content-Type'] = 'application/octet-stream'
        req.body = image_contents
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPBadRequest.code)

        # Test the image was killed...
        expected_headers = {'x-image-meta-id': '3',
                            'x-image-meta-status': 'killed'}
        req = webob.Request.blank("/images/3")
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        for key, value in expected_headers.iteritems():
            self.assertEquals(value, res.headers[key])

    def test_image_meta(self):
        """Test for HEAD /images/<ID>"""
        expected_headers = {'x-image-meta-id': '2',
                            'x-image-meta-name': 'fake image #2'}
        req = webob.Request.blank("/images/2")
        req.method = 'HEAD'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        for key, value in expected_headers.iteritems():
            self.assertEquals(value, res.headers[key])

    def test_show_image_basic(self):
        req = webob.Request.blank("/images/2")
        res = req.get_response(self.api)
        self.assertEqual('chunk00000remainder', res.body)

    def test_show_non_exists_image(self):
        req = webob.Request.blank("/images/42")
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPNotFound.code)

    def test_delete_image(self):
        req = webob.Request.blank("/images/2")
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)

        req = webob.Request.blank("/images/2")
        req.method = 'GET'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPNotFound.code,
                          res.body)

    def test_delete_non_exists_image(self):
        req = webob.Request.blank("/images/42")
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, webob.exc.HTTPNotFound.code)

    def test_delete_queued_image(self):
        """
        Here, we try to delete an image that is in the queued state.
        Bug #747799 demonstrated that trying to DELETE an image
        that had had its save process killed manually results in failure
        because the location attribute is None.
        """
        # Add an image the way that glance-upload adds an image...
        # by reserving a place in the database for an image without
        # really any attributes or information on the image and then
        # later doing an update with the image body and other attributes.
        # We will stop the process after the reservation stage, then
        # try to delete the image.
        fixture_headers = {'x-image-meta-store': 'file',
                           'x-image-meta-name': 'fake image #3'}

        req = webob.Request.blank("/images")
        req.method = 'POST'
        for k, v in fixture_headers.iteritems():
            req.headers[k] = v
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, httplib.CREATED)

        res_body = json.loads(res.body)['image']
        self.assertEquals('queued', res_body['status'])

        # Now try to delete the image...
        req = webob.Request.blank("/images/3")
        req.method = 'DELETE'
        res = req.get_response(self.api)
        self.assertEquals(res.status_int, 200)
