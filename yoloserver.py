import socket
import av
import cv2
import numpy as np
import struct
import time
import threading
import json
import torch
from ultralytics import YOLO

# 加载 YOLOv8 模型
device = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f"🚀 Using device: {device}")

model = YOLO('yolov8n.pt')
model.to(device)
print("✅ YOLOv8n model loaded and moved to", device)

# 启动服务器
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind(('0.0.0.0', 8080))
server_socket.listen(1)
print("✅ YOLO Server listening on port 8080...")

conn, addr = server_socket.accept()
print(f"📡 Connected by {addr}")

# 连接到 receiver
forward_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
forward_socket.connect(('localhost', 9090))
print("📤 Connected to Receiver (port 9090)")

# 主循环
data = b''
header_size = struct.calcsize('dQQ')  # capture_time, payload_size, frame_id

# 丢包统计
received_frame_ids = set()
expected_frame_id = None
received_count = 0
lost_count = 0
max_frame_id = 0

# FPS & warm-up
frame_count = 0
processed_frame_count = 0
fps = 0.0
fps_start_time = time.time()

# 解码器
decoder = av.CodecContext.create('h264', 'r')

try:
    while True:
        total_start = time.time()

        # 接收 header
        while len(data) < header_size:
            packet = conn.recv(4096)
            if not packet:
                raise ConnectionError("Sender disconnected.")
            data += packet

        capture_time, payload_size, frame_id = struct.unpack('dQQ', data[:header_size])
        data = data[header_size:]

        # 接收 payload
        while len(data) < payload_size:
            more = conn.recv(4096)
            if not more:
                raise ConnectionError("Stream ended.")
            data += more
        h264_data = data[:payload_size]
        data = data[payload_size:]

        # 丢包统计（按逻辑帧）
        max_frame_id = max(max_frame_id, frame_id)
        if expected_frame_id is None:
            expected_frame_id = frame_id
            print(f"🎯 First received frame ID: {frame_id}")

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

        frame_count += 1
        if frame_count <= 3:
            print(f"🔥 Skipping warm-up frame {frame_count}/3 (ID={frame_id})")
            continue

        # 关键：丢弃过期帧（>500ms）
        current_time = time.time()
        age_ms = (current_time - capture_time) * 1000
        if age_ms > 500:
            print(f"⏳ Skipped stale frame ID={frame_id} (age={age_ms:.1f}ms)")
            continue

        processed_frame_count += 1

        # 更新 FPS
        now = time.time()
        if now - fps_start_time >= 1.0:
            fps = processed_frame_count / (now - fps_start_time)
            processed_frame_count = 0
            fps_start_time = now

        # 解码
        try:
            packets = decoder.parse(h264_data)
            image = None
            for packet in packets:
                frames = decoder.decode(packet)
                if frames:
                    image = frames[0].to_ndarray(format='bgr24')
                    break
            if image is None:
                continue
        except Exception as e:
            print(f"⚠️ Decode error: {e}")
            continue

        # YOLOv8 推理
        infer_start = time.time()
        results = model(image, imgsz=320, verbose=False)
        infer_time = (time.time() - infer_start) * 1000

        # 收集检测结果
        detections = []
        boxes = results[0].boxes
        if len(boxes) > 0:
            xyxy = boxes.xyxy.cpu().numpy()
            conf = boxes.conf.cpu().numpy()
            cls = boxes.cls.cpu().numpy().astype(int)

            for i in range(len(boxes)):
                if conf[i] < 0.4:
                    continue
                x1, y1, x2, y2 = map(int, xyxy[i])
                label = model.names[cls[i]]
                detection = {
                    "label": label,
                    "confidence": float(conf[i]),
                    "bbox": [x1, y1, x2, y2]
                }
                detections.append(detection)

        # 发送检测结果到 receiver
        result_json = json.dumps({
            "capture_time": capture_time,
            "frame_id": frame_id,
            "detections": detections
        })

        result_bytes = result_json.encode('utf-8')
        header = struct.pack('dQ', capture_time, len(result_bytes))
        forward_socket.sendall(header + result_bytes)

        # 日志
        process_time = (time.time() - total_start) * 1000
        print(f"📊 Frame {frame_count:3d} (ID={frame_id}) | "
              f"Infer={infer_time:5.1f}ms | "
              f"Process={process_time:5.1f}ms | "
              f"FPS={fps:4.1f} | "
              f"Loss={loss_rate:5.1f}% | "
              f"Age={age_ms:5.1f}ms | "
              f"Detections={len(detections)}")

except KeyboardInterrupt:
    print("\n🛑 Stopped by user.")
except Exception as e:
    import traceback

    traceback.print_exc()
    print(f"❌ Server error: {e}")
finally:
    conn.close()
    forward_socket.close()



