# yoloserver.py - 优化版：详细阶段延迟日志
import socket
import av
import cv2
import torch
import numpy as np
import struct
import time
import threading
import queue

CLASS_NAMES = [
    'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat',
    'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat',
    'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe', 'backpack',
    'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball',
    'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard', 'tennis racket',
    'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple',
    'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair',
    'couch', 'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse',
    'remote', 'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink', 'refrigerator',
    'book', 'clock', 'vase', 'scissors', 'teddy bear', 'hair drier', 'toothbrush'
]

# ------------------------------- 加载模型
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"🚀 Using device: {device}")

model = torch.hub.load('ultralytics/yolov5', 'yolov5s', pretrained=True)
model.to(device).eval()
print("✅ YOLOv5s model loaded and moved to", device)

# ------------------------------- 启动服务器
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind(('0.0.0.0', 8080))
server_socket.listen(1)
print("✅ YOLO Server listening on port 8080...")

conn, addr = server_socket.accept()
print(f"📡 Connected by {addr}")

# ------------------------------- 转发到 receiver
forward_socket = None
forward_queue = queue.Queue(maxsize=5)

def forward_worker():
    while True:
        try:
            jpeg_data = forward_queue.get(timeout=2)
            if jpeg_data is None:
                break
            if forward_socket:
                header = struct.pack('Q', len(jpeg_data))
                forward_socket.sendall(header + jpeg_data)
        except queue.Empty:
            continue
        except Exception as e:
            print(f"❌ Forward error: {e}")
            break

try:
    forward_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    forward_socket.connect(('localhost', 9090))
    print("📤 Connected to Receiver (port 9090)")
    threading.Thread(target=forward_worker, daemon=True).start()
except Exception as e:
    print(f"⚠️ Cannot connect to receiver: {e}")

# ------------------------------- 显示线程
display_queue = queue.Queue(maxsize=5)

def display_worker():
    while True:
        frame = display_queue.get()
        if frame is None:
            break
        cv2.imshow('YOLO Server - Detection', frame)
        if cv2.waitKey(1) == ord('q'):
            cv2.destroyAllWindows()
            break
    cv2.destroyAllWindows()

threading.Thread(target=display_worker, daemon=True).start()

# ------------------------------- 主循环：接收 + 解码 + 推理 + 日志
data = b''
header_size = struct.calcsize('dQ')
frame_count = 0
fps = 0.0
prev_time = time.time()

decoder = av.CodecContext.create('h264', 'r')

try:
    while True:
        total_start = time.time()

        # 1. 接收 header
        header_start = time.time()
        while len(data) < header_size:
            packet = conn.recv(4096)
            if not packet:
                raise ConnectionError("Sender disconnected.")
            data += packet
        capture_time, payload_size = struct.unpack('dQ', data[:header_size])
        data = data[header_size:]
        header_time = (time.time() - header_start) * 1000

        # 2. 接收 H.264 数据
        payload_start = time.time()
        while len(data) < payload_size:
            more_data = conn.recv(4096)
            if not more_data:
                raise ConnectionError("Stream ended.")
            data += more_data
        h264_data = data[:payload_size]
        data = data[payload_size:]
        payload_time = (time.time() - payload_start) * 1000

        frame_count += 1
        if frame_count <= 3:
            print(f"🔥 Skipping warm-up frame {frame_count}/3")
            continue

        # FPS 计算
        if time.time() - prev_time >= 1.0:
            fps = 0.9 * fps + 0.1 * (1 / (time.time() - prev_time))
            prev_time = time.time()

        # 3. 解码
        decode_start = time.time()
        try:
            packets = decoder.parse(h264_data)
            for packet in packets:
                frames = decoder.decode(packet)
                for frame in frames:
                    image = frame.to_ndarray(format='bgr24')
                    break
                break
            if 'image' not in locals():
                continue
        except Exception as e:
            print(f"⚠️ Decode error: {e}")
            continue
        decode_time = (time.time() - decode_start) * 1000

        # 4. 推理
        infer_start = time.time()
        img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = model(img_rgb, size=320)
        detections = results.pandas().xyxy[0]
        infer_time = (time.time() - infer_start) * 1000

        # 5. 绘图
        draw_start = time.time()
        annotated_frame = image.copy()
        for _, row in detections.iterrows():
            if row['confidence'] < 0.4:
                continue
            x1, y1, x2, y2 = int(row['xmin']), int(row['ymin']), int(row['xmax']), int(row['ymax'])
            label = f"{row['name']} {row['confidence']:.2f}"
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(annotated_frame, label, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        draw_time = (time.time() - draw_start) * 1000

        # 6. 计算总延迟
        receive_time = time.time()
        end2end_delay = (receive_time - capture_time) * 1000  # ⭐ 端到端延迟
        process_time = (time.time() - total_start) * 1000

        # 添加文字
        cv2.putText(annotated_frame, f"Delay: {end2end_delay:.1f}ms", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(annotated_frame, f"FPS: {fps:.1f}", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        # 异步操作
        if not display_queue.full():
            display_queue.put(annotated_frame)
        else:
            print("⚠️ Display queue full")

        success, buf = cv2.imencode('.jpg', annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        if success and not forward_queue.full():
            forward_queue.put(buf.tobytes())
        elif not forward_queue.full():
            print("⚠️ Forward queue full")

        # 📊 打印各阶段耗时
        print(f"📊 Frame {frame_count:3d} | "
              f"Hdr={header_time:4.1f}ms | "
              f"Pay={payload_time:4.1f}ms | "
              f"Dec={decode_time:4.1f}ms | "
              f"Infer={infer_time:5.1f}ms | "
              f"Draw={draw_time:4.1f}ms | "
              f"Total={process_time:5.1f}ms | "
              f"End2End={end2end_delay:5.1f}ms | "
              f"FPS={fps:4.1f}")

except KeyboardInterrupt:
    print("\n🛑 Stopped by user.")
except Exception as e:
    print(f"❌ Server error: {e}")
finally:
    display_queue.put(None)
    forward_queue.put(None)
    time.sleep(0.5)
    conn.close()
    if forward_socket:
        forward_socket.close()
    cv2.destroyAllWindows()