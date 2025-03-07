import requests
import threading
import unittest

import time
from typing import Union

import urllib3.exceptions

from picohttp.httpServer import HttpServer as PicoHttpServer
from picohttp.httpClasses import HttpRequest as PiceHttpRequest
from picohttp.httpClasses import HttpResponse as PiceHttpResponse

from .test_nonblocking import no_op_listener
from .test_nonblocking import find_our_thread


class ClientThread(threading.Thread):
    def __init__(self, port: int, test_obj = None, server: PicoHttpServer=None,
                 delay: float = 5.0, shutdown: bool = False ):
        super().__init__(None)
        self.port = port
        self.test_obj: BlockingTestCase = test_obj
        self.start_delay = delay
        self.server = server
        self.shutdown = shutdown

    def run(self):
        time.sleep(self.start_delay)   # since our test is using a blocking server, we launch the client thread 1st with a delay
        try:
            print("ClientThread http_client attempting to connect to port: ", self.port, ' after delay of: ', self.start_delay)
            sc: int = http_client(self.port )
            if sc < 300:
                self.test_obj.increment_client_count()
                print("ClientThread http_client returned a SC < 300: ", sc)
            else:
                print("UhOH - our ClientThread http_client did not return a SC < 300: ", sc)
        except urllib3.exceptions.MaxRetryError as e:
            self.shutdown = True  # need to shutdown the server if we can't connect
        if self.shutdown and self.server is not None:
            self.server.shutdown = True



class DelayShutdownThread(threading.Thread):
    def __init__(self, server: PicoHttpServer, delay: float = 5.0):
        super().__init__(None)
        self.server = server
        self.delay = delay

    def run(self):
        time.sleep(self.delay)
        self.server.shutdown = True


class BlockingTestCase(unittest.TestCase):
    the_ports = [8080, 8090, 8180, 8190]  # have each test use a different port
    test_num = 0

    def setUp(self):
        self.ports_to_try = [BlockingTestCase.the_ports[BlockingTestCase.test_num]] # [8080, 8090, 8180]
        BlockingTestCase.test_num += 1
        if BlockingTestCase.test_num >= len(BlockingTestCase.the_ports):
            BlockingTestCase.test_num = 0  # reset in case we have more tests than ports
        self.num_clients = 0
        self.counter_lock: threading.Lock = threading.Lock()

    def increment_client_count(self):
        self.counter_lock.acquire()
        self.num_clients += 1
        self.counter_lock.release()

    def test_blocking_no_client(self):
        """
        Test the PicoHttpServer with a short period for accepting incoming connections. This is a non-blocking test.
        NOTE that there is no client attempt to connect. This is by design for this test as we want to confirm
        that the server thread will exit after the specified period without a connection.
        :return:
        """
        shutdown_delay = 4.0
        start_time = time.time()
        server = PicoHttpServer(self.ports_to_try, no_op_listener, threads=False, block=True, start=False,
                                one_request=False, accept_period=3)
        shutter = DelayShutdownThread(server, shutdown_delay )
        shutter.start()
        server.start()
        end_time = time.time()
        # time for our accept thread to run-down (if it hasn't already) - give accept_period + 1 at a minimum
        time.sleep( 4 )
        thr_name = find_our_thread('httpserver_', server.port)
        self.assertIsNone(thr_name)
        self.assertLess(end_time - start_time, shutdown_delay +1.0)  # looping 5 times with a 5 second sleep each time. allow for overhead

    def test_blocking_one_client(self):
        """
        Test the PicoHttpServer with a short period for accepting incoming connections. This is a blocking test.
        NOTE that there is only one client attempt to connect. This is by design for this test as we want to confirm
        that the one_request==True will cause the server to shutdown after the client request is processed.

        :return:
        """
        run_delay: float = 4.0
        start_time = time.time()
        server = PicoHttpServer(self.ports_to_try, no_op_listener, threads=False, block=True, start=False,
                                one_request=True, accept_period=3)
        # since we can't start the server until after we construct the client, assume the 1st port is avilable :-(
        the_client = ClientThread(self.ports_to_try[0], self, server, delay=run_delay, shutdown=True)
        the_client.start()
        server.start()  # it's block so we wait for the client cause the shutdown [as constructed]
        end_time = time.time()
        time.sleep( 4 )  # wait at least the accept_period + 1.0
        thr_name = find_our_thread('httpserver_', server.port)
        self.assertIsNone(thr_name)
        self.assertEqual( self.num_clients, 1)
        self.assertLess(end_time - start_time, run_delay + 2.0)  # allow for overhead

    def test_blocking_threading_clients(self):
        """
        Test the PicoHttpServer with a short period for accepting incoming connections. This is a blocking test.
        NOTE that there is are several clients attempting to connect. The client is the longer start delay is configured
        to try to shutdown the associated server.

        :return:
        """
        run_delay: float = 5.0
        start_time = time.time()
        server = PicoHttpServer(self.ports_to_try, no_op_listener, threads=True, block=True, start=False,
                                one_request=False, accept_period=3)
        # since we can't start the server until after we construct the client, assume the 1st port is available :-(
        c1 = ClientThread(self.ports_to_try[0], self, server, delay=run_delay,  shutdown=False)
        c2 = ClientThread(self.ports_to_try[0], self, server, delay=run_delay+2.0, shutdown=False)
        delay_shutdown = DelayShutdownThread(server, run_delay * 3.0)
        delay_shutdown.start()
        c1.start()
        c2.start()
        server.start()  # its blocking so we wait for the client cause the shutdown [as constructed]
        end_time = time.time()
        time.sleep(4.0)  # time for our accept thread to run-down - wait at least accept_period + 1
        thr_name = find_our_thread('httpserver_', server.port)
        self.assertIsNone(thr_name)
        self.assertEqual( self.num_clients, 2)
        self.assertLess(end_time - start_time, (run_delay * 3.0) + 1.0)


def http_client( port: int, host: str = 'localhost' ) -> int:
    """
    This function is used to simulate a client connecting to the server.
    :param port:
    :param host:
    :return:
    """
    response = requests.get(f'http://{host}:{port}')
    return response.status_code if response is not None else 501



if __name__ == '__main__':
    unittest.main()
