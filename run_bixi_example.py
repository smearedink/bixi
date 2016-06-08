# copy this to wherever and run it with the bixi module in your pythonpath

from bixi import Bixi, bixi_urls

db_fname = "bixi.db"
bixi = Bixi(db_fname)
bixi.collect_data(verbose=True, data_url=bixi_urls["montreal"])
