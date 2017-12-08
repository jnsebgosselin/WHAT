# -*- coding: utf-8 -*-

# Copyright © 2014-2017 Jean-Sebastien Gosselin
# email: jean-sebastien.gosselin@ete.inrs.ca
#
# This file is part of GWHAT (GroundWater Hydrograph Analysis Toolbox).
# Licensed under the terms of the GNU General Public License.


# ---- Imports: standard libraries

import csv
import os
from shutil import rmtree


# ---- Imports: third party

import numpy as np


def calc_dist_from_coord(lat1, lon1, lat2, lon2):
    """
    Compute the  horizontal distance in km between a location given in
    decimal degrees and a set of locations also given in decimal degrees.
    """
    lat1, lon1 = np.radians(lat1), np.radians(lon1)
    lat2, lon2 = np.radians(lat2), np.radians(lon2)

    r = 6373  # r is the Earth radius in km

    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))

    return r * c


def save_content_to_csv(fname, fcontent, mode='w', delimiter=',',
                        encoding='utf8'):
    """
    Save content in a csv file with the specifications provided
    in arguments.
    """
    with open(fname, mode, encoding='utf8') as csvfile:
        writer = csv.writer(csvfile, delimiter=delimiter, lineterminator='\n')
        writer.writerows(fcontent)


def delete_file(filename):
    """Try to delete a file on the disk and return the error if any."""
    try:
        os.remove(filename)
        return None
    except OSError as e:
        print("Error: %s - %s." % (e.filename, e.strerror))
        return e.strerror


def delete_folder_recursively(dirpath):
    """Try to delete all files and sub-folders below the given dirpath."""
    for filename in os.listdir(dirpath):
        filepath = os.path.join(dirpath, filename)
        try:
            rmtree(filepath)
        except OSError:
            os.remove(filepath)