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

bixi_urls = {
    "boston": "http://feeds.thehubway.com/stations/stations.xml",
    "london": "https://tfl.gov.uk/tfl/syndication/feeds/cycle-hire/livecyclehireupdates.xml",
    "minneapolis": "https://secure.niceridemn.org/data2/bikeStations.xml",
    "montreal": "https://montreal.bixi.com/data/bikeStations.xml",
    "toronto": "http://feeds.bikesharetoronto.com/stations/stations.xml",
    "washingtondc": "http://www.capitalbikeshare.com/data/stations/bikeStations.xml",
}

def _tstamp_to_datetime(tstamp):
    return _datetime.fromtimestamp(tstamp/1000)

def _datetime_to_tstamp(datetime_val):
    # avoiding datetime.timestamp for python2 compatability
    return int(1000*(_time.mktime(datetime_val.timetuple()) +\
      datetime_val.microsecond/1e6))

class Station(object):
    """
    A class containing data and methods for an individual bike station.
    """
    def __init__(self, station_id=0, name="", lat=0, lon=0, ndocks=0):
        self.station_id = station_id
        self.name = name
        self.lat = lat
        self.lon = lon
        self.ndocks = ndocks
        
        self.times = []
        self.nbikes = []
        self.last_updated = None

    def __repr__(self):
        return "<Station %d: %d data points>" % (self.station_id,\
          len(self.times))

    @classmethod
    def from_element(cls, xml_element):
        new_station = cls()
        new_station.set_info_from_element(xml_element)
        return new_station

    @classmethod
    def from_dict(cls, info_dict):
        new_station = cls()
        new_station.set_info_from_dict(info_dict)
        new_station.set_data_from_dict(info_dict)
        return new_station

    def set_info_from_element(self, xml_element):
        self.station_id = int(xml_element[0].text)
        self.name = xml_element[1].text
        self.lat = float(xml_element[4].text)
        self.lon = float(xml_element[5].text)
        self.ndocks = int(xml_element[12].text) + int(xml_element[13].text)

    def set_info_from_dict(self, info_dict):
        self.station_id = info_dict["station_id"]
        self.name = info_dict["name"]
        self.lat = info_dict["lat"]
        self.lon = info_dict["lon"]
        self.ndocks = info_dict["ndocks"]

    def set_data_from_dict(self, info_dict):
        if "times" in info_dict and "nbikes" in info_dict:
            self.times = info_dict["times"]
            self.nbikes = info_dict["nbikes"]
            self.last_updated = info_dict["last_updated"]

    def update_from_element(self, xml_element, verbose=False):
        try:
            most_recent_update = int(xml_element[14].text)
        except:
            return
        if len(self.times) == 0 or most_recent_update > self.times[-1]:
            self.times.append(most_recent_update)
            self.nbikes.append(int(xml_element[12].text))
            self.last_updated = int(xml_element[3].text)
            if verbose:
                print("Updated station %s" % self.name)

    def get_nbikes_at_time(self, t, override_endtime=None):
        """
        t is a datetime object or iterable of datetime objects
        override_endtime is a timestamp
        """
        if (len(self.nbikes) < 1) or (self.last_updated is None):
            raise ValueError("No data available for station %d" %\
              self.station_id)
        start_t = _tstamp_to_datetime(self.times[0])
        if override_endtime is None:
            end_t = _tstamp_to_datetime(self.last_updated)
        else:
            end_t = _tstamp_to_datetime(override_endtime)
        if isinstance(t, _Iterable):
            if (min(t) < start_t) or (max(t) > end_t):
                raise ValueError("Time falls outside of data range.")
            else:
                inds = _np.searchsorted(self.times,\
                  [_datetime_to_tstamp(ti) for ti in t])-1
                return [self.nbikes[i] for i in inds]
        else:
            if (t < start_t) or (t > end_t):
                raise ValueError("Time falls outside of data range.")
            else:
                return self.nbikes[_np.searchsorted(self.times,\
                  _datetime_to_tstamp(t))-1]

    def plot(self, ax=None, start_time=None, end_time=None):
        """
        start_time and end_time are datetime objects. If None, the earliest
        or latest timestamp for the station is used.
        """

        if len(self.times) < 1 or self.last_updated is None:
            print("No plottable data for station %d" % self.station_id)
            if ax is not None:
                ax.set_axis_bgcolor('black')
            return
        
        if start_time is None: t1 = self.times[0]
        else: t1 = _datetime_to_tstamp(start_time)
        if end_time is None: t2 = self.last_updated
        else: t2 = _datetime_to_tstamp(end_time)

        plot_times = list(self.times) + [self.last_updated]
        plot_nbikes = list(self.nbikes) + [self.nbikes[-1]]

        tscale = 1000 * 60

        if ax is None:
            fig = _plt.figure(figsize=(12,6))
            ax = fig.add_subplot(111)
            ax.set_xlabel("Time")
            ax.set_ylabel("Number of bikes")
            ax.set_title(self.name)

        ax.set_axis_bgcolor('black')
        ax.fill_between([plot_times[0]/tscale, plot_times[-1]/tscale],\
          [self.ndocks]*2, lw=0, color='0.3')
        ax.fill_between(_np.repeat(plot_times, 2)[1:]/tscale,\
          _np.repeat(plot_nbikes ,2)[:-1], lw=0, color='0.6')
        ax.set_xlim(t1/tscale, t2/tscale)
        ax.set_ylim(0, self.ndocks)
        ax.grid(axis="y", color="white")

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
                  end_time=end_time)
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

    def plot_total_empty_docks(self, start_time, end_time, npts,\
      return_vals=False, use_system_last_updated=True):
        """
        start_time and end_time should be datetime objects
        """
        timefmt = _mdates.DateFormatter('%H:%M')
        
        fig = _plt.figure()
        ax = fig.add_subplot(111)
        ax.xaxis_date()
        ax.xaxis.set_major_formatter(timefmt)

        dt = (end_time-start_time)/npts
        times = []
        curr = start_time
        while curr < end_time:
            times.append(curr)
            curr += dt

        if use_system_last_updated:
            override_endtime = self.last_updated
        else:
            override_endtime = None

        tot_nempty = _np.zeros(len(times), dtype=int)
        for s in self.stations:
            # NOTE this could be better
            try:
                nbikes = _np.array(self.stations[s].get_nbikes_at_time(times,\
                  override_endtime))
                tot_nempty += self.stations[s].ndocks - nbikes
            except:
                print("Getting total nbikes failed for station",\
                  "%d with error:\n  %s" %\
                  (self.stations[s].station_id, _sys.exc_info()[1]))

        ax.plot(times, tot_nempty, c="0.3", lw=2)

        curr_line = _datetime(start_time.year, start_time.month, start_time.day)
        while curr_line < end_time:
            ax.axvline(curr_line, color='0.5', ls='--')
            curr_line += _timedelta(days=1)

        ax.set_xlim(start_time, end_time)
        ax.set_xlabel("Time")
        ax.set_ylabel("Number of empty docks across city")

        if return_vals:
            return times, tot_nempty
