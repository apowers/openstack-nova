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

"""
Client classes for callers of a Glance system
"""

import httplib
import json
import logging
import urlparse
import socket
import sys
import urllib

from glance import utils
from glance.common import exception

#TODO(jaypipes) Allow a logger param for client classes


class ClientConnectionError(Exception):
    """Error resulting from a client connecting to a server"""
    pass


class ImageBodyIterator(object):

    """
    A class that acts as an iterator over an image file's
    chunks of data.  This is returned as part of the result
    tuple from `glance.client.Client.get_image`
    """

    CHUNKSIZE = 65536

    def __init__(self, response):
        """
        Constructs the object from an HTTPResponse object
        """
        self.response = response

    def __iter__(self):
        """
        Exposes an iterator over the chunks of data in the
        image file.
        """
        while True:
            chunk = self.response.read(ImageBodyIterator.CHUNKSIZE)
            if chunk:
                yield chunk
            else:
                break


class BaseClient(object):

    """A base client class"""

    CHUNKSIZE = 65536

    def __init__(self, host, port, use_ssl):
        """
        Creates a new client to some service.

        :param host: The host where service resides
        :param port: The port where service resides
        :param use_ssl: Should we use HTTPS?
        """
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.connection = None

    def get_connection_type(self):
        """
        Returns the proper connection type
        """
        if self.use_ssl:
            return httplib.HTTPSConnection
        else:
            return httplib.HTTPConnection

    def do_request(self, method, action, body=None, headers=None,
                   params=None):
        """
        Connects to the server and issues a request.  Handles converting
        any returned HTTP error status codes to OpenStack/Glance exceptions
        and closing the server connection. Returns the result data, or
        raises an appropriate exception.

        :param method: HTTP method ("GET", "POST", "PUT", etc...)
        :param action: part of URL after root netloc
        :param body: string of data to send, or None (default)
        :param headers: mapping of key/value pairs to add as headers
        :param params: dictionary of key/value pairs to add to append
                             to action

        :note

        If the body param has a read attribute, and method is either
        POST or PUT, this method will automatically conduct a chunked-transfer
        encoding and use the body as a file object, transferring chunks
        of data using the connection's send() method. This allows large
        objects to be transferred efficiently without buffering the entire
        body in memory.
        """
        if type(params) is dict:
            action += '?' + urllib.urlencode(params)

        try:
            connection_type = self.get_connection_type()
            headers = headers or {}
            c = connection_type(self.host, self.port)

            # Do a simple request or a chunked request, depending
            # on whether the body param is a file-like object and
            # the method is PUT or POST
            if hasattr(body, 'read') and method.lower() in ('post', 'put'):
                # Chunk it, baby...
                c.putrequest(method, action)

                for header, value in headers.items():
                    c.putheader(header, value)
                c.putheader('Transfer-Encoding', 'chunked')
                c.endheaders()

                chunk = body.read(self.CHUNKSIZE)
                while chunk:
                    c.send('%x\r\n%s\r\n' % (len(chunk), chunk))
                    chunk = body.read(self.CHUNKSIZE)
                c.send('0\r\n\r\n')
            else:
                # Simple request...
                c.request(method, action, body, headers)
            res = c.getresponse()
            status_code = self.get_status_code(res)
            if status_code in (httplib.OK,
                               httplib.CREATED,
                               httplib.ACCEPTED,
                               httplib.NO_CONTENT):
                return res
            elif status_code == httplib.UNAUTHORIZED:
                raise exception.NotAuthorized
            elif status_code == httplib.FORBIDDEN:
                raise exception.NotAuthorized
            elif status_code == httplib.NOT_FOUND:
                raise exception.NotFound
            elif status_code == httplib.CONFLICT:
                raise exception.Duplicate(res.read())
            elif status_code == httplib.BAD_REQUEST:
                raise exception.Invalid(res.read())
            elif status_code == httplib.INTERNAL_SERVER_ERROR:
                raise Exception("Internal Server error: %s" % res.read())
            else:
                raise Exception("Unknown error occurred! %s" % res.read())

        except (socket.error, IOError), e:
            raise ClientConnectionError("Unable to connect to "
                                        "server. Got error: %s" % e)

    def get_status_code(self, response):
        """
        Returns the integer status code from the response, which
        can be either a Webob.Response (used in testing) or httplib.Response
        """
        if hasattr(response, 'status_int'):
            return response.status_int
        else:
            return response.status


