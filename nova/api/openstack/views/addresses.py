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

from nova import utils
from nova.api.openstack import common


class ViewBuilder(object):
    ''' Models a server addresses response as a python dictionary.'''

    def build(self, inst):
        raise NotImplementedError()


class ViewBuilderV10(ViewBuilder):
    def build(self, inst):
        private_ips = self.build_private_parts(inst)
        public_ips = self.build_public_parts(inst)
        return dict(public=public_ips, private=private_ips)

    def build_public_parts(self, inst):
        return utils.get_from_path(inst, 'fixed_ips/floating_ips/address')

    def build_private_parts(self, inst):
        return utils.get_from_path(inst, 'fixed_ips/address')


class ViewBuilderV11(ViewBuilder):
    def build(self, inst):
        # TODO(tr3buchet) - this shouldn't be hard coded to 4...
        private_ips = utils.get_from_path(inst, 'fixed_ips/address')
        private_ips = [dict(version=4, addr=a) for a in private_ips]
        public_ips = utils.get_from_path(inst,
                                         'fixed_ips/floating_ips/address')
        public_ips = [dict(version=4, addr=a) for a in public_ips]
        return dict(public=public_ips, private=private_ips)
