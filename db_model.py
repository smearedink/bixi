from __future__ import absolute_import as _absolute_import
from __future__ import with_statement as _with_statement
from __future__ import print_function as _print_function
from __future__ import unicode_literals as _unicode_literals
from __future__ import division as _division

try:
    from urllib.request import urlopen as _urlopen
except:
    from urllib2 import urlopen as _urlopen
from datetime import datetime as _datetime, timedelta as _timedelta
from collections import Iterable as _Iterable
import time as _time
import numpy as _np
import sys as _sys
import matplotlib.pyplot as _plt
import matplotlib.dates as _mdates
import json as _json
from xml.etree import ElementTree as _ET

from sqlalchemy.ext.declarative import declarative_base as _declarative_base
from sqlalchemy.orm import relationship as _relationship
import sqlalchemy as _sql

Base = _declarative_base()

def _tstamp_to_datetime(tstamp):
    return _datetime.fromtimestamp(float(tstamp)/1000)

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
    last_updated = _sql.Column(_sql.DateTime)

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
        if (count.time, count.nbikes) not in zip([b.time for b in self.bike_count], [b.nbikes for b in self.bike_count]):
            self.bike_count.append(count)
            if verbose:
                print("Updated station %s" % self.name)

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



bixi_urls = {
    "boston": "http://feeds.thehubway.com/stations/stations.xml",
    "london": "https://tfl.gov.uk/tfl/syndication/feeds/cycle-hire/livecyclehireupdates.xml",
    "minneapolis": "https://secure.niceridemn.org/data2/bikeStations.xml",
    "montreal": "https://montreal.bixi.com/data/bikeStations.xml",
    "toronto": "http://feeds.bikesharetoronto.com/stations/stations.xml",
    "washingtondc": "http://www.capitalbikeshare.com/data/stations/bikeStations.xml",
}

# These are the tag labels we'll be grabbing from the XML and the types
# we wish to convert them to
tags = {
    'id': int,
    'name': str,
    'lat': float,
    'long': float,
    'nbBikes': int,
    'nbEmptyDocks': int,
    'lastUpdateTime': _tstamp_to_datetime,
}

# Annoyingly, in some systems, some tags have different names, so we check
# those if necessary
alternate_tag_names = {
    'lastUpdateTime': ['latestUpdateTime'],
}

def query_bixi_url(url):
    f = _urlopen(url)
    parsed_xml = _ET.parse(f)
    f.close()

    last_updated = parsed_xml.find('.').get('LastUpdate') or \
                   parsed_xml.find('.').get('LastUpdated') or \
                   parsed_xml.find('.').get('lastUpdate') or \
                   parsed_xml.find('.').get('lastUpdated')
    assert last_updated is not None

    stations = {}
    for station in parsed_xml.findall('./station'):
        installed = station.find('./installed').text
        if installed.lower()[0] == "f":
            continue
        info = {}
        for tag in tags:
            element = station.find('./' + tag)
            if element is None:
                if tag in alternate_tag_names:
                    for alt_tag in alternate_tag_names[tag]:
                        element = station.find('./' + alt_tag)
                        if element is not None:
                            break
            if element is None:
                if tag == 'lastUpdateTime':
                    info[tag] = tags[tag](last_updated)
                else:
                    info[tag] = None
            else:
                info[tag] = tags[tag](element.text)
        stations[info["id"]] = info

    return stations