class V1Client(BaseClient):

    """Main client class for accessing Glance resources"""

    DEFAULT_PORT = 9292

    def __init__(self, host, port=None, use_ssl=False, doc_root="/v1"):
        """
        Creates a new client to a Glance API service.

        :param host: The host where Glance resides
        :param port: The port where Glance resides (defaults to 9292)
        :param use_ssl: Should we use HTTPS? (defaults to False)
        :param doc_root: Prefix for all URLs we request from host
        """

        port = port or self.DEFAULT_PORT
        self.doc_root = doc_root
        super(Client, self).__init__(host, port, use_ssl)

    def do_request(self, method, action, body=None, headers=None, params=None):
        action = "%s/%s" % (self.doc_root, action.lstrip("/"))
        return super(V1Client, self).do_request(method, action, body,
                                                headers, params)

    def get_images(self, filters=None, marker=None, limit=None):
        """
        Returns a list of image id/name mappings from Registry

        :param filters: dictionary of attributes by which the resulting
                        collection of images should be filtered
        :param marker: id after which to start the page of images
        :param limit: maximum number of items to return
        """

        params = filters or {}
        if marker:
            params['marker'] = marker
        if limit:
            params['limit'] = limit
        res = self.do_request("GET", "/images", params=params)
        data = json.loads(res.read())['images']
        return data

    def get_images_detailed(self, filters=None, marker=None, limit=None):
        """
        Returns a list of detailed image data mappings from Registry

        :param filters: dictionary of attributes by which the resulting
                        collection of images should be filtered
        :param marker: id after which to start the page of images
        :param limit: maximum number of items to return
        """

        params = filters or {}
        if marker:
            params['marker'] = marker
        if limit:
            params['limit'] = limit
        res = self.do_request("GET", "/images/detail", params=params)
        data = json.loads(res.read())['images']
        return data

    def get_image(self, image_id):
        """
        Returns a tuple with the image's metadata and the raw disk image as
        a mime-encoded blob stream for the supplied opaque image identifier.

        :param image_id: The opaque image identifier

        :retval Tuple containing (image_meta, image_blob)
        :raises exception.NotFound if image is not found
        """
        res = self.do_request("GET", "/images/%s" % image_id)

        image = utils.get_image_meta_from_headers(res)
        return image, ImageBodyIterator(res)

    def get_image_meta(self, image_id):
        """
        Returns a mapping of image metadata from Registry

        :raises exception.NotFound if image is not in registry
        """
        res = self.do_request("HEAD", "/images/%s" % image_id)

        image = utils.get_image_meta_from_headers(res)
        return image

    def add_image(self, image_meta=None, image_data=None):
        """
        Tells Glance about an image's metadata as well
        as optionally the image_data itself

        :param image_meta: Optional Mapping of information about the
                           image
        :param image_data: Optional string of raw image data
                           or file-like object that can be
                           used to read the image data

        :retval The newly-stored image's metadata.
        """

        headers = utils.image_meta_to_http_headers(image_meta or {})

        if image_data:
            body = image_data
            headers['content-type'] = 'application/octet-stream'
        else:
            body = None

        res = self.do_request("POST", "/images", body, headers)
        data = json.loads(res.read())
        return data['image']

    def update_image(self, image_id, image_meta=None, image_data=None):
        """
        Updates Glance's information about an image
        """
        if image_meta is None:
            image_meta = {}

        headers = utils.image_meta_to_http_headers(image_meta)

        if image_data:
            body = image_data
            headers['content-type'] = 'application/octet-stream'
        else:
            body = None

        res = self.do_request("PUT", "/images/%s" % image_id, body, headers)
        data = json.loads(res.read())
        return data['image']

    def delete_image(self, image_id):
        """
        Deletes Glance's information about an image
        """
        self.do_request("DELETE", "/images/%s" % image_id)
        return True


Client = V1Client
