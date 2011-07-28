# Copyright 2011 OpenStack LLC.
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

from sqlalchemy import *
from migrate import *

from nova import log as logging
from nova import utils

meta = MetaData()

# Add priority column to networks table
priority = Column('priority', Integer())

def upgrade(migrate_engine):
    meta.bind = migrate_engine

    # grab tables and (column for dropping later)
    networks = Table('networks', meta, autoload=True)

    try:
        networks.create_column(priority)
    except Exception:
        logging.error(_("priority column not added to networks table"))
        raise

# TODO(bgh): figure out how to downgrade
def downgrade(migrate_engine):
    logging.error(_("Can't downgrade without losing data"))
    raise Exception