class BixiSystem(object):
    """
    A class containing a set of bike stations belonging to a single system
    and methods for plotting, updating, etc.
    """
    def __init__(self, stations={}):
        self.stations = {}
        self.last_updated = None

    def __repr__(self):
        return "<BixiSystem: %d stations>" % (len(self.stations))

    @classmethod
    def from_element_tree(cls, xml_tree):
        new_bixi = cls()
        new_bixi.set_stations_from_element_tree(xml_tree)
        return new_bixi

    @classmethod
    def from_json_file(cls, fname):
        with open(fname, 'r') as f:
            json_dict = _json.load(f)
        new_bixi = cls()
        for station_id in json_dict:
            new_bixi.stations[int(station_id)] =\
              Station.from_dict(json_dict[station_id])
        return new_bixi

    def to_json_file(self, fname):
        json_dict = {}
        for station_id in self.stations:
            json_dict[station_id] = self.stations[station_id].__dict__
        with open(fname, 'w') as f:
            _json.dump(json_dict, f)

    def set_stations_from_element_tree(self, xml_tree):
        for xml_element in xml_tree:
            station_id = int(xml_element[0].text)
            self.stations[station_id] = Station.from_element(xml_element)

    def collect_data(self, nsec_wait=10, ignore_time=86400, verbose=False,\
      data_url=bixi_urls["montreal"], **kwargs):
        """
        kwargs:
          dump_wait: If set, dump every dump_wait seconds.
          dump_fname: If dump_wait is set, write to this file. If not set,
                      defaults to "bixi_data.json".
        """
        dump_wait = None
        dump_fname = "bixi_data.json"

        if 'dump_wait' in kwargs:
            dump_wait = kwargs['dump_wait']
        if 'dump_fname' in kwargs:
            dump_fname = kwargs['dump_fname']

        start_time = _datetime.now()
        last_dump = _datetime.now()
        iter_num = 0
        try:
            print("Press Ctrl+C to stop collecting data.")
            while True:
                if iter_num > 0:
                    if verbose: print("Waiting %d seconds..." % nsec_wait)
                    _time.sleep(nsec_wait)
                iter_num += 1
                if verbose: print("Iteration number %d" % iter_num)
                if verbose: print("Querying XML data...")
                try:
                    # NOTE: Incredibly dumb form of error testing: get data
                    # twice and make sure they're the same
                    with _urlopen(data_url) as f:
                        parsed_xml = _ET.parse(f)
                        xml_tree = parsed_xml.getroot()
                    with _urlopen(data_url) as f:
                        parsed_xml = _ET.parse(f)
                        xml_tree_2 = parsed_xml.getroot()
                    if _ET.tostring(xml_tree) != _ET.tostring(xml_tree_2):
                        if verbose: print("Redundant XML tree doesn't match.")
                        continue
                except:
                    if verbose:
                        print("Something went wrong while creating element",\
                          "tree.")
                    continue
                if verbose: print("Checking for new data...")
                try:
                    self.last_updated = int(xml_tree.get('lastUpdate'))
                except:
                    self.last_updated = int(xml_tree.get('LastUpdate'))
                for xml_element in xml_tree:
                    station_id = int(xml_element[0].text)
                    last_comm_with_server = int(xml_element[3].text)
                    current_time = _datetime_to_tstamp(_datetime.now())
                    sec_since_comm = (current_time - last_comm_with_server)/1000
                    if sec_since_comm < ignore_time:
                        if station_id not in self.stations:
                            self.stations[station_id] =\
                              Station.from_element(xml_element)
                        self.stations[station_id].update_from_element(\
                          xml_element, verbose)
                if dump_wait is not None:
                    time_to_dump = dump_wait -\
                      (_datetime.now() - last_dump).total_seconds()
                    if time_to_dump <= 0:
                        if verbose: print("Dumping data...")
                        self.to_json_file(dump_fname)
                        last_dump = _datetime.now()
                    elif verbose: print("%d seconds to dump." % time_to_dump)
        except KeyboardInterrupt:
            nmin = (_datetime.now() - start_time).total_seconds()/60
            print("Stopped after %d iterations and %.1f minutes." %\
              (iter_num, nmin))

    def plot_all_stations(self, ncol, nrow, start_time=None, end_time=None):
        fig_ts = _plt.figure(figsize=(11,11))
        fig_map = _plt.figure(figsize=(8,8))
        ax_map = fig_map.add_subplot(111)

        lons = []
        lats = []

        station_ids = list(self.stations.keys())
        ii = 0
        max_ii = len(station_ids)-1
        for yy in range(nrow):
            for xx in range(ncol):
                if ii > max_ii:
                    break
                ax = fig_ts.add_subplot(nrow, ncol, ii+1)
                sid = station_ids[ii]
                self.stations[sid].plot(ax=ax, start_time=start_time,\
                  end_time=end_time, override_end=self.last_updated)
                ax.set_xticks([])
                ax.set_yticks([])
                ax.set_label("%s (%d docks)" % (self.stations[sid].name,\
                  self.stations[sid].ndocks))
                ax.set_gid(sid)
