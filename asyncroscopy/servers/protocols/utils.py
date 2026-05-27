'''
Serialization helpers
'''

import numpy as np

def package_message(data) -> bytes:
    """
    Produce bytes matching the client's expected format:
      b"[dtype,shape...]<binary payload>"

    Handles:
      - str -> [str,len]<utf8 bytes>
      - bytes/bytearray -> [uint8,n]<raw bytes>
      - numpy arrays -> [<dtype>,<dim1>,<dim2>,...]<tobytes()>
      - int/float -> [float32,1]<4-bytes>
      - list/tuple -> converted to numpy array
      - fallback: str(data)
    """
    # Strings
    if isinstance(data, str):
        enc = data.encode("utf-8")
        header = f"[str,{len(enc)}]".encode("ascii")
        return header + enc

    # Raw bytes
    if isinstance(data, (bytes, bytearray)):
        arr = np.frombuffer(data, dtype=np.uint8)
        header = f"[uint8,{arr.size}]".encode("ascii")
        return header + bytes(data)

    # Scalars -> treat as float32 vector length 1
    if isinstance(data, (int, float)):
        arr = np.array([data], dtype=np.float32)
        header = f"[float32,1]".encode("ascii")
        return header + arr.tobytes()

    # Lists/tuples -> numpy array
    if isinstance(data, (list, tuple)):
        data = np.asarray(data)

    # numpy arrays
    if isinstance(data, np.ndarray):
        dtype = data.dtype.name  # e.g. 'uint8', 'float32'
        shape = ",".join(str(x) for x in data.shape)
        header = f"[{dtype},{shape}]".encode("ascii")
        return header + data.tobytes()

    # fallback: stringify
    txt = str(data).encode("utf-8")
    header = f"[str,{len(txt)}]".encode("ascii")
    return header + txt

def unpackage_message(packet: bytes):
    """
    Inverse of package_message. Returns (dtype: str, shape: tuple[int,...], payload_data)
    payload_data is bytes for binary dtypes, or decoded string for 'str', or numpy array for numeric types.
    """
    try:
        end_idx = packet.index(b']') + 1
        header = packet[:end_idx].decode("ascii")
        payload = packet[end_idx:]
        parts = header[1:-1].split(",")
        dtype, *shape_parts = parts
        shape = tuple(int(x) for x in shape_parts) if shape_parts else ()
    except Exception:
        # malformed header -> return raw bytes
        return "bytes", (), packet
    if dtype == "str":
        return dtype, shape, payload.decode("utf-8")
    if dtype == "uint8":
        arr = np.frombuffer(payload, dtype=np.uint8)
        if shape:
            arr = arr.reshape(shape)
        return dtype, shape, arr
    if dtype.startswith("float") or dtype.startswith("int"):
        dtype_np = np.dtype(dtype)
        arr = np.frombuffer(payload, dtype=dtype_np)
        if shape:
            arr = arr.reshape(shape)
        return dtype, shape, arr
    # unknown dtype -> return raw bytes
    return dtype, shape, payload