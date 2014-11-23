#!/usr/bin/env python
# by Benedetto Lo Giudice
# the script runs 2 threads
# 1) a thread watches the /home subtree via inotify for files with name 
#    starting with "_" and logs every such file and the creation time in
#    /var/log/newfiles.log. Additionally it saves in memory the same data
# 2) the second thread is a HTTP server that responds to request with format
#    http://server:8888/N where N is a number of seconds. It returns a JSON 
#    containing: the list of files with name starting with "_" created in the 
#    past N seconds and the median of the length of the files' names (basename)
# Notes
# - using inotify with auto_add=True will watch new directories that are created
# - as this is an exercise, I did not have time to consider the implications of 
#   memory usage. There should be a criteria to purge the list of files created
#   or the program will exhaust the system memory eventually
# - other checks that need to be implemented:
#   - check that the /var filesystem (or where /var exists) does not fill up
######################################################################
import os
import re
import time
import BaseHTTPServer
import threading
import Queue
from time import sleep
import json
import pyinotify
import signal
import time


### Globals ##################
# the log file /var/log/newfiles.log
LOG_FILE="/var/log/newfiles.log"

# the following list is used to store all files with name
# starting with "_" creating while the script is active.
# there should be a cleanup periodically or eventually 
# it will exhaust the system memory
files_store = []

# handle pyinotify events.
class EventHandler(pyinotify.ProcessEvent):
    # we only handle creations, ignore the rest
    # log every file with a name matching our RE to the log file
    def process_IN_CREATE(self, event):
        # match files whose name starts with a '_'
        re_file_name = re.compile(r'^_')
        pool_sema.acquire()
        print "File %s was created" % event.pathname
        pool_sema.release()
        # was that a directory? we don't care because auto_add=True
        # takes care of that
        if not event.dir:
            # only consider files whose name starts with "_"
            # write to log and save to list
            match = re_file_name.search(event.name)
            if match:
                pool_sema.acquire()
                print "matched file: " + event.name
                ctime = int(time.time())
                f.write (str(ctime) + " " + event.pathname + "\n") 
                files_store.append ([ctime,event.pathname])
                pool_sema.release()
            else:
                pool_sema.acquire()
                print "File %s ignored" % event.name
                pool_sema.release()

# helper html sender
def send_html(s,http_response_code,message):
    s.send_response(http_response_code)
    s.send_header("Content-type", "text/html")
    s.end_headers()
    s.wfile.write("<html><head><title>Python Challenge</title></head>")
    s.wfile.write("<body><p>%s</p>" % message)
    s.wfile.write("</body></html>")

class MedianRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    def do_GET(s):
        # check that the value is numeric
        # and convert it to an integer
        seconds_from_url = s.path[1:]
        if seconds_from_url.isdigit():
            seconds=int(seconds_from_url)
        else:
            send_html(s,400,"please provide number of seconds")
            return

        # retrieve the files created in the last N seconds and
        # return it in a list
        file_list = retrieve_files_created_in_the_last(seconds)
        # now find the median if the file_list is not empty
        if len(file_list) > 0:
            files_only=[]
            # extract the files from the file_list
            for e in file_list:
                files_only.append(e[0])
            # work out the median and prepare the JSON 
            #print "valid list with length: %d " % len(file_list)
            #print file_list
            med = median_length_file_names(file_list)
            # prepare the JSON
            j={"files": files_only, "median_length": str(med) }
            # send response
            s.send_response(200)
            s.send_header("Content-type", "text/plain")
            s.end_headers()
            json.dump(j,s.wfile)
        else:
            send_html(s,200,"No Entry Found")

# the folloiwng is a brutal way to exit when cntrl-c is pressed
# normally not the ideal wait to terminate threads but in this 
# case it will do as the threads are not doing DB stuff
def handler(signum, frame):
    print "Ending abruptly!"
    os._exit(1)

# calculates the median of the length of the files' names
# file_list contains the file name (with path) and the length of
# of the file name (basename, no path) calculated previously
def median_length_file_names(file_list):
    f = sorted(file_list,key=lambda file: file[1]) # sort file list by name length
    for i in f:
        print i[1]
    if len(f) == 0:
        return None
    # odd?
    if len(f) % 2 == 1:
        med = f[len(f) / 2][1]
        #print "median is: %d" % med
        return float(med)
    # even
    i1 = len(f) / 2 
    i2 = i1 - 1 
    med = (( f[i1][1] + f[i2][1]) / 2.0 ) 
    #print "median is: %d" % med
    return med

# retrieve the files created in the last s seconds from 
# the list in memory
def retrieve_files_created_in_the_last(s):
    #print "inside retrieve_files"
    #print "files_store length: %d" % len(files_store)
    valid_files=[]
    # protect this section
    pool_sema.acquire()
    # sort the list of files by timestamp descending
    f = sorted(files_store,key=lambda file: file[0],reverse=True) 
    now = int(time.time())
    for line in f:
        #print line
        ctime = line[0]
        fpfilename = line[1]
        #print "file timestamp %d now %d interval %d difference %d" % (fs,now,s,now - s)
        # check if the file was created within the chosen time interval
        if ctime >= now - s:
            #print "%s is in" % fpfilename
            file_name = os.path.basename(fpfilename)
            name_length = len(file_name)
            valid_files.append([fpfilename,name_length])
            #print "files_store length: %d" % len(valid_files)
        else:
            # we've reached the end of the range, stop
            break 
    pool_sema.release()
    return valid_files
    
# the web server thread
def run_server():
    server_address = ('', 8888)
    httpd = BaseHTTPServer.HTTPServer(server_address, MedianRequestHandler)
    httpd.serve_forever()

# watch-the-directory thread 
def watch_directory():
    # Watch Manager
    wm = pyinotify.WatchManager()  
    # watched events: only create
    mask = pyinotify.IN_CREATE  
    handler = EventHandler()
    notifier = pyinotify.Notifier(wm, handler)
    wdd = wm.add_watch('/home', mask, rec=True,auto_add=True)
    notifier.loop()

# main function
# here we stitch all together: 2 threads, one for the inotify watch and
# the second for the webserver
if __name__ == "__main__":
    # handle cntrl-c
    signal.signal(signal.SIGINT, handler)
    # buffersize = 0 so it flushes at every write
    f = open ( LOG_FILE, 'a', 0 )
    maxconnections = 1
    http_server_thread = threading.Thread(target=run_server, args=[])
    watch_directory_thread = threading.Thread(target=watch_directory, args=[])
    pool_sema = threading.BoundedSemaphore(value=maxconnections)
    watch_directory_thread.start()
    http_server_thread.start()
    # listen in case of keyboard interrupt
    while True:
        time.sleep(1)
else:
    print "we don't run as module"