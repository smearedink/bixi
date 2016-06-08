from __future__ import absolute_import as _absolute_import
from __future__ import with_statement as _with_statement
from __future__ import print_function as _print_function
from __future__ import unicode_literals as _unicode_literals
from __future__ import division as _division

import numpy as _np
import time as _time
from sqlalchemy.ext.declarative import declarative_base as _declarative_base
from sqlalchemy.orm import relationship as _relationship
import sqlalchemy as _sql

from utils import datetime_to_tstamp as _datetime_to_tstamp
from utils import tstamp_to_datetime as _tstamp_to_datetime

Base = _declarative_base()

class Station(Base):
    """
    Information about a particular bike station in a Bixi system, including
    its location, the total number of docks, its name, the last time it was
    updated, and the number of bikes over time if data have been collected.
    """
    __tablename__ = 'stations'

    id = _sql.Column(_sql.Integer, primary_key=True)
    name = _sql.Column(_sql.String)
    lat = _sql.Column(_sql.Float)
    lon = _sql.Column(_sql.Float)
    ndocks = _sql.Column(_sql.Integer)

    bike_count = _relationship(
        "BikeCount", order_by="BikeCount.time", back_populates="station")

    def __repr__(self):
        return "<Station %d: %s>" % (self.id, self.name)

    @classmethod
    def from_dict(cls, station_dict):
        new_station = cls()
        new_station.set_info_from_dict(station_dict)
        new_station.update_from_dict(station_dict)
        return new_station

    def set_info_from_dict(self, station_dict):
        self.id = station_dict["id"]
        self.name = station_dict["name"]
        self.lat = station_dict["lat"]
        self.lon = station_dict["long"]
        self.ndocks = station_dict["nbBikes"] + station_dict["nbEmptyDocks"]

    def update_from_dict(self, station_dict, verbose=False):
        count = BikeCount(time=station_dict["lastUpdateTime"],\
          nbikes=station_dict["nbBikes"])
        b_times = [b.time for b in self.bike_count]
        b_nbikes = [b.nbikes for b in self.bike_count]
        if count.time not in b_times:
            if len(b_times):
                last_nbikes = b_nbikes[_np.argsort(b_times)[-1]]
            else:
                last_nbikes = -1
            if count.nbikes != last_nbikes:
                self.bike_count.append(count)
                if verbose:
                    print("Updated station %s" % self.name)

    def plot(self, ax=None, start_time=None, end_time=None, override_end=None):
        """
        start_time and end_time are datetime objects. If None, the earliest
        or latest timestamp for the station is used.
        override_end is a timestamp, adds extra point to end of timeseries
        at given time with same nbikes as previous time
        """
#        if len(self.times) < 1 or self.last_updated is None:
#            print("No plottable data for station %d" % self.station_id)
#            if ax is not None:
#                ax.set_axis_bgcolor('black')
#            return
        
        times = _np.array([b.time for b in self.bike_count])
        nbikes = _np.array([b.nbikes for b in self.bike_count])
        time_order = _np.argsort(times)
        times = times[time_order]
        nbikes = nbikes[time_order]

        if start_time is None: t1 = times[0]
        else: t1 = start_time
############        if end_time is None: t2 = self.last_updated or times[-1]
        if end_time is None: t2 = times[-1]
        else: t2 = end_time

        if override_end is not None:
            plot_times = list(times) + [override_end]
            plot_nbikes = list(nbikes) + [nbikes[-1]]
        else:
            plot_times = list(times) #########+ [self.last_updated]
            plot_nbikes = list(nbikes)

        #tscale = 1000 * 60

        if ax is None:
            fig = _plt.figure(figsize=(12,6))
            ax = fig.add_subplot(111)
            ax.set_xlabel("Time")
            ax.set_ylabel("Number of bikes")
            ax.set_title(self.name)

        ax.set_axis_bgcolor('black')
        ax.fill_between([plot_times[0], plot_times[-1]],\
          [self.ndocks]*2, lw=0, color='0.3')
        ax.fill_between(_np.repeat(plot_times, 2)[1:],\
          _np.repeat(plot_nbikes ,2)[:-1], lw=0, color='0.6')
        ax.set_xlim(t1, t2)
        ax.set_ylim(0, self.ndocks)
        ax.grid(axis="y", color="white")

    def activity_histogram(self, tstamp_bin_edges, activity_type='both'):
        """
        activity_type can be 'both', 'diff', 'increase', or 'decrease'
        """ 
        times = _np.array([b.time for b in self.bike_count])
        nbikes = _np.array([b.nbikes for b in self.bike_count])
        time_order = _np.argsort(times)

        times = [_datetime_to_tstamp(t) for t in times[time_order]]
        nbikes = nbikes[time_order]

        hist = _np.zeros(len(tstamp_bin_edges)-1, dtype=int)
        hist_ii = 0
        nbikes_diff = _np.diff(nbikes)
        for ii,t in enumerate(times[1:]):
            if t >= tstamp_bin_edges[0] and t <= tstamp_bin_edges[-1]:
                hist_ii += _np.searchsorted(tstamp_bin_edges[1:][hist_ii:], t)
                if activity_type.lower()=='increase' and nbikes_diff[ii] > 0:
                    hist[hist_ii] += nbikes_diff[ii]
                elif activity_type.lower()=='decrease' and nbikes_diff[ii] < 0:
                    hist[hist_ii] += -nbikes_diff[ii]
                elif activity_type.lower()=='both':
                    hist[hist_ii] += _np.abs(nbikes_diff[ii])
                elif activity_type.lower()=='diff':
                    hist[hist_ii] += nbikes_diff[ii]
        return hist

class BikeCount(Base):
    """
    The number of bikes in each station over time.
    """
    __tablename__ = 'bikecounts'

    id = _sql.Column(_sql.Integer, primary_key=True)
    time = _sql.Column(_sql.DateTime)
    nbikes = _sql.Column(_sql.Integer)
    station_id = _sql.Column(_sql.Integer, _sql.ForeignKey("stations.id"))
    station = _relationship("Station", back_populates="bike_count")

    def __repr__(self):
        return "<BikeCount: %d bikes at station id %d>" %\
          (self.nbikes, self.station.id)

