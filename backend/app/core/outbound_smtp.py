"""SMTP uses a validated IP while TLS still verifies the original hostname."""
import smtplib
import socket

from .outbound_http import resolve_destination


class PinnedSMTP(smtplib.SMTP):
    def __init__(self, host, port, **kwargs):
        self.destination = resolve_destination('https://' + host, 'integration')[1]
        super().__init__(host, port, **kwargs)

    def _get_socket(self, host, port, timeout):
        return socket.create_connection((self.destination, port), timeout, self.source_address)


class PinnedSMTPSSL(PinnedSMTP, smtplib.SMTP_SSL):
    def _get_socket(self, host, port, timeout):
        connection = PinnedSMTP._get_socket(self, host, port, timeout)
        try:
            return self.context.wrap_socket(connection, server_hostname=host)
        except Exception:
            connection.close()
            raise
