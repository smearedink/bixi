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
import time as _time
import numpy as _np
import sys as _sys
import matplotlib.pyplot as _plt
import matplotlib.dates as _mdates
from xml.etree import ElementTree as _ET
from sqlalchemy import create_engine as _create_engine
from sqlalchemy.orm import sessionmaker as _sessionmaker

import db_model
from utils import datetime_to_tstamp as _datetime_to_tstamp
from utils import tstamp_to_datetime as _tstamp_to_datetime

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

class Bixi(object):
    def __init__(self, sqlite_db=":memory:", output_sql=False):
        self.sqlite_db = sqlite_db
        self.engine = _create_engine('sqlite:///' + sqlite_db, echo=output_sql)
        db_model.Base.metadata.create_all(self.engine)
        Session = _sessionmaker(bind=self.engine)
        self.session = Session()

    def __repr__(self):
        return "<Bixi: %s>" % self.sqlite_db

    def collect_data(self, nsec_wait=10, verbose=False,\
      data_url=bixi_urls["montreal"]):
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
                    stations_dict = query_bixi_url(data_url)
                except:
                    if verbose:
                        print("Something went wrong while parsing XML.")
                    continue
                if verbose: print("Checking for new data...")

                db_stations = self.session.query(db_model.Station).all()
                db_ids = [s.id for s in db_stations]
                for station_id in stations_dict:
                    if station_id not in db_ids:
                        self.session.add(db_model.Station.from_dict(stations_dict[station_id]))
                for station in db_stations:
                    if station.id in stations_dict:
                        station.update_from_dict(stations_dict[station.id], verbose)

                self.session.commit()
        except KeyboardInterrupt:
            if verbose: print("Stopped after %d iterations." % iter_num)
            self.session.close()

    def plot_all_stations(self, ncol, nrow, start_time=None, end_time=None):
        fig_ts = _plt.figure(figsize=(11,11))
        fig_map = _plt.figure(figsize=(8,8))
        ax_map = fig_map.add_subplot(111)

        lons = []
        lats = []

        db_stations = self.session.query(db_model.Station).all()

#        station_ids = list(self.stations.keys())
        ii = 0
        max_ii = len(db_stations)-1
        for yy in range(nrow):
            for xx in range(ncol):
                if ii > max_ii:
                    break
                ax = fig_ts.add_subplot(nrow, ncol, ii+1)
#                sid = station_ids[ii]
#                self.stations[sid].plot(ax=ax, start_time=start_time,\
#                  end_time=end_time, override_end=self.last_updated)
                db_stations[ii].plot(ax=ax, start_time=start_time,\
                  end_time=end_time) #, override_end=self_updated)
                ax.set_xticks([])
                ax.set_yticks([])
                ax.set_label("%s (%d docks)" % (db_stations[ii].name,\
                  db_stations[ii].ndocks))
                ax.set_gid(ii)
                lons.append(db_stations[ii].lon)
                lats.append(db_stations[ii].lat)
                ii += 1
        
        ax_map.plot(lons, lats, '.', c='black')

        #fig.tight_layout(pad=1., h_pad=0.1, w_pad=0.1)
        txt = fig_ts.text(0.4, 0.92, "Click a plot to see which station it is")
        dot = ax_map.plot(lons[0], lats[0], 'o', c='red')

        def click_on_axes(event):
            txt.set_text(event.inaxes.get_label())
            ii = event.inaxes.get_gid()
            st = db_stations[ii]
            dot[0].set_data([st.lon], [st.lat])
            event.canvas.draw()
            fig_map.canvas.draw()

        fig_ts.canvas.mpl_connect('button_press_event', click_on_axes)

    def plot_total_activity(self, start_time, end_time, dt, activity_type='both', return_vals=False):
        db_stations = self.session.query(db_model.Station).all()

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
        for s in db_stations:
            try:
                tot_hist += s.activity_histogram(time_ax, activity_type=activity_type)
            except:
                print("Getting activity failed for station",\
                  "%d with error:\n  %s" %\
                  (s.id, _sys.exc_info()[1]))

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


"""
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
"""
