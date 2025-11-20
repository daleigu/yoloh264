import socket
import struct
import json
import time

receiver_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
receiver_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
receiver_socket.bind(('localhost', 9090))
receiver_socket.listen(1)
print("✅ Receiver listening on port 9090...")

conn, addr = receiver_socket.accept()
print(f"📥 Connected by {addr}")

data = b""
header_size = struct.calcsize('dQ')  # capture_time (double) + payload_size (uint64)

try:
    frame_count = 0
    received_frame_ids = set()
    expected_frame_id = None
    received_count = 0
    lost_count = 0

    # FPS计算
    start_time = time.time()
    processed_frame_count = 0
    fps = 0.0
    fps_start_time = time.time()

    # 延迟统计
    delay_sum = 0.0
    delay_count = 0

    while True:
        # 接收头部：capture_time + size
        while len(data) < header_size:
            packet = conn.recv(4096)
            if not packet:
                raise ConnectionError("Sender closed.")
            data += packet

        capture_time, payload_size = struct.unpack('dQ', data[:header_size])
        data = data[header_size:]

        # 接收 JSON 数据
        while len(data) < payload_size:
            packet = conn.recv(4096)
            if not packet:
                raise ConnectionError("Stream ended.")
            data += packet

        json_data = data[:payload_size]
        data = data[payload_size:]

        # 解析 JSON 结果
        result = json.loads(json_data.decode('utf-8'))
        frame_id = result['frame_id']
        detections = result['detections']

        # 计算真实端到端延迟
        current_time = time.time()
        end_to_end_delay_ms = (current_time - capture_time) * 1000

        # 延迟统计
        delay_sum += end_to_end_delay_ms
        delay_count += 1
        avg_delay = delay_sum / delay_count if delay_count > 0 else 0.0

        # 丢包统计
        if expected_frame_id is None:
            expected_frame_id = frame_id
        if frame_id not in received_frame_ids:
            received_frame_ids.add(frame_id)
            if frame_id == expected_frame_id:
                received_count += 1
                expected_frame_id += 1
            elif frame_id > expected_frame_id:
                lost_count += frame_id - expected_frame_id
                expected_frame_id = frame_id + 1

        total_processed = received_count + lost_count
        loss_rate = (lost_count / total_processed * 100) if total_processed > 0 else 0.0

        # FPS计算
        processed_frame_count += 1
        now = time.time()
        if now - fps_start_time >= 1.0:
            fps = processed_frame_count / (now - fps_start_time)
            processed_frame_count = 0
            fps_start_time = now

        frame_count += 1

        # 每30帧输出一次统计信息
        if frame_count % 30 == 0:
            print(f"📊 Receiver Frame {frame_count} | "
                  f"End-to-End Delay: {end_to_end_delay_ms:.1f}ms | "
                  f"Avg Delay: {avg_delay:.1f}ms | "
                  f"FPS: {fps:.1f} | "
                  f"Loss Rate: {loss_rate:.1f}% | "
                  f"Detections: {len(detections)}")

        # 打印检测结果
        if detections:
            print(f"🔍 Frame {frame_id}: {len(detections)} detections - ", end="")
            for det in detections:
                print(f"{det['label']} ({det['confidence']:.2f}) ", end="")
            print()

except Exception as e:
    print(f"❌ Receiver error: {e}")
finally:
    conn.close()
    receiver_socket.close()
    print(
        f"📊 Final Stats: Total Frames={frame_count}, Avg Delay={delay_sum / delay_count if delay_count > 0 else 0:.1f}ms, Loss Rate={loss_rate:.1f}%")



