"""Bounded loopback RFC6455 client for native notification delivery assertions."""
import base64
import hashlib
import json
import os
import socket
import struct


class WebSocket:
    def __init__(self, port, path, authorization):
        self.sock = socket.create_connection(('127.0.0.1', port), timeout=10)
        self.buf = b''
        key = base64.b64encode(os.urandom(16)).decode()
        request = ('GET ' + path + ' HTTP/1.1\r\nHost: 127.0.0.1:' + str(port) + '\r\n'
                   'Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\n'
                   'Sec-WebSocket-Key: ' + key + '\r\nAuthorization: ' + authorization + '\r\n\r\n')
        self.sock.sendall(request.encode())
        while b'\r\n\r\n' not in self.buf:
            block = self.sock.recv(4096)
            if not block or len(self.buf) > 16384:
                self.sock.close(); raise RuntimeError('Native WebSocket handshake failed')
            self.buf += block
        header, self.buf = self.buf.split(b'\r\n\r\n', 1)
        lines = header.decode().split('\r\n')
        expected = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
        headers = dict(line.split(':', 1) for line in lines[1:])
        headers = {k.lower(): v.strip() for k, v in headers.items()}
        if lines[0].split(' ', 2)[1] != '101' or headers.get('sec-websocket-accept') != expected:
            self.sock.close(); raise RuntimeError('Native WebSocket upgrade not accepted')

    def read(self, count):
        while len(self.buf) < count:
            block = self.sock.recv(max(4096, count - len(self.buf)))
            if not block:
                raise RuntimeError('Native WebSocket closed')
            self.buf += block
        result, self.buf = self.buf[:count], self.buf[count:]
        return result

    def send(self, opcode, data):
        mask = os.urandom(4)
        if len(data) > 125:
            raise RuntimeError('Control frame exceeds protocol bound')
        self.sock.sendall(bytes([0x80 | opcode, 0x80 | len(data)]) + mask +
                          bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def message(self):
        fragments = b''
        for _ in range(64):
            first, second = self.read(2)
            opcode, size = first & 0x0f, second & 0x7f
            if second & 0x80:
                raise RuntimeError('Server frame must be unmasked')
            if size == 126:
                size = struct.unpack('!H', self.read(2))[0]
            elif size == 127:
                size = struct.unpack('!Q', self.read(8))[0]
            if size + len(fragments) > 1024**2:
                raise RuntimeError('Native WebSocket message exceeds test bound')
            payload = self.read(size)
            if opcode == 9:
                self.send(10, payload); continue
            if opcode == 10:
                continue
            if opcode == 8:
                raise RuntimeError('Native WebSocket close received')
            if opcode not in {0, 1}:
                raise RuntimeError('Unexpected native WebSocket frame')
            fragments += payload
            if first & 0x80:
                return json.loads(fragments)
        raise RuntimeError('Native WebSocket fragment bound exceeded')

    def close(self):
        try:
            self.send(8, b'')
        except OSError:
            pass
        self.sock.close()
