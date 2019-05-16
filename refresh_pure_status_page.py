#!/usr/bin/python3
#
# Name:  refresh_pure_status_page.py
# Author:  T. Reppert
# Description:  This script will generate/update a web status page for a list of Pure Storage frames
# Original creation date:  8/11/2016
#
# Plan for future version of this script:  Use jinja2 html templates instead of embedding html inside this script
#

import re
import subprocess
import os
from datetime import datetime
from pprint import pprint
import socket
import sys
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


def get_hw_state(frame):
    ''' Get hardware state of provided Pure storage frame via SSH '''
    frame_vip = frame
    output = subprocess.Popen(['ssh', '-q', '-o UserKnownHostsFile=/dev/null', '-o StrictHostKeyChecking=no', '-o ConnectTimeout=10',
                               frame_vip, 'purehw', 'list'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    hw_state = output.communicate()[0].decode('utf-8').strip()
    lines = hw_state.splitlines()
    header = lines[0]
    hw_details = {}
    hw_details[frame] = [header]
    lines.pop(0)
    status = 'OK'
    for line in lines:
        fields = line.split()
        if fields[1] != "ok" :
            status = 'Issue'
            hw_details[frame].append(line)
    return status, hw_details


def get_hw_state_rest(frame, array):
    ''' Get hardware state of provided Pure storage frame via RESTAPI '''
    hw_state = array.list_hardware()
    hw_details = {}
    hw_details[frame] = []
    status = 'OK'
    for d in hw_state:
        if d['status'] != 'ok' and d['status'] != 'not_installed':
            status = 'Issue'
            hw_details[frame].append(d)
    return status, hw_details


def get_drive_state_rest(frame, array):
    ''' Get failed drive status in provided Pure storage frame via RESTAPI '''
    drive_state = array.list_drives()
    drive_details = {}
    drive_details[frame] = []
    bad_drives = 0
    status = 'OK'
    for d in drive_state:
        if d['status'] == 'healthy' or d['status'] == 'unused':
            continue
        else:
            status = 'Issue'
            drive_details[frame].append(d)
            bad_drives += 1
    return status, bad_drives, drive_details


def get_drive_state(frame):
    ''' Get failed drive status in provided Pure storage frame via SSH '''
    frame_vip = frame
    bad_drives = 0
    output = subprocess.Popen(['ssh', '-q', '-o UserKnownHostsFile=/dev/null', '-o StrictHostKeyChecking=no', '-o ConnectTimeout=10',
                                   frame_vip,'puredrive', 'list'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    drive_state = output.communicate()[0].decode('utf-8').strip()
    lines = drive_state.splitlines()
    header = lines[0]
    drive_details = {}
    drive_details[frame] = [header]
    lines.pop(0)
    status = 'OK'
    for line in lines:
        fields = line.split()
        if fields[2] == "healthy":
            continue
        elif fields[2] == "unused":
            continue
        else:
            status = 'Issue'
            drive_details[frame].append(line)
            bad_drives += 1
    return status, bad_drives, drive_details


def tcpcheck(frame,port):
    ''' Perform check of tcp connection to target Pure storage frame and ethernet management port '''
    frame_vip = frame
    serverHost = frame_vip # use port from ARGV 1
    serverPort = int(port) # use port from ARGV 2
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  #create a TCP socket
    s.settimeout(8)
    try:
        s.connect((serverHost, serverPort)) #connect to server on the port
        s.shutdown(2) #disconnect
        return "Online"
    except:
        return "Offline"
        sys.exit(1)


def get_full_frame_name(frame, pure_token_dict):
    ''' Obtain full pure storage frame name from pure token dictionary '''
    for k,v in pure_token_dict.items():
        if frame.lower() in k:
            return k
    print("Issue with finding %s in token file." % frame)
    sys.exit()


def main():
    hostname = socket.gethostname()
    pure_info_file = "<name of text file with list of pure frames>"
    pure_token_file = "<full path to pure_tokens.json file>"
    # pure_token_file is a json file which has the format of { "pureframe1" : "token", "pureframe2" : "token" } 
    #     for each pure storage frame
    webfile = "<path/name to .html file to use for pure status page>"
    pure_token_dict = load_pure_tokens(pure_token_file)


    pure_frames = load_pure_frame_list(pure_info_file)
    connectstatus = {}
    for pure_frame in pure_frames:
        connectstatus[pure_frame] = tcpcheck(pure_frame,22)

    hw_status = {}
    drive_status = {}
    drive_summary = {}
    hw_summary = {}
    for pure_frame in pure_frames:
        if connectstatus[pure_frame] == "Online":
            full_frame_name = get_full_frame_name(pure_frame, pure_token_dict)
            try:
                array = purestorage.FlashArray(full_frame_name, api_token=pure_token_dict[full_frame_name])
            except Exception as e:
                print("Issue with connecting to frame %s : %s" % (pure_frame, e))
                sys.exit()

            hw_state, hw_details = get_hw_state_rest(pure_frame, array)

            drive_state, failed_drives, drive_details = get_drive_state_rest(pure_frame, array)

            drive_summary[pure_frame] = drive_details[pure_frame]
            hw_summary[pure_frame] = hw_details[pure_frame]
            print('Pure Frame: '+pure_frame+'\t\t[ Status: '+hw_state+'\tFailed Drives: '+str(failed_drives)+" ]")
            hw_status[pure_frame] = hw_state
            drive_status[pure_frame] = failed_drives
        else:
            hw_status[pure_frame] = "Inaccessible"
            drive_status[pure_frame] = 0

    # Build HTML status page
    htmlpage = ["<html>\n",
                  "<head>\n",
		          "<title>Pure Storage Status</title>\n",
                  "<style type=\"text/css\">\n",
                  "h1{font-family:Arial, sans-serif;font-size:15px}\n",
                  "p{font-family:Arial, sans-serif;font-size:10px}\n",
                  ".tg  {border-collapse:collapse;border-spacing:0;border-color:#ccc;width:925px}\n",
                  ".tg td{font-family:Arial, sans-serif;font-size:11px;padding:5px 5px;border-style:solid;border-width:1px;overflow:hidden;word-break:normal;border-color:#ccc;color:#333;background-color:#fff;text-align:center;}\n",
                  ".tg th{font-family:Arial, sans-serif;font-weight:bold;font-size:12px;padding:5px 5px;border-style:solid;border-width:1px;overflow:hidden;word-break:normal;border-color:#ccc;color:#333;background-color:#f0f0f0;text-align:center;}\n",
                  ".t1 {border-collapse:collapse;border-spacing:0;border-color:#ccc;width:925px}\n",
                  ".t1 td{font-family: 'Ubuntu Mono', monospace;font-size:11px;padding:5px;border-style:solid;border-width:1px;overflow:hidden;word-break:normal;border-color:#ccc;color:#333;background-color:#fff;text-align:left;}\n",
                  ".t2 {font-family:Arial, sans-serif;font-size:11px;padding:5px;border-style:solid;border-width:1px;overflow:hidden;word-break:normal;border-color:#ccc;color:#333;background-color:#fff;text-align:center;}\n",
                  "span{font-family:'Ubuntu Mono',monospace;font-weight:bold;font-size:11px;color:red;background-color:#f0f0f0;}\n",
                  "#container { width:100%;margin:auto; }\n",
                  "#report { width:1115px;margin:auto; }\n",                  
                  "</style>\n",
                  "<link href='https://fonts.googleapis.com/css?family=Montserrat' rel='stylesheet' type='text/css'>\n",
                  "<link href='https://fonts.googleapis.com/css?family=Ubuntu+Mono' rel='stylesheet' type='text/css'>\n",
                  "</head>\n",
                  "<body>\n",
                  "<div id=\"container\">\n",
                  "<div id=\"report\">\n"]

    htmlpage.append("<table class=\"tg\" >\n")
    htmlpage.append("<tr>\n")

    htmlpage.append("    <th style=\"font-size:16px;font-weight:bold;color:rgb(254,80,0)\" colspan=\"100%\">Pure Storage Status Report</th>\n")
    htmlpage.append("</tr>\n")

    htmlpage.append("<tr>\n")
    htmlpage.append("<th class=\"tg\" style=\"font-weight:bold;font-size:12px;\" >Frame:</th>\n")
    for pure_frame in pure_frames:
        htmlpage.append("  <th class=\"tg\" style=\"font-family:Arial, sans-serif;font-weight:regular;\">%s</th>\n" % pure_frame)

    htmlpage.append("</tr>\n")

    htmlpage.append("<tr>\n")
    htmlpage.append("  <td class=\"tg\" style=\"font-size:12px;font-weight:bold;background-color:#f0f0f0;\" >Status:</td>\n")
    for pure_frame in pure_frames:
        if hw_status[pure_frame] == "OK":
            htmlpage.append("  <td class=\"tg\" style=\"background-color:#00FF09;\">%s</td>\n" % hw_status[pure_frame])
        else:
            htmlpage.append("  <td class=\"tg\" style=\"background-color:#F7FF00;\">%s</td>\n" % hw_status[pure_frame])

    htmlpage.append("</tr>\n")
    htmlpage.append("<tr>\n")
    htmlpage.append("  <td class=\"tg\" style=\"font-size:12px;font-weight:bold;background-color:#f0f0f0;\" >Failed Drives:</td>\n")
    for pure_frame in pure_frames:
        if drive_status[pure_frame] == 0:
            htmlpage.append("  <td class=\"tg\" style=\"background-color:#00FF09;\">%s</td>\n" % drive_status[pure_frame])
        else:
            htmlpage.append("  <td class=\"tg\" style=\"background-color:#F7FF00;\">%s</td>\n" % drive_status[pure_frame])

    htmlpage.append("</tr>\n")
    htmlpage.append("</table>\n")

    for pure_frame in pure_frames:
        if hw_status[pure_frame] == "Issue" or drive_status[pure_frame] > 0:
            htmlpage.append("<table class=\"t1\" >\n")
            htmlpage.append("<tr>\n<td class=\"t1\" style=\"font-size:13px;font-family:Arial,sans-serif;background-color:#f0f0f0;color:rgb(254,80,0)\">%s</td>\n</tr>\n" % pure_frame)
            if hw_status[pure_frame] == "Issue":
                htmlpage.append("<tr>\n")
                htmlpage.append("  <td class=\"t1\" style=\"background-color:#f0f0f0;\" ><pre>")
                for line in hw_summary[pure_frame]:
                    htmlpage.append("%s\n" % line)
                htmlpage.append("</pre></td>\n")
                htmlpage.append("</tr>\n")
            if drive_status[pure_frame] > 0:
                htmlpage.append("<tr>\n")
                htmlpage.append("  <td class=\"t1\" style=\"background-color:#f0f0f0;\" ><pre>")
                for line in drive_summary[pure_frame]:
                    htmlpage.append("%s\n" % line)
                htmlpage.append("</pre></td>\n")
                htmlpage.append("</tr>\n")

            htmlpage.append("</table>\n")

    now_string = datetime.now().strftime('%m/%d/%Y %H:%M')
    htmlpage.append("<p>Report generated on %s at %s</p>\n" % (hostname, now_string))
    htmlpage.append("</div>\n")
    htmlpage.append("</div>\n")        
    htmlpage.append("</body>\n")
    htmlpage.append("</html>\n")

    fo = open(webfile, 'w')
    for element in htmlpage:
        fo.write(str(element))
    fo.close()

    os.chmod(webfile, 0o0755)


if __name__ == '__main__':
    main()
