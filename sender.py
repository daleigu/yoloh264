# sender.py - 优化版：采集时打时间戳 + 阶段日志
import socket
import av
import cv2
import struct
import time
import sys

# ==================== 1. 连接 YOLO Server ====================
try:
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(('localhost', 8080))
    print("✅ Sender connected to YOLO Server (port 8080)")
except ConnectionRefusedError:
    print("❌ Cannot connect to server. Is yoloserver.py running?")
    sys.exit(1)
except Exception as e:
    print(f"❌ Connection error: {e}")
    sys.exit(1)

# ==================== 2. 打开摄像头 ====================
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
cap.set(cv2.CAP_PROP_FPS, 15)

if not cap.isOpened():
    print("❌ Cannot open camera")
    client_socket.close()
    sys.exit(1)

print("📹 Camera started. Streaming H.264...")

# ==================== 3. 创建 H.264 编码器 ====================
try:
    output = av.open(
        'appsrc ! videoconvert ! x264enc preset=ultrafast tune=zerolatency crf=28 ! h264parse ! appsink',
        'w', format='h264'
    )
    stream = output.add_stream('h264', rate=15)
    stream.width = 640
    stream.height = 480
    stream.pix_fmt = 'yuv420p'
except Exception as e:
    print(f"❌ Failed to create encoder: {e}")
    cap.release()
    client_socket.close()
    sys.exit(1)

# ==================== 4. 显示窗口（可选） ====================
try:
    cv2.namedWindow('Sender Camera', cv2.WINDOW_AUTOSIZE)
    display_enabled = True
    print("🖥️  Display enabled: Press 'q' or ESC to quit")
except Exception as e:
    print(f"⚠️  Cannot create OpenCV window: {e}. Running without display.")
    display_enabled = False

# ==================== 5. 初始化变量 ====================
header_size = struct.calcsize('dQ')  # 时间戳(double) + 长度(int64)
frame_count = 0
first_frame = True

# ==================== 6. 主循环 ====================
try:
    while True:
        # --- 1. 捕获帧 + 立即打时间戳（关键！）---
        ret, frame = cap.read()
        capture_time = time.time()  # ⭐ 精确：图像被摄像头捕获的时刻
        if not ret or frame is None:
            print("⚠️  Failed to read frame or frame is None")
            break

        # --- 显示 ---
        if display_enabled:
            cv2.imshow('Sender Camera', frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:
                print("🛑 User quit via keyboard")
                break

        # --- 预处理 ---
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        av_frame = av.VideoFrame.from_ndarray(frame_rgb, format='rgb24')
        av_frame.pts = frame_count
        frame_count += 1

        # --- 强制 I 帧 ---
        if first_frame:
            av_frame.pict_type = 1
            first_frame = False
            print("🔥 First frame forced as I-frame")

        # --- 编码 ---
        encode_start = time.time()
        try:
            packets = stream.encode(av_frame)
            for packet in packets:
                if packet is None:
                    continue
                h264_data = bytes(packet)
                send_time = time.time()  # 发送前时间（可选）
                header = struct.pack('dQ', capture_time, len(h264_data))  # ⭐ 使用 capture_time
                client_socket.sendall(header + h264_data)

                encode_time = (time.time() - encode_start) * 1000
                total_send_time = (time.time() - capture_time) * 1000
                print(f"📤 Sent Frame {frame_count}: "
                      f"Encode={encode_time:.1f}ms | "
                      f"SendTime={total_send_time:.1f}ms | "
                      f"Size={len(h264_data)}B")

        except Exception as e:
            print(f"❌ Encode/send error: {e}")

        time.sleep(1 / 15)

except KeyboardInterrupt:
    print("\n🛑 Interrupted by user (Ctrl+C)")
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"❌ Unexpected error: {e}")

finally:
    print("🧹 Cleaning up sender...")
    cap.release()
    client_socket.close()
    output.close()
    if display_enabled:
        cv2.destroyAllWindows()
    print("✅ Sender shutdown complete.")# sender.py - 优化版：采集时打时间戳 + 阶段日志
