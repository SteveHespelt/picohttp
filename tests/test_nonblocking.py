import requests
import threading
import unittest

import time
from typing import Union

from picohttp.httpServer import HttpServer as PicoHttpServer
from picohttp.httpClasses import HttpRequest as PiceHttpRequest
from picohttp.httpClasses import HttpResponse as PiceHttpResponse

CLIENT_TIMEOUT= 5.0   # plenty of time to start getting a response from the server


def no_op_listener(req: PiceHttpRequest, res: PiceHttpResponse, args: tuple = ()) -> bool:
    return False  # we do NOT want to initiate server shutdown


def find_our_thread(our_name_prefix: str, the_port: int = 0) -> Union[str,None]:
    """
    :param our_name_prefix: the "httpserver_ prefix is used in every thread name created by the PicoHttpServer
    :param the_port: if 0, we are looking for any thread with the prefix. If not 0, we are looking for a specific thread.
    :return:
    """
    current_threads:[] = threading.enumerate()
    for t in current_threads:
        if the_port > 0 and t.name == f'{our_name_prefix}{the_port}' :
            return t.name
        elif the_port == 0 and t.name.startswith(our_name_prefix):
            return t.name
    return None


class ClientThread(threading.Thread):
    def __init__(self, port: int, test_obj = None):
        super().__init__(None)
        self.port = port
        self.test_obj: MyTestCase = test_obj

    def run(self):
        sc: int = http_client(self.port )
        if sc < 300:
            self.test_obj.increment_client_count()


class MyTestCase(unittest.TestCase):
    def setUp(self):
        self.ports_to_try = [8080, 8090, 8180]
        self.num_clients = 0
        self.counter_lock: threading.Lock = threading.Lock()

    def increment_client_count(self):
        self.counter_lock.acquire()
        self.num_clients += 1
        self.counter_lock.release()

    def test_nonblocking_no_client(self):
        """
        Test the PicoHttpServer with a short period for accepting incoming connections. This is a non-blocking test.
        NOTE that there is no client attempt to connect. This is by design for this test as we want to confirm
        that the server thread will exit after the specified period without a connection.
        :return:
        """
        n: int = 0
        maxWaits: int = 5
        wait_period = 5.0
        start_time = time.time()
        server = PicoHttpServer(self.ports_to_try, no_op_listener, threads=False, block=False, start=True,
                                one_request=False, accept_period=4)
        while n < maxWaits:
            if n ==3:
                server.shutdown = True
            time.sleep(wait_period)
            # at this point, the thread(s) used by the PicoHttpServer should have exited. Need to verify this. TODO
            n += 1
        end_time = time.time()
        thr_name = find_our_thread('httpserver_', server.port)
        self.assertIsNone(thr_name)
        self.assertLess(end_time - start_time, (maxWaits*wait_period) +1.0)  # looping 5 times with a 5 second sleep each time. allow for overhead

    def test_nonblocking_one_client(self):
        """
        Test the PicoHttpServer with a short period for accepting incoming connections. This is a non-blocking test.
        NOTE that there is no client attempt to connect. This is by design for this test as we want to confirm
        that the server thread will exit after the specified period without a connection.
        :return:
        """
        sc: int = 501
        n: int = 0
        maxWaits: int = 5
        wait_period = 5.0
        start_time = time.time()
        server = PicoHttpServer(self.ports_to_try, no_op_listener, threads=False, block=False, start=True,
                                one_request=False, accept_period=4)
        while n < maxWaits:
            if n == 1:
                sc = http_client(server.port )
            if n ==3:
                server.shutdown = True
            time.sleep(wait_period)
            # at this point, the thread(s) used by the PicoHttpServer should have exited. Need to verify this. TODO
            n += 1

        end_time = time.time()
        thr_name = find_our_thread('httpserver_', server.port)
        self.assertIsNone(thr_name)
        self.assertLess(sc, 300)
        self.assertLess(end_time - start_time, (maxWaits*wait_period)+1.0)  # looping 5 times with a 5 second sleep each time. allow for overhead

    def test_nonblocking_threading_clients(self):
        """
        Test the PicoHttpServer with a short period for accepting incoming connections. This is a non-blocking test.
        We launch multiple clients on their own thread.
        :return: None
        """
        sc: int = 501
        n: int = 0
        maxWaits: int = 5
        wait_period = 5.0
        start_time = time.time()
        server = PicoHttpServer(self.ports_to_try, no_op_listener, threads=True, block=False, start=True,
                                one_request=False, accept_period=4)
        c1 = None
        c2 = None
        while n < maxWaits:
            if n == 1: # start 2 clients
                c1 = ClientThread(server.port, self)
                c2 = ClientThread(server.port, self)
                c1.start()
                c2.start()
            if n ==3:
                server.shutdown = True
            time.sleep(wait_period) # make this period at least 1 second longer than the accept_period
            # at this point, the thread(s) used by the PicoHttpServer should have exited. We verify this below
            n += 1
        end_time = time.time()
        thr_name = find_our_thread('httpserver_', server.port)  # accept port should have run down by now.
        self.assertFalse( c1.is_alive(), "Client 1 thread is still alive")
        self.assertFalse( c2.is_alive(), "Client 2 thread is still alive")
        self.assertIsNone(thr_name)
        self.assertEqual( self.num_clients, 2) # did all the clients connect? and the responses were ok?
        # we should have exited the server no later than the max loop time + 1 second for overhead
        self.assertLess(end_time - start_time, (maxWaits * wait_period)+1.0, 'Server sleep loop took too long' )


def http_client( port: int, host: str = 'localhost' ) -> int:
    """
    Create an HTTP client connecting to the server under test.
    :param port: the port the server is listening on
    :param host: usually localhost is appropriate for our tests
    :return:
    """
    response = None
    try:
        response = requests.get(f'http://{host}:{port}', timeout=CLIENT_TIMEOUT)
    except requests.exceptions.Timeout as e:
        pass # just eat it as we are testing the server not the client, 501 SC is assumed
    return response.status_code if response is not None else 501



if __name__ == '__main__':
    unittest.main()
