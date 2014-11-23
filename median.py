#!/usr/bin/env python
# print the median of a HTTP response code from the access.log file
# thanks to Steve P. for his advise and suggestions to improve the code
import os
import re
import time
import BaseHTTPServer
import threading
import Queue
from time import sleep
import json

SAMPLE = """66.194.6.80 - - [02/Oct/2005:19:52:46 +0100] "GET / HTTP/1.1" 200 2334 "-" "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; Q312460)" 11 sproglogs.com
208.53.82.111 - - [02/Oct/2005:20:14:49 +0100] "GET /account/login HTTP/1.1" 200 3679 "-" "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1; .NET CLR 1.1.4322)" 5 sproglogs.com
208.53.82.111 - - [02/Oct/2005:20:14:56 +0100] "GET /stylesheets/standard.css HTTP/1.1" 200 8329 "http://sproglogs.com/account/login" "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1; .NET CLR 1.1.4322)" 0 sproglogs.com
"""

CLF = re.compile(r'^\S+ \S+ \S+ \[.*?\] \".*?\" (?P<code>\d+) (?P<bytes>\d+) ')

requests = {}

# requests is { "code" => [size, size, ...], "code" => [size, size, size] }
# we could also recalculate the median everytime a new value is added
def parse_clf(reqs, seq):
    print "inside parse_clf"
    for line in seq:
        print "inside parse_clf inside for loop"
        match = CLF.search(line)
        if match:
            print "inside parse_clf:found match " + match.group("code")
            code = match.group("code")
            print "code: " + code
            size = int(match.group("bytes"))
            print "size: " + str(size)
            sizes = reqs.setdefault(code, [])
            sizes.append(size)
            print sizes
    # we never really get here, do we?
    print "leaving parse_clf"
    # and is this pro-forma too?
    return reqs


def median(items):
    s = sorted(items)
    print s
    if len(s) == 0:
        return None
    # odd?
    if len(s) % 2 == 1:
        return s[len(s) / 2]
    # even!
    i1 = len(s) / 2
    i2 = i1-1
    med = (s[i1] + s[i2])  / 2.0
    print "median: " + str(med) 
    return med

# assert median([]) is None
# assert median([1]) == 1
# assert median([1, 2, 3]) == 2
# assert median([1, 1]) == 1
# assert median([1, 2]) == 1.5

def follow(thefile):
#    thefile.seek(0,2)
    print "inside follow before while"
    while True:
        line = thefile.readline()
        if not line:
            time.sleep(0.1)
            continue
        print "yielding line " + line
        yield line
        
        
class MedianRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    def do_GET(s):
        #pool_sema.acquire()
        #print "thread 1: inside do_GET" 
        #pool_sema.release()        
        code = s.path[1:]
        pool_sema.acquire()
        print "code: " + code
        print "size requests: " + str ( len(requests))
        #for (code, sizes) in requests.items():
        #    print code, "inside do_GET -> ", median(sizes), " (", len(sizes), " reqs )"
        pool_sema.release()                
        sizes = requests.get(code, [])
        s.send_response(200)
        s.send_header("Content-type", "text/plain")
        s.end_headers()
        #m=median(sizes)
        #print "inside do_GET median: " + str(m)
        #pool_sema.acquire()
        #print "thread 1: after call to median with sizes: " + sizes + " median = " + str(m)
        #pool_sema.release()        
        j={"median_size": str(median(sizes))}
        json.dump(j,s.wfile)
        #s.wfile.write(json.dumps({"median_size": str(median(sizes))}))

def run_server(requests):
    pool_sema.acquire()
    print "thread 1: starting" 
    pool_sema.release()
    server_address = ('', 8000)
    httpd = BaseHTTPServer.HTTPServer(server_address, MedianRequestHandler)
    httpd.serve_forever()

def parse_log_file(requests):
    try:
        #print "inside try inside parse_log_file"
        parse_clf(requests, follow(open("access.log", 'r')))
    except KeyboardInterrupt:
        pass
    print "RESULTS:"
    for (code, sizes) in requests.items():
        print code, " -> ", median(sizes), " (", len(sizes), " reqs )"


# main function
if __name__ == "__main__":
    #print "inside main"
    maxconnections = 1
    http_server_thread = threading.Thread(target=run_server, args=[requests])
    log_parser_thread = threading.Thread(target=parse_log_file, args=[requests])
    pool_sema = threading.BoundedSemaphore(value=maxconnections)
    log_parser_thread.start()
    http_server_thread.start()
else:
    print "we don't run as module"
