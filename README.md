# picohttp - A minimal HTTP server

This is an HTTP 1.0 server framework that is useful for supporting applications where the behavior is constrained and relatively simple.

An application can define a server that listens for HTTP requests on a designated port, parses the request, and passes the request to a handler that is implemented by the application.  The request handler can access the parsed elements of the request and pass elements to the response.  When the handler returns, the server builds the HTTP response and sends it to the client.

The TCP connection from a client is closed after the response is sent.  Persistent HTTP 1.1 connections are not supported.  Every request is handled in a separate thread unless the server is instantiated with `threads=False`.  The server will start immediately unless it is instantiated with `start=False`, in which case the `start()` function must be called.  When the server starts it will block indefinitely unless it is instantiated with `block=False`.

The server does not attempt to validate any of the elements of the request or response, it just passes them to and from the request handler.  Any method, header, or status code may be used whether it is valid or not.  It is the responsibility of the request handler to perform any validation that may be required.  The server does require a valid Content-Length header if there is data present in the body of the request, otherwise the data will be ignored.

If the request handler does not assign a value to the response status code, it is assumed to be 200.  A Content-Length header is automatically added in the response to indicate the length of the response data.

### Specification

The HttpServer class is used to instantiate an HTTP server object.

**`class HttpServer(port=80, handler=staticResource, args=(), threads=True, start=True, block=True)`**

    port
        The port to listen on. An int or list of int values.

    handler
        The function defined to be the request handler.

    args
        A tuple containing optional additional arguments to be passed to the request handler

    threads
        If True handle each request in a separate thread, otherwise process them sequentially.

    reuse
           If True allow the reuse of the server address, otherwise the server will not start if the address is already in use.

    start
        If True immediately start the server, otherwise the start() function must be called.

    block
        If True the server will block indefinitely when it is started, otherwise the function starting it will return.

    one_request
        If True, shutdown the server after processing one request.

    accept_period
        The time in seconds to wait for a connection before checking if the server should be shutdown.

    accept_queue_size
        The maximum number of connections to queue before refusing new connections.

When a request is received it is parsed by the HTTP server and an HttpRequest object containing the request elements is passed to the request handler.

**`class HttpRequest(method, path, query, protocol, headers, data)`**

    method
        The HTTP method contained in the request.

    path
        A list of strings that were parsed from the hier-part of the HTTP request URI.

    query
        A dictionary containing keywords and values parsed from the query part of the HTTP request URI.

    protocol
        The HTTP protocol version contained in the request.

    headers
        A dictionary containing keywords and values of the request headers.

    data
        The data contained in the request body if present.

An HttpResponse object is passed to the request handler which may update the elements that will be assembled into the HTTP response that is sent to the client.

**`class HttpResponse(protocol, status, headers, data)`**

    protocol
        The response HTTP protocol version (Default: HTTP/1.0)

    status
        The response status code (Default: 200)

    headers
        A dictionary containing additional response headers.

    data
        Data to be sent in the response body.

The application must define a function to handle requests that is passed to the HttpServer object when it is instantiated.  Two positional arguments are required.  Additional arguments may be defined and the values for these are passed to the HttpServer object.

**`def`**`requestHandler`**`(request, response[, args, ...])`**

    request
        A HttpRequest object containing elements parsed from an HTTP request.

    response
        A HttpResponse object that the request handler will populate to form the HTTP response.

A helper function that facilitates the serving of static resources my be called from the request handler.

**`def staticResource(request, response, staticBase="", defaultResource="index.html", defaultMime="text/plain")`**

    request
        A HttpRequest object containing elements parsed from an HTTP request.

    response
        A HttpResponse object that the request handler will populate to form the HTTP response.

    staticBase
        The root directory in the filesystem where the static resources are located.

    defaultResource
        The name of the resource to return if there isn't one specified in the request path.

    defaultMime
        The HTTP mime type will be placed into a Content-Type header based on the file extension of the resource.  This is the default that should be used if it can't be determined.

### Examples

<!-- TODO add more examples showing the use of the most recent ctor flags -->
This is a minimal HTTP server.  It listens on port 80 and resources contained in the directory where the application is run from.
```
import picohttp
picohttp.HttpServer()
```

This is an application that listens on port 8080 and responds to certain words in the request path.
```
import picohttp

# define the request handler
def requestHandler(request, response):
    # look at the path and respond appropriately
    if request.path[0] == "hello":
        response.data = "Hello world!"
    elif request.path[0] == "goodbye":
        response.data = "Goodbye cruel world"
    else:   # unknown request
        response.status = 404
        response.data = "I don't know what to say"

# create and start the HTTP server
httpServer = picohttp.HttpServer(8080, requestHandler)
```
A more elaborate example implements a REST server that can create, update, and delete resources that are stored persistently in a file.
```
dataFileName = "test.json"
httpPort = 8765

import json
import picohttp

def requestHandler(request, response, dataFileName, dataDict):
    try:
        if request.method == "GET":
            if request.path[0] == "":   # return all items as json
                response.data = json.dumps(dataDict)
                response.headers["Content-Type"] = "application/json"
            else:   # return a specific item
                try:
                    response.data = dataDict[request.path[0]]
                except KeyError:
                    response.status = 404 # Not found
        elif request.method == "PUT":   # create or update an item
            if request.path[0] != "":
                dataDict[request.path[0]] = request.data
                with open(dataFileName, "w") as dataFile:   # save the data
                    json.dump(dataDict, dataFile)
            else:
                response.status = 400 # Bad request
        elif request.method == "DELETE":   # delete an item
            try:
                del(dataDict[request.path[0]])
                with open(dataFileName, "w") as dataFile:   # save the data
                    json.dump(dataDict, dataFile)
            except KeyError:
                response.status = 404 # Not found
        else:
            response.status = 501 # Not implemented
    except Exception as ex:
        response.status = 500 # Internal server error
        response.data = str(ex)

try:    # load the data if the file exists
    with open(dataFileName) as dataFile:
        dataDict = json.load(dataFile)
except FileNotFoundError:
    dataDict = {}
httpServer = picohttp.HttpServer(httpPort, requestHandler, args=(dataFileName, dataDict,))
```
