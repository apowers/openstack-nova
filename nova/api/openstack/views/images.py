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

import os.path


class ViewBuilder(object):
    """Base class for generating responses to OpenStack API image requests."""

    def __init__(self, base_url):
        """Initialize new `ViewBuilder`."""
        self._url = base_url

    def _format_dates(self, image):
        """Update all date fields to ensure standardized formatting."""
        for attr in ['created_at', 'updated_at', 'deleted_at']:
            if image.get(attr) is not None:
                image[attr] = image[attr].strftime('%Y-%m-%dT%H:%M:%SZ')

    def _format_status(self, image):
        """Update the status field to standardize format."""
        status_mapping = {
            'pending': 'QUEUED',
            'decrypting': 'PREPARING',
            'untarring': 'SAVING',
            'available': 'ACTIVE',
            'killed': 'FAILED',
        }

        try:
            image['status'] = status_mapping[image['status']].upper()
        except KeyError:
            image['status'] = image['status'].upper()

    def _build_server(self, image, image_obj):
        """Indicates that you must use a ViewBuilder subclass."""
        raise NotImplementedError()

    def generate_href(self, image_id):
        """Return an href string pointing to this object."""
        return os.path.join(self._url, "images", str(image_id))

    def build(self, image_obj, detail=False):
        """Return a standardized image structure for display by the API."""
        self._format_dates(image_obj)

        if "status" in image_obj:
            self._format_status(image_obj)

        image = {
            "id": image_obj.get("id"),
            "name": image_obj.get("name"),
        }

        self._build_server(image, image_obj)

        if detail:
            image.update({
                "created": image_obj.get("created_at"),
                "updated": image_obj.get("updated_at"),
                "status": image_obj.get("status"),
            })

            if image["status"] == "SAVING":
                image["progress"] = 0

        return image


class ViewBuilderV10(ViewBuilder):
    """OpenStack API v1.0 Image Builder"""

    def _build_server(self, image, image_obj):
        try:
            image['serverId'] = int(image_obj['properties']['instance_id'])
        except (KeyError, ValueError):
            pass


class ViewBuilderV11(ViewBuilder):
    """OpenStack API v1.1 Image Builder"""

    def _build_server(self, image, image_obj):
        try:
            image['serverRef'] = image_obj['properties']['instance_ref']
        except KeyError:
            return

    def build(self, image_obj, detail=False):
        """Return a standardized image structure for display by the API."""
        image = ViewBuilder.build(self, image_obj, detail)
        href = self.generate_href(image_obj["id"])

        if detail:
            image["metadata"] = image_obj.get("properties", {})

        image["links"] = [{
            "rel": "self",
            "href": href,
        },
        {
            "rel": "bookmark",
            "type": "application/json",
            "href": href,
        },
        {
            "rel": "bookmark",
            "type": "application/xml",
            "href": href,
        }]

        return image
