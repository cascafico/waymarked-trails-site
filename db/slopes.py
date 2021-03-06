# This file is part of the Waymarked Trails Map Project
# Copyright (C) 2015 Sarah Hoffmann
#
# This is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

""" Database for the combinded route/way view (slopes)
"""
from collections import namedtuple, OrderedDict

import osgende
from osgende.relations import RouteSegments
from osgende.ways import JoinedWays
from osgende.tags import TagStore

from sqlalchemy import text, select, func, and_, column, exists, not_

from db.tables.piste import PisteRouteInfo, PisteWayInfo, PisteSegmentStyle
from db.tables.piste import _basic_tag_transform as piste_tag_transform
from db.configs import SlopeDBConfig, PisteTableConfig
from db.routes import DB as RoutesDB
from db import conf

CONF = conf.get('ROUTEDB', SlopeDBConfig)
PISTE_CONF = conf.get('PISTE', PisteTableConfig)

class DB(RoutesDB):
    routeinfo_class = PisteRouteInfo
    segmentstyle_class = PisteSegmentStyle

    def create_tables(self):
        # all the route stuff we take from the RoutesDB implmentation
        tables = self.create_table_dict()

        # now create the additional joined ways
        subset = and_(text(CONF.way_subset),
                      not_(exists().where(column('id') == func.any(tables['segments'].data.c.ways))))
        ways = PisteWayInfo(self.metadata, self.osmdata,
                            subset=subset, geom_change=tables['updates'])
        ways.set_num_threads(self.get_option('numthreads'))
        tables['ways'] = ways

        cols = ('name', 'symbol', 'difficulty', 'piste')
        joins = JoinedWays(self.metadata, ways, cols,
                           self.osmdata, name=CONF.joinedway_table)
        tables['joined_ways'] = joins

        _RouteTables = namedtuple('_RouteTables', tables.keys())

        return _RouteTables(**tables)

    def dataview(self):
        schema = self.get_option('schema', '')
        if schema:
            schema += '.'
        with self.engine.begin() as conn:
            conn.execute("""CREATE OR REPLACE VIEW %sdata_view AS
                            (SELECT geom FROM %s%s
                             UNION SELECT geom FROM %s%s)"""
                         % (schema, schema, str(self.tables.style.data.name),
                            schema, str(self.tables.ways.data.name)))


    def mkshield(self):
        route = self.tables.routes
        sway = self.tables.ways

        rel = self.osmdata.relation.data
        way = self.osmdata.way.data
        todo = ((route, select([rel.c.tags]).where(rel.c.id == route.data.c.id)),
                (sway, select([way.c.tags]).where(way.c.id == sway.data.c.id)))

        donesyms = set()

        with self.engine.begin() as conn:
            for src, sel in todo:
                for r in conn.execution_options(stream_results=True).execute(sel):
                    tags = TagStore(r["tags"])
                    t, difficulty = piste_tag_transform(0, tags)
                    sym = src.symbols.create(tags, '', difficulty)

                    if sym is not None:
                        symid = sym.get_id()

                        if symid not in donesyms:
                            donesyms.add(symid)
                            src.symbols.write(sym, True)
