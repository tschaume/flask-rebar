from io import BytesIO
import sys
from urllib3.response import HTTPResponse

try:
    from unittest import mock
except ImportError:
    import mock

try:
    from http.client import responses as http_reasons
except ImportError:
    http_reasons = {}

__all__ = ['FlaskClientTest']


_exec = getattr(__import__('builtins'), 'exec')
_urllib3_import = """\
from %(package)s.rest import urllib3
HTTPResponse = urllib3.response.HTTPResponse
ProtocolError = urllib3.exceptions.ProtocolError
"""


class FlaskClientTest(object):
    """Context Manager for testing Flask apps using their swagger generated clients.

    This context manager can be used in conjunction with the swagger-generated Python
    client library to test a service without spinning up a "real" server. Calls to
    the client made via ``urllib3`` are intercepted and routed to the Flask test client.

    """
    def __init__(self, app, client_package):
        """Initialize the context manager.

        * :param: flask.Flask app
        * :param: str      client_package   The name of the client package (ie, "scribble-client").
                                            This must be importable at the time of construction.
        """
        self._app = app.test_client()

        evaldict = {}
        _exec(_urllib3_import % {'package': client_package}, evaldict)

        self._package = client_package + '.rest.urllib3'
        self._response_class = evaldict['HTTPResponse']
        self._error_class = evaldict['ProtocolError']

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()

    def _urlopen(self, pool, method, url, body=None, headers=None, **kwargs):
        return self._app.open(method=method, path=url, data=body, headers=headers)

    def start(self):
        """Start intercepting HTTP call and routing them to the test client"""
        def _urlopen(pool, method, url, body=None, headers=None, **kwargs):
            response = self._urlopen(pool, method, url, body=body, headers=headers,
                                     **kwargs)
            return HTTPResponse(
                body=BytesIO(response.get_data()),
                headers=response.headers,
                status=response.status_code,
                reason=http_reasons.get(response.status),
                decode_content=False,
                preload_content=False,
            )

        target = self._package + '.connectionpool.HTTPConnectionPool.urlopen'
        self._patcher = mock.patch(target, _urlopen)
        self._patcher.start()

    def stop(self):
        """Stop intercepting HTTP calls"""
        self._patcher.stop()
