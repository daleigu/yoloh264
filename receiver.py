# receiver.py
import socket
import cv2
import struct
import numpy as np

receiver_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
receiver_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
receiver_socket.bind(('localhost', 9090))
receiver_socket.listen(1)
print("✅ Receiver listening on port 9090...")

conn, addr = receiver_socket.accept()
print(f"📥 Connected by {addr}")

data = b""
header_size = struct.calcsize('Q')

try:
    while True:
        # 接收长度
        while len(data) < header_size:
            packet = conn.recv(4096)
            if not packet:
                raise ConnectionError("Sender closed.")
            data += packet
        payload_size = struct.unpack('Q', data[:header_size])[0]
        data = data[header_size:]

        # 接收图像数据
        while len(data) < payload_size:
            packet = conn.recv(4096)
            if not packet:
                raise ConnectionError("Stream ended.")
            data += packet
        frame_data = data[:payload_size]
        data = data[payload_size:]

        # 解码显示
        nparr = np.frombuffer(frame_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is not None:
            cv2.imshow('Receiver - Final View', frame)

        if cv2.waitKey(1) == ord('q'):
            break

except Exception as e:
    print(f"❌ Receiver error: {e}")
finally:
    conn.close()
    cv2.destroyAllWindows()