import socket
import av
import cv2
import struct
import time
import sys

# ==================== 1. 连接 YOLO Server ====================
try:
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(('localhost', 8080))
    print("✅ Sender connected to YOLO Server (port 8080)")
except ConnectionRefusedError:
    print("❌ Cannot connect to server. Is yoloserver.py running?")
    sys.exit(1)
except Exception as e:
    print(f"❌ Connection error: {e}")
    sys.exit(1)

# ==================== 2. 打开摄像头 ====================
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
cap.set(cv2.CAP_PROP_FPS, 15)

if not cap.isOpened():
    print("❌ Cannot open camera")
    client_socket.close()
    sys.exit(1)

print("📹 Camera started. Streaming H.264...")

# ==================== 3. 创建 H.264 编码器 ====================
try:
    output = av.open(
        'appsrc ! videoconvert ! x264enc preset=ultrafast tune=zerolatency crf=28 ! h264parse ! appsink',
        'w', format='h264'
    )
    stream = output.add_stream('h264', rate=15)
    stream.width = 640
    stream.height = 480
    stream.pix_fmt = 'yuv420p'
except Exception as e:
    print(f"❌ Failed to create encoder: {e}")
    cap.release()
    client_socket.close()
    sys.exit(1)

# ==================== 4. 显示窗口（可选） ====================
try:
    cv2.namedWindow('Sender Camera', cv2.WINDOW_AUTOSIZE)
    display_enabled = True
    print("🖥️  Display enabled: Press 'q' or ESC to quit")
except Exception as e:
    print(f"⚠️  Cannot create OpenCV window: {e}. Running without display.")
    display_enabled = False

# ==================== 5. 初始化变量 ====================
header_size = struct.calcsize('dQ')  # 时间戳(double) + 长度(int64)
frame_count = 0
first_frame = True

# ==================== 6. 主循环 ====================
try:
    while True:
        # --- 1. 捕获帧 + 立即打时间戳（关键！）---
        ret, frame = cap.read()
        capture_time = time.time()  # ⭐ 精确：图像被摄像头捕获的时刻
        if not ret or frame is None:
            print("⚠️  Failed to read frame or frame is None")
            break

        # --- 显示 ---
        if display_enabled:
            cv2.imshow('Sender Camera', frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:
                print("🛑 User quit via keyboard")
                break

        # --- 预处理 ---
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        av_frame = av.VideoFrame.from_ndarray(frame_rgb, format='rgb24')
        av_frame.pts = frame_count
        frame_count += 1

        # --- 强制 I 帧 ---
        if first_frame:
            av_frame.pict_type = 1
            first_frame = False
            print("🔥 First frame forced as I-frame")

        # --- 编码 ---
        encode_start = time.time()
        try:
            packets = stream.encode(av_frame)
            for packet in packets:
                if packet is None:
                    continue
                h264_data = bytes(packet)
                send_time = time.time()  # 发送前时间（可选）
                header = struct.pack('dQ', capture_time, len(h264_data))  # ⭐ 使用 capture_time
                client_socket.sendall(header + h264_data)

                encode_time = (time.time() - encode_start) * 1000
                total_send_time = (time.time() - capture_time) * 1000
                print(f"📤 Sent Frame {frame_count}: "
                      f"Encode={encode_time:.1f}ms | "
                      f"SendTime={total_send_time:.1f}ms | "
                      f"Size={len(h264_data)}B")

        except Exception as e:
            print(f"❌ Encode/send error: {e}")

        time.sleep(1 / 15)

except KeyboardInterrupt:
    print("\n🛑 Interrupted by user (Ctrl+C)")
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"❌ Unexpected error: {e}")

finally:
    print("🧹 Cleaning up sender...")
    cap.release()
    client_socket.close()
    output.close()
    if display_enabled:
        cv2.destroyAllWindows()
    print("✅ Sender shutdown complete.")