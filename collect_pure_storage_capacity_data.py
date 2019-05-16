#!/usr/bin/python3
#
#  Title:   collect_pure_storage_capacity_data.py
#  Author:  T. Reppert
#  Description:  This script will collect capacity data from pure frames and insert data into PostgreSQL database for analysis
#
#

import psycopg2
import os
import sys
import subprocess
import string
import re
from pprint import pprint
import datetime
from datetime import date
import json
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
import purestorage

def load_pure_tokens(pure_token_json_file):
    ''' Load pure storage frame tokens '''
    pure_tokens = {}
    try:
        with open(pure_token_json_file) as f:
            pure_tokens = json.loads(f.read())
    except Exception as e:
        print("Issue with opening %s.  Error: %s" % (pure_token_json_file, e))
        sys.exit()
    return pure_tokens

def load_pure_frame_list(pure_info_file):
    ''' Load pure storage frame list '''
    pure_frames = []
    try:
        with open(pure_info_file) as g:
            for line in g:
                pure_frames.append(line.strip().lower())
    except IOError as e:
        print("\n** Error: %s not found. This file is needed for communication mapping to VMAX frame(s) **\n" % pure_info_file)
        print(e)
        sys.exit()
    return pure_frames

def get_capacity_data_rest(array):
    ''' Example pure_array_capacity data:
            [{u'capacity': 27826918078665,
            u'data_reduction': 3.5766608404003124,
            u'hostname': u'PUREFRAME1',
            u'parity': 1.0,
            u'shared_space': 587131778549,
            u'snapshots': 0,
            u'system': 0,
            u'thin_provisioning': 0.1891204666376114,
            u'total': 4868648765139,
            u'total_reduction': 4.410841183238835,
            u'volumes': 4281516986590}]
    '''
    pure_array_capacity = array.get(space=True)[0]
    capacity = float(pure_array_capacity['capacity'])/1024/1024/1024/1024
    data_redux_ratio = float(pure_array_capacity['data_reduction'])
    total_redux_ratio = float(pure_array_capacity['total_reduction'])
    total = float(pure_array_capacity['total'])/1024/1024/1024/1024

    return capacity, total, data_redux_ratio, total_redux_ratio

def add_data_to_database(frame, now, cur, con, array):
    ''' Add capacity data to database
        args:  frame(str) - pure frame
               now(str) - current date
               cur(obj) - postgresql database cursor object
               con(obj) - postgresql database connection object
               array(obj) - purestorage object
    '''
    capacity, total, data_redux_ratio, total_redux_ratio = get_capacity_data_rest(array)
    print("%s\t\t%.02f\t\t%.02f\t\t%.01f\t\t\t%.01f\t\t\t%s" % (frame, capacity, total, data_redux_ratio, total_redux_ratio, now))
    capacity = str(capacity)
    total = str(total)
    data_redux_ratio = str(data_redux_ratio)
    total_redux_ratio = str(total_redux_ratio)
    # Insert capacity data into database
    try:
        cur.execute("INSERT INTO pure_capacity (frame, capacity, total, data_redux_ratio, total_redux_ratio, datetime) VALUES (%s, %s, %s, %s, %s, %s)", (frame, capacity, total, data_redux_ratio, total_redux_ratio, now))
        con.commit()

    except psycopg2.DatabaseError as e:
        print('Error: %s' % e)
        sys.exit(1)

def get_full_frame_name(frame, pure_token_dict):
    for k,v in pure_token_dict.items():
        if frame.lower() in k:
            return k
    print("Issue with finding %s in token file." % frame)
    sys.exit()

def main():

    pure_info_file = "<text file with list of pure storage frame names>"
    pure_frames = load_pure_frame_list(pure_info_file)
    pure_token_file = "<full path to pure_tokens.json file>"
    # pure_token_file is a json file which has the format of { "pureframe1" : "token", "pureframe2" : "token" } 
    #     for each pure storage frame
    pure_token_dict = load_pure_tokens(pure_token_file)

    # Connect to PostgreSQL database
    try:
        con = psycopg2.connect(host='dbserver', database='dbname', user='dbuser', password='##################')
        cur = con.cursor()

    except psycopg2.DatabaseError as e:
        print('Error %s' % e)
        sys.exit(1)

    # Get current date/time
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Add capacity data to database and also print output to console
    print("%s\t\t\t%s\t%s\t%s\t%s\t%s" % ("Frame","Capacity(TB)", "Total(TB)", "Data Reduction Ratio", "Total Reduction Ratio", "Date/Time"))
    for frame in pure_frames:
        full_frame_name = get_full_frame_name(frame, pure_token_dict)
        try:
            array = purestorage.FlashArray(full_frame_name, api_token=pure_token_dict[full_frame_name])
        except Exception as e:
            print("Issue with connecting to frame %s : %s" % (frame, e))
            sys.exit()
        add_data_to_database(frame, now, cur, con, array)

    if con:
        con.close()


if __name__ == '__main__':
    main()
