# sender.py - 按逻辑帧分配 frame_id，强化 zerolatency 编码
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
cap.set(cv2.CAP_PROP_FPS, 30)

if not cap.isOpened():
    print("❌ Cannot open camera")
    client_socket.close()
    sys.exit(1)

print("📹 Camera started. Streaming H.264...")

# ==================== 3. 创建 H.264 编码器（强化 zerolatency）====================
try:
    # 关键：彻底关闭 B 帧、lookahead、scenecut 等引入延迟的特性
    pipeline = (
        'appsrc ! videoconvert ! '
        'x264enc speed-preset=ultrafast tune=zerolatency keyint=15 b-adapt=0 bframes=0 '
        'scenecut=0 intra-refresh=1 sync-lookahead=0 rc-lookahead=0 ! '
        'h264parse ! appsink'
    )
    output = av.open(pipeline, 'w', format='h264')
    stream = output.add_stream('h264', rate=30)
    stream.width = 640
    stream.height = 480
    stream.pix_fmt = 'yuv420p'
except Exception as e:
    print(f"❌ Failed to create encoder: {e}")
    cap.release()
    client_socket.close()
    sys.exit(1)

# ==================== 4. 显示窗口（可选） ====================
display_enabled = False
try:
    cv2.namedWindow('Sender Camera', cv2.WINDOW_AUTOSIZE)
    display_enabled = True
    print("🖥️  Display enabled: Press 'q' or ESC to quit")
except Exception as e:
    print(f"⚠️  Cannot create OpenCV window: {e}. Running without display.")

# ==================== 5. 初始化变量 ====================
frame_id = 0  # 每成功读取一帧 +1（逻辑帧 ID）
first_frame = True

# ==================== 6. 主循环 ====================
try:
    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            print("⚠️  Failed to read frame")
            break

        capture_time = time.time()  # ⭐ 在读取后立即打时间戳
        frame_id += 1               # ⭐ 每逻辑帧 +1

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
        av_frame.pts = frame_id

        # --- 强制首帧为 I 帧 ---
        if first_frame:
            av_frame.pict_type = 1
            first_frame = False
            print("🔥 First frame forced as I-frame")

        # --- 编码并发送（所有 packet 共享同一个 header）---
        try:
            packets = stream.encode(av_frame)
            for packet in packets:
                if packet is None or packet.size == 0:
                    continue
                h264_data = bytes(packet)
                header = struct.pack('dQQ', capture_time, len(h264_data), frame_id)
                client_socket.sendall(header + h264_data)

            # 日志（仅每帧一次）
            total_send_time = (time.time() - capture_time) * 1000
            print(f"📤 Sent Frame {frame_id} | TotalSend={total_send_time:.1f}ms | Packets={len(packets)}")

        except Exception as e:
            print(f"❌ Encode/send error: {e}")

        time.sleep(1 / 30)

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