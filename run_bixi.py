from __future__ import absolute_import, with_statement, print_function,\
  unicode_literals, division
from bixi_system import Bixi, bixi_urls

db_fname = "bixi.db"
bixi = Bixi(db_fname)
bixi.collect_data(verbose=True, data_url=bixi_urls["montreal"])
