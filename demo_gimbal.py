# SPDX-FileCopyrightText: 2024 霜叶
# SPDX-License-Identifier: MIT

"""
树莓派 4 云台控制与相机实时预览程序
功能：
    1. 控制云台持续摇头（巡逻模式）
    2. 打开相机实时显示画面
    3. 支持优雅退出（Ctrl+C）
硬件依赖：
    - Raspberry Pi 4
    - PCA9685 驱动板 (地址 0x41)
    - 相机模块
"""

import sys
import signal
import logging
import threading
import time
import board
from adafruit_pca9685 import PCA9685
from picamera2 import Picamera2

# --- 配置常量 ---
# PCA9685 配置
PCA_ADDRESS = 0x41
PWM_FREQ = 60  # 舵机频率

# 通道定义
CH_FAN_POS = 10
CH_FAN_NEG = 11
CH_SERVO_PAN = 1  # 摇头通道

# PWM 占空比值 (12-bit resolution, 0x0000 - 0x0FFF)
# 请根据实际舵机中位微调这些值
SERVO_MIN = 0x1000  # 左极限
SERVO_MID = 0x1300  # 中位
SERVO_MAX = 0x2000  # 右极限
SERVO_STEP = 0x5F   # 步进速度

FAN_ON = 0x2000
FAN_OFF = 0x0000

# 全局运行标志
RUNNING = True

# --- 日志配置 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("GimbalCam")

# --- 信号处理 (用于优雅退出) ---
def signal_handler(sig, frame):
    global RUNNING
    logger.info("收到停止信号，正在关闭系统...")
    RUNNING = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# --- 云台控制类 ---
class GimbalController:
    def __init__(self):
        self.pca = None
        self.is_initialized = False

    def init(self):
        try:
            i2c = board.I2C()
            self.pca = PCA9685(i2c, address=PCA_ADDRESS)
            self.pca.frequency = PWM_FREQ
            self.is_initialized = True
            logger.info("PCA9685 初始化成功")
        except Exception as e:
            logger.error(f"PCA9685 初始化失败：{e}")
            self.is_initialized = False

    def set_fan(self, state):
        if not self.is_initialized: return
        duty = FAN_ON if state else FAN_OFF
        self.pca.channels[CH_FAN_POS].duty_cycle = duty
        self.pca.channels[CH_FAN_NEG].duty_cycle = FAN_OFF

    def set_servo(self, duty_cycle):
        if not self.is_initialized: return
        # 限制范围防止舵机损坏
        safe_duty = max(SERVO_MIN, min(SERVO_MAX, duty_cycle))
        self.pca.channels[CH_SERVO_PAN].duty_cycle = safe_duty

    def patrol_loop(self):
        """云台巡逻逻辑 (持续左右摇头)"""
        if not self.is_initialized:
            return
            
        logger.info("开始云台巡逻...")
        self.set_fan(True)
        
        # 初始归位
        self.set_servo(SERVO_MID)
        time.sleep(0.5)

        while RUNNING:
            # 向右转
            for i in range(SERVO_MID, SERVO_MAX, SERVO_STEP):
                if not RUNNING: break
                self.set_servo(i)
                time.sleep(0.03)
            
            # 向左转
            for i in range(SERVO_MAX, SERVO_MIN, -SERVO_STEP):
                if not RUNNING: break
                self.set_servo(i)
                time.sleep(0.03)
            
            # 回到中位 (可选，为了让运动更平滑，可以直接往复)
            # 这里为了演示完整的摇头动作，加上了回中位的过程
            for i in range(SERVO_MIN, SERVO_MID, SERVO_STEP):
                if not RUNNING: break
                self.set_servo(i)
                time.sleep(0.03)
                
        # 退出巡逻，归位并关闭风扇
        self.set_servo(SERVO_MID)
        self.set_fan(False)
        logger.info("云台巡逻已停止，舵机归位")

    def cleanup(self):
        """释放资源"""
        if self.pca:
            try:
                self.set_fan(False)
                self.set_servo(SERVO_MID)
                logger.info("云台控制器资源已释放")
            except:
                pass

# --- 相机功能函数 ---
def camera_loop():
    picam2 = None
    try:
        logger.info("正在初始化相机...")
        picam2 = Picamera2()
        
        # 配置预览
        preview_config = picam2.create_preview_configuration(main={"size": (640, 480)})
        picam2.configure(preview_config)
        
        picam2.start_preview()
        picam2.start()
        logger.info("相机预览已启动")
        
        # 保持运行直到主程序发出停止信号
        while RUNNING:
            time.sleep(0.5)
            
    except Exception as e:
        logger.error(f"相机运行错误：{e}")
    finally:
        if picam2:
            try:
                picam2.stop_preview()
                picam2.stop()
                picam2.close()
                logger.info("相机资源已释放")
            except:
                pass

# --- 主程序入口 ---
if __name__ == "__main__":
    logger.info(f"程序启动 - 用户：霜叶")
    
    # 初始化云台
    gimbal = GimbalController()
    gimbal.init()
    
    if not gimbal.is_initialized:
        logger.error("云台初始化失败，程序退出。")
        sys.exit(1)

    # 创建线程
    gimbal_thread = threading.Thread(target=gimbal.patrol_loop, name="GimbalThread")
    camera_thread = threading.Thread(target=camera_loop, name="CameraThread")

    try:
        gimbal_thread.start()
        camera_thread.start()
        
        # 主线程等待子线程结束
        gimbal_thread.join()
        camera_thread.join()
        
    except KeyboardInterrupt:
        pass
    finally:
        RUNNING = False
        # 给予线程短暂时间响应退出标志
        time.sleep(0.5) 
        gimbal.cleanup()
        logger.info("程序完全退出")