from __future__ import absolute_import, with_statement, print_function,\
  unicode_literals, division
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db_model import Base, Station, BikeCount, query_bixi_url, bixi_urls

db_fname = "bixi.db"

engine = create_engine('sqlite:///' + db_fname)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

verbose = True
nsec_wait = 10
iter_num = 0
try:
    print("Press Ctrl+C to stop collecting data.")
    while True:
        if iter_num > 0:
            if verbose: print("Waiting %d seconds..." % nsec_wait)
            time.sleep(nsec_wait)
        iter_num += 1
        if verbose: print("Iteration number %d" % iter_num)
        if verbose: print("Querying XML data...")
        try:
            stations_dict = query_bixi_url(bixi_urls["montreal"])
        except:
            if verbose:
                print("Something went wrong while parsing XML.")
            continue
        if verbose: print("Checking for new data...")

        db_stations = session.query(Station).all()
        db_ids = [s.id for s in db_stations]
        for station_id in stations_dict:
            if station_id not in db_ids:
                session.add(Station.from_dict(stations_dict[station_id]))
        for station in db_stations:
            if station.id in stations_dict:
                station.update_from_dict(stations_dict[station.id], verbose)
                
        session.commit()
except KeyboardInterrupt:
    session.close()