#                ax_map.plot(self.stations[sid].lon, self.stations[sid].lat,\
#                  '.', c='black')
                lons.append(self.stations[sid].lon)
                lats.append(self.stations[sid].lat)
                ii += 1
        
        ax_map.plot(lons, lats, '.', c='black')

        #fig.tight_layout(pad=1., h_pad=0.1, w_pad=0.1)
        txt = fig_ts.text(0.4, 0.92, "Click a plot to see which station it is")
        dot = ax_map.plot(lons[0], lats[0], 'o', c='red')

        def click_on_axes(event):
            txt.set_text(event.inaxes.get_label())
            sid = event.inaxes.get_gid()
            st = self.stations[sid]
            dot[0].set_data([st.lon], [st.lat])
            event.canvas.draw()
            fig_map.canvas.draw()

        fig_ts.canvas.mpl_connect('button_press_event', click_on_axes)

    def plot_total_activity(self, start_time, end_time, dt, activity_type='both', return_vals=False):
        start_ms = _datetime_to_tstamp(start_time)
        end_ms = _datetime_to_tstamp(end_time)
        dt_ms = dt * 1000
        time_ax = _np.arange(start_ms, end_ms, dt_ms)
        
        timefmt = _mdates.DateFormatter('%H:%M')
        fig = _plt.figure()
        ax = fig.add_subplot(111)
        ax.xaxis_date()
        ax.xaxis.set_major_formatter(timefmt)

        tot_hist = _np.zeros_like(time_ax[:-1])
        for s in self.stations:
            try:
                tot_hist += self.stations[s].activity_histogram(time_ax, activity_type=activity_type)
            except:
                print("Getting activity failed for station",\
                  "%d with error:\n  %s" %\
                  (self.stations[s].station_id, _sys.exc_info()[1]))

        times = [_tstamp_to_datetime(t) for t in time_ax[:-1]]
        ax.plot(times, tot_hist, c="0.3", lw=2)

        curr_line = _datetime(start_time.year, start_time.month, start_time.day)
        while curr_line < end_time:
            ax.axvline(curr_line, color='0.5', ls='--')
            curr_line += _timedelta(days=1)

        ax.set_xlim(start_time, end_time)
        ax.set_xlabel("Time")
        ax.set_ylabel("Total activity across city")

        if return_vals:
            return times, time_ax, tot_hist



    def plot_total_empty_docks(self, start_time, end_time, dt, return_vals=False):
        start_ms = _datetime_to_tstamp(start_time)
        end_ms = _datetime_to_tstamp(end_time)
        dt_ms = dt * 1000
        time_ax = _np.arange(start_ms, end_ms, dt_ms)
        
        timefmt = _mdates.DateFormatter('%H:%M')
        fig = _plt.figure()
        ax = fig.add_subplot(111)
        ax.xaxis_date()
        ax.xaxis.set_major_formatter(timefmt)

        tot_nempty = _np.zeros_like(time_ax)
        for s in self.stations:
            try:
                tot_nempty += self.stations[s].ndocks -\
                  self.stations[s].nbikes_timeseries(time_ax)
            except:
                print("Getting total nbikes failed for station",\
                  "%d with error:\n  %s" %\
                  (self.stations[s].station_id, _sys.exc_info()[1]))

        times = [_tstamp_to_datetime(t) for t in time_ax]
        ax.plot(times, tot_nempty, c="0.3", lw=2)

        curr_line = _datetime(start_time.year, start_time.month, start_time.day)
        while curr_line < end_time:
            ax.axvline(curr_line, color='0.5', ls='--')
            curr_line += _timedelta(days=1)

        ax.set_xlim(start_time, end_time)
        ax.set_xlabel("Time")
        ax.set_ylabel("Number of empty docks across city")

        if return_vals:
            return times, time_ax, tot_nempty

