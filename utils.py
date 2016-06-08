import time as _time
from datetime import datetime as _datetime

def tstamp_to_datetime(tstamp):
    return _datetime.fromtimestamp(float(tstamp)/1000)

def datetime_to_tstamp(datetime_val):
    # avoiding datetime.timestamp for python2 compatability
    return int(1000*(_time.mktime(datetime_val.timetuple()) +\
      datetime_val.microsecond/1e6))
