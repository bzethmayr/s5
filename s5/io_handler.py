import sys

from s5 import int_to_s5set, set_value, AddressType, RuntimeError_, _read_s5b, _write_s5b


class IOHandler:
    def __init__(self, buf_sizes=None):
        self._bufs = {0: bytearray(), 1: bytearray(), 2: bytearray()}
        self._sizes = {0: 0, 1: 0, 2: 0}
        if buf_sizes:
            self._sizes.update(buf_sizes)

    def _read_line(self, fd):
        buf = self._bufs.get(fd)
        if buf is None:
            return None
        idx = buf.find(b'\n')
        if idx < 0:
            return None
        line = buf[:idx]
        del buf[:idx + 1]
        return line.decode('utf-8')

    def _read_byte(self, fd):
        buf = self._bufs.get(fd)
        if buf is None:
            return None
        if not buf:
            return None
        b = buf[0]
        del buf[0]
        return b

    def _read_all(self, fd):
        buf = self._bufs.get(fd)
        if buf is None:
            return None
        if not buf:
            return None
        data = bytes(buf)
        buf.clear()
        return data

    def _append(self, fd, data):
        buf = self._bufs.get(fd)
        if buf is None:
            return
        buf.extend(data)
        size = self._sizes.get(fd, 0)
        if size > 0 and len(buf) > size:
            buf[:] = buf[-size:]
        elif size == 0:
            buf.clear()

    def resolve(self, addr_type, fd):
        if addr_type == AddressType.IO:
            line = self._read_line(fd)
            if line is None:
                if fd == 0:
                    line = sys.stdin.readline()
                else:
                    raise RuntimeError_(f"input: fd {fd} buffer empty")
            if not line:
                raise RuntimeError_("input: unexpected EOF")
            try:
                n = int(line.strip())
            except ValueError:
                raise RuntimeError_(f"input: expected integer, got {line.strip()!r}")
            return int_to_s5set(n)
        elif addr_type == AddressType.IO_S5B:
            raw = self._read_all(fd)
            if raw is None:
                if fd == 0:
                    raw = sys.stdin.buffer.read()
                else:
                    raise RuntimeError_(f"input: fd {fd} buffer empty")
            if not raw:
                raise RuntimeError_("input: unexpected EOF")
            return _read_s5b(raw)
        else:
            byte = self._read_byte(fd)
            if byte is None:
                if fd == 0:
                    raw = sys.stdin.buffer.read(1)
                    if not raw:
                        raise RuntimeError_("input: unexpected EOF")
                    byte = raw[0]
                else:
                    raise RuntimeError_(f"input: fd {fd} buffer empty")
            return int_to_s5set(byte)

    def assign(self, addr_type, fd, value):
        if addr_type == AddressType.IO:
            n = set_value(value)
            data = f"{n}\n".encode('utf-8')
            self._append(fd, data)
            if fd == 1:
                print(n)
            elif fd == 2:
                print(n, file=sys.stderr)
        elif addr_type == AddressType.IO_S5B:
            data = _write_s5b(value)
            self._append(fd, data)
            if fd == 1:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            elif fd == 2:
                sys.stderr.buffer.write(data)
                sys.stderr.buffer.flush()
        else:
            n = set_value(value)
            data = bytearray()
            while True:
                data.append(n & 0xFF)
                n >>= 8
                if n == 0:
                    break
            self._append(fd, data)
            if fd == 1:
                sys.stdout.buffer.write(bytes(data))
                sys.stdout.buffer.flush()
            elif fd == 2:
                sys.stderr.buffer.write(bytes(data))
                sys.stderr.buffer.flush()
