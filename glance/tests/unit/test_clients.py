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

import json
import os
import stubout
import StringIO
import unittest

import webob

from glance import client
from glance.common import exception
import glance.registry.db.api
from glance.registry import client as rclient
from tests import stubs


class TestBadClients(unittest.TestCase):

    """Test exceptions raised for bad clients"""

    def test_bad_address(self):
        """Test ClientConnectionError raised"""
        c = client.Client("127.999.1.1")
        self.assertRaises(client.ClientConnectionError,
                          c.get_image,
                          1)


class TestRegistryClient(unittest.TestCase):

    """
    Test proper actions made for both valid and invalid requests
    against a Registry service
    """

    def setUp(self):
        """Establish a clean test environment"""
        self.stubs = stubout.StubOutForTesting()
        stubs.stub_out_registry_db_image_api(self.stubs)
        stubs.stub_out_registry_and_store_server(self.stubs)
        self.client = rclient.RegistryClient("0.0.0.0")

    def tearDown(self):
        """Clear the test environment"""
        self.stubs.UnsetAll()

    def test_get_image_index(self):
        """Test correct set of public image returned"""
        fixture = {'id': 2,
                   'name': 'fake image #2'}
        images = self.client.get_images()
        self.assertEquals(len(images), 1)

        for k, v in fixture.items():
            self.assertEquals(v, images[0][k])

    def test_get_image_index_marker(self):
        """Test correct set of images returned with marker param."""
        extra_fixture = {'id': 3,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #125',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        images = self.client.get_images(marker=4)
        self.assertEquals(len(images), 2)

        for image in images:
            self.assertTrue(image['id'] < 4)

    def test_get_image_index_limit(self):
        """Test correct number of images returned with limit param."""
        extra_fixture = {'id': 3,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #125',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        images = self.client.get_images(limit=2)
        self.assertEquals(len(images), 2)

    def test_get_image_index_marker_limit(self):
        """Test correct set of images returned with marker/limit params."""
        extra_fixture = {'id': 3,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #125',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        images = self.client.get_images(marker=3, limit=1)
        self.assertEquals(len(images), 1)

        self.assertEquals(images[0]['id'], 2)

    def test_get_image_index_by_name(self):
        """Test correct set of public, name-filtered image returned. This
        is just a sanity check, we test the details call more in-depth."""
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        images = self.client.get_images({'name': 'new name! #123'})
        self.assertEquals(len(images), 1)

        for image in images:
            self.assertEquals('new name! #123', image['name'])

    def test_get_image_details(self):
        """Tests that the detailed info about public images returned"""
        fixture = {'id': 2,
                   'name': 'fake image #2',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf',
                   'status': 'active',
                   'size': 19,
                   'location': "file:///tmp/glance-tests/2",
                   'properties': {}}

        images = self.client.get_images_detailed()
        self.assertEquals(len(images), 1)

        for k, v in fixture.items():
            self.assertEquals(v, images[0][k])

    def test_get_image_details_marker_limit(self):
        """Test correct set of images returned with marker/limit params."""
        extra_fixture = {'id': 3,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #125',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        images = self.client.get_images_detailed(marker=3, limit=1)
        self.assertEquals(len(images), 1)

        self.assertEquals(images[0]['id'], 2)

    def test_get_image_details_by_name(self):
        """Tests that a detailed call can be filtered by name"""
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        images = self.client.get_images_detailed({'name': 'new name! #123'})
        self.assertEquals(len(images), 1)

        for image in images:
            self.assertEquals('new name! #123', image['name'])

    def test_get_image_details_by_status(self):
        """Tests that a detailed call can be filtered by status"""
        extra_fixture = {'id': 3,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        images = self.client.get_images_detailed({'status': 'saving'})
        self.assertEquals(len(images), 1)

        for image in images:
            self.assertEquals('saving', image['status'])

    def test_get_image_details_by_container_format(self):
        """Tests that a detailed call can be filtered by container_format"""
        extra_fixture = {'id': 3,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        images = self.client.get_images_detailed({'container_format': 'ovf'})
        self.assertEquals(len(images), 2)

        for image in images:
            self.assertEquals('ovf', image['container_format'])

    def test_get_image_details_by_disk_format(self):
        """Tests that a detailed call can be filtered by disk_format"""
        extra_fixture = {'id': 3,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        images = self.client.get_images_detailed({'disk_format': 'vhd'})
        self.assertEquals(len(images), 2)

        for image in images:
            self.assertEquals('vhd', image['disk_format'])

    def test_get_image_details_with_maximum_size(self):
        """Tests that a detailed call can be filtered by size_max"""
        extra_fixture = {'id': 3,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 21,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        images = self.client.get_images_detailed({'size_max': 20})
        self.assertEquals(len(images), 1)

        for image in images:
            self.assertTrue(image['size'] <= 20)

    def test_get_image_details_with_minimum_size(self):
        """Tests that a detailed call can be filtered by size_min"""
        extra_fixture = {'id': 3,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 20,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        images = self.client.get_images_detailed({'size_min': 20})
        self.assertEquals(len(images), 1)

        for image in images:
            self.assertTrue(image['size'] >= 20)

    def test_get_image_details_by_property(self):
        """Tests that a detailed call can be filtered by a property"""
        extra_fixture = {'id': 3,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None,
                         'properties': {'p a': 'v a'}}

        glance.registry.db.api.image_create(None, extra_fixture)

        images = self.client.get_images_detailed({'property-p a': 'v a'})
        self.assertEquals(len(images), 1)

        for image in images:
            self.assertEquals('v a', image['properties']['p a'])

    def test_get_image(self):
        """Tests that the detailed info about an image returned"""
        fixture = {'id': 1,
                   'name': 'fake image #1',
                   'is_public': False,
                   'disk_format': 'ami',
                   'container_format': 'ami',
                   'status': 'active',
                   'size': 13,
                   'location': "swift://user:passwd@acct/container/obj.tar.0",
                   'properties': {'type': 'kernel'}}

        data = self.client.get_image(1)

        for k, v in fixture.items():
            el = data[k]
            self.assertEquals(v, data[k],
                              "Failed v != data[k] where v = %(v)s and "
                              "k = %(k)s and data[k] = %(el)s" % locals())

    def test_get_image_non_existing(self):
        """Tests that NotFound is raised when getting a non-existing image"""

        self.assertRaises(exception.NotFound,
                          self.client.get_image,
                          42)

    def test_add_image_basic(self):
        """Tests that we can add image metadata and returns the new id"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vmdk',
                   'container_format': 'ovf',
                   'size': 19,
                   'location': "file:///tmp/glance-tests/acct/3.gz.0",
                  }

        new_image = self.client.add_image(fixture)

        # Test ID auto-assigned properly
        self.assertEquals(3, new_image['id'])

        # Test all other attributes set
        data = self.client.get_image(3)

        for k, v in fixture.items():
            self.assertEquals(v, data[k])

        # Test status was updated properly
        self.assertTrue('status' in data.keys())
        self.assertEquals('active', data['status'])

    def test_add_image_with_properties(self):
        """Tests that we can add image metadata with properties"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vmdk',
                   'container_format': 'ovf',
                   'size': 19,
                   'location': "file:///tmp/glance-tests/2",
                   'properties': {'distro': 'Ubuntu 10.04 LTS'}}

        new_image = self.client.add_image(fixture)

        # Test ID auto-assigned properly
        self.assertEquals(3, new_image['id'])

        for k, v in fixture.items():
            self.assertEquals(v, new_image[k])

        # Test status was updated properly
        self.assertTrue('status' in new_image.keys())
        self.assertEquals('active', new_image['status'])

    def test_add_image_already_exists(self):
        """Tests proper exception is raised if image with ID already exists"""
        fixture = {'id': 2,
                   'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vmdk',
                   'container_format': 'ovf',
                   'status': 'bad status',
                   'size': 19,
                   'location': "file:///tmp/glance-tests/2",
                  }

        self.assertRaises(exception.Duplicate,
                          self.client.add_image,
                          fixture)

    def test_add_image_with_bad_status(self):
        """Tests proper exception is raised if a bad status is set"""
        fixture = {'id': 3,
                   'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vmdk',
                   'container_format': 'ovf',
                   'status': 'bad status',
                   'size': 19,
                   'location': "file:///tmp/glance-tests/2",
                  }

        self.assertRaises(exception.Invalid,
                          self.client.add_image,
                          fixture)

    def test_update_image(self):
        """Tests that the /images PUT registry API updates the image"""
        fixture = {'name': 'fake public image #2',
                   'disk_format': 'vmdk'}

        self.assertTrue(self.client.update_image(2, fixture))

        # Test all other attributes set
        data = self.client.get_image(2)

        for k, v in fixture.items():
            self.assertEquals(v, data[k])

    def test_update_image_not_existing(self):
        """Tests non existing image update doesn't work"""
        fixture = {'id': 3,
                   'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vmdk',
                   'container_format': 'ovf',
                   'status': 'bad status',
                  }

        self.assertRaises(exception.NotFound,
                          self.client.update_image,
                          3,
                          fixture)

    def test_delete_image(self):
        """Tests that image metadata is deleted properly"""

        # Grab the original number of images
        orig_num_images = len(self.client.get_images())

        # Delete image #2
        self.assertTrue(self.client.delete_image(2))

        # Verify one less image
        new_num_images = len(self.client.get_images())

        self.assertEquals(new_num_images, orig_num_images - 1)

    def test_delete_image_not_existing(self):
        """Tests cannot delete non-existing image"""

        self.assertRaises(exception.NotFound,
                          self.client.delete_image,
                          3)


class TestClient(unittest.TestCase):

    """
    Test proper actions made for both valid and invalid requests
    against a Glance service
    """

    def setUp(self):
        """Establish a clean test environment"""
        self.stubs = stubout.StubOutForTesting()
        stubs.stub_out_registry_db_image_api(self.stubs)
        stubs.stub_out_registry_and_store_server(self.stubs)
        stubs.stub_out_filesystem_backend()
        self.client = client.Client("0.0.0.0", doc_root="")

    def tearDown(self):
        """Clear the test environment"""
        stubs.clean_out_fake_filesystem_backend()
        self.stubs.UnsetAll()

    def test_get_image(self):
        """Test a simple file backend retrieval works as expected"""
        expected_image = 'chunk00000remainder'
        expected_meta = {'id': 2,
                   'name': 'fake image #2',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf',
                   'status': 'active',
                   'size': 19,
                   'location': "file:///tmp/glance-tests/2",
                   'properties': {}}
        meta, image_chunks = self.client.get_image(2)

        image_data = ""
        for image_chunk in image_chunks:
            image_data += image_chunk

        self.assertEquals(expected_image, image_data)
        for k, v in expected_meta.items():
            self.assertEquals(v, meta[k])

    def test_get_image_not_existing(self):
        """Test retrieval of a non-existing image returns a 404"""

        self.assertRaises(exception.NotFound,
                          self.client.get_image,
                          3)

    def test_get_image_index(self):
        """Test correct set of public image returned"""
        fixture = {'id': 2,
                   'name': 'fake image #2'}
        images = self.client.get_images()
        self.assertEquals(len(images), 1)

        for k, v in fixture.items():
            self.assertEquals(v, images[0][k])

    def test_get_image_index_marker(self):
        """Test correct set of public images returned with marker param."""
        extra_fixture = {'id': 3,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #125',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        images = self.client.get_images(marker=4)
        self.assertEquals(len(images), 2)

        for image in images:
            self.assertTrue(image['id'] < 4)

    def test_get_image_index_limit(self):
        """Test correct number of public images returned with limit param."""
        extra_fixture = {'id': 3,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #125',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        images = self.client.get_images(limit=2)
        self.assertEquals(len(images), 2)

    def test_get_image_index_marker_limit(self):
        """Test correct set of images returned with marker/limit params."""
        extra_fixture = {'id': 3,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #125',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        images = self.client.get_images(marker=3, limit=1)
        self.assertEquals(len(images), 1)

        self.assertEquals(images[0]['id'], 2)

    def test_get_image_index_by_base_attribute(self):
        """Tests that an index call can be filtered by a base attribute"""
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        images = self.client.get_images({'name': 'new name! #123'})

        self.assertEquals(len(images), 1)
        self.assertEquals('new name! #123', images[0]['name'])

    def test_get_image_index_by_property(self):
        """Tests that an index call can be filtered by a property"""
        extra_fixture = {'id': 3,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None,
                         'properties': {'p a': 'v a'}}

        glance.registry.db.api.image_create(None, extra_fixture)

        images = self.client.get_images({'property-p a': 'v a'})

        self.assertEquals(len(images), 1)
        self.assertEquals(3, images[0]['id'])

    def test_get_image_details(self):
        """Tests that the detailed info about public images returned"""
        fixture = {'id': 2,
                   'name': 'fake image #2',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf',
                   'status': 'active',
                   'size': 19,
                   'location': "file:///tmp/glance-tests/2",
                   'properties': {}}

        expected = {'id': 2,
                   'name': 'fake image #2',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf',
                   'status': 'active',
                   'size': 19,
                   'location': "file:///tmp/glance-tests/2",
                   'properties': {}}

        images = self.client.get_images_detailed()
        self.assertEquals(len(images), 1)

        for k, v in expected.items():
            self.assertEquals(v, images[0][k])

    def test_get_image_details_marker_limit(self):
        """Test detailed calls are filtered by marker/limit params."""
        extra_fixture = {'id': 3,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        extra_fixture = {'id': 4,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #125',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        images = self.client.get_images_detailed(marker=3, limit=1)
        self.assertEquals(len(images), 1)

        self.assertEquals(images[0]['id'], 2)

    def test_get_image_details_by_base_attribute(self):
        """Tests that a detailed call can be filtered by a base attribute"""
        extra_fixture = {'id': 3,
                         'status': 'active',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None}

        glance.registry.db.api.image_create(None, extra_fixture)

        images = self.client.get_images_detailed({'name': 'new name! #123'})
        self.assertEquals(len(images), 1)

        for image in images:
            self.assertEquals('new name! #123', image['name'])

    def test_get_image_details_by_property(self):
        """Tests that a detailed call can be filtered by a property"""
        extra_fixture = {'id': 3,
                         'status': 'saving',
                         'is_public': True,
                         'disk_format': 'vhd',
                         'container_format': 'ovf',
                         'name': 'new name! #123',
                         'size': 19,
                         'checksum': None,
                         'properties': {'p a': 'v a'}}

        glance.registry.db.api.image_create(None, extra_fixture)

        images = self.client.get_images_detailed({'property-p a': 'v a'})
        self.assertEquals(len(images), 1)

        for image in images:
            self.assertEquals('v a', image['properties']['p a'])

    def test_get_image_meta(self):
        """Tests that the detailed info about an image returned"""
        fixture = {'id': 2,
                   'name': 'fake image #2',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf',
                   'status': 'active',
                   'size': 19,
                   'location': "file:///tmp/glance-tests/2",
                   'properties': {}}

        data = self.client.get_image_meta(2)

        for k, v in fixture.items():
            self.assertEquals(v, data[k])

    def test_get_image_iso_meta(self):
        """Tests that the detailed info about an ISO image is returned"""
        fixture = {'id': 3,
                   'name': 'fake iso image',
                   'is_public': False,
                   'disk_format': 'iso',
                   'container_format': 'bare',
                   'status': 'active',
                   'size': 19,
                   'location': "file:///tmp/glance-tests/3",
                   'properties': {}}

        new_image = self.client.add_image(fixture)
        new_image_id = new_image['id']

        # Test ID auto-assigned properly
        self.assertEquals(3, new_image_id)

        # Test all other attributes set
        data = self.client.get_image_meta(3)

        for k, v in fixture.items():
            self.assertEquals(v, data[k])

    def test_get_image_non_existing(self):
        """Tests that NotFound is raised when getting a non-existing image"""

        self.assertRaises(exception.NotFound,
                          self.client.get_image,
                          42)

    def test_add_image_without_location_or_raw_data(self):
        """Tests client returns image as queued"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf',
                  }
        image_meta = self.client.add_image(fixture)
        self.assertEquals('queued', image_meta['status'])
        self.assertEquals(0, image_meta['size'])

    def test_add_image_basic(self):
        """Tests that we can add image metadata and returns the new id"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf',
                   'size': 19,
                   'location': "file:///tmp/glance-tests/2",
                  }
        new_image = self.client.add_image(fixture)
        new_image_id = new_image['id']

        # Test ID auto-assigned properly
        self.assertEquals(3, new_image_id)

        # Test all other attributes set
        data = self.client.get_image_meta(3)

        for k, v in fixture.items():
            self.assertEquals(v, data[k])

        # Test status was updated properly
        self.assertTrue('status' in data.keys())
        self.assertEquals('active', data['status'])

    def test_add_image_with_properties(self):
        """Tests that we can add image metadata with properties"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf',
                   'size': 19,
                   'location': "file:///tmp/glance-tests/2",
                   'properties': {'distro': 'Ubuntu 10.04 LTS'},
                  }
        new_image = self.client.add_image(fixture)
        new_image_id = new_image['id']

        # Test ID auto-assigned properly
        self.assertEquals(3, new_image_id)

        # Test all other attributes set
        data = self.client.get_image_meta(3)

        for k, v in fixture.items():
            self.assertEquals(v, data[k])

        # Test status was updated properly
        self.assertTrue('status' in data)
        self.assertEquals('active', data['status'])

    def test_add_image_with_iso_properties(self):
        """Tests that we can add image metadata with ISO disk format"""
        fixture = {'name': 'fake public iso',
                   'is_public': True,
                   'disk_format': 'iso',
                   'container_format': 'bare',
                   'size': 19,
                   'location': "file:///tmp/glance-tests/2",
                   'properties': {'install': 'Bindows Heaven'},
                  }
        new_image = self.client.add_image(fixture)
        new_image_id = new_image['id']

        # Test ID auto-assigned properly
        self.assertEquals(3, new_image_id)

        # Test all other attributes set
        data = self.client.get_image_meta(3)

        for k, v in fixture.items():
            self.assertEquals(v, data[k])

        # Test status was updated properly
        self.assertTrue('status' in data)
        self.assertEquals('active', data['status'])

    def test_add_image_with_bad_iso_properties(self):
        """Verify that ISO with invalid container format is rejected.
        Intended to exercise error path once rather than be exhaustive
        set of mismatches"""
        fixture = {'name': 'fake public iso',
                   'is_public': True,
                   'disk_format': 'iso',
                   'container_format': 'vhd',
                   'size': 19,
                   'location': "file:///tmp/glance-tests/3",
                   'properties': {'install': 'Bindows Heaven'},
                  }

        self.assertRaises(exception.Invalid,
            self.client.add_image,
            fixture)

    def test_add_image_already_exists(self):
        """Tests proper exception is raised if image with ID already exists"""
        fixture = {'id': 2,
                   'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf',
                   'status': 'bad status',
                   'size': 19,
                   'location': "file:///tmp/glance-tests/2",
                  }

        self.assertRaises(exception.Duplicate,
                          self.client.add_image,
                          fixture)

    def test_add_image_with_bad_status(self):
        """Tests a bad status is set to a proper one by server"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf',
                   'status': 'bad status',
                   'size': 19,
                   'location': "file:///tmp/glance-tests/2",
                  }

        new_image = self.client.add_image(fixture)
        self.assertEquals(new_image['status'], 'active')

    def test_add_image_with_image_data_as_string(self):
        """Tests can add image by passing image data as string"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf',
                   'size': 19,
                   'properties': {'distro': 'Ubuntu 10.04 LTS'},
                  }

        image_data_fixture = r"chunk00000remainder"

        new_image = self.client.add_image(fixture, image_data_fixture)
        new_image_id = new_image['id']
        self.assertEquals(3, new_image_id)

        new_meta, new_image_chunks = self.client.get_image(3)

        new_image_data = ""
        for image_chunk in new_image_chunks:
            new_image_data += image_chunk

        self.assertEquals(image_data_fixture, new_image_data)
        for k, v in fixture.items():
            self.assertEquals(v, new_meta[k])

    def test_add_image_with_image_data_as_file(self):
        """Tests can add image by passing image data as file"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf',
                   'size': 19,
                   'properties': {'distro': 'Ubuntu 10.04 LTS'},
                  }

        image_data_fixture = r"chunk00000remainder"

        tmp_image_filepath = '/tmp/rubbish-image'

        if os.path.exists(tmp_image_filepath):
            os.unlink(tmp_image_filepath)

        tmp_file = open(tmp_image_filepath, 'wb')
        tmp_file.write(image_data_fixture)
        tmp_file.close()

        new_image = self.client.add_image(fixture, open(tmp_image_filepath))
        new_image_id = new_image['id']
        self.assertEquals(3, new_image_id)

        if os.path.exists(tmp_image_filepath):
            os.unlink(tmp_image_filepath)

        new_meta, new_image_chunks = self.client.get_image(3)

        new_image_data = ""
        for image_chunk in new_image_chunks:
            new_image_data += image_chunk

        self.assertEquals(image_data_fixture, new_image_data)
        for k, v in fixture.items():
            self.assertEquals(v, new_meta[k])

    def test_add_image_with_image_data_as_string_and_no_size(self):
        """Tests add image by passing image data as string w/ no size attr"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf',
                   'properties': {'distro': 'Ubuntu 10.04 LTS'},
                  }

        image_data_fixture = r"chunk00000remainder"

        new_image = self.client.add_image(fixture, image_data_fixture)
        new_image_id = new_image['id']
        self.assertEquals(3, new_image_id)

        new_meta, new_image_chunks = self.client.get_image(3)

        new_image_data = ""
        for image_chunk in new_image_chunks:
            new_image_data += image_chunk

        self.assertEquals(image_data_fixture, new_image_data)
        for k, v in fixture.items():
            self.assertEquals(v, new_meta[k])

        self.assertEquals(19, new_meta['size'])

    def test_add_image_with_bad_store(self):
        """Tests BadRequest raised when supplying bad store name in meta"""
        fixture = {'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf',
                   'size': 19,
                   'store': 'bad',
                   'properties': {'distro': 'Ubuntu 10.04 LTS'},
                  }

        image_data_fixture = r"chunk00000remainder"

        self.assertRaises(exception.Invalid,
                          self.client.add_image,
                          fixture,
                          image_data_fixture)

    def test_update_image(self):
        """Tests that the /images PUT registry API updates the image"""
        fixture = {'name': 'fake public image #2',
                   'disk_format': 'vmdk'}

        self.assertTrue(self.client.update_image(2, fixture))

        # Test all other attributes set
        data = self.client.get_image_meta(2)

        for k, v in fixture.items():
            self.assertEquals(v, data[k])

    def test_update_image_not_existing(self):
        """Tests non existing image update doesn't work"""
        fixture = {'id': 3,
                   'name': 'fake public image',
                   'is_public': True,
                   'disk_format': 'vhd',
                   'container_format': 'ovf',
                   'status': 'bad status',
                  }

        self.assertRaises(exception.NotFound,
                          self.client.update_image,
                          3,
                          fixture)

    def test_delete_image(self):
        """Tests that image metadata is deleted properly"""

        # Grab the original number of images
        orig_num_images = len(self.client.get_images())

        # Delete image #2
        self.assertTrue(self.client.delete_image(2))

        # Verify one less image
        new_num_images = len(self.client.get_images())

        self.assertEquals(new_num_images, orig_num_images - 1)

    def test_delete_image_not_existing(self):
        """Tests cannot delete non-existing image"""

        self.assertRaises(exception.NotFound,
                          self.client.delete_image,
                          3)
