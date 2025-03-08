# Limited HTTP server for REST services

import socket
import sys
import mimetypes
import http.client
import urllib.parse
from rutifu import *
from .httpClasses import *
from .staticResource import *
from typing import Union


class HttpServer(object):
    def __init__(self, port: Union[int, list] = 80, handler=staticResource, args=(), threads=True, reuse=True,
                 block=True, start=True, one_request=False, accept_period: float = 3.0, accept_queue_size: int = 5):
        """
        :param port: int or list of ints - ports to try to use. First successful bind() is utilized.
        :param handler: function to handle requests. The handler should take a request and response object as arguments.
        AND it returns True if it determines we should shut down the server, else False.
        :param args: Optional tuple of handler specific arguments. Last member in self.args is the server object. So the
        handler can access the server object if needed to set shutdown = True
        :param threads: True -> each request is handled in a separate thread. There is always a dedicated thread created
        to listen for incoming connects. If not threads, the listener thread will also handle the requests.
        :param reuse:
        :param block:
        :param start:
        :param one_request: True -> server will shut down after processing one request.
        :param accept_period: time to wait for a connection (via accept) before checking if we should shut down.
        """
        self.ports = listize(port)
        self.port = 0
        self.handler = handler
        self.args = (*args, self)
        self.threads = threads
        self.reuse = reuse
        self.block = block
        self.socket = None
        self.one_request_only = one_request  # we shut down after one request is processed.
        self.accept_period = accept_period
        self.accept_queue_size = accept_queue_size   # in blocking mode, if an incoming connection is used to trigger a
        # shutdown, we need to ensure that the accept() call is not blocked waiting for that connection. Definitely an
        # issue when using tightly timed clients in tests.
        self.shutdown = False
        if start:
            self.start()

    def start(self):
        """
           Start the server by opening a socket on the specified port and listening for incoming connections. The
           listening is either in a blocking mode or non-blocking. If non-blocking, the invoker must block using its
           own strategy (e.g. sleep(n) or wait for a signal).
        :return: 0 if no port was successful used to listen on (bind failed for all our ports), else the port number
        that was listened on.
        """
        debug("debugHttpServer", "httpServer", "starting")
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self.reuse:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        for port in self.ports:
            try:
                debug("debugHttpServer", "trying port", port)
                self.socket.bind(("", port))
                self.port = port
                debug("debugHttpServer", "opened socket on port", self.port)
                break
            except OSError:
                pass
        if self.port:
            self.socket.listen(self.accept_queue_size)
            startThread(f"httpserver_{self.port}", self.getRequests)
            # at this point, we now have another thread that is listening for incoming connections with a request
            # so we might need to block (if not, our caller will need to block using its own strategy)
            if self.block:
                self._block()
            return self.port
        else:
            self.socket.close()
            log("httpServer", "unable to find an available port")
            return 0

    # wait for requests
    def getRequests(self):
        debug("debugHttpServer", "waiting for request")
        self.socket.settimeout(self.accept_period)  # never block forever if there is a possible shutdown needed
        while True:
            # wait for a connection unless we've already been set to shut down
            if self.shutdown:
                self.socket.close()
                return
            try:  # we might be notified to shut down after we start waiting so use the accept_period max wait time
                (client, addr) = self.socket.accept()
                if self.threads:
                    startThread("httpserver_"+str(addr[0])+"_"+str(addr[1]), self.handleConnection,
                                args=(client, addr,))
                else:
                    self.handleConnection(client, addr)
                    if self.one_request_only:
                        self.shutdown = True
                        self.socket.close()
                        return  # our thread runs-down after one request
            except socket.timeout:
                if self.shutdown:
                    self.socket.close()
                    return
                # otherwise we just keep looping, waiting for a connection.

    def handleConnection(self, client, addr):
        stop = False
        request = HttpRequest()
        self.parseRequest(client, addr, request)
        debugRequest("debugHttpServer", addr, request)
        # send it to the request handler
        response = HttpResponse("HTTP/1.0", 200, {}, None)
        try:
            if self.handler(request, response, *self.args):
                stop = True
        except Exception as ex:
            logException("exception in request handler", ex)
            response.status = 500
            response.data = str(ex)+"\n"
        self.sendResponse(client, addr, response)
        debugResponse("debugHttpServer", addr, response)
        client.close()
        if stop and self.one_request_only:
            self.shutdown = True

    def parseRequest(self, client, addr, request):
        clientFile = client.makefile()
        # start a new request
        (request.method, uri, request.protocol) = fixedList(clientFile.readline().strip("\n").split(" "), 3, "")
        # parse the path string into components
        try:
            (pathStr, queryStr) = urllib.parse.unquote(uri).split("?")
            request.query = dict([fixedList(queryItem.split("="), 2) for queryItem in queryStr.split("&")])
        except ValueError:
            pathStr = uri
            request.query = {}
        request.path = pathStr.lstrip("/").rstrip("/").split("/")
        # read the headers
        request.headers = {}
        (headerName, headerValue) = fixedList(clientFile.readline().strip("\n").split(":"), 2, "")
        while headerName != "":
            request.headers[headerName.strip()] = headerValue.strip()
            (headerName, headerValue) = fixedList(clientFile.readline().strip("\n").split(":"), 2, "")
        # read the data
        try:
            request.data = urllib.parse.unquote(clientFile.read(int(request.headers["Content-Length"])))
        except KeyError:
            request.data = None
        clientFile.close()

    def sendResponse(self, client, addr, response):
        if response.data:
            response.headers["Content-Length"] = len(response.data)
        else:
            response.headers["Content-Length"] = 0
        response.headers["Connection"] = "close"
        try:
            reason = http.client.responses[response.status]
        except KeyError:
            reason = ""
        try:
            client.send(bytes(response.protocol+" "+str(response.status)+" "+reason+"\n", "utf-8"))
            for header in response.headers:
                client.send(bytes(header+": "+str(response.headers[header])+"\n", "utf-8"))
            client.send(bytes("\n", "utf-8"))
            if response.data:
                if isinstance(response.data, str):
                    client.send(bytes(response.data, "utf-8"))
                else:
                    client.send(response.data)
        except BrokenPipeError:     # can't do anything about this
            log("sendResponse", "broken pipe", addr[0])
            return

    def _block(self):
        """
        Block the calling thread indefinitely until we are set to shut down
        :return: None
        """
        while True:
            if self.shutdown:
                return
            time.sleep(1)
